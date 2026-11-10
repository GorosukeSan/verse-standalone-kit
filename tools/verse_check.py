"""UE6 から切り出した VerseCompilerCmd で .verse を型チェックする（実行はしない）。

使い方: python tools/verse_check.py <ソースフォルダ> [--profile cmd|uefn|fortnite] [--digests <フォルダ>]
  cmd      : verse.exe で動かす前提（Print は /Verse.org/Verse の <suspends> 版）
  uefn     : VersePrint の Print（UEFN と同じシグネチャ）を使う
  fortnite : UEFN の digest（Verse / UnrealEngine / Fortnite）を External パッケージとして読み込み、
             UEFN のコードを using ごとそのまま型チェックする。UE6 のコンパイラは UEFN より新しいので
             digest 自体にもエラーが出るが、それは判定から外し、ユーザーのファイルのエラーだけで OK / NG を決める
  fortnite の追加オプション（UEFN のビルドでだけ出るエラーを拾う）:
    --uefn-project <名前|.vproject>  UEFN が書き出した vproject の versePath・実験的機能の設定・Assets digest を使う
    --content <Content フォルダ>      アセットのあるフォルダを空のモジュールの代役にして足す
    lint は既定オン（--no-lint で止める）
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I でも同じフォルダの common を読む
import common

ROOT = common.KIT
RUNTIME_ENGINE = common.runtime_engine()

PROFILES = {
    "cmd": "Engine/VerseCmd",
    "uefn": "VersePrint/VersePrint",
    "fortnite": None,
}

# UEFN の vproject（Saved/VerseProject/<名前>/vproject/*.vproject）と同じ構成
DIGEST_PACKAGES = [
    ("Verse", "/Verse.org", []),
    ("UnrealEngine", "/UnrealEngine.com", ["Verse"]),
    ("Fortnite", "/Fortnite.com", ["UnrealEngine", "Verse"]),
]
# digest は UEFN（Fortnite）のファイルなのでキットには含めない。利用者の PC にあるものを使う
DIGEST_SEARCH = [
    # 環境変数で指定したフォルダ（glob 可）
    *([os.environ["VERSE_KIT_DIGESTS"]] if os.environ.get("VERSE_KIT_DIGESTS") else []),
    # UEFN がプロジェクトを開いたときに書き出す digest
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"UnrealEditorFortnite\Saved\VerseProject\*\Digests\BuiltIn"),
]


def digest_files(d):
    """<名前>.digest.verse が d 直下にあっても d/<名前>/ の下にあっても探す"""
    found = {}
    for name, _, _ in DIGEST_PACKAGES:
        for cand in (os.path.join(d, f"{name}.digest.verse"), os.path.join(d, name, f"{name}.digest.verse")):
            if os.path.isfile(cand):
                found[name] = cand
    return found if len(found) == len(DIGEST_PACKAGES) else None


def find_digests():
    for pattern in DIGEST_SEARCH:
        dirs = [d for d in glob.glob(pattern) if digest_files(d)]
        if dirs:
            # 一番新しく書き出された digest を使う
            return max(dirs, key=lambda d: os.path.getmtime(digest_files(d)["Fortnite"]))
    return None


UEFN_VERSE_PROJECTS = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"UnrealEditorFortnite\Saved\VerseProject")
# Content の中で、アセットがあってもモジュールにならないフォルダ
CONTENT_SKIP_DIRS = {"__ExternalActors__", "__ExternalObjects__", "Developers", "Collections"}
ASSET_EXTS = (".uasset", ".umap")
# 作業フォルダの digests/ の下に置くアセット用パッケージのフォルダ名（エラーの除外にも使う）
CONTENT_STUB_DIR = "ContentAssets"
PROJECT_ASSETS_DIR = "ProjectAssets"


def load_uefn_project(name_or_path):
    """UEFN が書き出した vproject（Saved/VerseProject/<名前>/vproject/<名前>.vproject）を読み、
    ユーザーパッケージの設定・Assets パッケージ（アセットのフォルダ＝モジュール）・BuiltIn digest の場所を返す"""
    path = name_or_path
    if not os.path.isfile(path):
        path = os.path.join(UEFN_VERSE_PROJECTS, name_or_path, "vproject", f"{name_or_path}.vproject")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        packages = [p["desc"] for p in json.load(f)["packages"]]
    source = next((p for p in packages if p["settings"].get("role") == "Source"), None)
    if not source:
        return None
    assets = [p for p in packages if p["name"].endswith("/Assets") and os.path.isdir(p["dirPath"])]
    builtin = next((os.path.dirname(p["dirPath"]) for p in packages if p["name"] == "Verse"), None)
    return {"vproject": path, "source": source, "assets": assets, "builtin": builtin}


def content_module_stub(content_dir, verse_path):
    """Content のアセットのあるフォルダを、中身の無いモジュールの宣言にした digest 風のファイル。
    UEFN はアセットのフォルダもモジュールにするので、同じ名前の変数・引数とぶつかる（3588 / 3532）のを standalone でも出す"""
    def walk(d, depth):
        lines = []
        for name in sorted(os.listdir(d)):
            sub = os.path.join(d, name)
            if not os.path.isdir(sub) or name in CONTENT_SKIP_DIRS or not name.isidentifier():
                continue
            if not any(f.lower().endswith(ASSET_EXTS) for _, _, fs in os.walk(sub) for f in fs):
                continue
            ind = "    " * depth
            lines.append(f"{ind}{name}<public> := module:")
            # 中身の無いモジュールは書けないので、使われない名前を 1 つ置く（digest なので値は external {}）
            lines += walk(sub, depth + 1) or [f"{ind}    _content_stub_<public>:int = external {{}}"]
        return lines
    body = walk(content_dir, 0)
    return f"# Content のアセットのフォルダから作ったモジュールの代役（verse_check.py が生成。{verse_path}）\n" + "\n".join(body) + "\n"


def build_digest_vproject(src_dir, digests_dir, work_dir, verse_version=None, project=None, content_dir=None):
    files = digest_files(digests_dir)
    out = []
    for name, verse_path, deps in DIGEST_PACKAGES:
        # 1 パッケージ = 1 フォルダなので、digest を 1 つずつ別フォルダに置く
        pkg_dir = os.path.join(work_dir, "digests", name)
        os.makedirs(pkg_dir)
        shutil.copy(files[name], pkg_dir)
        out.append({
            "desc": {"name": name, "dirPath": pkg_dir, "settings": {
                "versePath": verse_path, "verseScope": "PublicAPI", "role": "External",
                "dependencyPackages": deps, "vniDestDir": os.path.join(work_dir, "vni", name)}},
            "readOnly": True,
        })
    settings = project["source"]["settings"] if project else {}
    user_path = settings.get("versePath", "/user@fortnite.com/Program")
    allow_exp = settings.get("allowExperimental", True)
    user_deps = [n for n, _, _ in DIGEST_PACKAGES]
    # アセットのモジュール: Content のフォルダから作る代役（いまのフォルダ構成）か、
    # UEFN の Assets digest（最後にプロジェクトを開いたときの構成）
    asset_pkgs = []
    if content_dir:
        stub_dir = os.path.join(work_dir, "digests", CONTENT_STUB_DIR)
        os.makedirs(stub_dir)
        with open(os.path.join(stub_dir, f"{CONTENT_STUB_DIR}.digest.verse"), "w", encoding="utf-8") as f:
            f.write(content_module_stub(content_dir, user_path))
        asset_pkgs.append(("User/ContentAssets", stub_dir))
    elif project:
        for i, p in enumerate(project["assets"]):
            # 作業フォルダに写してから読む（digest 内のエラーの除外も digests/ の下でまとめてできる）
            d = os.path.join(work_dir, "digests", f"{PROJECT_ASSETS_DIR}{i or ''}")
            shutil.copytree(p["dirPath"], d)
            asset_pkgs.append((p["name"], d))
    for name, d in asset_pkgs:
        out.append({
            "desc": {"name": name, "dirPath": d, "settings": {
                "versePath": user_path, "verseScope": "InternalUser", "role": "External",
                "verseVersion": 1, "treatModulesAsImplicit": True,
                "dependencyPackages": [n for n, _, _ in DIGEST_PACKAGES]}},
            "readOnly": True,
        })
        user_deps.insert(0, name)
    out.append({
        "desc": {
            "name": "User/Program",
            "dirPath": os.path.abspath(src_dir),
            "settings": {"versePath": user_path, "verseScope": "PublicUser", "role": "Source",
                         "verseVersion": 1 if verse_version is None else verse_version,
                         "dependencyPackages": user_deps, "allowExperimental": allow_exp},
        },
        "readOnly": False,
    })
    path = os.path.join(work_dir, "check.vproject")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"packages": out}, f, indent=1)
    return path


def run_filtered(exe, vproject, digests_root):
    """digest 内のエラーを捨てて、ユーザーのファイルのエラーだけを表示する。戻り値はユーザー側のエラー数"""
    r = subprocess.run([exe, vproject], capture_output=True, text=True, encoding="utf-8", errors="replace")
    # 一時フォルダは 8.3 短縮名などで表記が揺れるので、前方一致ではなく「digests/<パッケージ>/<名前>.digest.verse」で見分ける
    pkg_dirs = [n for n, _, _ in DIGEST_PACKAGES] + [CONTENT_STUB_DIR, PROJECT_ASSETS_DIR + r"\d*"]
    digest_re = re.compile(r"/digests/(?:" + "|".join(pkg_dirs) + r")/[^/]+\.digest\.verse$", re.IGNORECASE)
    user_errors = skipped = 0
    in_digest = False
    for line in (r.stdout + r.stderr).splitlines():
        if "Verse compiler error" in line or "Verse compiler warning" in line:
            path = line.split(".digest.verse", 1)[0] + ".digest.verse" if ".digest.verse" in line else ""
            in_digest = bool(digest_re.search(path.replace("\\", "/")))
            is_error = "compiler error" in line
            if in_digest:
                skipped += is_error
            else:
                user_errors += is_error
                print(line)
        elif line.startswith((" ", "\t")) and not in_digest:
            # 候補一覧など、直前のメッセージの続き
            print(line)
    print(f"(digest 内のエラー {skipped} 件は無視)")
    # コンパイラが落ちた、または出力を読み取れなかったときは OK にしない
    crashed = r.returncode < 0 or r.returncode >= 0xC0000000
    if crashed or (r.returncode != 0 and user_errors == 0 and skipped == 0):
        print(f"コンパイラが想定外の終了をしました (exit {r.returncode})。出力:")
        print((r.stdout + r.stderr)[-4000:])
        return max(user_errors, 1)
    return user_errors


FUNC_PARAM_RE = re.compile(r"\b([A-Za-z_]\w*)\s*:\s*type\s*\{\s*_\s*\(")
SUBSCRIBE_RE = re.compile(r"\.Subscribe\(\s*([A-Za-z_]\w*)\s*\)")
DEF_RE = re.compile(r"^(\s*)[A-Za-z_]\w*(?:<[^>]*>)*\s*\((.*)\)[^=]*=\s*$")


def lint_uefn_only(src_dir):
    """standalone の型チェッカーでは出ず、UEFN のビルドでだけ出るエラーを、書き方から探す。
    - V3502: 関数の引数で受けた関数（type{_(...)...}）をそのまま listenable の Subscribe に渡す
      → メソッドを持つクラスで包んで、そのメソッドを渡す
    戻り値は [(ファイル, 行, メッセージ)]"""
    found = []
    for path in sorted(glob.glob(os.path.join(src_dir, "**", "*.verse"), recursive=True)):
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        params, indent = set(), None
        for no, line in enumerate(lines, 1):
            m = DEF_RE.match(line)
            if m:
                # 関数の定義の行: その引数のうち関数型のものを覚える（本体はこれより深いインデント）
                params, indent = set(FUNC_PARAM_RE.findall(m.group(2))), len(m.group(1))
                continue
            if indent is not None and line.strip() and len(line) - len(line.lstrip()) <= indent:
                params, indent = set(), None
            for name in SUBSCRIBE_RE.findall(line):
                if name in params:
                    found.append((path, no, f"引数で受けた関数 `{name}` を Subscribe にそのまま渡している"
                                            "（UEFN のビルドで V3502。メソッドを持つクラスで包んで渡す）"))
    return found


def build_vproject(src_dir, profile, work_dir, verse_version=None):
    with open(os.path.join(os.path.dirname(RUNTIME_ENGINE), "packages.json"), encoding="utf-8") as f:
        packages = {p["name"]: p for p in json.load(f)}

    # 選んだプロファイルの起点からたどれるパッケージだけを使う
    deps = []

    def visit(name):
        if name in deps:
            return
        for dep in packages[name]["settings"].get("dependencyPackages", []):
            visit(dep)
        deps.append(name)

    visit(PROFILES[profile])

    out = []
    for name in deps:
        p = packages[name]
        settings = dict(p["settings"])
        if "vniDestDir" in settings:
            settings["vniDestDir"] = os.path.join(work_dir, "vni", name.replace("/", "_"))
        out.append({
            "desc": {"name": name, "dirPath": os.path.join(RUNTIME_ENGINE, p["dir"]), "settings": settings},
            "readOnly": True,
        })
    # versePath を /User/Main にすると Main 関数と名前がぶつかる
    out.append({
        "desc": {
            "name": "User/Program",
            "dirPath": os.path.abspath(src_dir),
            "settings": dict({"versePath": "/User/Program", "verseScope": "PublicUser", "dependencyPackages": deps},
                             **({"verseVersion": verse_version} if verse_version is not None else {})),
        },
        "readOnly": False,
    })
    path = os.path.join(work_dir, "check.vproject")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"packages": out}, f, indent=1)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help=".verse を置いたフォルダ（.verse ファイル単体でも可）")
    ap.add_argument("--profile", choices=PROFILES, default=None,
                    help="省略時は cmd（--uefn-project / --content を付けたときは fortnite）")
    ap.add_argument("--runtime", default="runtime", help="使うコンパイラと標準ライブラリのフォルダ（キット内の相対パス。既定 runtime）")
    ap.add_argument("--digests", default=None, help="fortnite プロファイルで使う digest のフォルダ（省略時は自動で探す）")
    ap.add_argument("--verse-version", type=int, default=None, help="ユーザーパッケージの Verse 言語バージョン（0 / 1 / 2。省略時はコンパイラの既定 = 1）")
    ap.add_argument("--uefn-project", default=None,
                    help="fortnite プロファイル: UEFN のプロジェクト名（Saved/VerseProject/<名前>）か .vproject のパス。"
                         "そのプロジェクトの versePath・実験的機能の設定・Assets digest（アセットのフォルダ＝モジュール）・"
                         "BuiltIn digest を使う。ソースフォルダの根を Content と同じ並びにしておくこと")
    ap.add_argument("--content", default=None,
                    help="fortnite プロファイル: Content フォルダ。アセットのあるフォルダから空のモジュールの代役を作って足す"
                         "（UEFN で開いていない・digest が古いとき用。--uefn-project の Assets digest より優先）")
    ap.add_argument("--no-lint", action="store_true",
                    help="UEFN のビルドでだけ出るエラーの書き方チェック（fortnite プロファイルで既定オン）をしない")
    args = ap.parse_args()
    if args.profile is None:
        args.profile = "fortnite" if (args.uefn_project or args.content) else "cmd"
    elif args.profile != "fortnite" and (args.uefn_project or args.content):
        print("--uefn-project / --content は fortnite プロファイルでだけ使える")
        sys.exit(2)
    global RUNTIME_ENGINE
    RUNTIME_ENGINE = os.path.join(ROOT, args.runtime, "Engine")

    with tempfile.TemporaryDirectory(prefix="verse_check_") as work:
        src = args.src
        if os.path.isfile(src):
            # ファイル単体ならそれだけを入れたフォルダを作る
            src = os.path.join(work, "src")
            os.makedirs(src)
            with open(args.src, "rb") as fi, open(os.path.join(src, os.path.basename(args.src)), "wb") as fo:
                fo.write(fi.read())
        exe = common.binary("VerseCompilerCmd.exe", os.path.join(ROOT, args.runtime))
        if args.profile == "fortnite":
            project = None
            if args.uefn_project:
                project = load_uefn_project(args.uefn_project)
                if not project:
                    print(f"UEFN のプロジェクトが見つからない: {args.uefn_project}（{UEFN_VERSE_PROJECTS} の下の名前か .vproject のパス）")
                    sys.exit(2)
                print(f"project: {project['vproject']}（versePath {project['source']['settings'].get('versePath')}）")
            if args.content and not os.path.isdir(args.content):
                print(f"Content フォルダが見つからない: {args.content}")
                sys.exit(2)
            digests = args.digests
            if not digests and project and project["builtin"] and digest_files(project["builtin"]):
                digests = project["builtin"]  # そのプロジェクトを開いた UEFN と同じ版の digest
            digests = digests or find_digests()
            if not digests or not digest_files(digests):
                print("digest が見つからない。UEFN でプロジェクトを一度開くか、--digests（または環境変数 VERSE_KIT_DIGESTS）で\n"
                      "Verse / UnrealEngine / Fortnite の .digest.verse があるフォルダを指定する")
                sys.exit(2)
            print(f"digest: {digests}")
            if args.content:
                print(f"content: {args.content}（アセットのフォルダをモジュールの代役にする）")
            vproject = build_digest_vproject(src, digests, work, args.verse_version, project, args.content)
            errors = run_filtered(exe, vproject, os.path.join(work, "digests"))
            if not args.no_lint:
                lint = lint_uefn_only(src)
                for path, no, msg in lint:
                    print(f"{path.replace(os.sep, '/')}({no}): UEFN build lint error: {msg}")
                errors += len(lint)
            rc = 1 if errors else 0
        else:
            vproject = build_vproject(src, args.profile, work, args.verse_version)
            rc = subprocess.run([exe, vproject]).returncode
    print("OK" if rc == 0 else "NG")
    sys.exit(rc)


if __name__ == "__main__":
    main()

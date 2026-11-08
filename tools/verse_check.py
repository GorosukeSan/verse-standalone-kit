"""UE6 から切り出した VerseCompilerCmd で .verse を型チェックする（実行はしない）。

使い方: python tools/verse_check.py <ソースフォルダ> [--profile cmd|uefn|fortnite] [--digests <フォルダ>]
  cmd      : verse.exe で動かす前提（Print は /Verse.org/Verse の <suspends> 版）
  uefn     : VersePrint の Print（UEFN と同じシグネチャ）を使う
  fortnite : UEFN の digest（Verse / UnrealEngine / Fortnite）を External パッケージとして読み込み、
             UEFN のコードを using ごとそのまま型チェックする。UE6 のコンパイラは UEFN より新しいので
             digest 自体にもエラーが出るが、それは判定から外し、ユーザーのファイルのエラーだけで OK / NG を決める
"""
import argparse
import glob
import json
import os
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


def build_digest_vproject(src_dir, digests_dir, work_dir, verse_version=None):
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
    out.append({
        "desc": {
            "name": "User/Program",
            "dirPath": os.path.abspath(src_dir),
            "settings": {"versePath": "/user@fortnite.com/Program", "verseScope": "PublicUser", "role": "Source",
                         "verseVersion": 1 if verse_version is None else verse_version,
                         "dependencyPackages": [n for n, _, _ in DIGEST_PACKAGES], "allowExperimental": True},
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
    # 一時フォルダは 8.3 短縮名などで表記が揺れるので、前方一致ではなく「digests/<名前>/<名前>.digest.verse」で見分ける
    digest_tails = {f"/digests/{n}/{n}.digest.verse".lower() for n, _, _ in DIGEST_PACKAGES}
    user_errors = skipped = 0
    in_digest = False
    for line in (r.stdout + r.stderr).splitlines():
        if "Verse compiler error" in line or "Verse compiler warning" in line:
            path = line.split(".digest.verse", 1)[0] + ".digest.verse" if ".digest.verse" in line else ""
            in_digest = path.replace("\\", "/").lower().endswith(tuple(digest_tails))
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
    ap.add_argument("--profile", choices=PROFILES, default="cmd")
    ap.add_argument("--runtime", default="runtime", help="使うコンパイラと標準ライブラリのフォルダ（キット内の相対パス。既定 runtime）")
    ap.add_argument("--digests", default=None, help="fortnite プロファイルで使う digest のフォルダ（省略時は自動で探す）")
    ap.add_argument("--verse-version", type=int, default=None, help="ユーザーパッケージの Verse 言語バージョン（0 / 1 / 2。省略時はコンパイラの既定 = 1）")
    args = ap.parse_args()
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
            digests = args.digests or find_digests()
            if not digests or not digest_files(digests):
                print("digest が見つからない。UEFN でプロジェクトを一度開くか、--digests（または環境変数 VERSE_KIT_DIGESTS）で\n"
                      "Verse / UnrealEngine / Fortnite の .digest.verse があるフォルダを指定する")
                sys.exit(2)
            print(f"digest: {digests}")
            vproject = build_digest_vproject(src, digests, work, args.verse_version)
            rc = 1 if run_filtered(exe, vproject, os.path.join(work, "digests")) else 0
        else:
            vproject = build_vproject(src, args.profile, work, args.verse_version)
            rc = subprocess.run([exe, vproject]).returncode
    print("OK" if rc == 0 else "NG")
    sys.exit(rc)


if __name__ == "__main__":
    main()

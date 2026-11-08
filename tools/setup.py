"""UE のソースを取得し、Verse のツールだけをビルドして runtime/ に集める。

使い方:
  python tools/setup.py                       初回: clone → 依存ファイル → ビルド → 切り出し
  python tools/setup.py --update              最新に更新して作り直す
  python tools/setup.py --use-existing D:\\UE6 手元の UE ソース（clone 済み）を使う
  python tools/setup.py --ref <コミット>       特定のコミットに固定する（キットが clone した UE のみ）

認証について:
  このスクリプトはパスワードやトークンを受け取らず、保存もしない。GitHub への認証は
  利用者の git（Git Credential Manager や SSH 鍵）がそのまま行う。
"""
import argparse
import datetime
import json
import os
import shutil
import stat
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I でも同じフォルダの common を読む
import common
import pack

BUILD_TARGETS = ["VerseCompilerCmd", "VerseCmd"]   # VerseCmd = verse.exe
GITDEPS = os.path.join("Engine", "Binaries", "DotNET", "GitDependencies", "win-x64", "GitDependencies.exe")

NOTICE = """\
========================================================================
 Unreal Engine のソースコードを取得・ビルドします。

 - Unreal Engine のソースは Epic Games の EULA の下で提供されています。
   利用者自身が EULA に同意し、Epic Games アカウントと GitHub を連携して
   いる必要があります（https://www.unrealengine.com/ue-on-github）。
 - ビルドしてできた exe と標準ライブラリ（runtime/）は、利用者の PC の
   中だけで使ってください。一般への配布・公開は EULA で認められていません。
 - 依存ファイルの取得で Epic Games のサーバーからダウンロードが行われます。
 - 詳しくは docs/LEGAL.md と docs/SECURITY.md を読んでください。
========================================================================"""


def confirm_notice(cfg, assume_yes):
    if cfg.get("notice_acknowledged"):
        return
    print(NOTICE)
    if not assume_yes:
        if not sys.stdin.isatty():
            common.die("確認が必要です。内容を読んだうえで --yes を付けて実行してください。")
        if input("内容を確認して続けますか？ [yes/no]: ").strip().lower() != "yes":
            common.die("中止しました。", 0)
    cfg["notice_acknowledged"] = datetime.date.today().isoformat()


def _rmtree(path):
    def onerror(func, p, _):
        os.chmod(p, stat.S_IWRITE)   # git のオブジェクトは読み取り専用
        func(p)
    shutil.rmtree(path, onerror=onerror)


def clone(remote, branch, dest, full_history, ref):
    existed = os.path.isdir(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    cmd = ["git", "-c", "core.longpaths=true", "clone", "--branch", branch, "--single-branch", "--no-tags"]
    if not full_history:
        cmd += ["--depth", "1"]
    if ref:
        cmd += ["--no-checkout"]   # 固定するコミットを後で取り直すので、ブランチ先頭は展開しない
    print("GitHub から取得します。認証を求められたら、利用者自身でログインしてください（ブラウザが開くことがあります）。")
    rc = common.run([*cmd, "--", remote, dest], check=False)
    if rc != 0:
        # 途中まで作ったフォルダを残すと、次回「UE のソースではない」と分かりにくい失敗になる。
        # キットがこの実行で作ったフォルダ（元は無いか空だった）だけを消す
        if os.path.isdir(dest):
            if existed:
                for name in os.listdir(dest):
                    p = os.path.join(dest, name)
                    _rmtree(p) if os.path.isdir(p) else os.remove(p)
            else:
                _rmtree(dest)
        common.die("clone に失敗しました。\n"
                   "  - 「Repository not found」なら、認証できていないか、GitHub アカウントが EpicGames Organization に\n"
                   "    入っていません。Epic Games アカウントと GitHub を連携し、届いた招待を承認してください。\n"
                   "  - 通信が切れた場合は、そのままもう一度実行してください（途中のファイルは消しました）。")
    common.git(dest, "config", "core.longpaths", "true")
    common.git(dest, "config", common.MANAGED_KEY, "true")


def sync_managed(repo, branch, ref, shallow, fresh=False):
    """キットが clone したリポジトリを更新する。ローカルの変更があれば止まる（消さない）。
    ブランチは動かさず、取得したコミットを detached HEAD で展開する。
    fresh=True は「この実行で --no-checkout で clone した直後」。まだ何も展開していないので
    （git status には全ファイルが削除として出る）、変更の確認を飛ばして展開する"""
    if not fresh:
        dirty = common.git(repo, "status", "--porcelain", "--untracked-files=no")
        if dirty:
            common.die("UE のソースにローカルの変更があるので更新を止めました（勝手に消しません）:\n" + dirty[:2000])
    cmd = ["git", "-C", repo, "fetch", "--no-tags"]
    if shallow:
        cmd += ["--depth", "1"]
    common.run([*cmd, "--end-of-options", "origin", ref or branch])
    # checkout はローカルの変更を上書きしそうなら失敗する。ブランチやローカルのコミットには触れない
    common.run(["git", "-C", repo, "checkout", *(["--force"] if fresh else []), "--detach", "FETCH_HEAD"])


def main():
    cfg = common.load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine-dir", help=f"UE を clone する先（既定 {common.DEFAULT_ENGINE_DIR}）。短いパス推奨")
    ap.add_argument("--use-existing", metavar="DIR", help="clone 済みの UE ソースを使う（--update で fast-forward するだけ）")
    ap.add_argument("--remote", help=f"取得元（既定 {common.OFFICIAL_REMOTE}）")
    ap.add_argument("--allow-fork", action="store_true", help="公式以外（GitHub 上のフォーク）の取得元を許可する")
    ap.add_argument("--branch", help=f"ブランチ（既定 {common.DEFAULT_BRANCH}）")
    ap.add_argument("--ref", help="特定のコミットやタグに固定する（キットが clone した UE のみ）")
    ap.add_argument("--update", action="store_true", help="取得元から最新を取ってから作り直す")
    ap.add_argument("--full-history", action="store_true", help="履歴をすべて取る（既定は最新 1 コミットだけの浅い clone）")
    ap.add_argument("--full-setup", action="store_true",
                    help="UE 標準の Setup.bat を実行する（VC++ ランタイム等のインストール・git hooks・エンジン登録を含む）。"
                         "既定は依存ファイルの取得だけ")
    ap.add_argument("--skip-build", action="store_true", help="ビルドせず、既存の exe から切り出しだけやり直す")
    ap.add_argument("--yes", action="store_true", help="最初の確認を省略する（内容は docs/LEGAL.md で確認済みとみなす）")
    args = ap.parse_args()

    common.git_exe()
    common.safe_path(common.KIT, "キットのフォルダ")
    confirm_notice(cfg, args.yes)

    if args.use_existing:
        cfg.update(engine_root=common.safe_path(args.use_existing, "UE のフォルダ"), managed=False)
    elif args.engine_dir or "engine_root" not in cfg:
        cfg.update(engine_root=common.safe_path(args.engine_dir or common.DEFAULT_ENGINE_DIR, "UE のフォルダ"), managed=True)
    cfg["remote"] = args.remote or cfg.get("remote", common.OFFICIAL_REMOTE)
    cfg["branch"] = common.check_ref(args.branch or cfg.get("branch", common.DEFAULT_BRANCH), "ブランチ")
    if args.allow_fork:
        cfg["allow_fork"] = True
    if args.ref:
        common.check_ref(args.ref, "--ref")
    common.check_remote(cfg["remote"], cfg.get("allow_fork", False))

    ue = common.safe_path(cfg["engine_root"], "UE のフォルダ")
    # キットの中に置けるのは engine/ だけ（.gitignore で除外されている場所）
    if common.is_inside(ue, common.KIT) and os.path.normcase(ue) != os.path.normcase(common.DEFAULT_ENGINE_DIR):
        common.die(f"キットのフォルダの中に UE を置く場合は {common.DEFAULT_ENGINE_DIR} にしてください"
                   "（それ以外の場所は Git の除外対象ではなく、誤って公開されるおそれがあります）。")
    common.save_config(cfg)

    want_managed = cfg.get("managed", True)
    has_repo = os.path.isdir(os.path.join(ue, ".git"))

    # 1. 取得
    if want_managed and not has_repo:
        if os.path.isdir(ue) and os.listdir(ue):
            common.die(f"{ue} は空ではなく、git リポジトリでもありません。別のフォルダを指定してください。")
        clone(cfg["remote"], cfg["branch"], ue, args.full_history, args.ref)
        if args.ref:
            sync_managed(ue, cfg["branch"], args.ref, not args.full_history, fresh=True)
    elif not has_repo:
        common.die(f"{ue} に UE の git リポジトリが見つかりません。")
    else:
        origin = common.git(ue, "remote", "get-url", "origin", check=False)
        if not origin:
            common.die(f"{ue} に origin リモートがありません。")
        common.check_remote(origin, cfg.get("allow_fork", False))
        # キットが clone した印があるものだけを、キットが更新してよいリポジトリとして扱う
        managed = common.git(ue, "config", "--get", common.MANAGED_KEY, check=False) == "true"
        if managed and (args.update or args.ref):
            shallow = common.git(ue, "rev-parse", "--is-shallow-repository") == "true"
            sync_managed(ue, cfg["branch"], args.ref, shallow)
        elif args.ref:
            common.die("--ref はキットが clone した UE でだけ使えます。自分の clone では、git checkout で固定してから実行してください。")
        elif args.update:
            # 利用者のリポジトリ: 検査した origin から取り、fast-forward できるときだけ進める
            common.run(["git", "-C", ue, "fetch", "--end-of-options", "origin", cfg["branch"]])
            common.run(["git", "-C", ue, "merge", "--ff-only", "FETCH_HEAD"])
    if not os.path.exists(os.path.join(ue, "Engine", "Build", "BatchFiles", "Build.bat")):
        common.die(f"{ue} は UE のソースツリーではないようです（Engine/Build/BatchFiles/Build.bat がない）。")
    commit = common.git(ue, "rev-parse", "HEAD")
    print(f"UE のコミット: {commit}")

    # 2. 依存ファイル（Epic のサーバーから取得）
    if args.full_setup:
        common.run([os.path.join(ue, "Setup.bat")], cwd=ue)
    else:
        # フラグなし = ローカルで変更されたファイル（自分でビルドした exe など）は上書きせずに残す。
        # --prompt は対話できないと例外で落ちるので使わない
        common.run([os.path.join(ue, GITDEPS)], cwd=ue)

    # 3. Verse パッケージ構成（All.vproject）
    common.run([os.path.join(ue, "GenerateProjectFiles.bat"), "-VProject"], cwd=ue)

    # 4. ビルド（Verse のツールだけ。エディタはビルドしない）
    if not args.skip_build:
        bat = os.path.join(ue, "Engine", "Build", "BatchFiles", "Build.bat")
        for target in BUILD_TARGETS:
            common.run([bat, target, "Win64", "Development"], cwd=ue)

    # 5. 切り出し（失敗しても前の runtime/ は残る）
    pack.pack(os.path.join(ue, "Engine"), version={
        "ue_commit": commit,
        "ue_commit_date": common.git(ue, "log", "-1", "--format=%ci", commit),
        "remote": common.redact(common.git(ue, "remote", "get-url", "origin")),
        "branch": cfg["branch"],
        "packed_at": datetime.datetime.now().isoformat(timespec="seconds"),
    })

    # 6. 動作確認
    ok = smoke_test()
    print("\n完了しました。verse-check.bat / verse-run.bat が使えます。" if ok
          else "\n切り出しは終わりましたが、確認で失敗がありました。上のログを確認してください。")
    sys.exit(0 if ok else 1)


def smoke_test():
    tools = os.path.dirname(os.path.abspath(__file__))
    ok = True
    for name, profile in (("hello", "cmd"), ("uefn_print", "uefn")):
        d = os.path.join(common.KIT, "samples", name)
        ok &= common.run([sys.executable, "-I", os.path.join(tools, "verse_check.py"), d, "--profile", profile], check=False) == 0
    verse = os.path.join(common.runtime_engine(), "Binaries", "Win64", "verse.exe")
    ok &= subprocess.run([verse, os.path.join(common.KIT, "samples", "hello", "hello.verse")]).returncode == 0
    return ok


if __name__ == "__main__":
    main()

"""ビルド前の環境チェック。何も変更しない（--check-access のときだけ GitHub に問い合わせる）。

使い方: python tools/doctor.py [--engine-dir <フォルダ>] [--check-access] [--remote <URL>] [--branch <名前>]
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I でも同じフォルダの common を読む
import common

OK, NG, WARN = "  OK ", "  NG ", "  !! "


def vs_info():
    vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                           r"Microsoft Visual Studio\Installer\vswhere.exe")
    if not os.path.exists(vswhere):
        return None
    r = subprocess.run([vswhere, "-latest", "-products", "*",
                        "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                        "-property", "displayName"], capture_output=True, text=True)
    return r.stdout.strip() or None


def main():
    cfg = common.load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-dir", default=cfg.get("engine_root", common.DEFAULT_ENGINE_DIR))
    ap.add_argument("--remote", default=cfg.get("remote", common.OFFICIAL_REMOTE))
    ap.add_argument("--branch", default=cfg.get("branch", common.DEFAULT_BRANCH))
    ap.add_argument("--check-access", action="store_true",
                    help="GitHub のリポジトリに読み取りでアクセスできるか確かめる（git の認証画面が出ることがある）")
    args = ap.parse_args()
    fails = 0

    def report(ok, msg, hint=""):
        nonlocal fails
        print((OK if ok is True else WARN if ok is None else NG) + msg)
        if ok is not True and hint:
            print("       " + hint)
        fails += ok is False

    report(sys.version_info >= (3, 9), f"Python {sys.version.split()[0]}", "Python 3.9 以上が必要です")
    report(sys.platform == "win32", f"OS: {sys.platform}", "いまは Windows (Win64) だけに対応しています")
    git = common.find_exe("git")
    report(bool(git), f"git: {git or '見つからない'}", "Git for Windows を入れてください（Git Credential Manager 付き）")
    if git:
        helper = subprocess.run([git, "config", "--get", "credential.helper"], capture_output=True, text=True).stdout.strip()
        report(True if helper else None, f"git の資格情報ヘルパー: {helper or '未設定'}",
               "未設定だとパスワード入力を求められます。Git Credential Manager を推奨します（トークンを平文で保存しない）")
        longpaths = subprocess.run([git, "config", "--get", "core.longpaths"], capture_output=True, text=True).stdout.strip()
        report(True if longpaths == "true" else None, f"git core.longpaths: {longpaths or '未設定'}",
               "UE は長いパスを含みます。setup.bat は clone 時に有効にしますが、既存の clone では git config core.longpaths true を推奨")
    vs = vs_info()
    report(bool(vs), f"Visual Studio (C++): {vs or '見つからない'}",
           "Visual Studio 2022 以降と「C++ によるデスクトップ開発」「.NET」ワークロードが必要です")
    msvcp = os.path.join(common.windows_dir(), "System32", "msvcp140.dll")
    report(True if os.path.exists(msvcp) else None, "VC++ ランタイム (msvcp140.dll)",
           "ビルド後の exe の実行に必要です。setup.bat --full-setup か Microsoft の VC++ 再頒布可能パッケージで入ります")

    eng = os.path.abspath(args.engine_dir)
    report(len(eng) <= 60 or None, f"エンジンのフォルダ: {eng}（{len(eng)} 文字）",
           "UE のビルドは長いパスで失敗しやすいです。ドライブ直下の短いフォルダ（UE6 など）を推奨します")
    drive = os.path.splitdrive(eng)[0] + "\\"
    if os.path.exists(drive):
        free = shutil.disk_usage(drive).free / 1024 ** 3
        report(True if free >= 120 else None, f"空き容量 ({drive}): {free:.0f} GB",
               "ソース・依存ファイル・中間ファイルで 100GB 前後使います")

    if args.check_access and git:
        common.check_remote(args.remote, cfg.get("allow_fork", False))
        common.check_ref(args.branch, "ブランチ")
        print(f"  .. {args.remote} の {args.branch} にアクセスできるか確認中（認証画面が出たら利用者自身でログインしてください）")
        r = subprocess.run([git, "ls-remote", "--heads", args.remote, args.branch], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            report(True, "GitHub のアクセス権: あり")
        elif r.returncode == 0:
            report(False, f"ブランチ {args.branch} が見つからない", "--branch で正しいブランチ名を指定してください")
        else:
            report(False, "GitHub のアクセス権: なし（Repository not found / 認証失敗）",
                   "認証に失敗したか、まだ権限がありません。Epic Games アカウントと GitHub アカウントを連携し、EpicGames Organization への招待を承認してください。"
                   "手順は docs/LEGAL.md を参照")

    print("\n問題なし" if not fails else f"\n{fails} 件の問題があります")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

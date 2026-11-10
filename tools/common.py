"""キット共通の処理（設定・コマンド実行・パスや引数の検査）。

このキットは Epic Games のコードやバイナリを一切含まない。UE のソースは利用者自身が
GitHub から取得し（認証も利用者の git に任せる）、ビルドも利用者の PC で行う。
"""
import json
import os
import re
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(KIT, "kit.local.json")          # 利用者ごとの設定（Git 管理しない）
RUNTIME = os.path.join(KIT, "runtime")                 # ビルド結果の切り出し先（Git 管理しない・配布しない）

OFFICIAL_REMOTE = "https://github.com/EpicGames/UnrealEngine.git"
DEFAULT_BRANCH = "ue6-main"
DEFAULT_ENGINE_DIR = os.path.join(KIT, "engine")
MANAGED_KEY = "verse-kit.managed"                      # キットが clone した印（UE リポジトリの .git/config に書く）

# GitHub 上の <owner>/UnrealEngine だけを受け付ける
_REMOTE_RE = re.compile(
    r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<owner>[A-Za-z0-9-]+)/(?P<repo>UnrealEngine)(?:\.git)?/?$", re.I)
# cmd.exe 経由で .bat を呼ぶので、cmd が特別扱いする文字を含むパスや引数は拒否する（コマンド注入対策）
_CMD_UNSAFE = set('&|<>^%!"\r\n')
# git に渡すブランチ名・コミット（オプションと誤解されないよう先頭の - を禁止）
_REF_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/-]{0,199}$")


def die(msg, code=1):
    print(f"[エラー] {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg):
    print(f"[注意] {msg}")


def load_config():
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)


def redact(url):
    """エラー表示用: 認証情報やクエリを伏せる"""
    url = re.sub(r"//[^/@]*@", "//***@", url)
    return url.split("?", 1)[0].split("#", 1)[0]


def is_official(url):
    m = _REMOTE_RE.match(url.strip())
    return bool(m) and m.group("owner").lower() == "epicgames"


def check_remote(url, allow_fork=False):
    """認証情報入りの URL、GitHub 以外、UnrealEngine 以外のリポジトリを拒否する。公式以外は --allow-fork が必要"""
    url = url.strip()
    if re.match(r"^https?://[^/]*@", url) or "?" in url:
        die("リモート URL に認証情報（ユーザー名・トークン）やクエリを入れないでください。"
            "認証は git の資格情報マネージャー（Git Credential Manager）か SSH 鍵に任せます。")
    if not _REMOTE_RE.match(url):
        die(f"リモートは GitHub 上の <owner>/UnrealEngine リポジトリだけを受け付けます: {redact(url)}")
    if not is_official(url):
        if not allow_fork:
            die(f"公式（EpicGames/UnrealEngine）以外のリモートです: {redact(url)}\n"
                "       ビルド時にそのリポジトリのコードが実行されます。信頼できるフォークなら --allow-fork を付けてください。")
        warn(f"公式以外のリモートを使います: {redact(url)}（フォークの中身はその持ち主が変更できます）")


def check_ref(ref, what="ブランチ／コミット"):
    if not _REF_RE.match(ref) or ".." in ref:
        die(f"{what}の名前が不正です: {ref!r}")
    return ref


def safe_path(path, what="パス"):
    path = os.path.abspath(path)
    bad = _CMD_UNSAFE.intersection(path)
    if bad:
        die(f"{what}に使えない文字が含まれています（{''.join(sorted(bad))}）: {path}")
    return path


def is_inside(path, root):
    """path が root の中（root 自身を含む）にあるか。大文字小文字・別ドライブも考慮する"""
    try:
        p, r = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(root))
        return os.path.commonpath([p, r]) == r
    except ValueError:
        return False


def find_exe(name):
    """PATH だけから実行ファイルを探す（カレントフォルダに置かれた偽物を拾わない）"""
    cwd = os.path.normcase(os.getcwd())
    exts = [""] if os.path.splitext(name)[1] else os.environ.get("PATHEXT", ".EXE").lower().split(";")
    for d in os.environ.get("PATH", "").split(os.pathsep):
        d = d.strip('"')
        if not d or d == "." or not os.path.isabs(d) or os.path.normcase(os.path.abspath(d)) == cwd:
            continue
        for ext in exts:
            cand = os.path.join(d, name + ext)
            if os.path.isfile(cand):
                return cand
    return None


def git_exe():
    exe = find_exe("git")
    if not exe:
        die("git が見つかりません。Git for Windows（Git Credential Manager 付き）を入れてください。")
    return exe


def windows_dir():
    """Windows のフォルダ（SystemRoot が無いときはシステムドライブ直下の Windows）"""
    return os.environ.get("SystemRoot") or os.path.join(os.environ.get("SystemDrive", "C:") + os.sep, "Windows")


def cmd_exe():
    return os.environ.get("ComSpec") or os.path.join(windows_dir(), "System32", "cmd.exe")


def run(cmd, cwd=None, check=True, env=None):
    """引数リストでそのまま実行する（シェルを通さない）。.bat だけは cmd /c が必要なので全引数を検査する"""
    if cmd[0] == "git":
        cmd = [git_exe(), *cmd[1:]]
    if cmd[0].lower().endswith((".bat", ".cmd")):
        for part in cmd:
            if _CMD_UNSAFE.intersection(part):
                die(f"バッチファイルに渡せない文字を含む引数です: {part}")
        cmd = [cmd_exe(), "/d", "/c", *cmd]
    print(">", " ".join(cmd), flush=True)
    rc = subprocess.run(cmd, cwd=cwd, env=env).returncode
    if check and rc != 0:
        die(f"失敗しました (exit {rc}): {' '.join(cmd)}", 1)
    return rc


def git(repo, *args, check=True):
    r = subprocess.run([git_exe(), "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        die(f"git {' '.join(args)} が失敗しました:\n{r.stderr.strip()}")
    return r.stdout.strip()


def runtime_engine(runtime_dir=None):
    return os.path.join(runtime_dir or RUNTIME, "Engine")


def binary(name, runtime_dir=None):
    path = os.path.join(runtime_engine(runtime_dir), "Binaries", "Win64", name)
    if not os.path.exists(path):
        die(f"{name} がありません。先に setup.bat でビルドしてください。")
    return path

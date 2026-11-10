"""公開前チェック: 公開されるもの（Git の index・履歴、未追跡の新規ファイル）に、配布してはいけないものがないか調べる。

使い方: python tools/release_check.py        （release-check.bat からも呼べる）

調べること:
  - Epic Games のコード・バイナリ（runtime/・engine/ の中身、exe / dll など、Epic の著作権表示、
    標準ライブラリと同じ内容のファイル）
  - UEFN の digest（*.digest.verse）
  - 利用者ごとの設定（kit.local.json）、キットの中に置かれた別の Git リポジトリ（UE の clone など）
  - トークン・認証情報らしき文字列、個人のパス（Users\\<名前> で始まるユーザーフォルダ）
  - 大きすぎるファイル
  - 履歴: 過去のコミットに上の禁止ファイルが入っていないか
"""
import hashlib
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I でも同じフォルダの common を読む
import common

FORBIDDEN_DIRS = ("runtime/", "runtime-", "runtime.", "engine/")
FORBIDDEN_EXT = (".exe", ".dll", ".pdb", ".lib", ".vmodule", ".digest.verse", ".uasset", ".umap", ".pak",
                 ".uplugin", ".uproject", ".vproject", ".zip", ".7z")
FORBIDDEN_FILES = ("kit.local.json", "do_not_distribute.txt")
MAX_BYTES = 1024 * 1024
TEXT_PATTERNS = [
    (re.compile(r"Copyright\s+(\(c\)\s*)?Epic Games", re.I), "Epic Games の著作権表示（Epic のファイルの写し？）"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "GitHub トークン"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{40,}"), "GitHub トークン"),
    (re.compile(r"https?://[^/\s:@<]+:[^/\s@<]+@"), "URL に埋め込まれた認証情報"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "秘密鍵"),
    (re.compile(r"(?i)\b[A-Z]:[\\/]+Users[\\/]+(?![<%{$])[^\\/\s\"'`]+"), "個人のユーザーフォルダのパス"),
]
SELF = "tools/release_check.py"   # パターンそのものを含むので文字列検査から外す


def git(*args):
    r = subprocess.run([common.git_exe(), "-C", common.KIT, *args], capture_output=True)
    if r.returncode != 0:
        common.die("git リポジトリの中で実行してください。\n" + r.stderr.decode("utf-8", "replace"))
    return r.stdout


def norm_hash(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def engine_hashes():
    """ローカルに runtime/ があれば、標準ライブラリのファイルの中身（改行を揃えたもの）を集める"""
    hashes = {}
    root = common.runtime_engine()
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.endswith((".verse", ".vmodule")):
                with open(os.path.join(dirpath, fn), "rb") as f:
                    hashes[norm_hash(f.read())] = os.path.relpath(os.path.join(dirpath, fn), root)
    return hashes


def candidates():
    """公開されうるファイルと、その中身。追跡中のものは index（＝コミットされる内容）から読む"""
    tracked = [p for p in git("ls-files", "-z", "--cached").decode("utf-8").split("\0") if p]
    untracked = [p for p in git("ls-files", "-z", "--others", "--exclude-standard").decode("utf-8").split("\0") if p]
    for rel in tracked:
        yield rel, git("show", f":{rel}")
    for rel in untracked:
        path = os.path.join(common.KIT, rel)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                yield rel, f.read()


def nested_repos():
    found = []
    for dirpath, dirs, _ in os.walk(common.KIT):
        if dirpath == common.KIT:
            dirs[:] = [d for d in dirs if d not in (".git", "engine") and not d.startswith("runtime")]
            continue
        if ".git" in dirs or os.path.isfile(os.path.join(dirpath, ".git")):
            found.append(os.path.relpath(dirpath, common.KIT))
            dirs[:] = []
    return found


def path_problem(rel):
    low = rel.lower().replace("\\", "/")
    if low.startswith(FORBIDDEN_DIRS):
        return "ビルド結果・UE ソースのフォルダ"
    if low.endswith(FORBIDDEN_EXT):
        return "バイナリ／Epic のファイル形式／アーカイブ"
    if low.rsplit("/", 1)[-1] in FORBIDDEN_FILES:
        return "利用者ごとのファイル"
    return None


def main():
    problems = []
    hashes = engine_hashes()
    count = 0
    for rel, data in candidates():
        count += 1
        why = path_problem(rel)
        if why:
            problems.append((rel, why))
            continue
        if len(data) > MAX_BYTES:
            problems.append((rel, f"大きすぎる（{len(data) // 1024} KB）"))
        if b"\0" in data[:8000]:
            problems.append((rel, "バイナリファイル"))
            continue
        h = norm_hash(data)
        if h in hashes:
            problems.append((rel, f"UE の標準ライブラリと同じ内容（{hashes[h]}）"))
        if rel == SELF:
            continue
        text = data.decode("utf-8", errors="ignore")
        for pat, what in TEXT_PATTERNS:
            m = pat.search(text)
            if m:
                problems.append((f"{rel}:{text.count(chr(10), 0, m.start()) + 1}", what))

    for d in nested_repos():
        problems.append((d + "/", "キットの中に別の Git リポジトリがある（UE の clone は engine/ にだけ置く）"))

    # 履歴: 一度コミットして消したものも、公開すれば履歴から取り出せる
    has_commits = subprocess.run([common.git_exe(), "-C", common.KIT, "rev-parse", "--verify", "-q", "HEAD"],
                                 capture_output=True).returncode == 0
    if has_commits:
        seen = set()
        for rel in git("log", "--all", "--name-only", "--format=", "-z").decode("utf-8").replace("\n", "\0").split("\0"):
            if rel and rel not in seen:
                seen.add(rel)
                why = path_problem(rel)
                if why:
                    problems.append((f"(履歴) {rel}", why))

    print(f"{count} ファイルを確認しました" + ("" if has_commits else "（コミットがまだないので履歴は未確認）"))
    if not hashes:
        print("  ※ runtime/ がないので標準ライブラリとの中身の照合はしていません（著作権表示の検査は実施）")
    for rel, why in problems:
        print(f"  NG  {rel}  … {why}")
    print("公開してよい状態です" if not problems else f"{len(problems)} 件の問題があります。公開しないでください")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()

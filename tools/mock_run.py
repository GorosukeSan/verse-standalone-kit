"""UEFN のコードを、自前のモック（/Fortnite.com などの代わり）と一緒に verse.exe で動かす。

使い方: python tools/mock_run.py <mock.verse.txt> <main.verse.txt> <ユーザーの .verse ...>
verse.exe は 1 ファイルしか受け取らない（--mount は未実装）ので、次のように 1 ファイルにまとめて実行する。
  - ユーザーのファイルの `using { /... }` を消し、`using { FortMock }` に置き換える
  - `@editable` を消す（verse.exe の標準ライブラリにはない）
  - `Print(` を `MockPrint(` に置き換える（verse.exe の Print と引数がぶつかるため）
モックにない API を使うとコンパイルエラーになるので、そのときはモックに足す。
"""
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I でも同じフォルダの common を読む
import common


def convert_user(text):
    text = re.sub(r"^\s*using\s*\{\s*/[^}]*\}\s*$\n?", "", text, flags=re.M)
    text = re.sub(r"@editable\s*", "", text)
    text = re.sub(r"(?<![\w.:)])Print\(", "MockPrint(", text)
    return "using { FortMock }\n" + text


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    mock, main_file, users = sys.argv[1], sys.argv[2], sys.argv[3:]
    parts = [open(mock, encoding="utf-8").read()]
    parts += [convert_user(open(u, encoding="utf-8").read()) for u in users]
    parts.append(open(main_file, encoding="utf-8").read())
    with tempfile.TemporaryDirectory(prefix="mock_run_") as work:
        path = os.path.join(work, "all.verse")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
        r = subprocess.run([common.binary("verse.exe"), path])
        if r.returncode:
            print(f"(まとめたファイル: 行番号はモック → ユーザー → Main の順に連結したもの)")
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()

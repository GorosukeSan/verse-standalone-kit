"""ビルド済みの UE ソースツリーから Verse のツールと標準ライブラリを runtime/ に集める。

使い方: python tools/pack.py <UE の Engine フォルダ> [出力先の名前（既定 runtime。runtime-<名前> も可）]

runtime/Engine/ にエンジンと同じ相対パスで配置する。verse.exe は exe の位置から
エンジンフォルダを決め、そこから Verse パッケージのソースを読むため、この形が必要。
いったん <名前>.new に作り、すべて揃ったときだけ入れ替える（失敗しても前の runtime は残る）。

注意: runtime/ の中身は Epic Games の Engine Code（標準ライブラリの .verse）と
Engine Tools（exe）。利用者の PC の中だけで使い、配布・公開しないこと（docs/LEGAL.md）。
"""
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I でも同じフォルダの common を読む
import common

BINARIES = ["verse.exe", "VerseCompilerCmd.exe", "tbbmalloc.dll"]   # tbbmalloc.dll は verse.exe が読み込む
MARKER = "DO_NOT_DISTRIBUTE.txt"


def _target(name):
    """出力先はキット直下の runtime か runtime-<名前> に限る（それ以外のフォルダを消さないため）"""
    if not re.fullmatch(r"runtime(-[A-Za-z0-9_.]+)?", name):
        common.die(f"出力先の名前は runtime か runtime-<名前> にしてください: {name}")
    return os.path.join(common.KIT, name)


def _check_removable(path):
    """キットが作ったフォルダ（目印がある）か空のときだけ消してよい"""
    if os.path.isdir(path) and os.listdir(path) and not os.path.exists(os.path.join(path, MARKER)):
        common.die(f"{path} はキットが作ったフォルダではないので消しません。中身を確認して手で片付けてください。")


def pack(engine, name="runtime", version=None):
    engine = os.path.abspath(engine)
    runtime = _target(name)
    vproject = os.path.join(engine, "Intermediate", "ProjectFiles", "Verse", "All", "All.vproject")
    if not os.path.exists(vproject):
        common.die(f"{vproject} がありません。GenerateProjectFiles.bat -VProject が済んでいるか確認してください。")
    with open(vproject, encoding="utf-8-sig") as f:
        descs = [p["desc"] for p in json.load(f)["packages"]]

    missing = [b for b in BINARIES if not os.path.exists(os.path.join(engine, "Binaries", "Win64", b))]
    if missing:
        common.die("ビルドされていないバイナリがあります: " + ", ".join(missing) + "（前の runtime はそのまま残しています）")

    staging = runtime + ".new"
    _check_removable(staging)
    _check_removable(runtime)
    if os.path.isdir(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)
    with open(os.path.join(staging, MARKER), "w", encoding="utf-8") as f:
        f.write("このフォルダは Unreal Engine のソースからローカルでビルド・抽出したものです。\n"
                "Epic Games の EULA により、一般への配布・公開はできません。\n"
                "This folder contains Unreal Engine code built locally. Do not distribute it.\n")
    out_engine = os.path.join(staging, "Engine")

    packages = []
    for desc in descs:
        src = os.path.abspath(desc["dirPath"])
        if not common.is_inside(src, engine):
            continue
        rel = os.path.relpath(os.path.realpath(src), os.path.realpath(engine))
        for dirpath, _, files in os.walk(src):
            for fn in files:
                if fn.endswith((".verse", ".vmodule")):
                    out = os.path.join(out_engine, rel, os.path.relpath(dirpath, src))
                    os.makedirs(out, exist_ok=True)
                    shutil.copy2(os.path.join(dirpath, fn), out)
        settings = dict(desc["settings"])
        # vniDestDir があると VNI 対応パッケージ扱いになる。チェック時に一時フォルダへ差し替える
        if "vniDestDir" in settings:
            settings["vniDestDir"] = ""
        packages.append({"name": desc["name"], "dir": rel.replace("\\", "/"), "settings": settings})
    if not packages:
        common.die("Verse パッケージが 1 つも見つかりませんでした（前の runtime はそのまま残しています）。")

    with open(os.path.join(staging, "packages.json"), "w", encoding="utf-8") as f:
        json.dump(packages, f, indent=1, ensure_ascii=False)
    if version:
        with open(os.path.join(staging, "VERSION.json"), "w", encoding="utf-8") as f:
            json.dump(version, f, indent=1, ensure_ascii=False)

    bindir = os.path.join(out_engine, "Binaries", "Win64")
    os.makedirs(bindir, exist_ok=True)
    for b in BINARIES:
        shutil.copy2(os.path.join(engine, "Binaries", "Win64", b), bindir)

    # 揃ったので入れ替える（消せないとき＝exe を使用中などは止まる）
    if os.path.isdir(runtime):
        try:
            shutil.rmtree(runtime)
        except OSError as e:
            common.die(f"{runtime} を消せませんでした（verse.exe などを実行中？）: {e}\n新しいものは {staging} にあります。")
    os.replace(staging, runtime)
    print(f"{len(packages)} パッケージを {runtime} に集めました")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    pack(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "runtime")

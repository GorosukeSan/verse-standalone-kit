# VerseStandaloneKit

Unreal Engine エディタなしで **Verse の型チェックと実行**ができる環境を、自分の PC で作るためのキット。

キットには Epic Games のコードもバイナリも入っていません。UE のソースは利用者自身が GitHub から取得し（認証も利用者の git に任せる）、Verse のツールだけをビルドして使います。

> **非公式**のツールです。Epic Games とは関係がなく、Epic Games の承認も受けていません（Verse・Unreal Engine・UEFN・Fortnite はいずれも Epic Games のものです）。
> Unreal Engine のソースを使うには、Epic Games の EULA への同意と GitHub アカウントの連携が必要です → [docs/LEGAL.md](docs/LEGAL.md)

## できること

| コマンド | 内容 |
|---|---|
| `verse-check <フォルダ or .verse>` | 型チェック（`VerseCompilerCmd.exe`）。`--profile cmd`（既定）/ `uefn` / `fortnite` |
| `verse-run <script.verse>` | 実行（`verse.exe`、新 VerseVM）。`Main(Args:[]string, Env:[string]string)<suspends>:void` を呼ぶ |
| `python -I tools\mock_run.py <mock> <main> <user.verse...>` | UEFN のコードを、手書きのモックと一緒に `verse.exe` で動かす |

## 必要なもの

- Windows 10/11（64bit）
- Git for Windows（Git Credential Manager 付き）
- Python 3.9 以上
- Visual Studio 2022 以降（「C++ によるデスクトップ開発」「.NET」ワークロード）
- 空き容量 100GB 前後、ビルドに 20 分〜（PC による）
- Epic Games アカウントと GitHub の連携、EpicGames Organization への招待の承認（https://www.unrealengine.com/ue-on-github）

## はじめかた

```bat
rem 1. 環境チェック（--check-access で GitHub のアクセス権も確認。認証画面が出たら自分でログイン）
doctor --check-access

rem 2. 取得 → 依存ファイル → ビルド → 切り出し（初回は確認が出る）
setup

rem 3. 使う
verse-check samples\hello
verse-run samples\hello\hello.verse
```

UE は既定でキットの中の `engine\` に clone します（最新 1 コミットだけの浅い clone）。UE のビルドは長いパスに弱いので、`setup --engine-dir D:\UE6` のように短い場所を勧めます。キットの中に置く場合は `engine\` 以外は使えません（Git の除外対象にならないため）。

### setup のオプション

| オプション | 内容 |
|---|---|
| `--engine-dir <フォルダ>` | UE を clone する先 |
| `--use-existing <フォルダ>` | clone 済みの UE ソースを使う。キットは clone も checkout もせず、`--update` のときに origin から fast-forward するだけ |
| `--branch <名前>` | ブランチ（既定 `ue6-main`） |
| `--ref <コミット>` | 特定のコミットに固定する（キットが clone した UE のみ） |
| `--remote <URL>` | 取得元（既定は公式）。GitHub 上の `<owner>/UnrealEngine` のみ |
| `--allow-fork` | 公式以外（フォーク）の取得元を許可する。ビルド時にそのリポジトリのコードが実行されるので、信頼できるものだけ |
| `--full-history` | 履歴をすべて取る |
| `--full-setup` | UE 標準の `Setup.bat` を使う（VC++ ランタイム等のインストールを含む） |
| `--skip-build` | ビルドせず切り出しだけやり直す |
| `--yes` | 最初の確認を省略する |

### 更新

```bat
update            &rem 最新を取得して作り直す（ローカルの変更があれば止まる。前の runtime\ は新しいものが揃うまで残る）
```

## プロファイル（verse-check）

- `cmd`（既定）: `verse.exe` 用。`Print(:string)<suspends>` や `LoadTextFile` などが使える
- `uefn`: UEFN と同じシグネチャの `Print`。型チェックだけ
- `fortnite`: UEFN の digest を読み込み、`using { /Fortnite.com/Devices }` などを含むコードをそのまま型チェックする
  - digest はキットに入っていません。UEFN でプロジェクトを一度開くと `%LOCALAPPDATA%\UnrealEditorFortnite\Saved\VerseProject\*\Digests\BuiltIn` にでき、自動で見つけます。別の場所なら `--digests <フォルダ>` か環境変数 `VERSE_KIT_DIGESTS`
  - UE のコンパイラは UEFN より新しいことが多く、digest 自体にもエラーが出ます。digest 内のエラーは判定から外し、自分のファイルのエラーだけで OK / NG を決めます。digest 側の壊れた宣言のせいで、UEFN では通るコードが NG になることがあります

## フォルダ構成

| パス | 内容 | Git |
|---|---|---|
| `*.bat` | 入口（`setup` / `update` / `doctor` / `verse-check` / `verse-run` / `release-check`） | ○ |
| `tools/` | 本体（Python、標準ライブラリのみ） | ○ |
| `samples/` | 動作確認用のサンプル | ○ |
| `docs/` | [規約](docs/LEGAL.md)・[セキュリティ](docs/SECURITY.md) | ○ |
| `engine/` | clone した UE のソース | × |
| `runtime/` | ビルドした exe と標準ライブラリ（**配布禁止**） | × |
| `kit.local.json` | 利用者ごとの設定 | × |

`runtime/Engine/` は UE と同じ相対パスで並べています。`verse.exe` は exe の位置からエンジンのフォルダを決めて標準ライブラリを読むので、構成を崩さないでください。

## 制限

- Windows (Win64) だけ
- `verse.exe` が実行するのは新 VerseVM で、UEFN の実行環境（BPVM）ではありません。UEFN の API（`/Fortnite.com` など）の実装もないので、UEFN のコードはモック経由でしか動きません
- MSVC ランタイムはシステムのものを使います。入っていない PC では VC++ 再頒布可能パッケージが必要です（`doctor` で確認できます）
- `GenerateProjectFiles` のときに出る `Could not find definition for module 'VerseTimer'` は UE 側の既存の警告で、影響はありません

## 規約とセキュリティ

- [docs/LEGAL.md](docs/LEGAL.md): 何を配布してよく、何をしてはいけないか（`runtime/` は配布禁止）
- [docs/SECURITY.md](docs/SECURITY.md): 認証情報の扱い、実行されるもの、ローカルの変更を消さない仕組み
- `release-check`: キットを改変して再配布する前に、配布してはいけないもの（`runtime/` の中身など）が Git に入っていないかを調べる

## ライセンス

キットのスクリプト・ドキュメント・サンプルは [MIT](LICENSE)。キットが取得・ビルドする Unreal Engine には Epic Games の EULA が適用されます。

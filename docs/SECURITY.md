# セキュリティ

キットが何をして、何をしないか。利用者と、キットを変更する人向け。

## 認証情報

- キットは **パスワード・トークン・SSH 鍵を受け取らず、保存もしません**。GitHub の認証は利用者の git が行います（Git Credential Manager はトークンを Windows の資格情報マネージャーに保存し、平文で残しません）
- 取得元 URL に認証情報を埋め込んだもの（`https://<ユーザー>:<トークン>@github.com/...`）は拒否します。URL に書いたトークンは `.git/config` やログに平文で残るためです
- `kit.local.json` に保存するのは、UE のフォルダ・取得元 URL・ブランチ・確認日だけです
- `release-check.bat` は、GitHub トークン・URL 内の認証情報・秘密鍵・個人のユーザーフォルダのパスが Git に入っていないかを調べます

## 取得元の検証

- 取得元は GitHub 上の `<owner>/UnrealEngine` だけを受け付けます。公式（`EpicGames/UnrealEngine`）以外は、`--allow-fork` を付けたときだけ使えます（ビルド時にそのリポジトリのコードが実行され、フォークの中身はその持ち主が変更できるため）
- エラー表示では URL の認証情報やクエリを伏せます
- `--use-existing` で既存の clone を使うときも、`origin` の URL を同じ規則で確かめます
- 使ったコミットと実際の origin を `runtime/VERSION.json` に記録します。特定のコミットに固定するには `setup.bat --ref <コミット>` を使います（キットが clone した UE のみ）
- ブランチ名・`--ref` は英数字と `._/-` だけを受け付けて先頭の `-` を禁止し、git には `--end-of-options` の後に渡します（git のオプションとして解釈させないため）

## 実行されるもの

`setup.bat` は、取得した UE のソースに含まれる次のプログラムを実行します。UE を自分でビルドするのと同じ信頼関係です。

| 段階 | 実行するもの | 内容 |
|---|---|---|
| 依存ファイル | `GitDependencies.exe`（フラグなし） | Epic のサーバーからバイナリ依存ファイルをダウンロード。ローカルで変更したファイルは上書きしない |
| 構成生成 | `GenerateProjectFiles.bat -VProject` | Verse パッケージ構成（`All.vproject`）を作る |
| ビルド | `Build.bat VerseCompilerCmd / VerseCmd Win64 Development` | Verse のツールだけをビルド（エディタはビルドしない） |
| `--full-setup` のときだけ | `Setup.bat` | 上に加えて VC++ ランタイムと GameInput の **サイレントインストール**、git hooks の登録、エンジンの登録（レジストリ）を行う。既定では実行しない |

## ローカルの変更を消さない

- キットが clone したリポジトリには `.git/config` に `verse-kit.managed = true` の印を付け、印があるものだけをキットが更新します。既存の clone を `--engine-dir` に指定しても、印がなければ更新しません
- 更新前に `git status` で変更がないことを確かめ、変更があれば止まります。更新は取得したコミットを `git checkout --detach` で展開するだけで、ブランチやローカルのコミットは動かしません。`stash`・`reset`・`clean` は使いません
- `--use-existing` で指定した利用者のリポジトリは、`--update` のとき検査済みの origin から取得して `merge --ff-only` するだけです。`--ref` は使えません
- ファイルを消すのは次の場合だけです
  - `runtime/`（または `runtime-<名前>/`）を作り直すとき。新しいものを `runtime.new/` に作り、揃ってから入れ替えます。キットが置いた目印（`DO_NOT_DISTRIBUTE.txt`）のないフォルダは消しません
  - clone が失敗したとき、この実行で作ったフォルダの中身

## コマンド実行

- サブプロセスはすべて引数リストで起動し、シェルを通しません
- `git` と `cmd` は絶対パスで起動します（`git` は PATH から探してカレントフォルダは見ない。`cmd` は `%ComSpec%`）。カレントフォルダに置かれた偽の `git.exe` を拾わないためです
- ただし入口の `.bat` が呼ぶ `python` は cmd が探すので、カレントフォルダの `python.exe` が優先されます。信頼できないフォルダの中でキットのコマンドを実行しないでください
- `.bat` は `cmd /c` を通る必要があるため、cmd が特別扱いする文字（`& | < > ^ % ! "` と改行）を含むパスや引数は拒否します（バッチファイル経由のコマンド注入対策）。キットのフォルダ自体の場所も setup の最初に検査します
- `.bat` から Python を起動するときは `python -I`（分離モード）を使い、カレントフォルダや環境変数 `PYTHONPATH` のモジュールを読み込まないようにしています
- 一時ファイルは `tempfile` で作り、終わったら消します

## 公開前チェック（release-check）

- 公開されるもの（index の内容・未追跡の新規ファイル・過去のコミットのファイル名）を調べます
- Epic の著作権表示、標準ライブラリと同じ内容（改行を揃えて照合。`runtime/` があるときのみ）、バイナリ、digest、トークン、個人のパス、キット内の別リポジトリを NG にします
- 完全ではありません（大きく書き換えた写しは見つけられません）。公開する前には、`git status` やファイルの中身も目で確かめてください

## Verse コードの実行について

- `verse-run.bat` は Verse のスクリプトを **実行** します。`verse.exe` の標準ライブラリにはファイルの読み込みなどの機能があるので、信頼できない `.verse` を実行しないでください
- `verse-check.bat` はコンパイラで型チェックするだけで、コードは実行しません

## 脆弱性の報告

公開リポジトリの Issue ではなく、GitHub の「Security → Report a vulnerability」（Private vulnerability reporting）から報告してください。

# 規約について（Unreal Engine EULA ほか）

> これは法的助言ではありません。Epic Games の規約は改定されることがあります。公開・利用の前に、必ず最新の原文を確認してください。
> - Unreal Engine EULA: https://www.unrealengine.com/eula/unreal
> - GitHub でのソース利用: https://www.unrealengine.com/ue-on-github
> - 整理した日: 2026-11-06。下の表は EULA の要点を言い換えたもので、原文ではありません。判断に迷うときは原文を優先してください

## 結論

| もの | このキットに入れるか | 理由 |
|---|---|---|
| キットのスクリプト（`tools/*.py`、`*.bat`）・ドキュメント・サンプル | 入れる（MIT） | すべて自作。Epic のコードを含まない |
| UE のソースコード（標準ライブラリの `.verse` / `.vmodule` を含む） | **入れない** | Engine Code。ソースの形で渡せるのは、同じ版にアクセスできる他のライセンシーだけ |
| ビルドした `verse.exe`・`VerseCompilerCmd.exe`・DLL | **入れない** | UE に含まれるツール（EULA の Engine Tools にあたると考えられる）。EULA では、Engine Tools を含むものを一般に配布する経路が限られている（Fab Marketplace か、Epic の GitHub ネットワーク内のフォーク）。このキットは安全側に倒し、バイナリを一切配布しない |
| UEFN の digest（`*.digest.verse`） | **入れない** | Fortnite / UEFN 側のファイル。利用者の PC にあるものを読むだけ |
| `runtime/`・`engine/`・`kit.local.json` | **入れない** | 利用者ごとのビルド結果と設定。`.gitignore` と `release-check.bat` で防ぐ |

このため、キットは「取得からビルドまでの手順を自動化するスクリプト」だけを配り、UE のソースの取得（＝ EULA への同意とアクセス権）とビルドは、利用者がそれぞれ自分の PC で行います。

## 利用者がすること

1. Epic Games アカウントを作り、Unreal Engine の EULA に同意する
2. Epic Games アカウントに GitHub アカウントを連携し、届いた **EpicGames Organization への招待を承認**する（承認しないと `Repository not found` になる）
3. `setup.bat` を実行する。GitHub の認証は利用者の git（Git Credential Manager か SSH 鍵）が行い、キットはパスワードやトークンを扱わない

## ビルド結果の扱い

- `runtime/` には Epic のコードとツールが入っています。**利用者の PC の中だけ**で使ってください
- 他の人に渡したり、Git に入れたり、zip で公開したりしないでください（`runtime/DO_NOT_DISTRIBUTE.txt` を置いています）
- 他の人に使ってもらうときは、このキットを渡して、その人自身にビルドしてもらいます

## 商標

- 「Unreal」「Unreal Engine」「UEFN」「Fortnite」「Epic Games」は Epic Games, Inc. の商標です。Verse 言語も Epic Games が開発したものです。このキットでは、対応するソフトを説明するためだけに名前を使っています
- キットの名前・アイコン・説明に Epic のロゴを使ったり、公式のものと誤解される表現をしたりしないでください
- このキットは **非公式** で、Epic Games とは関係がなく、Epic Games の承認も受けていません

## サンプルについて

- `samples/` のコードはすべて自作です
- `samples/fortnite_mock/mock.verse.txt` は、UEFN の API と同じ名前で手書きした最小限の「まね」（テスト用モック）で、digest や Epic のコードの写しではありません。中身を digest から写して増やさないでください

## キット自体のライセンス

キットのスクリプト・ドキュメント・サンプルは MIT ライセンスです（`LICENSE`）。MIT はキットのファイルにだけ適用され、キットが取得・ビルドする Unreal Engine には Epic Games の EULA が適用されます。UE のコードとキットのコードを 1 つのファイルに混ぜないでください（コピーレフトのコードと UE を組み合わせることは EULA で禁じられているため、キットに GPL などのコードも入れない）。

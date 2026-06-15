# テスト仕様書

本ドキュメントは、GitHub Issueの取得・同期・自動記事生成を行うシステムに対するテスト項目（単体テスト・結合テスト）を定義する。

## 1. 単体テスト（IssueManager クラス）

### 1-1. データベース管理・状態更新 (`tests/test_issue_manager.py`)

| テストID | テスト対象 | 条件・入力 | 期待される結果 |
| --- | --- | --- | --- |
| IM-DB-01 | `_init_db` | DBファイルが存在しない状態でインスタンス化 | ディレクトリと初期構造のJSONファイルが作成されること |
| IM-DB-02 | `_load_db` | 不正なJSONファイルが存在する場合 | 例外がキャッチされ、初期状態のdictが返されること |
| IM-DB-03 | `get_next_unprocessed_issue` | `unprocessed`のIssueが複数存在する場合 | Issue番号が最小（最も古い）レコードが1件返されること |
| IM-DB-04 | `get_next_unprocessed_issue` | すべてのIssueが`processed`の場合 | `None`が返されること |
| IM-DB-05 | `update_issue_status` | 存在するIssueを指定し、`processed`に更新 | `status`が更新され、`processed_at`と`article_file`が記録されること |
| IM-DB-06 | `update_issue_status` | 存在しないIssue番号を指定 | エラーログが出力され、DBの内容が変更されないこと |

### 1-2. GitHub API同期（`sync_issues`）

※ `httpx.Client.get` をモック化してテストします。

| テストID | テスト対象 | 条件・入力 | 期待される結果 |
| --- | --- | --- | --- |
| IM-API-01 | 正常系：初回同期 | `last_sync_at`がNone。APIがIssueリストを返す | 全IssueがDBに保存され、`last_sync_at`が現在時刻で更新されること |
| IM-API-02 | 正常系：差分同期 | `last_sync_at`が存在。APIが更新分のみを返す | URLパラメータに`since`が付与され、既存レコードが正しくUPDATEされること |
| IM-API-03 | 正常系：ページネーション | レスポンスヘッダの`Link`に`rel="next"`が含まれる | 次のページのURLへ継続してリクエストが送信され、全件取得されること |
| IM-API-04 | 正常系：PRの除外 | レスポンスの中に`pull_request`キーを持つデータが含まれる | PRのデータは無視され、DBに保存されないこと |
| IM-API-05 | 異常系：環境変数なし | `GITHUB_REPOSITORY` が未設定 | エラーログが出力され、同期処理がスキップされること |
| IM-API-06 | 異常系：APIエラー | APIリクエスト時にHTTPエラー（403 Rate Limit等）が発生 | 例外がキャッチされ、それまでに取得したデータが保持されること |

---

## 2. 単体テスト（メイン処理・ヘルパー関数）

### 2-1. ファイル名生成（`sanitize_filename`）

| テストID | テスト対象 | 条件・入力 | 期待される結果 |
| --- | --- | --- | --- |
| MA-FN-01 | 正常系：英数字 | `title="Fix API Bug"`, `number=10` | `issue-10-fix-api-bug.html` が返されること |
| MA-FN-02 | 正常系：記号含む | `title="Error: 500 (Server)!"`, `number=11` | 記号が除去され、`issue-11-error-500-server.html` となること |
| MA-FN-03 | 正常系：長すぎる | `title="Very long title string exceeding limits"`, `number=12` | 30文字で切り捨てられ、末尾が適切なファイル名になること |
| MA-FN-04 | フォールバック：日本語のみ | `title="テスト項目作成"`, `number=13` | アルファベットが含まれないため `issue-13.html` にフォールバックすること |
| MA-FN-05 | フォールバック：短すぎる | `title="a"`, `number=14` | 文字数が足りないため `issue-14.html` にフォールバックすること |

### 2-2. Issue単体処理（`process_single_issue`）

※ `ChatModel`, `ArticleBuilder`, `sync_article_dates` をモック化してテストします。

| テストID | テスト対象 | 条件・入力 | 期待される結果 |
| --- | --- | --- | --- |
| MA-PR-01 | 正常系：マークダウンJSON | LLMが ````json { ... } ```` の形式でレスポンスを返す | JSONが正しく抽出・パースされ、HTMLビルドと完了ステータス更新が行われること |
| MA-PR-02 | 正常系：生JSON | LLMがマークダウンブロックなしで直接 `{ ... }` を返す | JSONがそのまま正しくパースされ、処理が成功すること |
| MA-PR-03 | 異常系：LLM空応答 | LLMのレスポンスが空文字列、またはNone | 例外が発生し、Issueステータスが `failed` に更新されること |
| MA-PR-04 | 異常系：不正なJSON | LLMがJSONとしてパースできない文字列（解説文混入など）を返す | `json.decoder.JSONDecodeError` が発生し、ステータスが `failed` に更新されること |
| MA-PR-05 | 異常系：ビルド失敗 | `ArticleBuilder` または `sync_article_dates` で例外発生 | 例外がキャッチされ、ステータスが `failed` に更新されること |

---

## 3. 結合テスト（シナリオテスト）

モックを使用せず、または最小限のモック（LLMやAPI）でシステム全体のフローを検証します。

| テストID | テスト対象 | シナリオ・手順 | 期待される結果 |
| --- | --- | --- | --- |
| IT-FL-01 | 一括実行モード | `--run-once` フラグを付けて `sync-github-issues.py` を実行 | 同期が1回走り、未処理Issueが1件処理された後、無限ループに入らずスクリプトが終了すること |
| IT-FL-02 | 処理対象なし | 同期後、DB内に `unprocessed` のIssueが存在しない状態で実行 | "No unprocessed issues found" のログが出力され、スリープ待機（または終了）に入ること |
| IT-FL-03 | リカバリ検証 | 一度 `failed` になったIssueの再処理（手動でDBを`unprocessed`に戻す等） | 再度 `process_single_issue` の対象としてピックアップされ、処理が試行されること |

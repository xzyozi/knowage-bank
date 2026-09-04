---
title: "テスト仕様書（単体テスト仕様）"
document_type: "test_spec"
version: "1.1"
created_at: "2026-06-16"
updated_at: "2026-08-31"
author: "開発チーム"
purpose: "GitHub Issue同期・Markdown原本・HTML出力・状態管理の単体テスト項目を定義するため"
related_documents:
  - "KNB-DD-001_詳細設計書_GitHubIssue同期.md"
  - "KNB-DD-002_詳細設計書_記事仕様.md"
  - "KNB-DS-001_データ構造仕様書_永続化データスキーマ.md"
---
# テスト仕様書（単体テスト仕様）
| 項目     | 内容         |
| :------- | :----------- |
| 文書番号 | KNB-TEST-001 |
| 版数     | Rev.1.1      |
| 改訂日   | 2026-08-31   |

## 1. IssueManager
| ID            | 対象                         | 条件・入力                     | 期待結果                                                                                                                                   |
| :------------ | :--------------------------- | :----------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------- |
| IM-DB-01      | `_init_db`                   | DB未存在                       | 初期JSONが作成される。                                                                                                                     |
| IM-DB-02      | `_load_db`                   | 不正JSON                       | 初期構造を返す。                                                                                                                           |
| IM-DB-03/04   | `get_next_unprocessed_issue` | 複数／なし                     | 最小番号を返す／`None`。                                                                                                                   |
| IM-DB-05      | `update_issue_status`        | `processed`または`failed`      | `processed_at`、`article_file`、`article_source_file`、`index_synced`、`attempt_id`、`failed_at`、`failure_reason`を状態に応じて記録する。 |
| IM-DB-06      | `update_issue_status`        | 不存在Issue                    | DBを変更しない。                                                                                                                           |
| IM-API-01〜04 | `sync_issues`                | 初回・差分・ページング・PR混在 | 同期、`since`、全ページ、PR除外を確認する。                                                                                                |

## 2. Output層ヘルパー
| ID     | 対象                                        | 条件・入力       | 期待結果                                               |
| :----- | :------------------------------------------ | :--------------- | :----------------------------------------------------- |
| AF-01  | `atomic_write_text`                         | 新規テキスト     | UTF-8テキストが保存され、`.tmp`が残らない。            |
| AF-02  | `atomic_write_json`                         | 辞書             | JSONが保存され、`.tmp`が残らない。                     |
| AF-03  | `atomic_write_text`                         | `os.replace`失敗 | 従前ファイルを保持し、`.tmp`を清掃して例外を送出する。 |
| ASM-01 | `save_article_source`/`load_article_source` | Markdown原本     | `issue-<番号>.md`を保存・読込できる。                  |
| ASM-02 | `load_article_source`                       | 原本不存在       | `FileNotFoundError`。                                  |
| ASM-03 | `rebuild_article_from_source`               | 保存済み原本     | LLM・外部リサーチなしでHTMLを生成する。                |

## 3. Markdown・HTML検証
| ID    | 対象                | 条件・入力                                                     | 期待結果                     |
| :---- | :------------------ | :------------------------------------------------------------- | :--------------------------- |
| MV-01 | `validate_url`      | HTTPS、HTTP、javascript、相対URL、資格情報付きURL              | HTTPS絶対URLだけを真とする。 |
| MV-02 | `validate_markdown` | 通常Markdown                                                   | 有効結果を返す。             |
| MV-03 | `validate_markdown` | 危険HTML、未閉鎖フェンス、非HTTPSリンク                        | 無効結果とエラーを返す。     |
| MV-04 | `validate_markdown` | `#`、`/`、`./`、`../`リンク                                    | 現実装どおり有効結果を返す。 |
| HV-01 | `validate_html`     | DOCTYPE、`lang=ja`、title、main/article、HTTPSリンクを含むHTML | 有効結果を返す。             |
| HV-02 | `validate_html`     | 必須構造欠落または非HTTPS href                                 | 無効結果と該当エラーを返す。 |

## 4. Issue単体処理（`process_single_issue`）
`ChatModel`、MCP SSE、`ArticleBuilder`、`sync_article_dates`をモック化する。旧JSONを前提としたMA-PR-01〜04は以下のMarkdown契約へ置換する。
| ID       | 条件・入力                                                                | 期待結果                                                                                                                                 |
| :------- | :------------------------------------------------------------------------ | :--------------------------------------------------------------------------------------------------------------------------------------- |
| MA-PR-01 | LLMが外側を`markdown`コードフェンスで囲んだ、または生の有効Markdownを返す | フェンス除去後に`markdown_text`を入力として原本・HTML・index同期が実行され、`processed`に原本名・HTML名・`index_synced=true`を記録する。 |
| MA-PR-02 | 空応答または`validate_markdown`が無効とするMarkdownを返す                 | `failed`を記録し、原本・HTML・indexを成功成果物として記録しない。                                                                        |
| MA-PR-03 | 原本保存が失敗する                                                        | `failed`を記録し、成功状態にしない。                                                                                                     |
| MA-PR-04 | 保存後HTMLが`validate_html`で無効となる                                   | `failed`を記録し、index同期・`processed`を行わない。                                                                                     |

現存テストはAF-01〜03、ASM-01〜03、MV-01〜04、HV-01〜02、MA-PR-01、MA-PR-02の空応答、MA-PR-03相当を含む。MA-PR-02の不正Markdown、MA-PR-04、indexの保存後検証、index書込み失敗時の状態補償、全成果物を通す同期統合テストは追加が必要である。

## 5. 改訂履歴
| 版数    | 改訂日     | 変更内容                                                                                                                     |
| :------ | :--------- | :--------------------------------------------------------------------------------------------------------------------------- |
| Rev.1.0 | 2026-08-13 | 初版制定                                                                                                                     |
| Rev.1.1 | 2026-08-31 | 旧JSON中心のMA-PR-01〜04をMarkdown正常系・入力検証・保存失敗・HTML検証へ更新し、状態追加フィールドとOutput層単体テストを追記 |

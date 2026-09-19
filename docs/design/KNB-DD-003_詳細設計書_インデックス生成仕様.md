---
title: "詳細設計書（index.html 生成仕様）"
document_type: "detailed_design"
version: "1.3"
created_at: "2026-06-14"
updated_at: "2026-09-05"
author: "開発チーム"
purpose: "public/index.htmlの構造、記事カード生成、日付同期、および現在の保存契約を定義するため"
related_documents:
  - "KNB-DD-001_詳細設計書_GitHubIssue同期.md"
  - "KNB-DD-002_詳細設計書_記事仕様.md"
  - "KNB-DS-001_データ構造仕様書_永続化データスキーマ.md"
---
# 詳細設計書（index.html 生成仕様）
| 項目     | 内容       |
| :------- | :--------- |
| 文書番号 | KNB-DD-003 |
| 版数     | Rev.1.3    |
| 改訂日   | 2026-09-05 |

## 1. 入出力
`src/scripts/sync-article-dates.py`は`public/articles/*.html`、Gitの初回コミット日、`config/category_config.json`を入力とし、各記事の`<time>`と`public/index.html`を更新する。indexは手編集せず、同期スクリプトのテンプレートと記事HTMLから再生成する。

## 2. カード情報と分類
記事の`h1`、`.lead`、`.eyebrow`、ファイル名、初回コミット日からカードを作る。`.eyebrow`を`category_config.json`のクラスタ定義へ照合し、新着は上位6件、ドメイン内のクラスタ・記事は作成日降順に表示する。未定義のeyebrowまたはGit履歴がない記事は警告・スキップまたは日付フォールバックの対象となる。

## 3. 処理フロー
```mermaid
flowchart TD
  A[記事HTMLを走査] --> B[git logから初回コミット日を取得]
  B --> C[各記事のtimeを更新]
  C --> D[eyebrowでクラスタへ分類]
  D --> E[新着・ドメイン別カードを生成]
  E --> F[public/index.htmlを原子的書込み・保存後検証・失敗時復元]
```
Issue同期から呼び出す場合は、Markdown保存・HTML保存後のこの処理でindexを同期し、その後にIssue状態の`index_synced=true`を記録する。

## 4. 保存・検証の契約
`public/index.html` は `atomic_write_text` による原子的書込み（同一ディレクトリの `.tmp`、flush、fsync、`os.replace`）で保存する。保存後は `IndexValidator` により再読み込みを行い、記事リンク、タイトル、日付、重複等の整合性を保存後検証する。検証に失敗した場合は保存前の `index.html` へ自動復元を行い、`IndexSyncError` を送出して旧ファイルを破損させない。

| 完了機能          | 実装内容・保証範囲                                                                                                                       |
| :---------------- | :--------------------------------------------------------------------------------------------------------------------------------------- |
| index原子的書込み | `.tmp` 一時ファイルへの書込み、flush・fsync・`os.replace` により保存失敗時に旧indexを破壊しない。                                        |
| 保存後検証・復元  | 保存済みindexのリンク、カード題名、日付、重複を `IndexValidator` で再読込検証し、不整合時は保存前内容へ復元して `IndexSyncError` を送出。 |
| 統合テスト        | `tests/test_output_sync_integration.py` および `tests/test_sync_article_dates.py` で成功/失敗/復元経路を検証済み。                   |

## 5. 改訂履歴
| 版数    | 改訂日     | 変更内容                                                                    |
| :------ | :--------- | :-------------------------------------------------------------------------- |
| Rev.1.1 | 2026-08-15 | 文書間整合性レビュー反映                                                    |
| Rev.1.2 | 2026-08-31 | indexが通常上書きである実態と、原子的書込み・保存後検証を追跡事項として更新 |
| Rev.1.3 | 2026-09-05 | FEAT-01完了に伴い、indexの原子的書込み・保存後検証・自動復元の契約を明記    |

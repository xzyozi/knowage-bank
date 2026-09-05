---
title: "Output層整合性・安全性改善 機能残件"
document_type: "feature_task"
document_id: "KNB-FEAT-001"
version: "1.6"
created_at: "2026-08-31"
updated_at: "2026-09-05"
status: "completed"
---
# KNB-FEAT-001 Output層整合性・安全性改善 機能残件

## 1. 目的と管理境界
本書はOutput層の機能残件を管理する。FEAT-01〜04の全タスクが完了し、`KNB-PM-001` およびテスト群（単体・統合）にて検証済みとなった。

## 2. 完了タスク
| ID      | 優先度 | 状態 | 実装内容                                                                                                                       |
| :------ | :----: | :--- | :----------------------------------------------------------------------------------------------------------------------------- |
| FEAT-01 |   P0   | 完了 | indexの原子的書込み、保存後検証、検証失敗時の復元、Issue状態への失敗記録を実装した。                                           |
| FEAT-02 |   P0   | 完了 | `repair_truncated_json`、旧JSON生成・解析を撤去し、Issue同期・手動CLI・MCP CLI・`ArticleBuilder`をMarkdown正規入力へ統一した。 |
| FEAT-03 |   P1   | 完了 | Markdown検証の拡充（必須frontmatter、構文拒否/許可、相対リンク、引用検証）。ローカル単体テスト・lint・mypyにて検証完了。         |
| FEAT-04 |   P1   | 完了 | Output同期の統合テスト（IT-OUT-01〜06）。モックによる成功/失敗経路の動作確認をローカルpytest（--run-integration）にて検証完了。   |

## 3. アクティブタスク
現在アクティブな機能残件タスクはありません。

## 4. 依存・運用制約
- FEAT-04は、完了済みのFEAT-01・02とFEAT-03の最終契約を対象とする。
- #11/#13は`failed`を維持する。再試行は失敗理由を解消し、将来の再試行承認ワークフローで対象・理由を記録する公開APIまたはCLIが提供された後に限る。
- 外部LLM、Deep Research、GitHub APIを使う結合実行は、テスト用設定と明示承認がある場合だけ実施する。

## 5. 関連文書
- `../decisions/ADR-001_記事入力JSON廃止.md`
- `../analysis/KNB-PM-001_Output層整合性・安全性改善_開発タスク管理.md`
- `../design/KNB-DD-001_詳細設計書_GitHubIssue同期.md`
- `../design/KNB-DD-002_詳細設計書_記事仕様.md`
- `../design/KNB-DD-003_詳細設計書_インデックス生成仕様.md`

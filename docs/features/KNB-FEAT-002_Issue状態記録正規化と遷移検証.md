---
title: "Issue状態記録正規化と遷移検証"
document_type: "feature_task"
document_id: "KNB-FEAT-002"
version: "1.0"
created_at: "2026-09-08"
updated_at: "2026-09-08"
status: "completed"
---
# KNB-FEAT-002 Issue状態記録正規化と遷移検証

## 1. 目的
既存の `data/issue_status.json` レコードを現行スキーマへ正規化し、Issue同期時の状態遷移を明示的に制限する。Output層の追跡事項 OUT-01 を完了させる。

## 2. 対象タスク
| ID         | 状態 | 実装内容                                                                                                            |
| :--------- | :--- | :------------------------------------------------------------------------------------------------------------------ |
| FEAT-02-01 | 完了 | 読み込み時に欠損した状態・成果物・失敗情報フィールドを既定値で補完する。未知の状態値は `unprocessed` へ正規化する。 |
| FEAT-02-02 | 完了 | `unprocessed → processing → processed / failed` だけを許可し、完了・失敗済み Issue の自動再処理を禁止する。         |
| FEAT-02-03 | 完了 | 旧形式レコードの正規化、許可遷移、拒否遷移を単体テストで網羅する。                                                  |

## 3. 対象外
- Issue #11 / #13 を含む failed Issue の再試行承認・再実行機能
- CIで実行できる lint、型検査、フォーマットのみを目的とした変更

## 4. 検証結果
- 対象ファイルの静的診断は問題なし。
- 対象 pytest は環境の依存取得に失敗して実行できなかった（`mcp==1.27.2` 取得時の `invalid peer certificate: UnknownIssuer`）。既存 `.venv` には `pytest` が未導入のため、CIで実行する。

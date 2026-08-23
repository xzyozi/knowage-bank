---
title: "詳細設計書（ブラウザ検索履歴収集・セッション解析・Issueルーティング仕様）"
document_type: "detailed_design"
version: "1.0"
created_at: "2026-08-23"
updated_at: "2026-08-23"
author: "開発チーム"
purpose: "Chromium/Firefoxからの非同期検索履歴抽出、5分以内重複排除、30分セッション分割、Jaccard類似度によるGit Issueルーティングの具象仕様を定義するため"
related_documents:
  - "KNB-BD-002_基本設計書_パーソナルナレッジ自動生成.md"
  - "KNB-DS-002_データ構造仕様書_パーソナルナレッジデータスキーマ.md"
---

# 詳細設計書（ブラウザ検索履歴収集・セッション解析・Issueルーティング仕様）
**検索履歴収集(DAO)・重複排除/セッション解析(Domain)・Issueルーティング(Integration)仕様**

| 項目 | 内容 |
| :--- | :--- |
| 文書番号 | KNB-DD-008 |
| ドキュメント名 | 詳細設計書（ブラウザ検索履歴収集・セッション解析・Issueルーティング仕様） |
| 版数 | Rev.1.0 (新規作成) |
| 改訂日 | 2026-08-23 |
| 作成日 | 2026-08-23 |
| 作成者 | 開発チーム |

---

## 1. 目的とスコープ

本ドキュメントは、パーソナル・ナレッジ自動生成システムにおいて以下の具象モジュール仕様を規定する。

1. **データアクセス層 (DAO)**: Chrome, Edge, Firefox からの安全なSQLite読み込みと検索クエリ抽出
2. **ビジネスロジック層 (Domain)**: 時系列5分以内重複排除、30分セッション分割、単発検索（1件のみ）の破棄
3. **連携層 (Integration)**: Jaccard係数に基づくOpen Issueへのルーティング（新規起票またはコメント追記）

---

## 2. 処理フローとシーケンス

```mermaid
sequenceDiagram
    autonumber
    actor Scheduler as 定期実行タスク
    participant Aggregator as HistoryAggregator
    participant ChromiumDAO as ChromiumHistoryDAO (Chrome/Edge)
    participant FirefoxDAO as FirefoxHistoryDAO (Firefox)
    participant Deduplicator as SessionDeduplicator
    participant Analyzer as SessionAnalyzer
    participant Router as IssueRouter
    participant GitHub as Git Issue API

    Scheduler ->> Aggregator: collect_and_process()
    Aggregator ->> ChromiumDAO: fetch_search_entries()
    ChromiumDAO -->> Aggregator: list[SearchEntry]
    Aggregator ->> FirefoxDAO: fetch_search_entries()
    FirefoxDAO -->> Aggregator: list[SearchEntry]
    
    Aggregator ->> Deduplicator: deduplicate(raw_entries)
    Note over Deduplicator: 時系列ソート & 5分以内同一キーワード結合<br>(ブラウザ識別子マージ)
    Deduplicator -->> Aggregator: list[SearchEntry] (重複排除済)

    Aggregator ->> Analyzer: analyze_sessions(deduped_entries)
    Note over Analyzer: 30分間隔でセッション分割<br>クエリ1件のみの単発セッションを破棄
    Analyzer -->> Aggregator: list[SearchSession] (有効セッション群)

    loop 各 SearchSession ごと
        Aggregator ->> Router: route_session(session)
        Router ->> GitHub: get_open_issues()
        GitHub -->> Router: list[Issue]
        Note over Router: 単語集合の Jaccard 類似度を計算
        alt 最大類似度 >= 閾値 (0.3)
            Router ->> GitHub: add_comment(target_issue_id, session_text)
        else 最大類似度 < 閾値
            Router ->> GitHub: create_issue(title="[自動抽出] ...", body=session_text)
        end
    end
    Aggregator -->> Scheduler: 処理完了
```

---

## 3. レイヤー別具象仕様

### 3.1 データモデル (DTO)

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class SearchEntry:
    """ブラウザから抽出された単一検索クエリDTO"""
    timestamp: datetime
    keyword: str
    source_browser: str

@dataclass
class SearchSession:
    """30分以内の連続検索で構成されるセッションDTO"""
    start_time: datetime
    end_time: datetime
    queries: list[str]
    source_browsers: list[str] = field(default_factory=list)
```

---

### 3.2 データアクセス層 (DAO) 仕様

#### ① パス解決とハードコード定義
外部からのファイルパス指定は排除し、各ブラウザの標準プロファイルパスを定義する。

```python
# Chromium 系 (Windows)
CHROME_HISTORY_PATH = Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data/Default/History"
EDGE_HISTORY_PATH = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/User Data/Default/History"

# Firefox (Windows: プロファイル名が可変のため *.default-release 配下の places.sqlite を探索)
FIREFOX_PROFILES_DIR = Path(os.environ.get("APPDATA", "")) / "Mozilla/Firefox/Profiles"
```

#### ② 安全コピーとサイレントエラー
* `shutil.copy2` を使用して `tempfile.TemporaryDirectory` 配下に複製。
* コピー時やクエリ実行時の `IOError`, `sqlite3.Error` 等の例外は捕捉し、ログ記録の上で空リスト `[]` を返却する（サイレント障害復旧）。

#### ③ URLパース仕様
* `https://www.google.com/search?q=...` 等から `q` パラメータを抽出。
* デコード処理（`urllib.parse.unquote_plus`）を行い、前後の空白を除去。

---

### 3.3 ビジネスロジック層 (Domain) 仕様

#### ① 重複排除モジュール (`Deduplicator`)
* **入力**: `list[SearchEntry]`（複数ブラウザの合算リスト）
* **手順**:
  1. `timestamp` 昇順でソート。
  2. 直前のエントリと比較し、以下を判定：
     - キーワード正規化（大文字小文字・前後の空白を無視）が一致
     - かつ `(current.timestamp - prev.timestamp).total_seconds() <= 300` (5分以内)
  3. 一致した場合、直前のエントリにマージ（`source_browser` が異なればカンマ区切り等で結合、タイムスタンプは最新または開始時を保持）。
* **出力**: 重複排除された `list[SearchEntry]`

#### ② セッション解析モジュール (`Analyzer`)
* **入力**: 重複排除済み `list[SearchEntry]`
* **手順**:
  1. 時系列順に走査し、直前のクエリとの時間間隔が **30分（1,800秒）以内** であれば同一セッションに追加。
  2. 30分を超えた場合、現在のセッションをクローズし新規セッションを開始。
  3. **ノイズ除去**: クエリ数が **1件のみ** の単発セッションは破棄（`len(session.queries) >= 2` のみ残す）。
* **出力**: `list[SearchSession]`

---

### 3.4 連携層 (Integration) 仕様

#### ① Issue ルーティング判定 (`IssueRouter`)
* **類似度計算アルゴリズム**: Jaccard 係数
  $$ J(A, B) = \frac{|A \cap B|}{|A \cup B|} $$
  - 単語分割: 簡易形態素/空白区切り/文字N-gram（バイグラム）またはユニーク単語集合を作成。
  - セッション内のクエリ集合 $A$ と、既存 Open Issue（タイトル＋本文＋コメント）の語彙集合 $B$ を比較。
* **ルーティング分岐**:
  - `max_similarity >= 0.3` (閾値: 0.3): 最大類似度の Issue にコメントとしてセッション内容を追記。
  - `max_similarity < 0.3`: 新規 Issue を作成。
    - タイトル: `[自動抽出] <最初のクエリ> 関連の調査`
    - 本文: 開始日時、終了日時、クエリ一覧、ブラウザ情報。

---

## 4. エラーハンドリングと例外設計

| 発生レイヤー | 想定異常事象 | 処置 |
| :--- | :--- | :--- |
| **DAO層** | ブラウザ起動中によるDBロック | 一時コピーにより回避。コピー自体の失敗時はサイレントにスキップ |
| **DAO層** | Firefox プロファイルディレクトリ不存在 | インストールなしとみなし安全にスキップ |
| **Domain層** | タイムスタンプ欠損 / 不正文字列 | 当該レコードのみスキップして処理継続 |
| **Integration層** | GitHub API トークン未設定 / 通信エラー | ログ記録し次回実行へ繰り延べ（セッション消失防止） |

---

## 5. 単体テスト要件

1. **DAO層テスト (`test_browser_dao.py`)**:
   - SQLiteモックファイルを作成し、WebKit時間/PRTimeの変換、URLからのクエリ抽出を検証。
   - ファイル不在・コピー失敗時のサイレント動作（例外送出せず空リスト返却）を検証。
2. **重複排除テスト (`test_deduplicator.py`)**:
   - 5分以内の同一キーワード結合、ブラウザ識別子結合、大文字小文字無視を検証。
   - 5分超の同一キーワードが別エントリとして保持されることを検証。
3. **セッション解析テスト (`test_analyzer.py`)**:
   - 30分以内のグループ化、30分超のセッション分割を検証。
   - 1件のみの単発検索が破棄され、2件以上の連続検索のみが `SearchSession` となることを検証。
4. **ルーティングテスト (`test_issue_router.py`)**:
   - 類似度算出ロジック（Jaccard係数）の検証。
   - 閾値以上でのコメント追記コール、閾値未満での新規Issue起票コールをモック検証。

---

## 6. 改訂履歴 (Change Log)

| 版数 | 改訂日 | 変更者 | 変更内容・変更理由 (Why) |
| :--- | :--- | :--- | :--- |
| Rev.1.0 | 2026-08-23 | 開発チーム | 新規作成（ブラウザ履歴収集・セッション解析・Issueルーティング詳細設計初版制定） |

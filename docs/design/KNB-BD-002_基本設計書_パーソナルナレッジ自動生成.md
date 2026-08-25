---
title: "基本設計書（パーソナル・ナレッジ自動生成システム）"
document_type: "basic_design"
version: "1.5"
created_at: "2026-08-23"
updated_at: "2026-08-25"
author: "開発チーム"
purpose: "複数ブラウザの検索履歴から技術的調査セッションを自動抽出し、Git IssueまたはローカルストレージをキューとしてローカルLLM/Gemini APIでMarkdownナレッジを自律生成するシステムの全体アーキテクチャを定義するため"
related_documents:
  - "KNB-DD-008_詳細設計書_ブラウザ検索履歴収集とセッション解析.md"
  - "KNB-DS-002_データ構造仕様書_パーソナルナレッジデータスキーマ.md"
---

# 基本設計書（パーソナル・ナレッジ自動生成システム）
**複数ブラウザ検索履歴横断収集・セッション解析・自律ナレッジ生成アーキテクチャ**

| 項目           | 内容                                               |
| :------------- | :------------------------------------------------- |
| 文書番号       | KNB-BD-002                                         |
| ドキュメント名 | 基本設計書（パーソナル・ナレッジ自動生成システム） |
| 版数           | Rev.1.5 (ディレクトリ構成図・クラス図の追加)       |
| 改訂日         | 2026-08-25                                         |
| 作成日         | 2026-08-23                                         |
| 作成者         | 開発チーム                                         |

---

## 1. システム概要と基本方針

### 1.1 システム目的と対象範囲
本システムは、ユーザーのローカルPC上で稼働する複数ブラウザ（Google Chrome, Microsoft Edge, Mozilla Firefox）の検索履歴を横断的に収集し、意味のある「技術的調査セッション」として自動でグループ化（クラスタリング）する。
その後、Issueクライアント層（GitHub Issue または ローカルJSON/メモリ）をタスクキューとして活用してデータを蓄積し、最終的にLLM（ローカルOllamaまたはGoogle Gemini API）によってパーソナル・ナレッジ（Markdown記事）として構造化・出力する。

**「ユーザーに一切の操作や意識をさせず、バックグラウンドで自律稼働すること」** および **「GitHub未連携のスタンドアロン環境でもローカル単体動作可能であること」** を基本要件とする。

### 1.2 設計上の基本原則
1. **関心の分離 (Separation of Concerns)**:
   - データ抽出（DAO層）、ビジネスロジック（Domain層）、外部連携・ストレージ（Integration層）、ナレッジ生成（Output層）を明確にレイヤー分離する。
2. **完全独立したパッケージ構造**:
   - 既存の静的サイトビルド系モジュールとは完全分離した独立パッケージ（`src/personal_knowledge/`）として構築し、結合度を極小化する。
3. **意図判定フィルタとベクトル埋め込みクラスタリング (Intent Filtering & Semantic Clustering)**:
   - クラウド連携オプションとして、Google Gemini API (`gemini-1.5-flash` / `gemini-2.5-flash`) による「ナレッジ意図判定（True/False）」と `text-embedding-004` & コサイン類似度による高精度な意味的セッション分離をサポートする。
4. **ストレージ依存の抽象化 (Decoupled Issue Tracker)**:
   - 抽象基底クラス `BaseIssueClient` を通じて操作を行うことで、GitHub Issue REST API 連携（`GitHubIssueClient`）とローカルJSON/メモリ保存（`LocalFileIssueClient`）をシームレスに切り替え可能とする。
5. **非侵入・サイレントフォールト耐性**:
   - ブラウザ稼働中のファイルロックを回避するため、SQLiteファイルを一時ディレクトリへ安全にコピーして読み取る。
   - コピー失敗等の例外はサイレントに処理し、ユーザー体験を妨げることなく次回の定期実行に委ねる。
6. **外部入力の排除と自律動作**:
   - ブラウザDBパスや対象ブラウザ定義はコード内にカプセル化し、CLI入力なしで常駐・定期起動可能とする。

---

## 2. システム全体アーキテクチャ

システムは4層アーキテクチャおよび抽象Issueタスクキューを中心に構成される。

### 2.1 レイヤー構成図

```mermaid
flowchart TD
    subgraph DataSources ["データソース (ローカルブラウザDB)"]
        Chrome[("Chrome\n(SQLite)")]
        Edge[("Edge\n(SQLite)")]
        Firefox[("Firefox\n(SQLite)")]
    end

    subgraph DAOLayer ["データアクセス層 (DAO)"]
        BaseDAO["BrowserHistoryDAO\n(基底クラス)"]
        ChromiumDAO["ChromiumHistoryDAO\n(Chrome / Edge)"]
        FirefoxDAO["FirefoxHistoryDAO\n(Firefox)"]
        BaseDAO <|-- ChromiumDAO
        BaseDAO <|-- FirefoxDAO
    end

    subgraph DomainLayer ["ビジネスロジック層 (Domain)"]
        Deduplicator["重複排除モジュール\n(5分以内の同一クエリ結合)"]
        Filter["クエリ意図判定フィルタ\n(ブラックリスト + Gemini API LLM判定)"]
        Analyzer["セッション解析・クラスタリング\n(30分間隔分割 または Embeddingコサイン類似度)"]
    end

    subgraph IntegrationLayer ["キュー管理・API連携層 (Integration)"]
        Router["Issueルーティング\n(Jaccard/Overlap係数による類似度マージ判定)"]
        BaseClient["BaseIssueClient\n(抽象クライアント)"]
        GitHubClient["GitHubIssueClient\n(GitHub REST API)"]
        LocalClient["LocalFileIssueClient\n(ローカルJSON/メモリ)"]
        BaseClient <|-- GitHubClient
        BaseClient <|-- LocalClient
    end

    subgraph OutputLayer ["ナレッジ生成層 (Output)"]
        LLM["LLMエンジン\n(Ollama / Gemini API)"]
    end
    
    GitIssue{{"Issue / ナレッジタスクキュー\n(GitHub Issue または ローカルJSON)"}}

    Chrome --> ChromiumDAO
    Edge --> ChromiumDAO
    Firefox --> FirefoxDAO
    ChromiumDAO --> Deduplicator
    FirefoxDAO --> Deduplicator
    Deduplicator --> Filter
    Filter --> Analyzer
    Analyzer --> Router
    Router --> BaseClient
    BaseClient -- "新規起票 / コメント追記" --> GitIssue
    GitIssue -- "Openかつ12h更新なし" --> LLM
    LLM -- "Markdown出力 & Issue Close" --> GitIssue
```

### 2.2 ディレクトリ構成

`src/personal_knowledge/` パッケージ配下のレイヤー別ディレクトリ構成を以下に示す。

```
src/personal_knowledge/
├── __init__.py
├── service.py                      # PersonalKnowledgeService（全体オーケストレーション）
├── dao/                             # データアクセス層 (DAO Layer)
│   ├── __init__.py
│   ├── base_dao.py                  # BrowserHistoryDAO（抽象基底クラス）
│   ├── chromium_dao.py              # ChromiumHistoryDAO（Chrome / Edge）
│   └── firefox_dao.py               # FirefoxHistoryDAO（Firefox）
├── domain/                          # ビジネスロジック層 (Domain Layer)
│   ├── __init__.py
│   ├── models.py                    # SearchEntry / SearchSession（DTO）
│   ├── deduplicator.py               # SessionDeduplicator（5分以内重複排除）
│   └── analyzer.py                   # SessionAnalyzer（30分セッション分割）
│                                     # ※ IntentFilter / SemanticClusterer は未着手（本書§3.2参照）
└── integration/                     # キュー管理・API連携層 (Integration Layer)
    ├── __init__.py
    ├── base_issue_client.py          # BaseIssueClient（抽象基底クラス）
    ├── github_client.py              # GitHubIssueClient
    ├── local_file_client.py          # LocalFileIssueClient
    └── issue_router.py               # IssueRouter / RoutingDecision

src/scripts/
└── run-personal-knowledge-collector.py   # CLI実行エントリーポイント（§5.2参照）
```

> ナレッジ生成層 (Output Layer) は独立ディレクトリとして未着手であり、上記構成には含まれない（本書§3.4参照）。

### 2.3 クラス図

各レイヤーの主要クラスと継承・依存関係を以下に示す。

```mermaid
classDiagram
    class BrowserHistoryDAO {
        <<abstract>>
        +browser_name: str
        +default_history_path: Path
        +target_history_path: Path
        +fetch_search_entries(limit) list~SearchEntry~
        #_extract_from_sqlite(db_path, limit) list~SearchEntry~
    }
    class ChromiumHistoryDAO {
        +browser_name: str
        +default_history_path: Path
    }
    class FirefoxHistoryDAO {
        +browser_name: str
        +default_history_path: Path
    }
    BrowserHistoryDAO <|-- ChromiumHistoryDAO
    BrowserHistoryDAO <|-- FirefoxHistoryDAO

    class SearchEntry {
        +timestamp: datetime
        +keyword: str
        +source_browser: str
    }
    class SearchSession {
        +start_time: datetime
        +end_time: datetime
        +queries: list~str~
        +source_browsers: list~str~
    }
    class SessionDeduplicator {
        +time_window_seconds: int
        +deduplicate(entries) list~SearchEntry~
    }
    class SessionAnalyzer {
        +session_gap_seconds: int
        +min_queries: int
        +analyze_sessions(entries) list~SearchSession~
    }
    SessionDeduplicator ..> SearchEntry : uses
    SessionAnalyzer ..> SearchEntry : uses
    SessionAnalyzer ..> SearchSession : creates

    class BaseIssueClient {
        <<abstract>>
        +is_configured: bool
        +get_open_issues() list~dict~
        +create_issue(title, body) int
        +add_comment(issue_number, comment_body) bool
        +close_issue(issue_number) bool
    }
    class GitHubIssueClient {
        +repo: str
        +token: str
        +is_configured: bool
    }
    class LocalFileIssueClient {
        +storage_path: Path
        +is_configured: bool
    }
    BaseIssueClient <|-- GitHubIssueClient
    BaseIssueClient <|-- LocalFileIssueClient

    class RoutingDecision {
        +action: str
        +target_issue_number: int
        +similarity_score: float
        +title: str
        +body: str
    }
    class IssueRouter {
        +similarity_threshold: float
        +tokenize(text) set~str~
        +calculate_similarity(a, b) float
        +evaluate_routing(session, open_issues) RoutingDecision
    }
    IssueRouter ..> SearchSession : uses
    IssueRouter ..> RoutingDecision : creates

    class PersonalKnowledgeService {
        +daos: list~BrowserHistoryDAO~
        +deduplicator: SessionDeduplicator
        +analyzer: SessionAnalyzer
        +router: IssueRouter
        +issue_client: BaseIssueClient
        +collect_raw_entries() list~SearchEntry~
        +run_pipeline(dry_run) PipelineExecutionResult
    }
    PersonalKnowledgeService --> BrowserHistoryDAO : composes
    PersonalKnowledgeService --> SessionDeduplicator : composes
    PersonalKnowledgeService --> SessionAnalyzer : composes
    PersonalKnowledgeService --> IssueRouter : composes
    PersonalKnowledgeService --> BaseIssueClient : composes
```

---

## 3. レイヤー別責務とコンポーネント設計

### 3.1 データアクセス層 (DAO Layer)
各ブラウザがローカルに保持する履歴DBから、Google等の検索クエリを抽出する。

* **稼働方針**:
  - 実行時のファイルロック競合を回避するため、SQLiteファイルを一時ディレクトリにコピー（`shutil.copy2`）してから読み取る。
  - 万が一コピーに失敗した場合は例外を握り潰し（サイレントエラー）、次回のスケジュール実行に委ねる。
* **設定管理**:
  - DBのパス（Windows `%LOCALAPPDATA%`, `%APPDATA%` 等）や対象ブラウザはコード内にハードコードし、外部引数への依存を排除する。

| クラス名             | 対象ブラウザ | 主な責務                                                                       |
| :------------------- | :----------- | :----------------------------------------------------------------------------- |
| `BrowserHistoryDAO`  | 共通基底     | 一時コピー作成、安全なコネクション管理、抽象メソッド定義                       |
| `ChromiumHistoryDAO` | Chrome, Edge | WebKitタイムスタンプ変換、`urls` テーブルからの検索クエリ抽出                  |
| `FirefoxHistoryDAO`  | Firefox      | PRTime (マイクロ秒) 変換、`places.sqlite` の `moz_places` からの検索クエリ抽出 |

### 3.2 ビジネスロジック層 (Domain Layer)
抽出された生の検索ログをクレンジングし、意図判定と意味的グループ化（クラスタリング）を行う。

| 処理ステップ                        | モジュール                       | 仕様                                                                                                                                                                                     |
| :---------------------------------- | :------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **重複排除**                        | `Deduplicator`                   | 時系列順にソート後、**5分以内**に発生した同一キーワード（大文字小文字・空白無視）の検索を1つにマージする。マージ時、`source_browser` プロパティを結合してトレーサビリティを残す。        |
| **意図判定フィルタ**                | `IntentFilter`                   | ブラックリストキーワード（天気、ナビ、娯楽等）を除外し、必要に応じて Gemini API (`gemini-1.5-flash`) で技術・ナレッジ調査目的（True）か日常消費目的（False）かを二値判定する。           |
| **セッション分割 / クラスタリング** | `Analyzer` / `SemanticClusterer` | **ルールベース**: 30分以内の連続検索をグループ化し単発破棄。<br>**Embeddingベース**: `text-embedding-004` (768次元) とコサイン類似度 ($\ge 0.70$) で意味的なセッションにクラスタリング。 |

### 3.3 キュー管理・API連携層 (Integration Layer)
Issue（またはローカルナレッジ保存先）を揮発しない状態保持キューとして利用し、セッションの分断を吸収する。
`BaseIssueClient` インターフェースを通じて具象ストレージをカプセル化する。

* **クライアント切替方針**:
  - 環境変数 `GITHUB_REPOSITORY` が定義されている場合: `GitHubIssueClient`（GitHub REST API 経由で起票・コメント追加）
  - 環境変数が未定義の場合または CLI 引数 `--backend local`: `LocalFileIssueClient`（ローカル `data/personal_knowledge_issues.json` またはメモリ保存）
* **ルーティング判定 (`IssueRouter`)**:
  - 抽出された `SearchSession` の代表クエリ・語彙トークンと、現在 `Open` 状態の全Issueのテキスト間の類似度（Jaccard係数 / Szymkiewicz-Simpson Overlap係数）を計算する。
  - **類似度 $\ge$ 閾値 (`issue_similarity_threshold`, デフォルト 0.3)**: 該当Issueに**コメントとして追記**（分断されたセッションの結合）。
  - **類似度 $<$ 閾値**: **新規Issueとして起票**（タイトル: `[自動抽出] <最初のクエリ> 関連の調査`）。

### 3.4 ナレッジ生成層 (Output Layer)
* `Open` 状態かつ**12時間以上更新がない**Issueを検出し、調査完了と判断する。
* Issueのタイトル、本文、コメント（全クエリ履歴）を入力としてローカルLLM（Ollama）または Gemini API を呼び出し、構造化されたMarkdown記事を生成する。
* 生成完了後、該当Issueを `Closed` に更新する。

---

## 4. データモデル (DTO)

モジュール間で受け渡しされるデータ構造の概要を示す。各DTOの詳細フィールド仕様（型・必須性・デフォルト値）は詳細設計書 (KNB-DD-008) §3.1 を正本 (SSOT) とし、本書では概要のみを示す。

| DTO名             | 担当レイヤー             | 概要                                                             |
| :---------------- | :----------------------- | :--------------------------------------------------------------- |
| `SearchEntry`     | DAO $\to$ Domain         | ブラウザから抽出された単一の検索クエリ                           |
| `SearchSession`   | Domain $\to$ Integration | 30分以内の連続検索または意味的クラスタで構成される調査セッション |
| `RoutingDecision` | Integration              | セッションのルーティング判定結果（新規起票/コメント追記）        |

---

## 5. 動作前提とシステム境界

### 5.1 実行前提環境
- **対応OS**: Windows（主要ブラウザのデフォルト配置パスに準拠）
- **ランタイム**: Python 3.10以上
- **外部依存**: Git CLI / GitHub API (`GITHUB_TOKEN`, `GITHUB_REPOSITORY` 指定時)、Google Gemini API (`GEMINI_API_KEY` 指定時) または ローカルJSONストレージ、Ollama (ローカルLLM)

### 5.2 CLI 実行エントリーポイント
`src/scripts/run-personal-knowledge-collector.py` を手動または定期実行タスクのエントリーポイントとする。

| 引数名          | 必須性 | 既定値                         | 説明                                                                                                             |
| :-------------- | :----: | :----------------------------- | :--------------------------------------------------------------------------------------------------------------- |
| `--dry-run`     |  任意  | 無効                           | Issueへの起票・コメント追記を行わず、抽出・ルーティング判定結果のみを表示する                                    |
| `--json-output` |  任意  | 無効                           | 実行結果サマリーをJSON形式で標準出力に出力する                                                                   |
| `--backend`     |  任意  | 未指定（環境変数から自動判定） | 保存先バックエンドを `github` または `local` に固定する。未指定時は環境変数 `GITHUB_REPOSITORY` の有無で自動判定 |

### 5.3 安全回路・システム境界方針
- **サイレントエラー契約**: DAO層でのブラウザDB読み込みエラー（ロック中など）はログ出力のみで処理を中断せず安全にスキップする。
- **キュー安全性**: ネットワーク断や障害発生時は次回サイクルへ安全に繰り延べ、セッション喪失や重複起票を防ぐ。

---

## 6. 基本設計における変更管理方針
- **拡張時のルール**: 新規コンポーネントを追加する場合も、DAO/Domain/Integration/Outputの4層分離を維持し、新層を跨ぐ直接依存（例: DAOがIntegration層を直接呼び出す等）を追加しない。既存レイヤーの責務変更を伴う場合は、本書と詳細設計書 (KNB-DD-008) を同時に更新する。
- **仕様の決定権 (SSOT)**: システム全体のアーキテクチャ方針・レイヤー分離・コンポーネント責務境界は本書を正本とする。DTOの詳細フィールド仕様・状態遷移・シーケンスは詳細設計書 (KNB-DD-008) を正本とし、永続化スキーマ・排他制御は データ構造仕様書 (KNB-DS-002) を正本とする。

---

## 7. 改訂履歴 (Change Log)

| 版数    | 改訂日     | 変更者     | 変更内容・変更理由 (Why)                                                                                                                    |
| :------ | :--------- | :--------- | :------------------------------------------------------------------------------------------------------------------------------------------ |
| Rev.1.0 | 2026-08-23 | 開発チーム | 新規作成（パーソナル・ナレッジ自動生成システムの基本設計初版制定）                                                                          |
| Rev.1.1 | 2026-08-25 | 開発チーム | `BaseIssueClient` 抽象インターフェースおよび `LocalFileIssueClient` の追加、GitHub分離・ローカルスタンドアロン動作仕様の明記                |
| Rev.1.2 | 2026-08-25 | 開発チーム | Google Gemini API (`gemini-1.5-flash`, `text-embedding-004`) によるクエリ意図判定フィルタおよびコサイン類似度意味的クラスタリング仕様の反映 |
| Rev.1.3 | 2026-08-25 | 開発チーム | 規約違反修正: DTO詳細フィールド定義の重複記述を解消し、SSOTを詳細設計書(KNB-DD-008)に一元化                                                 |
| Rev.1.4 | 2026-08-25 | 開発チーム | レビュー対応: 変更管理方針章(§6)とCLIエントリーポイント仕様(§5.2)を追加                                                                     |
| Rev.1.5 | 2026-08-25 | 開発チーム | 実装イメージ図追加: `src/personal_knowledge/` のディレクトリ構成(§2.2)と主要クラスの関係を示すクラス図(§2.3)を追加                          |

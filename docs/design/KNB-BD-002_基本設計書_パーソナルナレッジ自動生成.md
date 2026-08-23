---
title: "基本設計書（パーソナル・ナレッジ自動生成システム）"
document_type: "basic_design"
version: "1.0"
created_at: "2026-08-23"
updated_at: "2026-08-23"
author: "開発チーム"
purpose: "複数ブラウザの検索履歴から技術的調査セッションを自動抽出し、Git IssueをキューとしてローカルLLMでMarkdownナレッジを自律生成するシステムの全体アーキテクチャを定義するため"
related_documents:
  - "KNB-DD-008_詳細設計書_ブラウザ検索履歴収集とセッション解析.md"
  - "KNB-DS-002_データ構造仕様書_パーソナルナレッジデータスキーマ.md"
---

# 基本設計書（パーソナル・ナレッジ自動生成システム）
**複数ブラウザ検索履歴横断収集・セッション解析・自律ナレッジ生成アーキテクチャ**

| 項目 | 内容 |
| :--- | :--- |
| 文書番号 | KNB-BD-002 |
| ドキュメント名 | 基本設計書（パーソナル・ナレッジ自動生成システム） |
| 版数 | Rev.1.0 (新規作成) |
| 改訂日 | 2026-08-23 |
| 作成日 | 2026-08-23 |
| 作成者 | 開発チーム |

---

## 1. システム概要と基本方針

### 1.1 システム目的と対象範囲
本システムは、ユーザーのローカルPC上で稼働する複数ブラウザ（Google Chrome, Microsoft Edge, Mozilla Firefox）の検索履歴を横断的に収集し、意味のある「技術的調査セッション」として自動でグループ化する。
その後、Git Issueをタスクキューとして活用してデータを蓄積し、最終的にローカルLLM（Ollama）によってパーソナル・ナレッジ（Markdown記事）として構造化・出力する。

**「ユーザーに一切の操作や意識をさせず、バックグラウンドで自律稼働すること」** を基本要件とする。

### 1.2 設計上の基本原則
1. **関心の分離 (Separation of Concerns)**:
   - データ抽出（DAO層）、ビジネスロジック（Domain層）、外部連携（Integration層）、ナレッジ生成（Output層）を明確にレイヤー分離する。
2. **完全独立したパッケージ構造**:
   - 既存の静的サイトビルド系モジュールとは完全分離した独立パッケージ（`src/personal_knowledge/`）として構築し、結合度を極小化する。
3. **非侵入・サイレントフォールト耐性**:
   - ブラウザ稼働中のファイルロックを回避するため、SQLiteファイルを一時ディレクトリへ安全にコピーして読み取る。
   - コピー失敗等の例外はサイレントに処理し、ユーザー体験を妨げることなく次回の定期実行に委ねる。
4. **外部入力の排除と自律動作**:
   - ブラウザDBパスや対象ブラウザ定義はコード内にカプセル化し、CLI入力なしで常駐・定期起動可能とする。

---

## 2. システム全体アーキテクチャ

システムは4層アーキテクチャおよびGit Issueタスクキューを中心に構成される。

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
        Analyzer["セッション解析モジュール\n(30分以内の連続検索抽出)"]
    end

    subgraph IntegrationLayer ["キュー管理・API連携層 (Integration)"]
        Router["Issueルーティング\n(Jaccard係数による類似度マージ判定)"]
    end

    subgraph OutputLayer ["ナレッジ生成層 (Output)"]
        LLM["ローカルLLM\n(Ollama)"]
    end
    
    GitIssue{{"Git Issue\n(永続タスクキュー)"}}

    Chrome --> ChromiumDAO
    Edge --> ChromiumDAO
    Firefox --> FirefoxDAO
    ChromiumDAO --> Deduplicator
    FirefoxDAO --> Deduplicator
    Deduplicator --> Analyzer
    Analyzer --> Router
    Router -- "新規起票 / コメント追記" --> GitIssue
    GitIssue -- "Openかつ12h更新なし" --> LLM
    LLM -- "Markdown出力 & Issue Close" --> GitIssue
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

| クラス名 | 対象ブラウザ | 主な責務 |
| :--- | :--- | :--- |
| `BrowserHistoryDAO` | 共通基底 | 一時コピー作成、安全なコネクション管理、抽象メソッド定義 |
| `ChromiumHistoryDAO` | Chrome, Edge | WebKitタイムスタンプ変換、`urls` テーブルからの検索クエリ抽出 |
| `FirefoxHistoryDAO` | Firefox | PRTime (マイクロ秒) 変換、`places.sqlite` の `moz_places` からの検索クエリ抽出 |

### 3.2 ビジネスロジック層 (Domain Layer)
抽出された生の検索ログをクレンジングし、意味のある単位（セッション）に変換する。

| 処理ステップ | モジュール | 仕様 |
| :--- | :--- | :--- |
| **重複排除** | `Deduplicator` | 時系列順にソート後、**5分以内**に発生した同一キーワード（大文字小文字・空白無視）の検索を1つにマージする。マージ時、`source_browser` プロパティを結合してトレーサビリティを残す。 |
| **セッション分割** | `Analyzer` | 検索間隔が**30分以内**の連続したクエリを1つの `SearchSession` としてグループ化する。クエリが1件のみの単発検索はノイズとみなし破棄する。 |

### 3.3 キュー管理・API連携層 (Integration Layer)
Git Issueを揮発しない状態保持キューとして利用し、セッションの分断を吸収する。
ラベル機能は使用せず、ステータス（Open/Closed）とタイムスタンプのみで状態を管理する。

* **ルーティング判定**:
  - 抽出された `SearchSession` の語彙（単語セット）と、現在 `Open` 状態の全Issueのテキスト間の類似度（Jaccard係数等）を計算する。
  - **類似度 $\ge$ 閾値**: 該当Issueに**コメントとして追記**（分断されたセッションの結合）。
  - **類似度 $<$ 閾値**: **新規Issueとして起票**（タイトル: `[自動抽出] <最初のクエリ> 関連の調査`）。

### 3.4 ナレッジ生成層 (Output Layer)
* `Open` 状態かつ**12時間以上更新がない**Issueを検出し、調査完了と判断する。
* Issueのタイトル、本文、コメント（全クエリ履歴）を入力としてローカルLLM（Ollama）を呼び出し、構造化されたMarkdown記事を生成する。
* 生成完了後、該当Issueを `Closed` に更新する。

---

## 4. データモデル (DTO)

モジュール間で受け渡しされるデータ構造を定義する。

| DTO名 | 担当レイヤー | 主要フィールド | 説明 |
| :--- | :--- | :--- | :--- |
| `SearchEntry` | DAO $\to$ Domain | `timestamp: datetime`<br>`keyword: str`<br>`source_browser: str` | ブラウザから抽出された単一の検索クエリ |
| `SearchSession` | Domain $\to$ Integration | `start_time: datetime`<br>`end_time: datetime`<br>`queries: list[str]`<br>`source_browsers: list[str]` | 30分以内の連続検索で構成される調査セッション（2件以上） |

---

## 5. 動作前提とシステム境界

### 5.1 実行前提環境
- **対応OS**: Windows（主要ブラウザのデフォルト配置パスに準拠）
- **ランタイム**: Python 3.10以上
- **外部依存**: Git CLI / GitHub API (PATまたはローカルリポジトリ連携), Ollama (ローカルLLM)

### 5.2 安全回路・システム境界方針
- **サイレントエラー契約**: DAO層でのブラウザDB読み込みエラー（ロック中など）はログ出力のみで処理を中断せず安全にスキップする。
- **Git Issueキュー安全性**: ネットワーク断等のAPI障害時はキュー投入を次回サイクルに延期し、重複起票を防ぐ。

---

## 6. 改訂履歴 (Change Log)

| 版数 | 改訂日 | 変更者 | 変更内容・変更理由 (Why) |
| :--- | :--- | :--- | :--- |
| Rev.1.0 | 2026-08-23 | 開発チーム | 新規作成（パーソナル・ナレッジ自動生成システムの基本設計初版制定） |

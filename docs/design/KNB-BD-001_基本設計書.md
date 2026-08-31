---
title: "基本設計書（システム全体アーキテクチャ定義）"
document_type: "basic_design"
version: "1.4"
created_at: "2026-06-14"
updated_at: "2026-08-31"
author: "開発チーム"
purpose: "「技術質問ノート」サイト全体のシステム構成、データフロー、コンポーネント間の依存関係を明記し、開発・改修時の設計ブレを防ぐため"
related_documents:
  - "KNB-DD-001_詳細設計書_GitHubIssue同期.md"
  - "KNB-DD-002_詳細設計書_記事仕様.md"
  - "KNB-DD-003_詳細設計書_インデックス生成仕様.md"
  - "KNB-DD-004_詳細設計書_ホームページ仕様.md"
  - "KNB-DD-005_詳細設計書_CSS仕様.md"
  - "KNB-DD-006_詳細設計書_Skill動作仕様.md"
  - "KNB-DD-007_詳細設計書_ローカルLLM運用仕様.md"
  - "KNB-DS-001_データ構造仕様書_永続化データスキーマ.md"
---

# 基本設計書（システム全体アーキテクチャ定義）
**「技術質問ノート」サイト全体システムアーキテクチャ**

| 項目           | 内容                                         |
| :------------- | :------------------------------------------- |
| 文書番号       | KNB-BD-001                                   |
| ドキュメント名 | 基本設計書（システム全体アーキテクチャ定義） |
| 版数           | Rev.1.3                                      |
| 改訂日         | 2026-08-27                                   |
| 作成日         | 2026-06-14                                   |
| 作成者         | 開発チーム                                   |

---

本ドキュメントは「技術質問ノート」サイト全体のシステム構成、データフロー、コンポーネント間の依存関係をプログラム仕様書の粒度で記述する。

## 1. システム概要

| 項目           | 内容                                                           |
| -------------- | -------------------------------------------------------------- |
| 種別           | 静的サイト（ビルドツールなし）                                 |
| ホスティング   | GitHub Pages（main ブランチ / ルート配信）                     |
| デプロイ方式   | `push → GitHub Actions → upload-pages-artifact → deploy-pages` |
| ランタイム依存 | なし（HTML/CSS/SVG のみ配信）                                  |
| 開発時依存     | Python 3（スクリプト実行）、Git（作成日取得）                  |
| 言語           | 日本語（`lang="ja"`）                                          |
| 文字コード     | UTF-8（BOM なし）、改行 LF                                     |

## 2. ディレクトリ構造と責務

```
.
├── index.html                  # エントリーポイント（スクリプト生成）
├── README.md                   # リポジトリ説明
├── AGENTS.md                   # AI エージェント向け運用ルール
├── .gitignore                  # ホワイトリスト方式（html/css/md/svg/画像のみ許可）
├── .github/
│   └── workflows/
│       └── deploy-pages.yml    # GitHub Pages デプロイワークフロー（Actions）
├── config/
│   └── category_config.json    # カテゴリ・クラスタ定義（メタデータ）
├── docs/                       # 運用・仕様ドキュメント
│   ├── KNB-BD-001_基本設計書.md                   # 本ファイル
│   ├── KNB-DD-001_詳細設計書_GitHubIssue同期.md    # GitHub Issue同期・ローカル管理仕様
│   ├── KNB-DD-002_詳細設計書_記事仕様.md             # 記事 HTML 仕様
│   ├── KNB-DD-003_詳細設計書_インデックス生成仕様.md   # index.html 生成仕様
│   ├── KNB-DD-004_詳細設計書_ホームページ仕様.md     # ホーム画面レイアウト仕様
│   ├── KNB-DD-005_詳細設計書_CSS仕様.md            # スタイルシート仕様
│   ├── KNB-DD-006_詳細設計書_Skill動作仕様.md        # Skill 動作仕様
│   ├── KNB-DD-007_詳細設計書_ローカルLLM運用仕様.md   # ローカルLLM・思考モデル運用仕様
│   ├── KNB-DS-001_データ構造仕様書_永続化データスキーマ.md # 永続化データスキーマ仕様
│   ├── TEMPLATE/               # 設計ドキュメントテンプレート・ガイドライン
│   ├── setup/
│   │   └── KNB-ENV-001_環境構築仕様書_プロジェクトセットアップ.md # 環境構築仕様書
│   └── test/
│       ├── KNB-TEST-001_テスト仕様書_単体テスト.md # 単体テスト仕様書
│       └── KNB-TEST-002_テスト仕様書_結合テスト.md # 結合テスト仕様書
├── logs/
│   └── llm_output.log          # ローカルLLMの生応答ログ
├── public/                     # 公開静的ファイルディレクトリ
│   ├── index.html              # ホーム画面エントリーポイント
│   ├── articles/               # 記事 HTML（1 ファイル = 1 質問）
│   │   ├── <slug>.html
│   │   └── template.html       # 手動作成用HTMLテンプレート
│   └── styles/
│       └── site.css            # 共通スタイルシート
├── src/                        # Pythonソースコード
│   ├── app/
│   │   ├── templates/
│   │   │   └── article_template.html # 自動生成用Jinja2テンプレート
│   │   ├── utils/
│   │   │   ├── markdown_parser.py  # 自由形式Markdown→HTML変換パーサー
│   │   │   ├── markdown_cleaner.py # Stage 0.5: 参考文献フッター分離・クレンジング
│   │   │   ├── citation_processor.py # Stage 3: 引用番号リナンバリング・アンカー生成
│   │   │   └── logger.py          # ログ出力ユーティリティ
│   │   ├── article_builder.py  # JSON/Markdownデータからの記事HTMLビルド・カテゴリ正規化
│   │   ├── chatmodel.py        # ローカルLLM (Ollama) 接続ラッパー
│   │   └── config.py           # 環境変数・パス設定
│   ├── personal_knowledge/     # パーソナル・ナレッジ自動生成パッケージ (KNB-BD-002)
│   │   ├── dao/                # 複数ブラウザ履歴抽出 (Chromium/Firefox)
│   │   ├── domain/             # 重複排除・30分セッション解析・Gemini意図判定/クラスタリング
│   │   ├── integration/        # Issueタスクキュー連携 (GitHub API / ローカルJSON)
│   │   ├── config_loader.py    # パイプライン設定読み込み
│   │   └── service.py          # 全体オーケストレーションサービス
│   └── scripts/
│       ├── generate-article.py # JSONベース技術記事自動生成スクリプト
│       ├── sync-github-issues.py # GitHub Issue同期・MCP連携・記事生成パイプライン
│       ├── sync-article-dates.py # 記事作成日同期・index.html再生成
│       └── run-personal-knowledge-collector.py # ブラウザ検索履歴収集・セッション解析CLI
└── pyproject.toml              # プロジェクト設定と依存関係（jinja2, google-genai等含む）
```

## 3. データフロー

```mermaid
flowchart TD
    Issue["GitHub Issue"] --> Prompt["Markdown専用プロンプト"]
    Prompt --> ValidateMd["保存前検証: validate_markdown"]
    ValidateMd --> Source["data/article_sources/issue-<番号>.md\n原本を原子的保存"]
    Source --> Builder["markdown_textでMarkdown→HTML変換"]
    Builder --> Html["public/articles/<slug>.html\n原子的保存"]
    Html --> ValidateHtml["保存後検証: validate_html"]
    ValidateHtml --> Index["public/index.htmlを同期\n通常上書き"]
    Index --> State["data/issue_status.jsonの状態を更新"]
```

## 4. コンポーネント依存関係

```mermaid
graph TD
    IndexHTML["public/index.html"] -->|href='articles/*.html'| ArticleHTML["public/articles/<slug>.html"]
    IndexHTML -->|href='styles/site.css'| SiteCSS["public/styles/site.css"]
    ArticleHTML -->|href='../styles/site.css'| SiteCSS
    ArticleHTML -->|src='../images/*.svg'| Images["public/images/*.svg"]
```

- `index.html` は `styles/site.css` を直接参照（同階層）
- `articles/*.html` は `../styles/site.css` を相対パスで参照（1階層上）
- 画像は `articles/` から `../images/` で参照
- JavaScript 依存なし
- 外部 CDN 依存なし

## 5. デプロイパイプライン仕様

### ファイル: `.github/workflows/deploy-pages.yml`

| 項目                 | 値                                                                   |
| -------------------- | -------------------------------------------------------------------- |
| トリガー             | `push` to `main`, `devlop`, `feat/*`, `test/*` / `workflow_dispatch` |
| ランナー             | `ubuntu-latest`                                                      |
| パーミッション       | `contents: read`, `pages: write`, `id-token: write`                  |
| 同時実行制御         | group `"pages"`, 進行中はキャンセルしない                            |
| アーティファクト対象 | `public` ディレクトリ（`path: './public'`）                          |

### ステップ

1. `actions/checkout@v4` — リポジトリチェックアウト
2. `actions/upload-pages-artifact@v3` — `public` 配下の静的ファイルをアーティファクトに格納
3. `actions/deploy-pages@v4` — GitHub Pages へデプロイ

## 6. Git 管理ポリシー

### .gitignore 方式: ホワイトリスト

デフォルトですべて無視（`*`）し、以下のみ許可:

| パターン                                                                | 用途                 |
| ----------------------------------------------------------------------- | -------------------- |
| `!*/`                                                                   | ディレクトリ走査許可 |
| `!*.html`                                                               | 記事・index          |
| `!*.css`                                                                | スタイル             |
| `!*.md`                                                                 | ドキュメント         |
| `!*.svg`                                                                | 図解                 |
| `!*.png`, `!*.jpg`, `!*.jpeg`, `!*.gif`, `!*.webp`, `!*.ico`, `!*.avif` | 画像                 |
| `!.gitignore`                                                           | 自身                 |

**意図**: `.env`、`.json`、`.py`、実行ファイルなど機密情報を含みうるファイルを一律除外し、公開リポジトリとしての安全性を確保する。

> 注意: `scripts/sync-article-dates.py` は `.py` が gitignore されているため、現状ではコミットできない。運用開始時に `!*.py` または `!scripts/*.py` の追加が必要。

## 7. セキュリティ設計

| 対策               | 実装                                                  |
| ------------------ | ----------------------------------------------------- |
| 機密情報の混入防止 | ホワイトリスト gitignore + AGENTS.md の記載禁止ルール |
| 外部スクリプト排除 | JavaScript 不使用、外部 CDN 不使用                    |
| XSS リスク         | ユーザー入力なし（静的 HTML のみ）                    |
| HTTPS              | GitHub Pages が自動適用                               |
| Content Security   | 静的配信のため追加ヘッダ設定なし（Pages デフォルト）  |

## 8. レスポンシブ設計

| ブレークポイント | 対象                                      |
| ---------------- | ----------------------------------------- |
| > 900px          | デスクトップ（新着3列、横長カード横並び） |
| 721px–900px      | タブレット（新着2列、カード折り返し）     |
| ≤ 720px          | スマホ（1列、縦積み、ナビピル化）         |

## 9. 拡張時の影響範囲

| 変更         | 影響するファイル                                                                                   |
| ------------ | -------------------------------------------------------------------------------------------------- |
| 記事追加     | `articles/<slug>.html`, `scripts/sync-article-dates.py`（ARTICLE_CLUSTER）, `index.html`（再生成） |
| カテゴリ追加 | `scripts/sync-article-dates.py`（CLUSTERS, CLUSTER_ORDER）, `index.html`（再生成）                 |
| スタイル変更 | `styles/site.css`（全ページに影響）                                                                |
| 図解追加     | `images/<name>.svg`, 対応する `articles/<slug>.html`                                               |
| 新着件数変更 | `scripts/sync-article-dates.py`（RECENT_LIMIT）, `index.html`（再生成）                            |

---

## 10. 改訂履歴 (Change Log)

| 版数    | 改訂日     | 変更者     | 変更内容・変更理由 (Why)                                                                                                         |
| :------ | :--------- | :--------- | :------------------------------------------------------------------------------------------------------------------------------- |
| Rev.1.0 | 2026-08-13 | 開発チーム | TEMPLATEに準拠したドキュメント構造化およびフォーマット標準化                                                                     |
| Rev.1.1 | 2026-08-15 | 開発チーム | 自由形式Markdown変換アーキテクチャおよびStage 0.5〜5引用アンカー自動連携仕様を追加                                               |
| Rev.1.2 | 2026-08-15 | 開発チーム | ドキュメント間整合性レビュー反映：データフロー図をMarkdown/JSONハイブリッド対応に更新、ディレクトリ構造にutilsモジュール群を追記 |
## 追補: Output層の現行契約（2026-08-31）

Issue起点の記事生成では、記事本文の正規入力をMarkdownとする。処理は「Issue取得 → Markdown生成 → 保存前検証 → `data/article_sources/issue-<番号>.md`への原本保存 → `markdown_text`からのHTML原子的保存 → 保存後HTML検証 → `public/index.html`同期 → Issue状態更新」の順に実行する。

記事本文の外部入力およびLLM出力としてのJSONはADR-001により廃止する。`issue_status.json`およびカテゴリ設定JSONは、状態管理・設定用途として従来どおり読み書きする。記事JSON修復経路の撤去はFeature `FEAT-02`で管理する。

| 成果物       | 正本・保存方式                                     | 現在の保証範囲                           |
| :----------- | :------------------------------------------------- | :--------------------------------------- |
| Issue状態    | `data/issue_status.json`、原子的JSON保存           | 試行・失敗・成果物情報を記録する。       |
| Markdown原本 | `data/article_sources/issue-<番号>.md`、原子的保存 | 保存済み原本のみからHTMLを再生成できる。 |
| 記事HTML     | `public/articles/<slug>.html`、原子的保存          | 保存後にHTML骨格・リンクを検証する。     |
| index        | `public/index.html`、通常上書き                    | 原子的書込み・保存後検証・補償は未保証。 |

実装上の未完了機能は`docs/features/KNB-FEAT-001_Output層整合性・安全性残件.md`、文書更新は`docs/analysis/KNB-PM-001_Output層整合性・安全性改善_開発タスク管理.md`で管理する。

## 改訂履歴（追記）

| 日付       | 内容                                                                      |
| :--------- | :------------------------------------------------------------------------ |
| 2026-08-31 | Output層のMarkdown正規入力、成果物の正本・保存方式、Feature管理境界を追記 |

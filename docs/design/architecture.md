# アーキテクチャ仕様書

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
│       └── static.yml          # GitHub Pages デプロイワークフロー
├── .codex/
│   └── skills/                 # AI Skill 定義
│       ├── claim-context-review/
│       │   └── SKILL.md
│       └── qa-html-note/
│           └── SKILL.md
├── articles/                   # 記事 HTML（1 ファイル = 1 質問）
│   ├── <slug>.html
│   └── ...
├── docs/                       # 運用・仕様ドキュメント
│   ├── homepage.md             # ホーム画面レイアウト運用ルール
│   ├── architecture.md         # 本ファイル
│   ├── article-spec.md         # 記事 HTML 仕様
│   ├── css-spec.md             # スタイルシート仕様
│   ├── index-generation-spec.md # index.html 生成仕様
│   └── skill-spec.md           # Skill 動作仕様
├── images/                     # 図解（SVG）
├── scripts/
│   └── sync-article-dates.py   # 作成日同期・index 再生成（未実装）
└── styles/
    └── site.css                # 共通スタイルシート
```

## 3. データフロー

```
[ユーザー] ── 質問 ──> [AI / 手動]
                            │
                            ▼
               articles/<slug>.html を作成
                            │
                            ▼
      scripts/sync-article-dates.py の ARTICLE_CLUSTER に登録
                            │
                            ▼
         python3 scripts/sync-article-dates.py を実行
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
     各記事の <time> を更新       index.html を再生成
     （git 初回コミット日）      （新着6件 + カテゴリ別）
                │                       │
                └───────────┬───────────┘
                            ▼
                    git add & commit
                            │
                            ▼
                  git push origin main
                            │
                            ▼
          GitHub Actions (static.yml) が発火
                            │
                            ▼
              GitHub Pages へデプロイ完了
```

## 4. コンポーネント依存関係

```
index.html ─────────────────────────── styles/site.css
    │                                       ▲
    │ href="articles/*.html"                │
    ▼                                       │
articles/<slug>.html ───────────── ../styles/site.css
    │
    │ src="../images/*.svg"
    ▼
images/*.svg
```

- `index.html` は `styles/site.css` を直接参照（同階層）
- `articles/*.html` は `../styles/site.css` を相対パスで参照（1階層上）
- 画像は `articles/` から `../images/` で参照
- JavaScript 依存なし
- 外部 CDN 依存なし

## 5. デプロイパイプライン仕様

### ファイル: `.github/workflows/static.yml`

| 項目                 | 値                                                  |
| -------------------- | --------------------------------------------------- |
| トリガー             | `push` to `main` / `workflow_dispatch`              |
| ランナー             | `ubuntu-latest`                                     |
| パーミッション       | `contents: read`, `pages: write`, `id-token: write` |
| 同時実行制御         | group `"pages"`, 進行中はキャンセルしない           |
| アーティファクト対象 | リポジトリルート全体（`path: '.'`）                 |

### ステップ

1. `actions/checkout@v4` — リポジトリチェックアウト
2. `actions/configure-pages@v5` — Pages 設定
3. `actions/upload-pages-artifact@v3` — 静的ファイルをアーティファクトに格納
4. `actions/deploy-pages@v5` — GitHub Pages へデプロイ

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

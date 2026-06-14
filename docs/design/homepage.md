# ホーム画面（index.html）のレイアウトと運用ルール

トップページ `public/index.html` は **手書きせず**、原則として `scripts/sync-article-dates.py` の生成結果を正とします。カテゴリ分けはフォルダではなく UI のみで行います。

## ファイルの役割

| パス | 役割 |
|------|------|
| `public/index.html` | ホーム。記事一覧・カテゴリ・新着（スクリプト生成） |
| `public/articles/*.html` | 各質問ノート本文 |
| `public/styles/site.css` | 共通スタイル（新着カード・横長カード行など） |
| `scripts/sync-article-dates.py` | 作成日同期・index 再生成 |

## ページ構成（上から順）

1. **ヒーロー** — サイトの説明
2. **分類マップ** — 新着・開発・ゲーム・AI・インフラへのアンカー
3. **新着**（`#recent`）— 直近 **6 件**、作成日の新しい順、**カード形式**
4. **カテゴリ別一覧** — 開発 / ゲーム / AI / インフラ、各ドメイン内はサブカテゴリごとに **横長カード行**

## 大カテゴリ（ドメイン）

| ID | ナビ表示 | 内容 |
|----|----------|------|
| `dev` | 開発 | フロントエンド・配信 / バックエンド・API / 開発基盤 |
| `game` | ゲーム | エンジン選定 |
| `ai` | AI | 開発ワークフロー / アプリ設計 / 基礎 / 安全・運用 |
| `infra` | インフラ | クラウド（AWS）/ ネットワーク |

サブカテゴリ（クラスタ）の定義はスクリプト内の `CLUSTERS` と `ARTICLE_CLUSTER` を参照してください。

## 並び順のルール

- **新着**: 全記事のうち git 初回コミット日が新しい **6 件** のみ
- **カテゴリ内の各リスト**: 同じサブカテゴリ内で作成日 **降順**
- **サブカテゴリブロック**: そのブロック内の最新記事の日付が新しい順（新しいブロックほど上）

## 作成日の定義

- 記事ページ・index の日付は、**その HTML ファイルの git 初回コミット日**（`git log --follow --reverse`）
- 旧パス（`programming/` など）から `articles/` へ移したファイルも `--follow` で追跡
- 記事ヒーロー直下: `<p class="article-created"><time datetime="YYYY-MM-DD">作成日: YYYY年M月D日</time></p>`

## UI パターン

### 新着 — `article-card`

- 3 列グリッド（タブレット 2 列、スマホ 1 列）
- 日付 + タグ（`card-meta-row`）、タイトル（`h4`）、概要、メタ行

### カテゴリ別 — `article-row`（横長カード）

1 行 = 1 記事の独立カード。構造は次のとおり。

```html
<a class="article-row" href="articles/….html">
  <div class="article-row-aside">   <!-- 左: 日付・タグ -->
  <div class="article-row-main">    <!-- 中央: タイトル・概要 -->
  <span class="article-row-meta">   <!-- 右: メタ（狭い画面では下段） -->
</a>
```

- タイトルは中央カラムに幅を確保し、細い列での不自然な折り返しを避ける
- スタイルの詳細は `public/styles/site.css` の `.article-row*` を参照

## 記事を追加するときの手順

1. `public/articles/<slug>.html` を追加（既存記事と同じ HTML 構成。タグ `<p class="eyebrow">` に登録したいカテゴリ名を正しく記述）
2. 必要なら `config/category_config.json` の `clusters` / `cluster_order` を更新（新しいサブカテゴリを定義するときのみ）
3. リポジトリルートで実行:

```bash
python3 src/scripts/sync-article-dates.py
```

4. `public/index.html` と全記事の作成日が更新されることを確認

`public/index.html` を手で直した場合、次回スクリプト実行で上書きされます。カードの文言や内容を変えたいときは、各記事 HTML の `h1` や `.lead` を編集してスクリプトを再実行してください。

## 変更してはいけないこと（運用上）

- トピック別サブディレクトリ（`programming/` など）に記事を分けない — 記事は **`public/articles/` のみ**
- ホームのカテゴリをフォルダ名と一致させようとしない
- 作成日を手入力でばらつかせない（git と同期スクリプトを正とする）

## 定数の変更

新着件数はスクリプト先頭付近の **`RECENT_LIMIT`**（現在 **6**）。変更後は必ず `sync-article-dates.py` を再実行してください。
カテゴリ定義や並び順の変更は、`config/category_config.json` を編集してください。

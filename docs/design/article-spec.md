# 記事 HTML 仕様書

本ドキュメントは `articles/` 配下に配置する各記事 HTML の構造、必須要素、命名規則、マークアップパターンをプログラム仕様書の粒度で定義する。

## 1. ファイル仕様

| 項目             | 値                                                        |
| ---------------- | --------------------------------------------------------- |
| 配置ディレクトリ | `articles/`（サブディレクトリ禁止）                       |
| ファイル名規則   | `<slug>.html`（英小文字、ハイフン区切り、拡張子 `.html`） |
| 文字コード       | UTF-8（BOM なし）                                         |
| 改行コード       | LF                                                        |
| DOCTYPE          | `<!doctype html>`                                         |
| 言語属性         | `<html lang="ja">`                                        |

### スラッグ命名規則

- トピックを表す英語キーワードをハイフンで連結
- 冠詞・前置詞は省略可
- 略語は一般的なものを使用（例: `ssr`, `rag`, `mcp`）
- 例: `nodejs-versions.html`, `react-19-changes.html`, `ai-friendly-relational-database.html`

## 2. ドキュメント構造（セクション順序）

```html
<!doctype html>
<html lang="ja">
<head>...</head>
<body>
  <header class="site-header">...</header>
  <main class="page">
    <article>
      ① ヒーロー (<header class="hero">)
      ② 簡潔なQ&A (<section class="qa">)
      ③ 図解（任意）(<figure class="figure">)
      ④ 本文セクション群 (<h2> + <h3> + 段落)
      ⑤ 要点 (<section class="note">)
      ⑥ 参考資料 (<section class="related">)
      ⑦ 関連ナビゲーション (<nav class="related">)
    </article>
  </main>
  <footer class="site-footer">...</footer>
</body>
</html>
```

## 3. `<head>` セクション

```html
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{記事タイトル} | 技術質問ノート</title>
  <link rel="stylesheet" href="../styles/site.css">
</head>
```

| 要素                        | 必須 | 備考                          |
| --------------------------- | ---- | ----------------------------- |
| `charset`                   | ○    | 必ず `utf-8`                  |
| `viewport`                  | ○    | レスポンシブ対応              |
| `<title>`                   | ○    | `{h1テキスト}                 | 技術質問ノート` 形式 |
| `<link rel="stylesheet">`   | ○    | 相対パス `../styles/site.css` |
| `<meta name="description">` | △    | あれば SEO 有利だが現状未使用 |
| JavaScript                  | ×    | 使用禁止                      |
| 外部 CDN                    | ×    | 使用禁止                      |

## 4. サイトヘッダー

```html
<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="../index.html">技術質問ノート</a>
  </div>
</header>
```

- 記事ページではナビゲーションリンク（新着・開発・ゲーム等）は含めない
- `href` は `../index.html`（1階層上）

## 5. ヒーロー（必須）

```html
<header class="hero">
  <p class="eyebrow">{カテゴリ / サブカテゴリ}</p>
  <h1>{質問形式のタイトル}</h1>
  <p class="article-created"><time datetime="YYYY-MM-DD">作成日: YYYY年M月D日</time></p>
  <p class="lead">{1段落のリード文}</p>
</header>
```

| 要素               | 必須 | 仕様                                                                                       |
| ------------------ | ---- | ------------------------------------------------------------------------------------------ |
| `.eyebrow`         | ○    | index.html のカード eyebrow と一致させる                                                   |
| `h1`               | ○    | 質問形式または主題を端的に表現                                                             |
| `.article-created` | ○    | `<time datetime="YYYY-MM-DD">` を含む。日付は sync スクリプトが git 初回コミット日で上書き |
| `.lead`            | ○    | 記事の結論または概要を1段落で。最大3文程度                                                 |

### datetime フォーマット

- 属性値: `YYYY-MM-DD`（ISO 8601 短縮形）
- 表示テキスト: `作成日: YYYY年M月D日`（月・日はゼロ埋めしない）

## 6. 簡潔な Q&A セクション（必須）

```html
<section class="qa" aria-labelledby="quick-answer">
  <h2 id="quick-answer">簡潔なQ&amp;A</h2>
  <dl>
    <dt>Q. {質問文}</dt>
    <dd>A. {短い回答文}</dd>
    <!-- 複数ペア可 -->
  </dl>
</section>
```

| ルール     | 詳細                                               |
| ---------- | -------------------------------------------------- |
| 見出し     | 必ず `簡潔なQ&A`                                   |
| 定義リスト | `<dl>` + `<dt>`/`<dd>` ペア                        |
| Q 接頭辞   | `Q. `                                              |
| A 接頭辞   | `A. `                                              |
| ペア数     | 1〜6 程度（ページの問いの数に応じる）              |
| 文体       | 体言止めまたは短い常体。スキャン可能な長さに収める |

## 7. 図解（任意）

```html
<figure class="figure">
  <img src="../images/{name}.svg" alt="{代替テキスト}" width="{w}" height="{h}">
  <figcaption>{図のキャプション}</figcaption>
</figure>
```

| ルール           | 詳細                                               |
| ---------------- | -------------------------------------------------- |
| 形式             | SVG 推奨（概念図・フロー図）                       |
| 配置             | `images/` ディレクトリ直下                         |
| パス             | `../images/{name}.svg`                             |
| `alt`            | 必須。図の内容を説明する意味のあるテキスト         |
| `width`/`height` | レイアウトシフト防止のため推奨                     |
| `figcaption`     | 推奨。図を参照している本文とは独立して意味が通る文 |

## 8. 本文セクション群

```html
<h2>{セクション見出し}</h2>
<p>...</p>

<h3>{サブセクション見出し}</h3>
<p>...</p>
<ul>
  <li>...</li>
</ul>
```

### 使用可能な要素

| 要素                      | 用途             |
| ------------------------- | ---------------- |
| `<h2>`                    | 大トピック区切り |
| `<h3>`                    | サブトピック     |
| `<p>`                     | 段落             |
| `<ul>`, `<ol>`            | リスト           |
| `<table class="figure">`  | 比較表・一覧表   |
| `<code>`                  | インラインコード |
| `<pre><code>`             | コードブロック   |
| `<strong>`, `<em>`        | 強調             |
| `<figure class="figure">` | 追加の図解       |

### 比較表のマークアップ

```html
<table class="figure">
  <thead>
    <tr>
      <th scope="col">{列見出し1}</th>
      <th scope="col">{列見出し2}</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>{セル}</td>
      <td>{セル}</td>
    </tr>
  </tbody>
</table>
```

- `scope="col"` または `scope="row"` をヘッダセルに付与（アクセシビリティ）
- `class="figure"` で共通の枠線・角丸スタイルが適用される

## 9. 要点セクション（必須）

```html
<section class="note">
  <h2>要点</h2>
  <p>{記事全体のまとめ。3〜5文程度}</p>
</section>
```

- 見出しは必ず `要点`
- 本文で詳述した内容の要約。新情報は入れない
- 箇条書きも可だが、できれば段落で簡潔に

## 10. 参考資料セクション（必須）

```html
<section class="related" aria-label="参考資料">
  <h2>参考資料</h2>
  <ul>
    <li><a href="{URL}">{ソース名: タイトル}</a></li>
    ...
  </ul>
</section>
```

| ルール       | 詳細                                                                                 |
| ------------ | ------------------------------------------------------------------------------------ |
| ソース種別   | 一次情報のみ（公式ドキュメント、仕様書、原論文、ベンダー公式ブログ、公開リポジトリ） |
| 最低件数     | 1 件以上                                                                             |
| リンク形式   | 完全な HTTPS URL                                                                     |
| テキスト形式 | `{組織/サイト名}: {ページタイトル}` が望ましい                                       |
| 二次情報     | 含めない（個人ブログ、ニュースサイト、SNS投稿は原則除外）                            |

## 11. 関連ナビゲーション（必須）

```html
<nav class="related" aria-label="関連リンク">
  <p><a href="{slug}.html">{関連記事タイトル}</a></p>
  <p><a href="{slug}.html">{関連記事タイトル}</a></p>
  <p><a href="../index.html">インデックスへ戻る</a></p>
</nav>
```

| ルール             | 詳細                                           |
| ------------------ | ---------------------------------------------- |
| 関連記事           | 同ドメインまたは近いトピックの記事を 1〜3 件   |
| インデックスリンク | 必ず末尾に含める                               |
| パス               | 同階層は `{slug}.html`、上位は `../index.html` |

## 12. サイトフッター

```html
<footer class="site-footer">
  <p>技術質問ノート</p>
</footer>
```

- 記事ページではシンプルなテキストのみ
- index.html のフッターとは文言が異なっても可

## 13. アクセシビリティ要件

| 項目             | 実装                                                   |
| ---------------- | ------------------------------------------------------ |
| 見出し階層       | `h1` → `h2` → `h3` の順序を守る（飛ばし禁止）          |
| 画像代替テキスト | すべての `<img>` に意味のある `alt`                    |
| テーブルヘッダ   | `<th scope="col                                        | row">` |
| ランドマーク     | `<header>`, `<main>`, `<article>`, `<nav>`, `<footer>` |
| aria-label       | `<section>` や `<nav>` に目的を示すラベル              |
| リンクテキスト   | 「こちら」ではなく具体的なリンク先を示す文言           |
| フォーカス       | デフォルトのブラウザフォーカスリングを維持             |

## 14. 禁止事項

- `<script>` タグの使用
- 外部 CDN リンク（フォント、JS ライブラリ等）
- `style` 属性によるインラインスタイル
- サブディレクトリによるカテゴリ分け
- 個人情報・機密情報の記載
- 装飾目的のみの画像（alt="" で放置しない）

## 15. 記事作成チェックリスト

新規記事を作成した際、以下を確認する:

- [ ] ファイル名が英小文字ハイフン区切り
- [ ] `<html lang="ja">` が設定されている
- [ ] `<title>` が `{タイトル} | 技術質問ノート` 形式
- [ ] CSS パスが `../styles/site.css`
- [ ] ヒーロー内に `.article-created` の `<time>` がある
- [ ] `section.qa` が存在し、`<dl>` で Q&A を記述
- [ ] 本文の見出し階層が h1 → h2 → h3 で正しい
- [ ] `section.note` に要点がある
- [ ] `section.related` に一次情報の参考リンクが 1 件以上
- [ ] `nav.related` にインデックスへの戻りリンクがある
- [ ] 画像がある場合、`alt` と `../images/` パスが正しい
- [ ] `ARTICLE_CLUSTER` に登録済み
- [ ] `sync-article-dates.py` を実行済み

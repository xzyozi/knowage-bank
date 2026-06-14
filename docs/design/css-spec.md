# CSS スタイルシート仕様書

本ドキュメントは `public/styles/site.css` の設計方針、カスタムプロパティ、コンポーネント定義、レスポンシブ戦略を記述する。

## 1. ファイル仕様

| 項目           | 値                                 |
| -------------- | ---------------------------------- |
| パス           | `public/styles/site.css`           |
| 文字コード     | UTF-8（BOM なし）                  |
| 改行コード     | LF                                 |
| プリプロセッサ | 不使用（素の CSS）                 |
| 外部依存       | なし（@import なし、CDN なし）     |
| CSS 変数       | `:root` にカスタムプロパティで定義 |

## 2. カスタムプロパティ（デザイントークン）

```css
:root {
  color-scheme: light;
  --bg: #f6f7f4;           /* ページ背景 */
  --paper: #fffefa;        /* カード・セクション背景 */
  --ink: #202124;          /* 本文テキスト */
  --muted: #5b625f;        /* 補助テキスト */
  --line: #d9ded6;         /* ボーダー */
  --accent: #0f766e;       /* アクセント（ティール） */
  --accent-strong: #115e59;/* アクセント濃色 */
  --accent-soft: #d8f3ef;  /* アクセント薄色（背景） */
  --blue: #315f8c;         /* 青系アクセント */
  --blue-soft: #e7f0f8;    /* 青系薄色 */
  --gold: #9a6b18;         /* 金系アクセント */
  --gold-soft: #fbefd1;    /* 金系薄色 */
  --code: #243447;         /* コードテキスト */
  --shadow: 0 14px 34px rgba(32, 33, 36, 0.08); /* カードシャドウ */
}
```

### カラーパレット用途マッピング

| トークン          | 使用箇所                                     |
| ----------------- | -------------------------------------------- |
| `--bg`            | `body` 背景                                  |
| `--paper`         | カード、Q&A セクション、テーブル背景         |
| `--ink`           | 本文、見出し、ブランドリンク                 |
| `--muted`         | 日付、概要文、メタ情報、フッター             |
| `--line`          | ボーダー、区切り線                           |
| `--accent`        | セクションマップ上部ボーダー、Q&A 左ボーダー |
| `--accent-strong` | リンク色、eyebrow テキスト                   |
| `--accent-soft`   | 横長カードサイド背景、note セクション背景    |
| `--blue`          | ゲームカテゴリ色                             |
| `--gold`          | 開発カテゴリ色                               |
| `--code`          | `<code>` テキスト色                          |

## 3. リセットとグローバル

```css
* { box-sizing: border-box; }
body { margin: 0; overflow-wrap: anywhere; }
img { max-width: 100%; height: auto; }
```

### フォントスタック

```
-apple-system, BlinkMacSystemFont, "Hiragino Sans",
"Yu Gothic", "YuGothic", "Noto Sans JP", sans-serif
```

- システムフォント優先（Web フォント読み込みなし）
- 日本語対応フォントを明示的に含む
- `line-height: 1.8`（本文）

## 4. レイアウトシステム

### コンテンツ幅

```css
.header-inner, .page, .site-footer {
  width: min(1040px, calc(100% - 32px));
  margin: 0 auto;
}
```

- 最大幅: `1040px`
- 左右パディング: 各 `16px`（合計 32px のガター）
- モバイル時: `min(100% - 24px, 1040px)`（合計 24px）

### ページパディング

| 画面         | padding-top | padding-bottom |
| ------------ | ----------- | -------------- |
| デスクトップ | 52px        | 72px           |
| モバイル     | 30px        | 52px           |

## 5. コンポーネント一覧

### 5.1 サイトヘッダー `.site-header`

| プロパティ        | 値                         | 目的           |
| ----------------- | -------------------------- | -------------- |
| `position`        | `sticky`                   | スクロール追従 |
| `top`             | `0`                        | 上部固定       |
| `z-index`         | `10`                       | 他要素の上に   |
| `background`      | `rgba(255, 254, 250, 0.9)` | 半透明         |
| `backdrop-filter` | `blur(16px)`               | 背景ぼかし     |
| `border-bottom`   | `1px solid var(--line)`    | 境界線         |

#### `.header-inner`

- `display: flex`
- `align-items: center`
- `justify-content: space-between`
- モバイル: `flex-direction: column`, `align-items: flex-start`

### 5.2 ナビゲーション `.nav`

- `display: flex`, `flex-wrap: wrap`, `gap: 14px`
- モバイル: ピル型ボタン化（`border-radius: 999px`, border + 背景）

### 5.3 ヒーロー `.hero`

- `margin-bottom: 34px`（モバイル: 24px）
- `.home-hero`: `max-width: 900px`, `padding-bottom: 10px`

### 5.4 セクションマップ `.section-map`

```
display: grid
grid-template-columns: repeat(auto-fit, minmax(150px, 1fr))
gap: 10px
```

各カード:
- `border-top: 4px solid {色}` で色分け
  - 1番目: `--accent`（新着）
  - 2番目: `--gold`（開発）
  - 3番目: `--blue`（ゲーム）
  - 4番目: `#6f6a58`（AI）
  - 5番目以降: デフォルト `--accent`
- ホバー: `transform: translateY(-2px)`, `box-shadow: var(--shadow)`

### 5.5 新着カード `.article-card`

```
display: block
min-height: 170px
padding: 18px
border: 1px solid var(--line)
border-radius: 8px
background: var(--paper)
```

#### `.card-meta-row`

- `display: flex`, `flex-wrap: wrap`, `gap: 8px 12px`
- 日付 + eyebrow を横並び

#### グリッドレイアウト

| 画面      | 列数 |
| --------- | ---- |
| > 900px   | 3列  |
| 721–900px | 2列  |
| ≤ 720px   | 1列  |

### 5.6 横長カード `.article-row`

```
display: flex
align-items: stretch
min-height: 88px
border-radius: 8px
```

#### 3カラム構造

| パーツ   | クラス               | flex        | 幅目安    |
| -------- | -------------------- | ----------- | --------- |
| 左サイド | `.article-row-aside` | `0 0 118px` | 固定118px |
| 中央本文 | `.article-row-main`  | `1 1 auto`  | 残り全部  |
| 右メタ   | `.article-row-meta`  | `0 0 9.5em` | 固定9.5em |

#### `.article-row-aside`

- 左ボーダー分離（`border-right: 1px solid var(--line)`）
- グラデーション背景: `linear-gradient(180deg, var(--accent-soft), rgba(216,243,239,0.45))`
- 日付 + eyebrow を縦配置

#### `.article-row-main`

- タイトル: `.article-row-title`（17px, 700, `text-wrap: pretty`）
- 概要: `.article-row-desc`（14px, 2行クランプ）

#### レスポンシブ（≤ 900px）

- `flex-wrap: wrap`
- `.article-row-meta`: 幅100%, 下段に移動, 上ボーダー追加

#### レスポンシブ（≤ 720px）

- `flex-direction: column`
- `.article-row-aside`: 横方向、全幅、下ボーダー
- `.article-row-main`: 通常パディング
- `.article-row-meta`: 全幅、左寄せ

### 5.7 Q&A セクション `.qa`

```css
margin: 28px 0 30px;
padding: 24px;
border-left: 5px solid var(--accent);
border-radius: 8px;
background: var(--paper);
box-shadow: var(--shadow);
```

- `h2`: `margin-top: 0`
- `dl`: `margin: 0`
- `dt`: `font-weight: 700`, `margin: 18px 0 6px`
- `dd`: `margin: 0`

### 5.8 図解・テーブル `.figure`

共通スタイル:
```css
margin: 30px 0;
padding: 18px;
border: 1px solid var(--line);
border-radius: 8px;
background: var(--paper);
```

テーブル固有:
- `display: table`, `width: 100%`, `border-collapse: collapse`
- `th`: `background: #ece6db`, `font-weight: 700`
- モバイル: `display: block`, `overflow-x: auto`

### 5.9 要点 `.note`

```css
padding: 18px 20px;
border: 1px solid #b7d7d2;
border-radius: 8px;
background: var(--accent-soft);
```

### 5.10 参考・関連 `.related`

```css
margin-top: 46px;
padding-top: 24px;
border-top: 1px solid var(--line);
```

### 5.11 コード

インライン `code`:
```css
padding: 0.12em 0.28em;
border-radius: 4px;
background: #ece6db;
color: var(--code);
font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
font-size: 0.92em;
```

`pre`: `overflow-x: auto`

### 5.12 フッター `.site-footer`

```css
padding: 28px 0 40px;
border-top: 1px solid var(--line);
color: var(--muted);
font-size: 14px;
```

## 6. タイポグラフィスケール

| 要素            | デスクトップ | モバイル | line-height |
| --------------- | ------------ | -------- | ----------- |
| `h1`            | 44px         | 30px     | 1.35        |
| `h2`            | 26px         | 23px     | 1.35        |
| `h3`            | 20px         | 18px     | 1.35        |
| `h4`            | 18px         | 18px     | 1.38        |
| `body`          | 16px (暗黙)  | 16px     | 1.8         |
| `.lead`         | 18px         | 16px     | 1.8         |
| `.eyebrow`      | 13px         | 13px     | —           |
| `.article-date` | 13px         | 13px     | —           |
| `.meta`         | 14px         | 14px     | —           |

## 7. インタラクション

### ホバーエフェクト（カード共通）

```css
transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
```

ホバー時:
- `transform: translateY(-2px)`
- `border-color: #b8c7c2`
- `box-shadow: var(--shadow)`

### リンクスタイル

```css
a {
  color: var(--accent-strong);
  text-decoration-thickness: 0.08em;
  text-underline-offset: 0.18em;
}
```

## 8. ブレークポイント

| ブレークポイント | メディアクエリ     | 主な変更                                              |
| ---------------- | ------------------ | ----------------------------------------------------- |
| タブレット       | `max-width: 900px` | 新着2列、横長カードメタ折り返し                       |
| スマホ           | `max-width: 720px` | 1列化、ヘッダー縦積み、ナビピル化、フォントサイズ縮小 |

## 9. 未使用 / 予約クラス

| クラス           | 状態        | 想定用途                                    |
| ---------------- | ----------- | ------------------------------------------- |
| `.muted-cluster` | HTML未使用  | 淡色背景のクラスタ（`background: #f1f4ef`） |
| `.empty-note`    | HTML未使用  | 記事が空のクラスタ向けプレースホルダー      |
| `.blue-soft`     | CSS定義のみ | 青系背景バリエーション                      |
| `.gold-soft`     | CSS定義のみ | 金系背景バリエーション                      |

## 10. スタイル追加ガイドライン

新しいコンポーネントを追加する際のルール:

1. カスタムプロパティを使う（ハードコード色禁止）
2. コンポーネント単位でまとめて記述する
3. BEM は使わないが、`.parent-child` のフラットな命名を維持
4. `!important` は使用しない
5. 新ブレークポイントの追加は既存の 900px / 720px に統合
6. アニメーションは `transition` のみ（`@keyframes` は原則不使用）
7. `position: fixed` は避ける（sticky ヘッダーのみ例外）

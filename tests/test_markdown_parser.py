import pytest
from app.utils.markdown_parser import FlexibleMarkdownParser
from app.article_builder import ArticleBuilder

def test_flexible_markdown_parser_frontmatter():
    md_text = """---
title: "AWS KIROとCursorの比較・移行手順"
eyebrow: "AI > 開発ワークフロー"
tags: ["AWS", "AI", "Cursor", "KIRO"]
created_at: "2026-08-13"
---

# 概要

これは任意のMarkdown本文です。

## 基本機能

- 機能1: 高速な検索
- 機能2: 自動コード生成

Q: KIROとは何ですか？
A: AWSが提供するAIコードエディタです。

[AWS公式](https://aws.amazon.com)
"""
    parser = FlexibleMarkdownParser(md_text)
    data = parser.parse()

    assert data["title"] == "AWS KIROとCursorの比較・移行手順"
    assert data["eyebrow"] == "AI > 開発ワークフロー"
    assert "AWS" in data["tags"]
    assert len(data["qa"]) == 1
    assert data["qa"][0]["q"] == "KIROとは何ですか？"
    assert len(data["references"]) == 1
    assert data["references"][0]["url"] == "https://aws.amazon.com"
    assert "<h2>基本機能</h2>" in data["body_html"]
    assert "<li>機能1: 高速な検索</li>" in data["body_html"]

def test_article_builder_with_flexible_markdown():
    md_text = """---
title: "自由構成Markdownのテスト"
eyebrow: "開発 > バックエンド"
---

## 導入
任意の形式で記述された本文です。

```python
def hello():
    print("Hello, World!")
```
"""
    builder = ArticleBuilder()
    html_output = builder.build_article_html({"markdown_text": md_text})

    assert "<title>自由構成Markdownのテスト | 技術質問ノート</title>" in html_output
    assert 'class="eyebrow">開発 > バックエンド' in html_output
    assert "<h2>導入</h2>" in html_output
    assert '<pre><code class="language-python">' in html_output

def test_stage0_5_and_stage3_pipeline():
    raw_md = """---
title: "統計データ活用の実態調査"
eyebrow: "AI > 統計"
---

## 調査概要

政府統計データ [11, 20] や世論調査 [21] によると、活用の幅が広がっています。

[11] e-Stat（政府統計ポータル）
URL: https://www.e-stat.go.jp

[20] 無関係な雑多な資料
URL: https://example.com/junk

[21] 外務省 世論調査
URL: https://www.mofa.go.jp
"""
    builder = ArticleBuilder()
    data = {
        "markdown_text": raw_md,
        "citations_keep": [11, 21],  # 20 は LLM により除外指定
        "citation_labels": {
            "11": "e-Stat ポータル",
            "21": "外務省 2026年世論調査"
        }
    }
    html_output = builder.build_article_html(data)

    # 引用番号が 1, 2 にリナンバリングされているか確認
    assert '<sup><a href="#ref-1">1</a>,<a href="#ref-2">2</a></sup>' in html_output or '<sup><a href="#ref-1">1</a></sup>' in html_output
    # 20 番の除外確認
    assert "example.com/junk" not in html_output
    # アンカーおよびラベルの確認
    assert '<li id="ref-1">' in html_output
    assert '<a href="https://www.e-stat.go.jp" target="_blank" rel="noopener">e-Stat ポータル</a>' in html_output
    assert '<li id="ref-2">' in html_output
    assert '<a href="https://www.mofa.go.jp" target="_blank" rel="noopener">外務省 2026年世論調査</a>' in html_output

def test_pipe_table_and_mermaid_parsing():
    md_text = """
## 表のテスト

| パターン | 利点 | 用途 |
| :--- | :--- | :--- |
| **線形** | 高速 | 定型処理 |
| **グラフ** | 柔軟 | 複雑なフロー |

```mermaid
graph TD
    A --> B
```
"""
    parser = FlexibleMarkdownParser(md_text)
    data = parser.parse()
    
    assert '<div class="figure table-wrapper">' in data["body_html"]
    assert '<table>' in data["body_html"]
    assert '<th scope="col">パターン</th>' in data["body_html"]
    assert '<td><strong>線形</strong></td>' in data["body_html"]
    assert '<div class="mermaid">' in data["body_html"]
    assert 'A --> B' in data["body_html"]

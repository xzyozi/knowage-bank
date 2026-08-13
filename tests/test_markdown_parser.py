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

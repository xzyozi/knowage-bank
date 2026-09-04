"""markdown_validator.py の単体テスト。"""

from app.utils.markdown_validator import (
    validate_html,
    validate_markdown,
    validate_url,
)


def test_validate_url() -> None:
    """URL 検証の正常系・異常系テスト"""
    assert validate_url("https://qiita.com/items/123") is True
    assert validate_url("https://github.com/xzyozi/knowage-bank") is True

    # 非 HTTPS
    assert validate_url("http://example.com") is False
    assert validate_url("javascript:alert(1)") is False
    # 相対パス
    assert validate_url("/articles/issue-1.html") is False
    # 資格情報付き
    assert validate_url("https://user:pass@example.com") is False


def test_validate_markdown_valid() -> None:
    """正常な Markdown の検証パス"""
    valid_md = (
        "---\ntitle: テスト記事\neyebrow: 技術\nlead: リード文\n---\n\n"
        "## セクション1\n内容テキスト\n\n"
        "### サブセクション\n"
        "- [公式ドキュメント](https://docs.python.org/3/)\n\n"
        "```python\nprint('hello')\n```"
    )
    result = validate_markdown(valid_md)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_validate_markdown_forbidden_html() -> None:
    """危険な生 HTML タグ検出のテスト"""
    invalid_md = "## 見出し\n<script>alert('xss')</script>\n内容"
    result = validate_markdown(invalid_md)
    assert result.is_valid is False
    assert any("Forbidden or dangerous HTML" in e for e in result.errors)


def test_validate_markdown_unclosed_codeblock() -> None:
    """未閉鎖コードフェンス検出のテスト"""
    unclosed_md = "## コード例\n```python\nprint('hi')\n"
    result = validate_markdown(unclosed_md)
    assert result.is_valid is False
    assert any("Unclosed code fence" in e for e in result.errors)


def test_validate_markdown_non_https_link() -> None:
    """非 HTTPS リンク検出のテスト"""
    non_https_md = "## 参照\n- [非安全サイト](http://insecure-site.com)"
    result = validate_markdown(non_https_md)
    assert result.is_valid is False
    assert any("non-https" in e.lower() for e in result.errors)


def test_validate_markdown_anchor_and_relative_links() -> None:
    """アンカーリンク (#) や相対パスリンク (/, ./, ../) が許可されるテスト"""
    relative_md = (
        "---\ntitle: テスト\neyebrow: Tech\nlead: lead\n---\n\n"
        "## セクション\n- [内部アンカー](#section-1)\n"
        "- [ルート相対](/articles/issue-1.html)\n"
        "- [相対パス](./issue-2.html)\n"
        "- [親ディレクトリ相対](../articles/issue-3.html)"
    )
    result = validate_markdown(relative_md)
    assert result.is_valid is True
    assert len(result.errors) == 0


def test_validate_html_valid() -> None:
    """正常な HTML 構造の検証テスト"""
    valid_html = (
        "<!DOCTYPE html>\n<html lang=\"ja\">\n<head><title>テスト</title></head>\n"
        "<body><main><article><h1>タイトル</h1>"
        "<a href=\"https://example.com\">リンク</a>"
        "<a href=\"../articles/issue-1.html\">相対リンク</a></article></main></body></html>"
    )
    result = validate_html(valid_html)
    assert result.is_valid is True


def test_validate_html_invalid_structure() -> None:
    """必須要素欠損および非 HTTPS href 検出のテスト"""
    invalid_html = "<div><a href=\"http://example.com\">非安全</a></div>"
    result = validate_html(invalid_html)
    assert result.is_valid is False
    assert any("Missing DOCTYPE" in e for e in result.errors)
    assert any("Missing lang='ja'" in e for e in result.errors)
    assert any("Missing <title>" in e for e in result.errors)
    assert any("Missing <article> or <main>" in e for e in result.errors)
    assert any("Non-HTTPS" in e for e in result.errors)

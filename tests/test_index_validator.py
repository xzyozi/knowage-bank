"""index_validator.py の単体テスト。"""

from datetime import datetime
from typing import Any

from app.utils.index_validator import validate_index_html


def _make_index_html(card_html: str) -> str:
    return f"""<!doctype html>
<html lang="ja">
<body>
    <section>
        <!-- BEGIN_RECENT_ARTICLES -->
{card_html}
        <!-- END_RECENT_ARTICLES -->
    </section>
</body>
</html>
"""


def test_validate_index_html_success(tmp_path: Any) -> None:
    """IV-01: リンク・タイトル・日付が整合する正常系"""
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()
    (articles_dir / "issue-1.html").write_text("<html></html>", encoding="utf-8")

    card = """            <a class="article-card" href="articles/issue-1.html">
                <p class="card-meta-row">
                    <time class="article-date" datetime="2026-08-01">2026年8月1日</time>
                </p>
                <h4>テスト記事</h4>
            </a>"""
    index_html = _make_index_html(card)

    articles = [{"filename": "issue-1.html", "title": "テスト記事", "date": datetime(2026, 8, 1)}]

    result = validate_index_html(index_html, articles, str(articles_dir))
    assert result.is_valid
    assert result.errors == []


def test_validate_index_html_missing_article_file(tmp_path: Any) -> None:
    """IV-02: リンク先の記事HTMLが実在しない場合はエラー"""
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()
    # issue-1.html を作成しない

    card = """            <a class="article-card" href="articles/issue-1.html">
                <h4>テスト記事</h4>
            </a>"""
    index_html = _make_index_html(card)

    articles = [{"filename": "issue-1.html", "title": "テスト記事", "date": datetime(2026, 8, 1)}]

    result = validate_index_html(index_html, articles, str(articles_dir))
    assert not result.is_valid
    assert any("does not exist" in e for e in result.errors)


def test_validate_index_html_title_mismatch(tmp_path: Any) -> None:
    """IV-03: index内のタイトルが記事メタデータと異なる場合はエラー"""
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()
    (articles_dir / "issue-1.html").write_text("<html></html>", encoding="utf-8")

    card = """            <a class="article-card" href="articles/issue-1.html">
                <time datetime="2026-08-01"></time>
                <h4>間違ったタイトル</h4>
            </a>"""
    index_html = _make_index_html(card)

    articles = [{"filename": "issue-1.html", "title": "正しいタイトル", "date": datetime(2026, 8, 1)}]

    result = validate_index_html(index_html, articles, str(articles_dir))
    assert not result.is_valid
    assert any("Title mismatch" in e for e in result.errors)


def test_validate_index_html_date_mismatch(tmp_path: Any) -> None:
    """IV-04: index内の日付が記事メタデータと異なる場合はエラー"""
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()
    (articles_dir / "issue-1.html").write_text("<html></html>", encoding="utf-8")

    card = """            <a class="article-card" href="articles/issue-1.html">
                <time datetime="2020-01-01"></time>
                <h4>テスト記事</h4>
            </a>"""
    index_html = _make_index_html(card)

    articles = [{"filename": "issue-1.html", "title": "テスト記事", "date": datetime(2026, 8, 1)}]

    result = validate_index_html(index_html, articles, str(articles_dir))
    assert not result.is_valid
    assert any("Date mismatch" in e for e in result.errors)


def test_validate_index_html_duplicate_links(tmp_path: Any) -> None:
    """IV-05: 同一セクション内に重複したリンクがある場合はエラー"""
    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()
    (articles_dir / "issue-1.html").write_text("<html></html>", encoding="utf-8")

    card = """            <a class="article-card" href="articles/issue-1.html">
                <time datetime="2026-08-01"></time>
                <h4>テスト記事</h4>
            </a>
            <a class="article-card" href="articles/issue-1.html">
                <time datetime="2026-08-01"></time>
                <h4>テスト記事</h4>
            </a>"""
    index_html = _make_index_html(card)

    articles = [{"filename": "issue-1.html", "title": "テスト記事", "date": datetime(2026, 8, 1)}]

    result = validate_index_html(index_html, articles, str(articles_dir))
    assert not result.is_valid
    assert any("Duplicate article link" in e for e in result.errors)


def test_validate_index_html_empty_content() -> None:
    """IV-06: 空コンテンツは即時エラー"""
    result = validate_index_html("", [], "")
    assert not result.is_valid
    assert any("empty" in e for e in result.errors)

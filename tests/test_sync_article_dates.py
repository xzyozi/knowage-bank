import os
import sys
import importlib.util
from datetime import datetime
import pytest

# ファイル全体のテストを結合テスト（integration）としてマーク
pytestmark = pytest.mark.integration

# ハイフンを含むスクリプトファイル 'sync-article-dates.py' を動的インポート
script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "scripts", "sync-article-dates.py"))
spec = importlib.util.spec_from_file_location("sync_article_dates", script_path)
sync_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_module)

def test_parse_html_metadata(tmp_path):
    """HTMLからタイトル、リード文、eyebrow、メタデータが正しく抽出できるかのテスト"""
    test_html = """<!doctype html>
<html lang="ja">
<head>
    <title>テスト記事 | 技術質問ノート</title>
</head>
<body>
    <header class="hero">
        <p class="eyebrow">開発 > バックエンド</p>
        <h1>テスト質問タイトル？</h1>
        <p class="lead">テスト用のリード文（概要説明）です。</p>
    </header>
    <span class="meta">追加メタテキスト</span>
</body>
</html>
"""
    file_path = tmp_path / "test-article.html"
    file_path.write_text(test_html, encoding="utf-8")

    meta = sync_module.parse_html_metadata(str(file_path))
    assert meta["title"] == "テスト質問タイトル？"
    assert meta["description"] == "テスト用のリード文（概要説明）です。"
    assert meta["eyebrow"] == "開発 > バックエンド"
    assert meta["meta_text"] == "追加メタテキスト"

def test_update_article_date(tmp_path):
    """HTML内の日付が新しい日付に書き換わるかのテスト"""
    test_html = """<!doctype html>
<html>
<body>
    <header class="hero">
        <p class="article-created"><time datetime="2020-01-01">作成日: 2020年1月1日</time></p>
    </header>
</body>
</html>
"""
    file_path = tmp_path / "date-test.html"
    file_path.write_text(test_html, encoding="utf-8")

    test_date = datetime(2026, 6, 14)
    sync_module.update_article_date(str(file_path), test_date)

    updated_content = file_path.read_text(encoding="utf-8")
    assert 'datetime="2026-06-14"' in updated_content
    assert '作成日: 2026年6月14日' in updated_content

def test_get_creation_date_fallback(tmp_path):
    """Git履歴のないファイルの場合、ファイルの更新日が取得されるかのテスト"""
    file_path = tmp_path / "new-file.html"
    file_path.write_text("content", encoding="utf-8")

    date = sync_module.get_creation_date(str(file_path))
    assert date is not None
    assert isinstance(date, datetime)

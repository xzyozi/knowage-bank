from typing import Any
import os
import sys
import importlib.util
from datetime import datetime
from unittest.mock import patch
import pytest

from app.utils.index_validator import IndexSyncError

# ファイル全体のテストを結合テスト（integration）としてマーク
pytestmark = pytest.mark.integration

# ハイフンを含むスクリプトファイル 'sync-article-dates.py' を動的インポート
script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "scripts", "sync-article-dates.py"))
spec = importlib.util.spec_from_file_location("sync_article_dates", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError("sync-article-dates.py ????????")
sync_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_module)


def test_parse_html_metadata(tmp_path: Any) -> None:
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


def test_update_article_date(tmp_path: Any) -> None:
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
    assert "作成日: 2026年6月14日" in updated_content


def test_get_creation_date_fallback(tmp_path: Any) -> None:
    """Git履歴のないファイルの場合、ファイルの更新日が取得されるかのテスト"""
    file_path = tmp_path / "new-file.html"
    file_path.write_text("content", encoding="utf-8")

    date = sync_module.get_creation_date(str(file_path))
    assert date is not None
    assert isinstance(date, datetime)


def test_save_index_with_verification_success(tmp_path: Any) -> None:
    """SIV-01: 正常系。原子的に保存され、.tmpが残らないこと"""
    index_path = str(tmp_path / "index.html")
    articles_dir = str(tmp_path / "articles")
    os.makedirs(articles_dir, exist_ok=True)
    with open(os.path.join(articles_dir, "issue-1.html"), "w", encoding="utf-8") as f:
        f.write("<html></html>")

    original_content = "<html>old</html>"
    new_content = """<html>
<a class="article-card" href="articles/issue-1.html">
<time datetime="2026-08-01"></time>
<h4>Test</h4>
</a>
</html>"""

    articles = [{"filename": "issue-1.html", "title": "Test", "date": datetime(2026, 8, 1)}]

    sync_module._save_index_with_verification(index_path, new_content, original_content, articles, articles_dir)

    with open(index_path, "r", encoding="utf-8") as f:
        saved = f.read()
    assert saved == new_content
    assert not os.path.exists(f"{index_path}.tmp")


def test_save_index_with_verification_restores_on_validation_failure(tmp_path: Any) -> None:
    """SIV-02: 保存後検証が失敗した場合、元のindex内容へ復元されること"""
    index_path = str(tmp_path / "index.html")
    articles_dir = str(tmp_path / "articles")
    os.makedirs(articles_dir, exist_ok=True)
    # issue-1.html を作成しない -> 検証エラーになる

    original_content = "<html>old</html>"
    new_content = """<html>
<a class="article-card" href="articles/issue-1.html">
<time datetime="2026-08-01"></time>
<h4>Test</h4>
</a>
</html>"""

    articles = [{"filename": "issue-1.html", "title": "Test", "date": datetime(2026, 8, 1)}]

    with pytest.raises(IndexSyncError):
        sync_module._save_index_with_verification(index_path, new_content, original_content, articles, articles_dir)

    with open(index_path, "r", encoding="utf-8") as f:
        restored = f.read()
    assert restored == original_content
    assert not os.path.exists(f"{index_path}.tmp")


def test_save_index_with_verification_atomic_write_failure(tmp_path: Any) -> None:
    """SIV-03: 原子的書込み自体が失敗した場合、既存indexが変更されないこと"""
    index_path = str(tmp_path / "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("<html>old</html>")

    with patch("sync_article_dates.atomic_write_text", side_effect=OSError("disk full")):
        with pytest.raises(IndexSyncError):
            sync_module._save_index_with_verification(index_path, "<html>new</html>", "<html>old</html>", [], str(tmp_path))

    with open(index_path, "r", encoding="utf-8") as f:
        assert f.read() == "<html>old</html>"


def test_save_index_with_verification_restore_failure_raises(tmp_path: Any) -> None:
    """SIV-04: 検証失敗後の復元自体も失敗した場合、IndexSyncErrorが送出されること"""
    index_path = str(tmp_path / "index.html")
    articles_dir = str(tmp_path / "articles")
    os.makedirs(articles_dir, exist_ok=True)
    # issue-1.html を作成しない -> 検証エラーになる

    original_content = "<html>old</html>"
    new_content = """<html>
<a class="article-card" href="articles/issue-1.html">
<time datetime="2026-08-01"></time>
<h4>Test</h4>
</a>
</html>"""

    articles = [{"filename": "issue-1.html", "title": "Test", "date": datetime(2026, 8, 1)}]

    call_count = {"n": 0}
    real_atomic_write_text = sync_module.atomic_write_text

    def side_effect(path: str, content: str) -> None:
        call_count["n"] += 1
        if call_count["n"] == 1:
            # 最初の呼び出し（新しい内容の保存）は成功させる
            real_atomic_write_text(path, content)
        else:
            # 復元時の呼び出しを失敗させる
            raise OSError("restore failed")

    with patch("sync_article_dates.atomic_write_text", side_effect=side_effect):
        with pytest.raises(IndexSyncError, match="restoring the previous"):
            sync_module._save_index_with_verification(index_path, new_content, original_content, articles, articles_dir)


def test_main_returns_false_when_index_missing(tmp_path: Any, monkeypatch: Any) -> None:
    """SIV-05: public/index.html が存在しない場合、mainはFalseを返すこと"""
    articles_dir = tmp_path / "public" / "articles"
    articles_dir.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    result = sync_module.main()
    assert result is False

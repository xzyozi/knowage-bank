"""ブラウザ履歴 DAO の単体テスト。"""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pytest

from personal_knowledge.dao.chromium_dao import ChromiumHistoryDAO
from personal_knowledge.dao.firefox_dao import FirefoxHistoryDAO


@pytest.fixture
def temp_chromium_db(tmp_path: Path) -> Path:
    """Chromium 形式のモック SQLite DB を生成するフィクスチャ。"""
    db_file = tmp_path / "History"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE urls (
            id INTEGER PRIMARY KEY,
            url TEXT,
            title TEXT,
            visit_count INTEGER,
            typed_count INTEGER,
            last_visit_time INTEGER,
            hidden INTEGER
        )
    """)

    # 2026-08-23 10:00:00 UTC の WebKit タイムスタンプ
    # 2026-08-23 10:00:00 UTC = 1787479200 unix epoch
    # webkit timestamp = (1787479200 + 11644473600) * 1_000_000 = 13431952800000000
    webkit_time1 = (1787479200 + 11644473600) * 1_000_000
    webkit_time2 = (1787479300 + 11644473600) * 1_000_000

    cursor.execute(
        "INSERT INTO urls (url, title, last_visit_time) VALUES (?, ?, ?)",
        ("https://www.google.com/search?q=Python+asyncio+task", "Google 検索", webkit_time1),
    )
    cursor.execute(
        "INSERT INTO urls (url, title, last_visit_time) VALUES (?, ?, ?)",
        ("https://www.bing.com/search?q=Rust+ownership+model", "Bing", webkit_time2),
    )
    cursor.execute(
        "INSERT INTO urls (url, title, last_visit_time) VALUES (?, ?, ?)",
        ("https://example.com/not-search", "Example", webkit_time1),
    )
    conn.commit()
    conn.close()
    return db_file


@pytest.fixture
def temp_firefox_db(tmp_path: Path) -> Path:
    """Firefox 形式のモック places.sqlite DB を生成するフィクスチャ。"""
    db_file = tmp_path / "places.sqlite"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE moz_places (
            id INTEGER PRIMARY KEY,
            url TEXT,
            title TEXT,
            last_visit_date INTEGER
        )
    """)

    # 2026-08-23 10:05:00 UTC の PRTime (unix epoch * 1_000_000)
    prtime1 = 1787479500 * 1_000_000
    cursor.execute(
        "INSERT INTO moz_places (url, title, last_visit_date) VALUES (?, ?, ?)",
        ("https://duckduckgo.com/?q=FastAPI+dependency+injection", "DuckDuckGo", prtime1),
    )
    conn.commit()
    conn.close()
    return db_file


def test_chromium_dao_fetch_success(temp_chromium_db: Path) -> None:
    """ChromiumHistoryDAO が正常に検索クエリと WebKit タイムスタンプを抽出できること。"""
    dao = ChromiumHistoryDAO(browser_type="chrome", history_path=temp_chromium_db)
    entries = dao.fetch_search_entries()

    assert len(entries) == 2
    keywords = [e.keyword for e in entries]
    assert "Rust ownership model" in keywords
    assert "Python asyncio task" in keywords
    assert entries[0].source_browser == "chrome"
    assert isinstance(entries[0].timestamp, datetime)
    assert entries[0].timestamp.tzinfo == timezone.utc


def test_firefox_dao_fetch_success(temp_firefox_db: Path) -> None:
    """FirefoxHistoryDAO が正常に検索クエリと PRTime を抽出できること。"""
    dao = FirefoxHistoryDAO(history_path=temp_firefox_db)
    entries = dao.fetch_search_entries()

    assert len(entries) == 1
    assert entries[0].keyword == "FastAPI dependency injection"
    assert entries[0].source_browser == "firefox"
    assert isinstance(entries[0].timestamp, datetime)


def test_dao_silent_skip_on_missing_file(tmp_path: Path) -> None:
    """存在しないファイルパスが指定された場合、例外を送出せず空リストを返すこと (サイレント動作)。"""
    missing_path = tmp_path / "non_existent.sqlite"
    dao = ChromiumHistoryDAO(browser_type="edge", history_path=missing_path)
    entries = dao.fetch_search_entries()
    assert entries == []

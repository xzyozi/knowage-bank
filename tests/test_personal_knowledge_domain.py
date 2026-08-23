"""Domain 層 (重複排除・セッション解析) の単体テスト。"""

from datetime import datetime, timezone

from personal_knowledge.domain.analyzer import SessionAnalyzer
from personal_knowledge.domain.deduplicator import SessionDeduplicator
from personal_knowledge.domain.models import SearchEntry


def test_deduplicator_merges_same_keyword_within_5_minutes() -> None:
    """5分以内の同一キーワード（大文字小文字・空白無視）がマージされ、ブラウザ名が統合されること。"""
    deduplicator = SessionDeduplicator(time_window_seconds=300)

    entries = [
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc),
            keyword="Python asyncio",
            source_browser="chrome",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 2, 0, tzinfo=timezone.utc),
            keyword="python  asyncio ",  # 大文字小文字・空白違い
            source_browser="edge",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 10, 0, tzinfo=timezone.utc),
            keyword="Python asyncio",  # 8分後 (5分超) なので別扱い
            source_browser="firefox",
        ),
    ]

    deduped = deduplicator.deduplicate(entries)

    assert len(deduped) == 2
    # 最初のマージエントリ
    assert deduped[0].keyword == "Python asyncio"
    assert "chrome" in deduped[0].source_browser
    assert "edge" in deduped[0].source_browser
    assert deduped[0].timestamp == datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc)

    # 2つ目のエントリ
    assert deduped[1].keyword == "Python asyncio"
    assert deduped[1].source_browser == "firefox"
    assert deduped[1].timestamp == datetime(2026, 8, 23, 10, 10, 0, tzinfo=timezone.utc)


def test_analyzer_groups_30_minutes_and_discards_single_queries() -> None:
    """30分以内の連続検索がセッション化され、1件のみの単発検索が破棄されること。"""
    analyzer = SessionAnalyzer(session_gap_seconds=1800, min_queries=2)

    entries = [
        # セッション 1 (3件の連続検索)
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc),
            keyword="React useEffect clean up",
            source_browser="chrome",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 15, 0, tzinfo=timezone.utc),
            keyword="React AbortController",
            source_browser="chrome",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 30, 0, tzinfo=timezone.utc),
            keyword="React 19 useEffect changes",
            source_browser="edge",
        ),
        # 単発検索 (前と1時間離れており、1件のみ) -> 破棄されるべき
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc),
            keyword="Random weather",
            source_browser="firefox",
        ),
        # セッション 2 (2件の連続検索)
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 14, 0, 0, tzinfo=timezone.utc),
            keyword="Docker compose volume",
            source_browser="chrome",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 14, 20, 0, tzinfo=timezone.utc),
            keyword="Docker bind mount permissions",
            source_browser="chrome",
        ),
    ]

    sessions = analyzer.analyze_sessions(entries)

    assert len(sessions) == 2

    # セッション 1 の検証
    s1 = sessions[0]
    assert len(s1.queries) == 3
    assert s1.queries[0] == "React useEffect clean up"
    assert s1.queries[2] == "React 19 useEffect changes"
    assert s1.start_time == datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc)
    assert s1.end_time == datetime(2026, 8, 23, 10, 30, 0, tzinfo=timezone.utc)
    assert "chrome" in s1.source_browsers
    assert "edge" in s1.source_browsers

    # セッション 2 の検証
    s2 = sessions[1]
    assert len(s2.queries) == 2
    assert s2.queries[0] == "Docker compose volume"
    assert s2.queries[1] == "Docker bind mount permissions"

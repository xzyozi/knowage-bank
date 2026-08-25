"""PersonalKnowledgeService への IntentFilter / SemanticClusterer 統合テスト。"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from personal_knowledge.dao.base_dao import BrowserHistoryDAO
from personal_knowledge.domain.intent_filter import IntentFilter
from personal_knowledge.domain.models import SearchEntry, SearchSession
from personal_knowledge.domain.semantic_clusterer import SemanticClusterer
from personal_knowledge.integration.local_file_client import LocalFileIssueClient
from personal_knowledge.service import PersonalKnowledgeService


class _MockDAO(BrowserHistoryDAO):
    def __init__(self, entries: list[SearchEntry]) -> None:
        super().__init__()
        self._entries = entries

    @property
    def default_history_path(self) -> Path:
        return Path("/mock/path")

    @property
    def browser_name(self) -> str:
        return "chrome"

    def fetch_search_entries(self, limit: int = 500) -> list[SearchEntry]:
        return self._entries

    def _extract_from_sqlite(self, db_path: Path, limit: int) -> list[SearchEntry]:
        return self._entries


def test_intent_filter_none_uses_rule_based_only_by_default() -> None:
    """intent_filter/semantic_clusterer 未指定時は既存のルールベース動作のみで処理されること。"""
    entries = [
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc),
            keyword="pytest fixture scope",
            source_browser="chrome",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 5, 0, tzinfo=timezone.utc),
            keyword="pytest monkeypatch env vars",
            source_browser="chrome",
        ),
    ]
    service = PersonalKnowledgeService(
        daos=[_MockDAO(entries)],
        issue_client=LocalFileIssueClient(storage_path=""),
    )

    assert service.intent_filter is None
    assert service.semantic_clusterer is None

    deduped, sessions = service.process_entries_to_sessions(entries)
    assert len(deduped) == 2
    assert len(sessions) == 1


def test_intent_filter_excludes_non_knowledge_queries() -> None:
    """intent_filter を指定した場合、知識探求目的でないクエリが除外されること。"""
    entries = [
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc),
            keyword="Python asyncio タスクキャンセル",
            source_browser="chrome",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 5, 0, tzinfo=timezone.utc),
            keyword="今日の天気",
            source_browser="chrome",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 10, 0, tzinfo=timezone.utc),
            keyword="asyncio CancelledError ハンドリング",
            source_browser="chrome",
        ),
    ]

    mock_filter = MagicMock(spec=IntentFilter)
    mock_filter.is_knowledge_query.side_effect = lambda kw: "天気" not in kw

    service = PersonalKnowledgeService(
        daos=[_MockDAO(entries)],
        issue_client=LocalFileIssueClient(storage_path=""),
        intent_filter=mock_filter,
    )

    _, sessions = service.process_entries_to_sessions(entries)

    assert len(sessions) == 1
    assert sessions[0].queries == ["Python asyncio タスクキャンセル", "asyncio CancelledError ハンドリング"]


def test_semantic_clusterer_is_used_when_provided() -> None:
    """semantic_clusterer を指定した場合、ルールベースの analyzer ではなくクラスタリング結果が使われること。"""
    entries = [
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc),
            keyword="query A",
            source_browser="chrome",
        ),
    ]

    mock_session = SearchSession(
        start_time=datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc),
        queries=["query A"],
        source_browsers=["chrome"],
    )
    mock_clusterer = MagicMock(spec=SemanticClusterer)
    mock_clusterer.process_entries.return_value = [mock_session]

    service = PersonalKnowledgeService(
        daos=[_MockDAO(entries)],
        issue_client=LocalFileIssueClient(storage_path=""),
        semantic_clusterer=mock_clusterer,
    )

    _, sessions = service.process_entries_to_sessions(entries)

    assert sessions == [mock_session]
    mock_clusterer.process_entries.assert_called_once()

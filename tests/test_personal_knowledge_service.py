"""PersonalKnowledgeService の統合テスト。"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from personal_knowledge.dao.base_dao import BrowserHistoryDAO
from personal_knowledge.domain.models import SearchEntry
from personal_knowledge.integration.github_client import GitHubIssueClient
from personal_knowledge.integration.local_file_client import LocalFileIssueClient
from personal_knowledge.service import PersonalKnowledgeService


class MockDAO(BrowserHistoryDAO):
    """テスト用モック DAO。"""

    def __init__(self, browser: str, entries: list[SearchEntry]) -> None:
        super().__init__()
        self._browser = browser
        self._entries = entries

    @property
    def default_history_path(self) -> Path:
        return Path("/mock/path")

    @property
    def browser_name(self) -> str:
        return self._browser

    def fetch_search_entries(self, limit: int = 500) -> list[SearchEntry]:
        return self._entries

    def _extract_from_sqlite(self, db_path: Path, limit: int) -> list[SearchEntry]:
        return self._entries


def test_personal_knowledge_service_pipeline_end_to_end() -> None:
    """複数ブラウザの履歴収集から重複排除、セッション抽出、Issue起票・コメント追記までパイプラインが正しく自律動作すること。"""
    chrome_entries = [
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc),
            keyword="LangChain prompt template",
            source_browser="chrome",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 10, 0, tzinfo=timezone.utc),
            keyword="LangChain output parser",
            source_browser="chrome",
        ),
    ]

    edge_entries = [
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 1, 0, tzinfo=timezone.utc),
            keyword="langchain  prompt template ",
            source_browser="edge",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 13, 0, 0, tzinfo=timezone.utc),
            keyword="FastAPI BackgroundTasks",
            source_browser="edge",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 13, 15, 0, tzinfo=timezone.utc),
            keyword="FastAPI Celery async worker",
            source_browser="edge",
        ),
    ]

    firefox_entries = [
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 15, 0, 0, tzinfo=timezone.utc),
            keyword="Isolated single query",
            source_browser="firefox",
        )
    ]

    mock_daos: list[BrowserHistoryDAO] = [
        MockDAO("chrome", chrome_entries),
        MockDAO("edge", edge_entries),
        MockDAO("firefox", firefox_entries),
    ]

    mock_github = MagicMock(spec=GitHubIssueClient)
    mock_github.is_configured = True
    mock_github.create_issue.return_value = 101
    mock_github.add_comment.return_value = True

    existing_open_issues: list[dict[str, Any]] = [
        {
            "number": 50,
            "title": "[自動抽出] FastAPI routing 関連の調査",
            "body": "FastAPI 非同期ワーカーと BackgroundTasks の実装...",
            "comments": [],
        }
    ]

    service = PersonalKnowledgeService(
        daos=mock_daos,
        github_client=mock_github,
    )

    result = service.run_pipeline(dry_run=False, mock_open_issues=existing_open_issues)

    assert result.raw_entries_count == 6
    assert result.deduped_entries_count == 5
    assert result.sessions_count == 2
    assert result.created_issues_count == 1
    assert result.added_comments_count == 1

    mock_github.create_issue.assert_called_once()
    mock_github.add_comment.assert_called_once_with(50, result.decisions[1].body)


def test_personal_knowledge_service_with_local_file_client() -> None:
    """LocalFileIssueClient を使用したパイプライン実行テスト。"""
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
    mock_daos: list[BrowserHistoryDAO] = [MockDAO("chrome", entries)]

    local_client = LocalFileIssueClient(storage_path="")
    service = PersonalKnowledgeService(daos=mock_daos, issue_client=local_client)

    result = service.run_pipeline(dry_run=False)

    assert result.sessions_count == 1
    assert result.created_issues_count == 1
    assert len(local_client.get_open_issues()) == 1
    assert "pytest fixture scope" in local_client.get_open_issues()[0]["body"]

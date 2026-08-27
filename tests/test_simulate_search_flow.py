"""simulate-search-flow スクリプトの動作確認用ユニットテスト。"""

import os
import sys

# src/ をモジュール検索パスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from scripts.simulate_search_flow import (
    MockHistoryDAO,
    create_sample_open_issues,
    create_sample_search_history,
    run_simulation,
)
from personal_knowledge.integration.local_file_client import LocalFileIssueClient
from personal_knowledge.service import PersonalKnowledgeService


def test_create_sample_search_history() -> None:
    """サンプル検索履歴が正しく生成されることの検証。"""
    entries = create_sample_search_history()
    assert len(entries) == 8
    keywords = [e.keyword for e in entries]
    assert "python dataclass 使い方" in keywords
    assert "fastapi async def sync def 違い" in keywords


def test_simulate_search_flow_pipeline() -> None:
    """シミュレーション用パイプラインが dry_run モードで安全に動作することの検証。"""
    mock_entries = create_sample_search_history()
    mock_issues = create_sample_open_issues()

    mock_dao = MockHistoryDAO(mock_entries)
    service = PersonalKnowledgeService(
        daos=[mock_dao],
        issue_client=LocalFileIssueClient(),
    )

    result = service.run_pipeline(dry_run=True, mock_open_issues=mock_issues)

    assert result.raw_entries_count == 8
    assert result.deduped_entries_count == 7  # 1件重複排除
    assert result.sessions_count == 2  # 2セッション抽出 (単発天気ログは最小2件を満たさず除外)
    assert len(result.decisions) == 2
    # dry_run なので実際のカウントは 0
    assert result.created_issues_count == 0
    assert result.added_comments_count == 0


def test_run_simulation_execution(caplog) -> None:
    """run_simulation 関数がエラーなく完了することの検証。"""
    run_simulation()

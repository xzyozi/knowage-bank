from typing import Any
import importlib.util
import os
import sys
import pytest
import json
import subprocess
from unittest.mock import patch, MagicMock

# scripts/sync-github-issues.py を動的インポート
script_dir = os.path.join(os.path.dirname(__file__), "..", "src", "scripts")
sync_script_path = os.path.join(script_dir, "sync-github-issues.py")
spec = importlib.util.spec_from_file_location("sync_github_issues", sync_script_path)
if spec is None or spec.loader is None:
    raise RuntimeError("sync-github-issues.py ????????")
sync_github_issues = importlib.util.module_from_spec(spec)
sys.modules["sync_github_issues"] = sync_github_issues
spec.loader.exec_module(sync_github_issues)

sanitize_filename = sync_github_issues.sanitize_filename
process_single_issue = sync_github_issues.process_single_issue


def test_sanitize_filename() -> None:
    # MA-FN-01: 正常系：英数字
    assert sanitize_filename("Fix API Bug", 10) == "issue-10-fix-api-bug.html"

    # MA-FN-02: 正常系：記号含む
    assert sanitize_filename("Error: 500 (Server)!", 11) == "issue-11-error-500-server.html"

    # MA-FN-03: 正常系：長すぎる
    result = sanitize_filename("Very long title string exceeding limits", 12)
    assert len(result) <= 50  # プレフィックスと拡張子含めて一定長以内に収まること
    assert result.startswith("issue-12-very-long-title-string-exceedi")

    # MA-FN-04: フォールバック：日本語のみ
    assert sanitize_filename("テスト項目作成", 13) == "issue-13.html"

    # MA-FN-05: フォールバック：短すぎる
    assert sanitize_filename("a", 14) == "issue-14.html"


def setup_mcp_mock(mock_sse: Any, mock_session: Any) -> None:
    session_instance = MagicMock()

    async def mock_initialize():
        return None

    session_instance.initialize = mock_initialize

    mock_result = MagicMock()
    mock_content = MagicMock()
    mock_content.text = "Deep Research Mock Results"
    mock_result.content = [mock_content]

    async def mock_call_tool(*args, **kwargs):
        return mock_result

    session_instance.call_tool = mock_call_tool

    class AsyncCM:
        async def __aenter__(self):
            return session_instance

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_session.return_value = AsyncCM()

    class SseCM:
        async def __aenter__(self):
            return (None, None)

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_sse.return_value = SseCM()


@patch("sync_github_issues.sse_client")
@patch("sync_github_issues.ClientSession")
@patch("sync_github_issues.git_commit")
@patch("sync_github_issues.ChatModel")
@patch("sync_github_issues.ArticleBuilder")
@patch("sync_github_issues.sync_article_dates")
@pytest.mark.asyncio
async def test_process_single_issue_success_markdown_json(
    mock_sync: Any,
    mock_builder_class: Any,
    mock_model_class: Any,
    mock_git_commit: Any,
    mock_session: Any,
    mock_sse: Any,
) -> None:
    """MA-PR-01: LLMがマークダウンブロックで囲まれたJSONを返す正常系"""
    setup_mcp_mock(mock_sse, mock_session)
    mock_git_commit.return_value = True
    mock_manager = MagicMock()

    mock_model = MagicMock()
    mock_model_class.return_value = mock_model

    # LLM応答: 1回目はクエリ、2回目はマークダウンJSON
    mock_query_res = MagicMock(content="Test Query")
    mock_json_str = '{"title": "Test Title", "eyebrow": "AI > 開発ワークフロー", "lead": "test lead", "qa": [], "sections": [], "key_points": [], "references": []}'
    mock_article_res = MagicMock(content=f"```json\n{mock_json_str}\n```")
    mock_model.generate_response.side_effect = [mock_query_res, mock_article_res]

    mock_builder = MagicMock()
    mock_builder_class.return_value = mock_builder

    # テスト対象Issue
    issue = {"number": 99, "title": "Test Issue Title", "body": "Issue Body"}

    # 実行
    res = await process_single_issue(issue, mock_manager, git_commit_flag=True, git_push=True)

    assert res is True
    mock_manager.update_issue_status.assert_any_call(99, "processing")
    mock_manager.update_issue_status.assert_any_call(99, "processed", article_file="issue-99-test-issue-title.html")
    mock_builder.save_article.assert_called_once()
    mock_sync.main.assert_called_once()


@patch("sync_github_issues.sse_client")
@patch("sync_github_issues.ClientSession")
@patch("sync_github_issues.git_commit")
@patch("sync_github_issues.ChatModel")
@patch("sync_github_issues.ArticleBuilder")
@patch("sync_github_issues.sync_article_dates")
@pytest.mark.asyncio
async def test_process_single_issue_success_raw_json(
    mock_sync: Any,
    mock_builder_class: Any,
    mock_model_class: Any,
    mock_git_commit: Any,
    mock_session: Any,
    mock_sse: Any,
) -> None:
    """MA-PR-02: LLMが直接生JSONを返す正常系"""
    setup_mcp_mock(mock_sse, mock_session)
    mock_git_commit.return_value = True
    mock_manager = MagicMock()

    mock_model = MagicMock()
    mock_model_class.return_value = mock_model

    # LLM応答: 1回目はクエリ、2回目は生JSON
    mock_query_res = MagicMock(content="Test Query")
    mock_json_str = '{"title": "Test Title", "eyebrow": "AI > 開発ワークフロー", "lead": "test lead", "qa": [], "sections": [], "key_points": [], "references": []}'
    mock_article_res = MagicMock(content=mock_json_str)
    mock_model.generate_response.side_effect = [mock_query_res, mock_article_res]

    mock_builder = MagicMock()
    mock_builder_class.return_value = mock_builder

    issue = {"number": 99, "title": "Test Issue Title", "body": "Issue Body"}

    res = await process_single_issue(issue, mock_manager, git_commit_flag=True, git_push=True)

    assert res is True
    mock_manager.update_issue_status.assert_any_call(99, "processed", article_file="issue-99-test-issue-title.html")


@patch("sync_github_issues.sse_client")
@patch("sync_github_issues.ClientSession")
@patch("sync_github_issues.ChatModel")
@pytest.mark.asyncio
async def test_process_single_issue_empty_llm_response(mock_model_class: Any, mock_session: Any, mock_sse: Any) -> None:
    """MA-PR-03: LLMのレスポンスが空の場合に失敗(failed)ステータスになる異常系"""
    setup_mcp_mock(mock_sse, mock_session)
    mock_manager = MagicMock()

    mock_model = MagicMock()
    mock_model_class.return_value = mock_model

    # 2回目の生成結果が空
    mock_query_res = MagicMock(content="Test Query")
    mock_article_res = MagicMock(content="")
    mock_model.generate_response.side_effect = [mock_query_res, mock_article_res]

    issue = {"number": 99, "title": "Test Issue Title", "body": "Issue Body"}

    res = await process_single_issue(issue, mock_manager)

    assert res is False
    mock_manager.update_issue_status.assert_any_call(99, "failed")


@patch("sync_github_issues.sse_client")
@patch("sync_github_issues.ClientSession")
@patch("sync_github_issues.ChatModel")
@pytest.mark.asyncio
async def test_process_single_issue_invalid_json(mock_model_class: Any, mock_session: Any, mock_sse: Any) -> None:
    """MA-PR-04: LLMが不正なJSONを返した場合に失敗(failed)ステータスになる異常系"""
    setup_mcp_mock(mock_sse, mock_session)
    mock_manager = MagicMock()

    mock_model = MagicMock()
    mock_model_class.return_value = mock_model

    # 2回目の生成結果が不正JSON
    mock_query_res = MagicMock(content="Test Query")
    mock_article_res = MagicMock(content="{this is not a valid json}")
    mock_model.generate_response.side_effect = [mock_query_res, mock_article_res]

    issue = {"number": 99, "title": "Test Issue Title", "body": "Issue Body"}

    res = await process_single_issue(issue, mock_manager)

    assert res is False
    mock_manager.update_issue_status.assert_any_call(99, "failed")


@patch("sync_github_issues.sse_client")
@patch("sync_github_issues.ClientSession")
@patch("sync_github_issues.git_commit")
@patch("sync_github_issues.ChatModel")
@patch("sync_github_issues.ArticleBuilder")
@patch("sync_github_issues.sync_article_dates")
@pytest.mark.asyncio
async def test_process_single_issue_no_push(
    mock_sync: Any,
    mock_builder_class: Any,
    mock_model_class: Any,
    mock_git_commit: Any,
    mock_session: Any,
    mock_sse: Any,
) -> None:
    """git_commit_flag=False, git_push=False のときに git_commit が呼び出されないことを検証"""
    setup_mcp_mock(mock_sse, mock_session)
    mock_manager = MagicMock()

    mock_model = MagicMock()
    mock_model_class.return_value = mock_model

    mock_query_res = MagicMock(content="Test Query")
    mock_json_str = '{"title": "Test Title", "eyebrow": "AI > 開発ワークフロー", "lead": "test lead", "qa": [], "sections": [], "key_points": [], "references": []}'
    mock_article_res = MagicMock(content=mock_json_str)
    mock_model.generate_response.side_effect = [mock_query_res, mock_article_res]

    mock_builder = MagicMock()
    mock_builder_class.return_value = mock_builder

    issue = {"number": 99, "title": "Test Issue Title", "body": "Issue Body"}

    res = await process_single_issue(issue, mock_manager, git_commit_flag=False, git_push=False)

    assert res is True
    # git_commit が呼び出されていないこと
    mock_git_commit.assert_not_called()
    mock_manager.update_issue_status.assert_any_call(99, "processed", article_file="issue-99-test-issue-title.html")


@patch("sync_github_issues.sse_client")
@patch("sync_github_issues.ClientSession")
@patch("sync_github_issues.git_commit")
@patch("sync_github_issues.ChatModel")
@patch("sync_github_issues.ArticleBuilder")
@patch("sync_github_issues.sync_article_dates")
@pytest.mark.asyncio
async def test_process_single_issue_commit_only(
    mock_sync: Any,
    mock_builder_class: Any,
    mock_model_class: Any,
    mock_git_commit: Any,
    mock_session: Any,
    mock_sse: Any,
) -> None:
    """git_commit_flag=True, git_push=False (コミットのみ) のときに git_commit(..., push=False) が呼び出されることを検証"""
    setup_mcp_mock(mock_sse, mock_session)
    mock_git_commit.return_value = True
    mock_manager = MagicMock()

    mock_model = MagicMock()
    mock_model_class.return_value = mock_model

    mock_query_res = MagicMock(content="Test Query")
    mock_json_str = '{"title": "Test Title", "eyebrow": "AI > 開発ワークフロー", "lead": "test lead", "qa": [], "sections": [], "key_points": [], "references": []}'
    mock_article_res = MagicMock(content=mock_json_str)
    mock_model.generate_response.side_effect = [mock_query_res, mock_article_res]

    mock_builder = MagicMock()
    mock_builder_class.return_value = mock_builder

    issue = {"number": 99, "title": "Test Issue Title", "body": "Issue Body"}

    res = await process_single_issue(issue, mock_manager, git_commit_flag=True, git_push=False)

    assert res is True
    # git_commit が push=False で呼び出されていること
    mock_git_commit.assert_called_once_with("issue-99-test-issue-title.html", 99, "Test Issue Title", push=False)


@patch("sync_github_issues.subprocess.run")
def test_git_commit_success_no_push(mock_run: Any) -> None:
    """git_commit: コマンド成功かつプッシュなしのテスト"""
    mock_branch_res = MagicMock()
    mock_branch_res.stdout = "test/issue-sync\n"

    mock_diff_res = MagicMock()
    mock_diff_res.return_value = MagicMock(returncode=1)

    # git pushなしのコマンド呼び出し
    mock_run.side_effect = [mock_branch_res, MagicMock(), mock_diff_res.return_value, MagicMock()]

    res = sync_github_issues.git_commit("issue-99.html", 99, "Test Title", push=False)
    assert res is True

    # 呼び出し引数のアサート (git pushが含まれていないこと)
    mock_run.assert_any_call(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True)
    mock_run.assert_any_call(["git", "add", "public/articles/issue-99.html", "public/index.html"], check=True)
    mock_run.assert_any_call(["git", "diff", "--cached", "--quiet"])
    mock_run.assert_any_call(["git", "commit", "-m", "feat: Issue #99 からの自動記事追加: Test Title"], check=True)

    # git pushが呼び出されていないことを確認
    for call in mock_run.call_args_list:
        assert "push" not in call[0][0]


@patch("sync_github_issues.subprocess.run")
def test_git_commit_success_with_push(mock_run: Any) -> None:
    """git_commit: コマンド成功かつプッシュありのテスト"""
    mock_branch_res = MagicMock()
    mock_branch_res.stdout = "test/issue-sync\n"

    mock_diff_res = MagicMock()
    mock_diff_res.return_value = MagicMock(returncode=1)

    # git pushありのコマンド呼び出し
    mock_run.side_effect = [mock_branch_res, MagicMock(), mock_diff_res.return_value, MagicMock(), MagicMock()]

    res = sync_github_issues.git_commit("issue-99.html", 99, "Test Title", push=True)
    assert res is True

    # 呼び出し引数のアサート (git pushが含まれていること)
    mock_run.assert_any_call(["git", "push", "origin", "test/issue-sync"], check=True)


@patch("sync_github_issues.subprocess.run")
def test_git_commit_no_changes(mock_run: Any) -> None:
    """git_commit: 変更がないためスキップするケース"""
    mock_branch_res = MagicMock()
    mock_branch_res.stdout = "test/issue-sync\n"

    mock_diff_res = MagicMock()
    mock_diff_res.return_value = MagicMock(returncode=0)

    mock_run.side_effect = [mock_branch_res, MagicMock(), mock_diff_res.return_value]

    res = sync_github_issues.git_commit("issue-99.html", 99, "Test Title")
    assert res is True


@patch("sync_github_issues.subprocess.run")
def test_git_commit_failure(mock_run: Any) -> None:
    """git_commit: コマンド失敗時のテスト"""
    mock_run.side_effect = subprocess.CalledProcessError(1, "git")

    res = sync_github_issues.git_commit("issue-99.html", 99, "Test Title")
    assert res is False

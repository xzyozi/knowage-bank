from typing import Any
import os
import json
import pytest
from unittest.mock import patch, MagicMock
from app.issue_manager import IssueManager


@pytest.fixture
def temp_db_path(tmp_path: Any) -> str:
    """テスト用の一時的なデータベースファイルパスを提供するフィクスチャ"""
    return os.path.join(tmp_path, "issue_status.json")


def test_init_db(temp_db_path: Any) -> None:
    """IM-DB-01: DBファイルが存在しない状態でインスタンス化されると、初期JSONが作成される"""
    assert not os.path.exists(temp_db_path)

    manager = IssueManager(db_path=temp_db_path)

    assert os.path.exists(temp_db_path)
    with open(temp_db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["last_sync_at"] is None
    assert data["issues"] == {}


def test_load_db_invalid_json(temp_db_path: Any) -> None:
    """IM-DB-02: 不正なJSONファイルが存在する場合、デフォルトの構造が返される"""
    db_dir = os.path.dirname(temp_db_path)
    os.makedirs(db_dir, exist_ok=True)
    with open(temp_db_path, "w", encoding="utf-8") as f:
        f.write("{invalid json}")

    manager = IssueManager(db_path=temp_db_path)
    db_data = manager._load_db()

    assert db_data["last_sync_at"] is None
    assert db_data["issues"] == {}


def test_get_next_unprocessed_issue(temp_db_path: Any) -> None:
    """IM-DB-03/04: unprocessedな最古のIssueを正しく選定し、未処理がない場合はNoneを返す"""
    manager = IssueManager(db_path=temp_db_path)

    # テスト用データの書き込み
    test_data = {
        "last_sync_at": None,
        "issues": {
            "20": {"number": 20, "title": "Newer Issue", "status": "unprocessed"},
            "10": {"number": 10, "title": "Older Issue", "status": "unprocessed"},
            "30": {"number": 30, "title": "Completed Issue", "status": "processed"},
        },
    }
    manager._save_db(test_data)

    # 複数存在する場合、最古（番号が最小）の10が返されること (IM-DB-03)
    next_issue = manager.get_next_unprocessed_issue()
    assert next_issue is not None
    assert next_issue["number"] == 10

    # 状態をすべて processed に更新
    manager.update_issue_status(10, "processed")
    manager.update_issue_status(20, "processed")

    # 未処理がない場合は None が返されること (IM-DB-04)
    assert manager.get_next_unprocessed_issue() is None


def test_update_issue_status(temp_db_path: Any) -> None:
    """IM-DB-05/06: ステータスの更新動作（正常系・異常系）"""
    manager = IssueManager(db_path=temp_db_path)
    test_data = {
        "last_sync_at": None,
        "issues": {
            "10": {
                "number": 10,
                "title": "Issue 10",
                "status": "unprocessed",
                "processed_at": None,
                "article_file": None,
            }
        },
    }
    manager._save_db(test_data)

    # 正常系：processedに更新 (IM-DB-05)
    manager.update_issue_status(
        10,
        "processed",
        article_file="issue-10.html",
        article_source_file="issue-10.md",
        index_synced=True,
        attempt_id="test-attempt-uuid",
    )
    db_data = manager._load_db()
    issue = db_data["issues"]["10"]
    assert issue["status"] == "processed"
    assert issue["processed_at"] is not None
    assert issue["article_file"] == "issue-10.html"
    assert issue["article_source_file"] == "issue-10.md"
    assert issue["index_synced"] is True
    assert issue["attempt_id"] == "test-attempt-uuid"
    assert issue["failed_at"] is None
    assert issue["failure_reason"] is None

    # 正常系：failedに更新と失敗理由の記録
    manager.update_issue_status(
        10,
        "failed",
        failure_reason="[Stage 3] ValidationFailed: Forbidden HTML tag",
        attempt_id="test-attempt-uuid-2",
    )
    db_data_failed = manager._load_db()
    issue_failed = db_data_failed["issues"]["10"]
    assert issue_failed["status"] == "failed"
    assert issue_failed["failed_at"] is not None
    assert issue_failed["failure_reason"] == "[Stage 3] ValidationFailed: Forbidden HTML tag"
    assert issue_failed["attempt_id"] == "test-attempt-uuid-2"

    # 異常系：存在しないIssueを指定 (IM-DB-06)
    manager.update_issue_status(999, "processed")
    db_data_after = manager._load_db()
    assert "999" not in db_data_after["issues"]


@patch("httpx.Client")
def test_sync_issues_initial(mock_client_class: Any, temp_db_path: Any) -> None:
    """IM-API-01/04: 初回同期の正常系。PRは除外されること"""
    manager = IssueManager(db_path=temp_db_path)
    manager.github_repo = "owner/repo"

    # httpx.Clientのモック設定
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client

    # APIモックレスポンス（PRを含む）
    mock_api_data = [
        {"number": 1, "title": "First Issue", "state": "open", "body": "Hello"},
        {"number": 2, "title": "Pull Request", "state": "open", "body": "PR", "pull_request": {}},
    ]
    mock_response = MagicMock()
    mock_response.json.return_value = mock_api_data
    mock_response.headers = {}
    mock_client.get.return_value = mock_response

    manager.sync_issues()

    # DBの検証
    db_data = manager._load_db()
    assert db_data["last_sync_at"] is not None
    assert "1" in db_data["issues"]
    assert "2" not in db_data["issues"]  # PRは除外されていること (IM-API-04)
    assert db_data["issues"]["1"]["title"] == "First Issue"


@patch("httpx.Client")
def test_sync_issues_since(mock_client_class: Any, temp_db_path: Any) -> None:
    """IM-API-02: 差分同期の正常系。sinceパラメータが渡されること"""
    manager = IssueManager(db_path=temp_db_path)
    manager.github_repo = "owner/repo"

    # 既存DBデータ（前回同期時刻あり）
    test_data = {
        "last_sync_at": "2026-06-15T12:00:00Z",
        "issues": {"1": {"number": 1, "title": "Old Title", "state": "open", "status": "unprocessed"}},
    }
    manager._save_db(test_data)

    # httpx.Clientのモック設定
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client

    # 差分更新用APIデータ
    mock_api_data = [{"number": 1, "title": "Updated Title", "state": "closed", "body": "Fixed"}]
    mock_response = MagicMock()
    mock_response.json.return_value = mock_api_data
    mock_response.headers = {}
    mock_client.get.return_value = mock_response

    manager.sync_issues()

    # GETリクエストの引数検証（sinceパラメータが渡されているか）
    called_args, called_kwargs = mock_client.get.call_args
    assert called_kwargs["params"]["since"] == "2026-06-15T12:00:00Z"

    # DBの更新検証 (IM-API-02)
    db_data = manager._load_db()
    assert db_data["issues"]["1"]["title"] == "Updated Title"
    assert db_data["issues"]["1"]["state"] == "closed"


@patch("httpx.Client")
def test_sync_issues_pagination(mock_client_class: Any, temp_db_path: Any) -> None:
    """IM-API-03: 複数ページにまたがるページネーション処理の正常系"""
    manager = IssueManager(db_path=temp_db_path)
    manager.github_repo = "owner/repo"

    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client

    # ページ1のレスポンス（Linkヘッダーにnext付き）
    resp1 = MagicMock()
    resp1.json.return_value = [{"number": 1, "title": "Issue 1", "state": "open"}]
    resp1.headers = {"Link": '<https://api.github.com/repositories/123/issues?page=2>; rel="next"'}

    # ページ2のレスポンス（Linkヘッダーなし）
    resp2 = MagicMock()
    resp2.json.return_value = [{"number": 2, "title": "Issue 2", "state": "open"}]
    resp2.headers = {}

    # 順にレスポンスを返すように設定
    mock_client.get.side_effect = [resp1, resp2]

    manager.sync_issues()

    # 両方のページのデータが保存されていること
    db_data = manager._load_db()
    assert "1" in db_data["issues"]
    assert "2" in db_data["issues"]
    assert mock_client.get.call_count == 2

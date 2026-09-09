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

    # 状態をすべて processing 経由で processed に更新
    manager.update_issue_status(10, "processing")
    manager.update_issue_status(10, "processed")
    manager.update_issue_status(20, "processing")
    manager.update_issue_status(20, "processed")

    # 未処理がない場合は None が返されること (IM-DB-04)
    assert manager.get_next_unprocessed_issue() is None


def test_normalizes_legacy_issue_records(temp_db_path: Any) -> None:
    """IM-DB-05: 旧形式・未知状態のレコードを現行スキーマへ正規化する。"""
    manager = IssueManager(db_path=temp_db_path)
    manager._save_db(
        {
            "issues": {
                "10": {"number": 10, "title": "Legacy", "status": "unknown"},
                "11": {"title": "Missing fields", "status": "unprocessed"},
            }
        }
    )

    db_data = manager._load_db()
    normalized_unknown = db_data["issues"]["10"]
    normalized_missing = db_data["issues"]["11"]

    assert db_data["last_sync_at"] is None
    assert normalized_unknown["status"] == "unprocessed"
    assert normalized_unknown["article_source_file"] is None
    assert normalized_unknown["index_synced"] is False
    assert normalized_unknown["failure_reason"] is None
    assert normalized_missing["number"] == 11
    assert normalized_missing["body"] == ""
    assert set(normalized_missing) == {
        "number",
        "title",
        "body",
        "state",
        "status",
        "processed_at",
        "article_file",
        "article_source_file",
        "index_synced",
        "attempt_id",
        "failed_at",
        "failure_reason",
    }

    persisted = json.loads(open(temp_db_path, encoding="utf-8").read())
    assert persisted == db_data


def test_update_issue_status_enforces_allowed_transitions(temp_db_path: Any) -> None:
    """IM-DB-06: 有効な遷移だけを保存し、終端状態からの再遷移を拒否する。"""
    manager = IssueManager(db_path=temp_db_path)
    manager._save_db(
        {
            "last_sync_at": None,
            "issues": {"10": {"number": 10, "title": "Issue 10", "status": "unprocessed"}},
        }
    )

    assert manager.update_issue_status(10, "processed") is False
    assert manager.update_issue_status(10, "unsupported") is False
    assert manager._load_db()["issues"]["10"]["status"] == "unprocessed"

    assert manager.update_issue_status(10, "processing", attempt_id="attempt-1") is True
    assert manager.update_issue_status(
        10,
        "processed",
        article_file="issue-10.html",
        article_source_file="issue-10.md",
        index_synced=True,
    ) is True
    processed = manager._load_db()["issues"]["10"]
    assert processed["processed_at"] is not None
    assert processed["index_synced"] is True
    assert processed["failed_at"] is None
    assert processed["failure_reason"] is None
    assert manager.update_issue_status(10, "failed", failure_reason="must not retry") is False
    assert manager._load_db()["issues"]["10"]["status"] == "processed"


def test_update_issue_status_records_failure_from_processing(temp_db_path: Any) -> None:
    """IM-DB-07: processingからfailedへの遷移では失敗情報を保持する。"""
    manager = IssueManager(db_path=temp_db_path)
    manager._save_db(
        {
            "last_sync_at": None,
            "issues": {"10": {"number": 10, "title": "Issue 10", "status": "unprocessed"}},
        }
    )

    assert manager.update_issue_status(10, "processing", attempt_id="attempt-2") is True
    assert manager.update_issue_status(10, "failed", failure_reason="validation failed") is True
    failed = manager._load_db()["issues"]["10"]
    assert failed["failed_at"] is not None
    assert failed["failure_reason"] == "validation failed"
    assert manager.update_issue_status(10, "processing") is False


def test_update_issue_status_missing_issue_is_ignored(temp_db_path: Any) -> None:
    """IM-DB-08: 存在しないIssueの状態は更新しない。"""
    manager = IssueManager(db_path=temp_db_path)

    assert manager.update_issue_status(999, "processing") is False
    assert "999" not in manager._load_db()["issues"]


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

"""LocalFileIssueClient の単体テスト。"""

from pathlib import Path
import tempfile

from personal_knowledge.integration.local_file_client import LocalFileIssueClient


def test_local_file_issue_client_in_memory() -> None:
    """インメモリ動作時に Issue 作成、取得、コメント追記が正しく動作すること。"""
    client = LocalFileIssueClient(storage_path="")
    assert client.is_configured is True
    assert len(client.get_open_issues()) == 0

    # Issue 作成
    num1 = client.create_issue("Python async", "asyncio description")
    assert num1 == 1

    open_issues = client.get_open_issues()
    assert len(open_issues) == 1
    assert open_issues[0]["title"] == "Python async"
    assert open_issues[0]["number"] == 1

    # コメント追記
    ok = client.add_comment(1, "Comment 1")
    assert ok is True

    open_issues_after = client.get_open_issues()
    assert len(open_issues_after[0]["comments"]) == 1
    assert open_issues_after[0]["comments"][0] == "Comment 1"

    # Issue クローズ
    closed_ok = client.close_issue(1)
    assert closed_ok is True
    assert len(client.get_open_issues()) == 0


def test_local_file_issue_client_persistence() -> None:
    """JSON ファイルへのデータ保存と再読み込みが正常に行われること。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = Path(tmpdir) / "test_issues.json"

        # 1. データの作成と保存
        client1 = LocalFileIssueClient(storage_path=json_path)
        num = client1.create_issue("Persistent Title", "Body text")
        assert num == 1
        client1.add_comment(1, "Persisted Comment")

        assert json_path.exists()

        # 2. 新しいクライアントインスタンスで読み込み検証
        client2 = LocalFileIssueClient(storage_path=json_path)
        issues = client2.get_open_issues()
        assert len(issues) == 1
        assert issues[0]["title"] == "Persistent Title"
        assert issues[0]["comments"] == ["Persisted Comment"]

        # 次の ID が 2 に更新されていること
        num2 = client2.create_issue("Second Issue", "Second body")
        assert num2 == 2

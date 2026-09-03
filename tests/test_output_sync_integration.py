"""Output同期の成果物と状態遷移を検証する統合テスト。"""

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from app.article_source_manager import save_article_source
from app.issue_manager import IssueManager

VALID_MARKDOWN = """---
title: Output Sync Test
eyebrow: AI > 開発ワークフロー
lead: 同期成功を確認する記事です。
---

## 概要
同期処理は原本、HTML、index、状態を更新します。
"""


def _install_mcp_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP未導入環境でも同期CLIをimportできる最小スタブを登録する。"""
    mcp_module = ModuleType("mcp")
    mcp_client_module = ModuleType("mcp.client")
    mcp_sse_module = ModuleType("mcp.client.sse")

    mcp_module.ClientSession = object
    mcp_sse_module.sse_client = lambda _: None

    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.client", mcp_client_module)
    monkeypatch.setitem(sys.modules, "mcp.client.sse", mcp_sse_module)


def _load_sync_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """ハイフンを含む同期CLIを、MCPスタブを用いて読み込む。"""
    _install_mcp_stub(monkeypatch)
    script_path = Path(__file__).parents[1] / "src" / "scripts" / "sync-github-issues.py"
    spec = importlib.util.spec_from_file_location("sync_github_issues_for_test", script_path)
    assert spec is not None and spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_unprocessed_issue(manager: IssueManager, issue: dict[str, Any]) -> None:
    """テスト対象Issueを実際の状態JSONへ登録する。"""
    database = manager._load_db()
    database["issues"][str(issue["number"])] = {
        "number": issue["number"],
        "title": issue["title"],
        "body": issue["body"],
        "state": "open",
        "status": "unprocessed",
        "processed_at": None,
        "article_file": None,
        "article_source_file": None,
        "index_synced": False,
        "attempt_id": None,
        "failed_at": None,
        "failure_reason": None,
    }
    manager._save_db(database)


@pytest.mark.integration
def test_process_single_issue_persists_outputs_and_marks_processed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有効なMarkdownで原本・HTML・index・processed状態をまとめて記録する。"""
    sync_module = _load_sync_module(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "public" / "articles").mkdir(parents=True)
    index_path = tmp_path / "public" / "index.html"
    index_path.write_text("before synchronization", encoding="utf-8", newline="\n")

    issue = {"number": 42, "title": "Output Sync Test", "body": "同期の検証"}
    manager = IssueManager(db_path=str(tmp_path / "issue_status.json"))
    _create_unprocessed_issue(manager, issue)
    source_dir = tmp_path / "article_sources"

    class FakeChatModel:
        def __init__(self) -> None:
            self.responses = iter(("output sync research", VALID_MARKDOWN))

        def generate_response(self, _: dict[str, Any]) -> SimpleNamespace:
            return SimpleNamespace(content=next(self.responses))

    def save_source(issue_number: int, markdown_text: str) -> str:
        return save_article_source(issue_number, markdown_text, source_dir=str(source_dir))

    def synchronize_index() -> bool:
        index_path.write_text("after synchronization", encoding="utf-8", newline="\n")
        return True

    monkeypatch.setattr(sync_module, "ChatModel", FakeChatModel)
    monkeypatch.setattr(sync_module, "save_article_source", save_source)
    monkeypatch.setattr(sync_module.sync_article_dates, "main", synchronize_index)
    monkeypatch.setattr(sync_module, "sse_client", lambda _: (_ for _ in ()).throw(RuntimeError("MCP disabled")))

    processed = __import__("asyncio").run(sync_module.process_single_issue(issue, manager))

    assert processed is True
    assert (source_dir / "issue-42.md").read_text(encoding="utf-8") == VALID_MARKDOWN
    assert (tmp_path / "public" / "articles" / "issue-42-output-sync-test.html").exists()
    assert index_path.read_text(encoding="utf-8") == "after synchronization"

    database = json.loads((tmp_path / "issue_status.json").read_text(encoding="utf-8"))
    record = database["issues"]["42"]
    assert record["status"] == "processed"
    assert record["article_source_file"] == "issue-42.md"
    assert record["article_file"] == "issue-42-output-sync-test.html"
    assert record["index_synced"] is True
    assert record["attempt_id"]


@pytest.mark.integration
def test_process_single_issue_stops_before_saving_when_markdown_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Markdown検証失敗時は成果物を保存せず、failed状態を記録する。"""
    sync_module = _load_sync_module(monkeypatch)
    monkeypatch.chdir(tmp_path)

    issue = {"number": 43, "title": "Invalid Markdown", "body": "失敗の検証"}
    manager = IssueManager(db_path=str(tmp_path / "issue_status.json"))
    _create_unprocessed_issue(manager, issue)
    saved_outputs: list[str] = []

    class FakeChatModel:
        def __init__(self) -> None:
            self.responses = iter(("invalid markdown research", "```python\nprint('unclosed')"))

        def generate_response(self, _: dict[str, Any]) -> SimpleNamespace:
            return SimpleNamespace(content=next(self.responses))

    def unexpected_output(*_: Any, **__: Any) -> None:
        saved_outputs.append("output")
        raise AssertionError("Markdown validation failure must stop output creation.")

    monkeypatch.setattr(sync_module, "ChatModel", FakeChatModel)
    monkeypatch.setattr(sync_module, "save_article_source", unexpected_output)
    monkeypatch.setattr(sync_module, "ArticleBuilder", unexpected_output)
    monkeypatch.setattr(sync_module.sync_article_dates, "main", unexpected_output)
    monkeypatch.setattr(sync_module, "sse_client", lambda _: (_ for _ in ()).throw(RuntimeError("MCP disabled")))

    processed = __import__("asyncio").run(sync_module.process_single_issue(issue, manager))

    assert processed is False
    assert saved_outputs == []
    database = json.loads((tmp_path / "issue_status.json").read_text(encoding="utf-8"))
    record = database["issues"]["43"]
    assert record["status"] == "failed"
    assert record["failure_reason"].startswith("[Stage 3] Markdown ValidationFailed:")
    assert record["attempt_id"]


@pytest.mark.integration
def test_process_single_issue_stops_before_index_when_html_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTML検証失敗時は原本とHTMLを残し、index同期を行わずfailedにする。"""
    sync_module = _load_sync_module(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "public" / "articles").mkdir(parents=True)

    issue = {"number": 44, "title": "Invalid HTML", "body": "HTML失敗の検証"}
    manager = IssueManager(db_path=str(tmp_path / "issue_status.json"))
    _create_unprocessed_issue(manager, issue)
    source_dir = tmp_path / "article_sources"
    index_called = False

    class FakeChatModel:
        def __init__(self) -> None:
            self.responses = iter(("invalid html research", VALID_MARKDOWN))

        def generate_response(self, _: dict[str, Any]) -> SimpleNamespace:
            return SimpleNamespace(content=next(self.responses))

    class InvalidHtmlBuilder:
        def save_article(self, _: dict[str, Any], filename: str) -> str:
            output_path = tmp_path / "public" / "articles" / filename
            output_path.write_text("<html>invalid</html>", encoding="utf-8", newline="\n")
            return str(output_path)

    def save_source(issue_number: int, markdown_text: str) -> str:
        return save_article_source(issue_number, markdown_text, source_dir=str(source_dir))

    def unexpected_index_sync() -> bool:
        nonlocal index_called
        index_called = True
        raise AssertionError("HTML validation failure must stop index synchronization.")

    monkeypatch.setattr(sync_module, "ChatModel", FakeChatModel)
    monkeypatch.setattr(sync_module, "save_article_source", save_source)
    monkeypatch.setattr(sync_module, "ArticleBuilder", InvalidHtmlBuilder)
    monkeypatch.setattr(sync_module.sync_article_dates, "main", unexpected_index_sync)
    monkeypatch.setattr(sync_module, "sse_client", lambda _: (_ for _ in ()).throw(RuntimeError("MCP disabled")))

    processed = __import__("asyncio").run(sync_module.process_single_issue(issue, manager))

    assert processed is False
    assert (source_dir / "issue-44.md").exists()
    assert (tmp_path / "public" / "articles" / "issue-44-invalid-html.html").exists()
    assert index_called is False
    database = json.loads((tmp_path / "issue_status.json").read_text(encoding="utf-8"))
    record = database["issues"]["44"]
    assert record["status"] == "failed"
    assert record["failure_reason"].startswith("[Stage 5] HTML ValidationFailed:")


@pytest.mark.integration
def test_process_single_issue_marks_saved_outputs_unsynchronized_when_index_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """index同期失敗時は保存済み成果物を記録し、failed・未同期にする。"""
    sync_module = _load_sync_module(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "public" / "articles").mkdir(parents=True)

    issue = {"number": 45, "title": "Index Failure", "body": "index失敗の検証"}
    manager = IssueManager(db_path=str(tmp_path / "issue_status.json"))
    _create_unprocessed_issue(manager, issue)
    source_dir = tmp_path / "article_sources"

    class FakeChatModel:
        def __init__(self) -> None:
            self.responses = iter(("index failure research", VALID_MARKDOWN))

        def generate_response(self, _: dict[str, Any]) -> SimpleNamespace:
            return SimpleNamespace(content=next(self.responses))

    def save_source(issue_number: int, markdown_text: str) -> str:
        return save_article_source(issue_number, markdown_text, source_dir=str(source_dir))

    monkeypatch.setattr(sync_module, "ChatModel", FakeChatModel)
    monkeypatch.setattr(sync_module, "save_article_source", save_source)
    monkeypatch.setattr(sync_module.sync_article_dates, "main", lambda: False)
    monkeypatch.setattr(sync_module, "sse_client", lambda _: (_ for _ in ()).throw(RuntimeError("MCP disabled")))

    processed = __import__("asyncio").run(sync_module.process_single_issue(issue, manager))

    assert processed is False
    assert (source_dir / "issue-45.md").exists()
    assert (tmp_path / "public" / "articles" / "issue-45-index-failure.html").exists()
    database = json.loads((tmp_path / "issue_status.json").read_text(encoding="utf-8"))
    record = database["issues"]["45"]
    assert record["status"] == "failed"
    assert record["article_source_file"] == "issue-45.md"
    assert record["article_file"] == "issue-45-index-failure.html"
    assert record["index_synced"] is False
    assert record["failure_reason"].startswith("[Stage 6] index.html sync failed")

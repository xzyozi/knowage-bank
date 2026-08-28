"""Integration 層 (IssueRouter) の単体テスト。"""

from datetime import datetime, timezone

from personal_knowledge.domain.models import SearchSession
from personal_knowledge.integration.issue_router import IssueRouter


def test_jaccard_similarity_calculation() -> None:
    """Jaccard 係数計算が正確に行われること。"""
    tokens_a = {"python", "asyncio", "coroutine"}
    tokens_b = {"python", "asyncio", "task"}
    # 共通: python, asyncio (2)
    # 和集合: python, asyncio, coroutine, task (4)
    # Jaccard = 2 / 4 = 0.5
    score = IssueRouter.calculate_jaccard_similarity(tokens_a, tokens_b)
    assert score == 0.5


def test_tokenize_japanese_and_english() -> None:
    """英語単語および日本語バイグラムがトークンとして抽出されること。"""
    text = "Python 非同期処理 asyncio"
    tokens = IssueRouter.tokenize(text)

    assert "python" in tokens
    assert "asyncio" in tokens
    assert "非同" in tokens
    assert "同期" in tokens
    assert "期処" in tokens
    assert "処理" in tokens


def test_router_creates_new_issue_when_no_match() -> None:
    """類似する Open Issue がない場合、新規 Issue 起票 (create_issue) と判定されること。"""
    router = IssueRouter(similarity_threshold=0.3)

    session = SearchSession(
        start_time=datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 8, 23, 10, 15, 0, tzinfo=timezone.utc),
        queries=["Rust WebAssembly wasm-bindgen", "Rust wasm pack tutorial"],
        source_browsers=["chrome"],
    )

    open_issues = [
        {
            "number": 1,
            "title": "[自動抽出] Python asyncio 関連の調査",
            "body": "Python 非同期処理...",
            "comments": [],
        }
    ]

    decision = router.evaluate_routing(session, open_issues)

    assert decision.action == "create_issue"
    assert decision.target_issue_number is None
    assert decision.title == "[自動抽出] Rust WebAssembly wasm-bindgen 関連の調査"
    assert "### 検索クエリ一覧" in decision.body
    assert "1. Rust WebAssembly wasm-bindgen" in decision.body


def test_router_adds_comment_when_similarity_high() -> None:
    """類似する Open Issue が存在する場合、コメント追記 (add_comment) と判定されること。"""
    router = IssueRouter(similarity_threshold=0.3)

    session = SearchSession(
        start_time=datetime(2026, 8, 23, 11, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 8, 23, 11, 20, 0, tzinfo=timezone.utc),
        queries=["Python asyncio wait_for タイムアウト", "asyncio TaskGroup exception handling"],
        source_browsers=["firefox"],
    )

    open_issues = [
        {
            "number": 42,
            "title": "[自動抽出] Python asyncio タスクキャンセル 関連の調査",
            "body": "Python asyncio TaskGroup 例外伝播の仕組み",
            "comments": [],
        }
    ]

    decision = router.evaluate_routing(session, open_issues)

    assert decision.action == "add_comment"
    assert decision.target_issue_number == 42
    assert decision.similarity_score >= 0.3
    assert "### 追加の調査セッション" in decision.body
    assert "Python asyncio wait_for タイムアウト" in decision.body

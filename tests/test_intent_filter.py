"""IntentFilter の単体テスト。"""

from unittest.mock import MagicMock, patch

from personal_knowledge.domain.intent_filter import IntentFilter


def test_single_token_non_tech_returns_false_without_llm_call() -> None:
    """1トークンで技術用語辞書に含まれない単語 (例: サイコロ, 128GB) の場合、LLM呼び出しなしで False を返すこと。"""
    intent_filter = IntentFilter()

    with patch.object(intent_filter, "_judge_with_llm") as mock_judge:
        result_saikoro = intent_filter.is_knowledge_query("サイコロ")
        result_model = intent_filter.is_knowledge_query("128GB")

    assert result_saikoro is False
    assert result_model is False
    mock_judge.assert_not_called()


def test_single_token_tech_keyword_calls_llm_judgment() -> None:
    """1トークンでも技術辞書に含まれる単語 (例: python, docker) の場合、LLM判定に進むこと。"""
    intent_filter = IntentFilter()

    with patch.object(intent_filter, "_judge_with_llm", return_value=True) as mock_judge:
        result = intent_filter.is_knowledge_query("python")

    assert result is True
    mock_judge.assert_called_once_with("python")


def test_multi_token_query_calls_llm_judgment() -> None:
    """複数トークンのクエリの場合、LLM判定が呼び出されその結果が返されること。"""
    intent_filter = IntentFilter()

    with patch.object(intent_filter, "_judge_with_llm", return_value=True) as mock_judge:
        result = intent_filter.is_knowledge_query("Python asyncio タスクキャンセル")

    assert result is True
    mock_judge.assert_called_once_with("Python asyncio タスクキャンセル")


def test_judge_with_llm_parses_true_response() -> None:
    """Gemini API レスポンスが 'True' の場合に True を返すこと。"""
    intent_filter = IntentFilter(api_key="dummy-key")

    mock_response = MagicMock()
    mock_response.text = "True"
    mock_response.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=2, total_token_count=12)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        result = intent_filter._judge_with_llm("Python asyncio タスクキャンセル")

    assert result is True
    assert intent_filter.usage_stats.request_count == 1
    assert intent_filter.usage_stats.total_tokens == 12


def test_judge_with_llm_defaults_to_false_on_api_error() -> None:
    """Gemini API呼び出しが例外を発生させた場合、安全なデフォルト(False)を返すこと。"""
    intent_filter = IntentFilter(api_key="dummy-key")

    with patch("google.genai.Client", side_effect=RuntimeError("API unavailable")):
        result = intent_filter._judge_with_llm("some query")

    assert result is False

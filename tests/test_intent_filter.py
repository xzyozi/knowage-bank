"""IntentFilter の単体テスト。"""

from unittest.mock import MagicMock, patch

from google import genai

from personal_knowledge.domain.intent_filter import IntentFilter


def test_blacklisted_keyword_returns_false_without_llm_call() -> None:
    """ブラックリストキーワードに部分一致する場合、LLM呼び出しなしで False を返すこと。"""
    intent_filter = IntentFilter(blacklisted_keywords=["天気", "youtube"])

    with patch.object(intent_filter, "_judge_with_llm") as mock_judge:
        result = intent_filter.is_knowledge_query("今日の天気 東京")

    assert result is False
    mock_judge.assert_not_called()


def test_non_blacklisted_keyword_calls_llm_judgment() -> None:
    """ブラックリストに一致しない場合、LLM判定が呼び出されその結果が返されること。"""
    intent_filter = IntentFilter(blacklisted_keywords=["天気"])

    with patch.object(intent_filter, "_judge_with_llm", return_value=True) as mock_judge:
        result = intent_filter.is_knowledge_query("Python asyncio タスクキャンセル")

    assert result is True
    mock_judge.assert_called_once_with("Python asyncio タスクキャンセル")


def test_judge_with_llm_parses_true_response() -> None:
    """Gemini API レスポンスが 'True' の場合に True を返すこと。"""
    intent_filter = IntentFilter(blacklisted_keywords=[], api_key="dummy-key")

    mock_response = MagicMock()
    mock_response.text = "True"
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        result = intent_filter._judge_with_llm("Python asyncio タスクキャンセル")

    assert result is True


def test_judge_with_llm_defaults_to_false_on_api_error() -> None:
    """Gemini API呼び出しが例外を発生させた場合、安全なデフォルト(False)を返すこと。"""
    intent_filter = IntentFilter(blacklisted_keywords=[], api_key="dummy-key")

    with patch("google.genai.Client", side_effect=RuntimeError("API unavailable")):
        result = intent_filter._judge_with_llm("some query")

    assert result is False


def test_judge_with_llm_defaults_to_false_on_false_response() -> None:
    """Gemini API レスポンスが 'False' の場合に False を返すこと。"""
    intent_filter = IntentFilter(blacklisted_keywords=[], api_key="dummy-key")

    mock_response = MagicMock()
    mock_response.text = "False"
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        result = intent_filter._judge_with_llm("YouTubeで動画を見る")

    assert result is False

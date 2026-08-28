from typing import Any

"""
tests/test_llm_base.py

tools.base.llm_client_base モジュールのユニットテスト。
"""

from unittest.mock import MagicMock, patch
import pytest

from tools.base import BaseLLMClient, extract_json_from_text


def test_extract_json_from_text_direct() -> None:
    text = '{"name": "test", "value": 123}'
    res = extract_json_from_text(text)
    assert res == {"name": "test", "value": 123}


def test_extract_json_from_text_embedded_markdown() -> None:
    text = """Here is the response:
```json
{
    "status": "ok",
    "items": [1, 2, 3]
}
```
Thank you."""
    res = extract_json_from_text(text)
    assert res == {"status": "ok", "items": [1, 2, 3]}


def test_extract_json_from_text_invalid() -> None:
    assert extract_json_from_text("Invalid text without json") is None
    assert extract_json_from_text("") is None


@patch("tools.base.llm_client_base.OpenAI")
def test_base_llm_client_completion(mock_openai_cls: Any) -> None:
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    mock_choice = MagicMock()
    mock_choice.message.content = '{"result": "success"}'
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    client = BaseLLMClient(api_base="http://localhost:8080/v1")
    res = client.completion(model="test-model", system_prompt="sys", user_prompt="usr", expect_json=True)

    assert res == {"result": "success"}
    mock_client.chat.completions.create.assert_called_once()

import pytest
from app.chatmodel import chat_model_instance, ChatModel

def test_ollama_singleton_connection():
    """シングルトンの chat_model_instance を使った Ollama 疎通テスト"""
    try:
        response = chat_model_instance.get_response("Hello")
        assert response is not None
        assert len(response) > 0
        print(f"\nOllama singleton response: {response}")
    except Exception as e:
        pytest.fail(f"Ollama connection via singleton failed: {e}")

def test_chat_model_class_connection():
    """ChatModel クラスのインスタンス生成と疎通テスト"""
    try:
        model = ChatModel()
        history = {
            "messages": [
                {"role": "system", "content": model.system_prompt},
                {"role": "user", "content": "1+1は何ですか？"}
            ]
        }
        response = model.generate_response(history)
        assert response is not None
        assert response.content is not None
        print(f"\nOllama ChatModel response content: {response.content}")
    except Exception as e:
        pytest.fail(f"Ollama connection via ChatModel class failed: {e}")

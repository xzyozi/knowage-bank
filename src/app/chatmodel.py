from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import os
import time
import traceback
from typing import Any, Dict, List, Optional

import openai

from app import config
from app.utils.logger import logger  # ロガーオブジェクトを直接インポート


class AbstractChatModel(ABC):
    """チャットモデルの抽象基底クラス"""
    @abstractmethod
    def get_response(self, prompt: str) -> str:
        """プロンプトに対して応答を生成します。"""
        pass

class OllamaModel(AbstractChatModel):
    """OllamaをローカルAPI経由で使用するモデル"""
    def __init__(self, model_name: str, base_url: str):
        self.model_name = model_name
        self.base_url = base_url
        compat_url = base_url if "/v1" in base_url else f"{base_url.rstrip('/')}/v1"
        self.client = openai.OpenAI(
            base_url=compat_url,
            api_key="ollama",  # Ollamaの場合はダミーキーで動作します
        )
        logger.info(f"Initialized OllamaModel with model '{model_name}' at {compat_url}")

    def get_response(self, prompt: str) -> str:
        logger.debug(f"Sending prompt to Ollama ({self.model_name}): {prompt}")
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            return completion.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Ollama API request failed: {e}")
            raise e

def _initialize_model() -> AbstractChatModel:
    """設定に基づいて適切なチャットモデルのインスタンスを返すファクトリ関数"""
    model_name = config.KNOWAGE_BANK_MODEL
    base_url = config.OLLAMA_BASE_URL
    
    # ollama/ プレフィックスがあれば除去
    clean_model_name = model_name
    if model_name.startswith("ollama/"):
        clean_model_name = model_name[7:]
        
    logger.info(f"Using Ollama model based on configuration: {clean_model_name}")
    return OllamaModel(model_name=clean_model_name, base_url=base_url)

# アプリケーション起動時にモデルを一度だけ初期化し、シングルトンとして提供
chat_model_instance: AbstractChatModel = _initialize_model()

class ChatModel:
    def __init__(self,
                 model_name: Optional[str] = None,
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 site_url: str = "",
                 site_name: str = ""
                 ) -> None:
        raw_model = model_name or config.KNOWAGE_BANK_MODEL
        
        # ollama/ プレフィックスのハンドリング
        self.model_name = raw_model
        if raw_model.startswith("ollama/"):
            self.model_name = raw_model[7:]
            api_key = api_key or "ollama"
            base_url = base_url or config.OLLAMA_BASE_URL
        else:
            api_key = api_key or "ollama"
            base_url = base_url or config.OLLAMA_BASE_URL

        # OpenAI互換エンドポイントの補正
        compat_url = base_url if "/v1" in base_url else f"{base_url.rstrip('/')}/v1"

        self.client = openai.OpenAI(
            base_url=compat_url,
            api_key=api_key,
        )
        self.extra_headers: Dict[str, str] = {}
        if site_url:
            self.extra_headers["HTTP-Referer"] = site_url
            self.extra_headers["X-Title"] = site_name
        self.extra_body: Dict[str, Any] = {}

        # システムプロンプト（外部ファイルからロード、失敗時はフォールバック）
        # src/app/chatmodel.py から 2階層上がリポジトリルートとなり、そこから prompts/system_prompt.txt を参照
        prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "prompts", "system_prompt.txt")
        if not os.path.exists(prompt_path):
            # ルートからの相対パス等、いくつかのフォールバックパスを試す
            prompt_path = "prompts/system_prompt.txt"

        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
            logger.info(f"Loaded system prompt from {prompt_path}")
        except Exception as e:
            logger.warning(f"Failed to load system prompt from {prompt_path}, using minimum default. Error: {e}")
            self.system_prompt = "あなたは優秀なAIアシスタントです。明確で具体的な情報を日本語で提供してください。"

    def generate_response(self, history: Dict[str, Any], tools: Optional[List[Dict[str, Any]]] = None) -> Optional[openai.types.chat.ChatCompletionMessage]:
        max_retries = 3
        retry_wait_seconds = 15

        # Ollama用のコンテキスト制限拡張設定を extra_body に差し込む
        extra_body_params = dict(self.extra_body)
        if "options" not in extra_body_params:
            extra_body_params["options"] = {
                "num_ctx": 8192,
                "num_predict": 4096
            }

        api_params = {
            "model": self.model_name,
            "messages": history.get("messages", []),
            "temperature": 0.7,
            "top_p": 0.95,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.3,
            "n": 1,
            "stream": False,
            "max_tokens": 4096,  # 構成拡張による出力の長文化に対応
            "extra_headers": self.extra_headers,
            "extra_body": extra_body_params,
        }

        # ツールが明示的に渡された場合のみ、パラメータに追加
        if tools and isinstance(tools, list) and len(tools) > 0:
            api_params["tools"] = tools
            api_params["tool_choice"] = "auto"
        else:
            # ツールがない場合は、念のため関連パラメータを削除（あるいは追加しない）
            api_params.pop("tools", None)
            api_params.pop("tool_choice", None)

        # 不要なヘッダーを除去し、APIパラメータを整理
        if not self.extra_headers:
            api_params.pop("extra_headers", None)
        if not self.extra_body:
            api_params.pop("extra_body", None)

        for attempt in range(1, max_retries + 1):
            try:
                # APIリクエスト
                completion = self.client.chat.completions.create(**api_params)

                response_message = completion.choices[0].message
                logger.info(f"Response message: {response_message}")
                return response_message

            except openai.InternalServerError as e:
                logger.warning(f"Server error: Retry {attempt}/{max_retries}")
                if hasattr(e, "response") and e.response is not None:
                    logger.debug(f"HTTP Status Code: {e.response.status_code}")
                    logger.debug(f"Response Headers: {e.response.headers}")
                    try:
                        logger.debug(f"Response JSON: {e.response.json()}")
                    except Exception:
                        logger.debug(f"Response Text: {e.response.text}")

                if attempt < max_retries:
                    time.sleep(retry_wait_seconds)
                else:
                    logger.error("Max retries reached.")

            except openai.APIStatusError as e:
                # ステータスコードとエラーメッセージを表示
                logger.error(f"ステータスコード: {e.status_code}")
                logger.error(f"レスポンス内容: {e.response.text}")
                break

            except Exception as e:
                logger.error("Unexpected exception occurred:")
                logger.error(traceback.format_exc())
                if hasattr(e, "response") and e.response is not None:
                    logger.debug(f"HTTP Status Code: {e.response.status_code}")
                    logger.debug(f"Response Headers: {e.response.headers}")
                    try:
                        logger.debug(f"Response JSON: {e.response.json()}")
                    except Exception:
                        logger.debug(f"Response Text: {e.response.text}")
                break

        return None


# chat model configer
@dataclass
class ChatAPIConfig:
    model_name: str
    api_key: str
    base_url: str

class ChatConfigManager:
    DEFAULT_CONFIG_PATH = "config/chat_api_config.json"

    def __init__(self, config_path: Optional[str] = None) -> None:
        path = config_path or self.DEFAULT_CONFIG_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            self._create_default_config(path)
        self._load_config(path)

    def _create_default_config(self, path: str) -> None:
        default = {
            "providers": {
                "openai": [
                    {
                        "model_name": "gpt-4",
                        "api_key": "your-api-key",
                        "base_url": "https://api.openai.com/v1"
                    }
                ]
            }
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)

    def _load_config(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.model_index: Dict[str, ChatAPIConfig] = {}
        for provider_entries in data.get("providers", {}).values():
            for entry in provider_entries:
                model = entry["model_name"]
                self.model_index[model] = ChatAPIConfig(**entry)

    def get(self, model_name: str) -> Optional[ChatAPIConfig]:
        return self.model_index.get(model_name)

    def __getitem__(self, model_name: str) -> Optional[ChatAPIConfig]:
        return self.get(model_name)

    def all_models(self) -> Dict[str, ChatAPIConfig]:
        return self.model_index

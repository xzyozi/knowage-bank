"""検索クエリの知識探求意図を判定するフィルタリングモジュール。"""

from dataclasses import dataclass
import logging
import os
import re

from personal_knowledge.config_loader import FilteringConfig, load_config

logger = logging.getLogger(__name__)

# 主要な技術キーワード辞書 (1トークンでも正当な技術とみなす辞書)
KNOWN_TECH_KEYWORDS: set[str] = {
    "python",
    "fastapi",
    "docker",
    "git",
    "sql",
    "react",
    "vue",
    "api",
    "vram",
    "pytest",
    "cuda",
    "ollama",
    "sqlite",
    "linux",
    "ubuntu",
    "pip",
    "npm",
    "uv",
    "github",
    "pandas",
    "numpy",
    "pytorch",
    "tensorflow",
    "llama",
    "huggingface",
    "claude",
    "gemini",
    "openai",
    "bash",
    "powershell",
    "json",
    "yaml",
    "html",
    "css",
    "js",
    "ts",
    "typescript",
    "javascript",
    "c",
    "cpp",
    "rust",
    "go",
    "golang",
    "java",
    "kotlin",
    "swift",
    "flutter",
    "aws",
    "gcp",
    "azure",
}


@dataclass
class ApiUsageStats:
    """Gemini API の使用量統計。"""

    request_count: int = 0
    prompt_tokens: int = 0
    candidates_tokens: int = 0
    total_tokens: int = 0


class IntentFilter:
    """動的単一トークン判定および Gemini API による LLM 判定を行うクラス。"""

    def __init__(
        self,
        system_prompt: str | None = None,
        chat_model: str = "gemini-1.5-flash",
        api_key: str | None = None,
        custom_tech_keywords: set[str] | None = None,
    ) -> None:
        """IntentFilter を初期化する。"""
        if system_prompt is None:
            config: FilteringConfig = load_config().filtering
            system_prompt = config.llm_system_prompt

        self.system_prompt = system_prompt
        self.chat_model = chat_model
        self._api_key = api_key
        self.tech_keywords = KNOWN_TECH_KEYWORDS.union(custom_tech_keywords or set())
        self.usage_stats = ApiUsageStats()

    def is_single_token_non_tech(self, keyword: str) -> bool:
        """トークン数が1つだけで、かつ技術キーワード辞書に存在しない文脈なし単語かを動的判定する。"""
        trimmed = keyword.strip()
        if not trimmed:
            return True

        tokens = [t for t in re.split(r"[\s,._/|\-]+", trimmed) if t]

        if len(tokens) >= 2:
            return False

        lowered = trimmed.lower()
        if lowered in self.tech_keywords:
            return False

        if re.match(r"^--?[a-z0-9\-]+$", trimmed) or re.match(r"^v?\d+(\.\d+)+$", trimmed):
            return False

        return True

    def _judge_with_llm(self, keyword: str) -> bool:
        """Gemini API を呼び出し、キーワードの知識探求意図を True/False で判定し、トークン数を計測する。

        APIキーがない場合や例外発生時は、安全なフォールバックとして True (通過) を返却する。
        """
        try:
            api_key = self._api_key or os.environ.get("GEMINI_API_KEY")
            if not api_key:
                return True

            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=self.chat_model,
                contents=keyword,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.0,
                ),
            )

            self.usage_stats.request_count += 1
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                meta = response.usage_metadata
                self.usage_stats.prompt_tokens += getattr(meta, "prompt_token_count", 0) or 0
                self.usage_stats.candidates_tokens += getattr(meta, "candidates_token_count", 0) or 0
                self.usage_stats.total_tokens += getattr(meta, "total_token_count", 0) or 0

            result_text = (response.text or "").strip().lower()
            return result_text.startswith("true")
        except Exception as e:
            logger.warning(f"Gemini API intent judgment failed for keyword '{keyword}': {e}. Defaulting to True.")
            return True

    def is_knowledge_query(self, keyword: str) -> bool:
        """検索キーワードが知識探求・技術解決目的かどうかを判定する。

        単一トークンかつ技術辞書に含まれないコンテキストなしノイズを動的除外した上で、
        必要に応じて Gemini LLM 判定を行う。
        """
        if self.is_single_token_non_tech(keyword):
            return False
        return self._judge_with_llm(keyword)

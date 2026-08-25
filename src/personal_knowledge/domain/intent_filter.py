"""検索クエリの知識探求意図を判定するフィルタリングモジュール。"""

import logging

from personal_knowledge.config_loader import FilteringConfig, load_config

logger = logging.getLogger(__name__)


class IntentFilter:
    """ブラックリストおよび Gemini API による LLM 判定で、検索クエリの知識探求意図を判定するクラス。"""

    def __init__(
        self,
        blacklisted_keywords: list[str] | None = None,
        system_prompt: str | None = None,
        chat_model: str = "gemini-1.5-flash",
        api_key: str | None = None,
    ) -> None:
        """IntentFilter を初期化する。

        Args:
            blacklisted_keywords: 即座に除外する非技術系日常検索キーワードリスト。
                None の場合は config.json (または既定値) から読み込む。
            system_prompt: LLM 意図判定用システムプロンプト。None の場合は config.json
                (または既定値) から読み込む。
            chat_model: 意図判定に使用する Gemini モデル名。
            api_key: Gemini API キー。None の場合は環境変数 GEMINI_API_KEY を使用。
        """
        if blacklisted_keywords is None or system_prompt is None:
            config: FilteringConfig = load_config().filtering
            if blacklisted_keywords is None:
                blacklisted_keywords = config.blacklisted_keywords
            if system_prompt is None:
                system_prompt = config.llm_system_prompt

        self.blacklisted_keywords = blacklisted_keywords
        self.system_prompt = system_prompt
        self.chat_model = chat_model
        self._api_key = api_key

    def _is_blacklisted(self, keyword: str) -> bool:
        """キーワードがブラックリストに部分一致するか判定する。

        Args:
            keyword: 判定対象の検索キーワード。

        Returns:
            bool: ブラックリストに部分一致する場合は True。
        """
        normalized = keyword.lower()
        return any(bl.lower() in normalized for bl in self.blacklisted_keywords)

    def _judge_with_llm(self, keyword: str) -> bool:
        """Gemini API を呼び出し、キーワードの知識探求意図を True/False で判定する。

        API呼び出しやレスポンス解析に失敗した場合は、安全なデフォルトとして
        False (知識探求目的ではない) を返却する (サイレントフォールト)。

        Args:
            keyword: 判定対象の検索キーワード。

        Returns:
            bool: 知識探求目的と判定された場合は True。
        """
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self._api_key) if self._api_key else genai.Client()
            response = client.models.generate_content(
                model=self.chat_model,
                contents=keyword,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.0,
                ),
            )
            result_text = (response.text or "").strip().lower()
            return result_text.startswith("true")
        except Exception as e:
            logger.warning(f"Gemini API intent judgment failed for keyword '{keyword}': {e}. Defaulting to False.")
            return False

    def is_knowledge_query(self, keyword: str) -> bool:
        """検索キーワードが知識探求・技術解決目的かどうかを判定する。

        まずブラックリスト判定を行い、部分一致する場合は即座に False を返す。
        一致しない場合は Gemini API による LLM 二値判定を行う。

        Args:
            keyword: 判定対象の検索キーワード。

        Returns:
            bool: 知識探求目的と判定された場合は True。
        """
        if self._is_blacklisted(keyword):
            return False
        return self._judge_with_llm(keyword)

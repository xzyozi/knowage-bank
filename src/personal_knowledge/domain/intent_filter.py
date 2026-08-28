"""検索クエリの知識探求意図を判定するフィルタリングモジュール。"""

from dataclasses import dataclass
import json
import logging
import os
import re
import time

from personal_knowledge.config_loader import FilteringConfig, load_config
from personal_knowledge.infrastructure.model_resolver import ModelResolutionError, ModelResolver

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
    """動的単一トークン判定および Gemini API による LLM 判定（単一・バッチ処理）を行うクラス。"""

    def __init__(
        self,
        system_prompt: str | None = None,
        chat_model: str | None = None,
        api_key: str | None = None,
        custom_tech_keywords: set[str] | None = None,
        model_resolver: ModelResolver | None = None,
    ) -> None:
        """IntentFilter を初期化する。"""
        config = load_config()
        if system_prompt is None:
            filtering_config: FilteringConfig = config.filtering
            system_prompt = filtering_config.llm_system_prompt

        self.system_prompt = system_prompt
        self.chat_model = chat_model or config.api.chat_model
        self._api_key = api_key
        self.model_resolver = model_resolver or ModelResolver(config=config.api, api_key=api_key)
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
        """単一キーワードの LLM 意図判定。"""
        results = self.judge_batch_with_llm([keyword])
        return results[0] if results else True

    def judge_batch_with_llm(self, keywords: list[str]) -> list[bool]:
        """複数の検索キーワードを 1 回のリクエストでまとめて Gemini API に送信し一括判定する (バッチ処理)。

        429 Too Many Requests 発生時は自動ウェイト＆リトライを適用し、確実にレスポンスを取得します。
        """
        if not keywords:
            return []

        api_key = self._api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return [True] * len(keywords)

        candidate_models, source = self.model_resolver.resolve_candidates("generate_content")
        self.model_resolver.start_resolution("generate_content", source)

        from google.genai import types

        client = self.model_resolver.get_client()
        batch_payload = {str(i): kw for i, kw in enumerate(keywords, 1)}
        prompt = (
            "以下の検索クエリリストについて、それぞれの探求意図を判定してください。\n"
            "『技術的な学習・概念理解・プログラミング・問題解決・仕事関連知識』が目的の場合は true、\n"
            "『マッチングアプリ・恋愛・ゲーム・エンタメ・買い物・生活日常タスク・型番単体』等の場合は false としてください。\n"
            "返答は必ず JSON 形式で {\"1\": true, \"2\": false, ...} のように番号に対応する boolean のみを返してください。\n\n"
            f"{json.dumps(batch_payload, ensure_ascii=False, indent=2)}"
        )

        pending_models = list(candidate_models)
        attempted_models: set[str] = set()
        while pending_models:
            model = pending_models.pop(0)
            if model in attempted_models:
                continue
            attempted_models.add(model)

            for retry_count in range(self.model_resolver.config.model_retry_count):
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            response_mime_type="application/json",
                        ),
                    )

                    self.usage_stats.request_count += 1
                    if hasattr(response, "usage_metadata") and response.usage_metadata:
                        meta = response.usage_metadata
                        self.usage_stats.prompt_tokens += getattr(meta, "prompt_token_count", 0) or 0
                        self.usage_stats.candidates_tokens += getattr(meta, "candidates_token_count", 0) or 0
                        self.usage_stats.total_tokens += getattr(meta, "total_token_count", 0) or 0

                    parsed = json.loads((response.text or "").strip())
                    results = [bool(parsed.get(str(i), parsed.get(i, True))) for i in range(1, len(keywords) + 1)]
                    self.chat_model = model
                    self.model_resolver.record_success("generate_content", model, source)
                    return results
                except Exception as error:
                    if self.model_resolver.raises_immediately(error):
                        raise ModelResolutionError(f"Geminiモデル '{model}' の利用を継続できません: {error}") from error

                    category = self.model_resolver.classify_error(error)
                    self.model_resolver.record_fallback("generate_content", model, error)
                    if category == "not_found":
                        self.model_resolver.invalidate("generate_content")
                        refreshed_models, source = self.model_resolver.resolve_candidates(
                            "generate_content", force_refresh=True, exclude=attempted_models
                        )
                        pending_models.extend(candidate for candidate in refreshed_models if candidate not in pending_models)
                        break
                    if category in {"rate_limited", "transient"} and retry_count + 1 < self.model_resolver.config.model_retry_count:
                        sleep_seconds = self.model_resolver.retry_delay_seconds(retry_count)
                        logger.info(
                            "Geminiモデル '%s' が%sのため %.1f 秒後に再試行します (%d/%d)",
                            model,
                            category,
                            sleep_seconds,
                            retry_count + 1,
                            self.model_resolver.config.model_retry_count,
                        )
                        time.sleep(sleep_seconds)
                        continue
                    logger.warning("Geminiモデル '%s' の意図判定に失敗しました: %s", model, error)
                    break

        return [True] * len(keywords)

    def is_knowledge_query(self, keyword: str) -> bool:
        """検索キーワードが知識探求・技術解決目的かどうかを判定する。"""
        if self.is_single_token_non_tech(keyword):
            return False
        return self._judge_with_llm(keyword)

    def filter_knowledge_queries_batch(self, keywords: list[str], batch_size: int = 50) -> list[bool]:
        """検索キーワード群をバッチ分割し、最小リクエスト数で一括判定する。"""
        results: list[bool] = []

        for i in range(0, len(keywords), batch_size):
            if i > 0:
                time.sleep(1.0)  # レートリミット回避のための1秒インターバル

            chunk = keywords[i : i + batch_size]

            chunk_results: list[bool | None] = []
            queries_for_llm: list[str] = []
            llm_indices: list[int] = []

            for idx, kw in enumerate(chunk):
                if self.is_single_token_non_tech(kw):
                    chunk_results.append(False)
                else:
                    chunk_results.append(None)
                    queries_for_llm.append(kw)
                    llm_indices.append(idx)

            if queries_for_llm:
                llm_results = self.judge_batch_with_llm(queries_for_llm)
                for pos, res in zip(llm_indices, llm_results):
                    chunk_results[pos] = res

            results.extend([bool(r) for r in chunk_results])

        return results

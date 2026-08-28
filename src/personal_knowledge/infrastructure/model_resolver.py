"""Gemini APIの利用可能モデルを用途別に解決する運用基盤。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import os
import re
import time
from typing import Any, Callable, Literal

from personal_knowledge.config_loader import ApiConfig, load_config

logger = logging.getLogger(__name__)

ModelPurpose = Literal["generate_content", "embed_content"]


class ModelResolutionError(RuntimeError):
    """認証・権限・リクエスト不備など、候補切替してはいけないモデル解決エラー。"""


@dataclass
class ModelResolution:
    """用途別の実利用モデルとフォールバック履歴。"""

    purpose: ModelPurpose
    selected_model: str | None = None
    candidate_source: str = "configured_fallback"
    fallback_count: int = 0
    fallback_reasons: list[str] = field(default_factory=list)
    resolved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class _CandidateCache:
    candidates: list[str]
    source: str
    created_at: float


class ModelResolver:
    """Geminiのモデル一覧をキャッシュし、用途別の候補順を提供する。"""

    def __init__(
        self,
        config: ApiConfig | None = None,
        api_key: str | None = None,
        client: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or load_config().api
        self._api_key = api_key
        self._client = client
        self._clock = clock
        self._cache: dict[ModelPurpose, _CandidateCache] = {}
        self._resolutions: dict[ModelPurpose, ModelResolution] = {}

    def resolve_candidates(
        self,
        purpose: ModelPurpose,
        *,
        force_refresh: bool = False,
        exclude: set[str] | None = None,
    ) -> tuple[list[str], str]:
        """用途に対応する候補を優先順位順に返す。"""
        exclude = exclude or set()
        cached = self._cache.get(purpose)
        if cached is not None and not force_refresh and self._is_cache_valid(cached):
            return self._exclude(cached.candidates, exclude), cached.source

        candidates: list[str] = []
        source = "configured_fallback"
        if self.config.model_discovery and self._has_api_key():
            try:
                candidates = self._discover_candidates(purpose)
                source = "api_discovery"
            except Exception as error:
                logger.warning("Geminiモデル一覧の取得に失敗したため設定候補を使用します: %s", error)

        if not candidates:
            candidates = self._configured_candidates(purpose)
            source = "configured_fallback"

        self._cache[purpose] = _CandidateCache(candidates=candidates, source=source, created_at=self._clock())
        return self._exclude(candidates, exclude), source

    def invalidate(self, purpose: ModelPurpose) -> None:
        """404検知時などに用途別の候補キャッシュを破棄する。"""
        self._cache.pop(purpose, None)

    def start_resolution(self, purpose: ModelPurpose, source: str) -> ModelResolution:
        """実行単位の利用モデル記録を開始する。"""
        resolution = ModelResolution(purpose=purpose, candidate_source=source)
        self._resolutions[purpose] = resolution
        return resolution

    def record_success(self, purpose: ModelPurpose, model: str, source: str) -> ModelResolution:
        """実際に成功したモデルを記録する。"""
        resolution = self._resolutions.get(purpose) or self.start_resolution(purpose, source)
        resolution.selected_model = model
        resolution.candidate_source = source
        return resolution

    def record_fallback(self, purpose: ModelPurpose, model: str, error: Exception) -> None:
        """候補切替の理由を機密情報を含めずに記録する。"""
        resolution = self._resolutions.get(purpose) or self.start_resolution(purpose, "configured_fallback")
        resolution.fallback_count += 1
        resolution.fallback_reasons.append(f"{model}: {self.classify_error(error)}")

    def get_resolution(self, purpose: ModelPurpose) -> ModelResolution | None:
        """直近の用途別モデル解決結果を返す。"""
        return self._resolutions.get(purpose)

    def retry_delay_seconds(self, retry_index: int) -> float:
        """429および一時障害に対する限定リトライの待機時間を返す。"""
        return 2.5 * (retry_index + 1)

    @staticmethod
    def classify_error(error: Exception) -> str:
        """HTTP/APIエラーを候補切替ポリシー用に分類する。"""
        message = str(error).lower()
        if "404" in message or "not_found" in message:
            return "not_found"
        if "429" in message or "resource_exhausted" in message:
            return "rate_limited"
        if "400" in message or "invalid_argument" in message:
            return "bad_request"
        if "401" in message or "unauthenticated" in message:
            return "unauthenticated"
        if "403" in message or "permission_denied" in message:
            return "permission_denied"
        if any(code in message for code in ("500", "502", "503", "504", "timeout", "timed out", "connection")):
            return "transient"
        return "unknown"

    @classmethod
    def raises_immediately(cls, error: Exception) -> bool:
        """候補切替で隠蔽してはいけないエラーかを判定する。"""
        return cls.classify_error(error) in {"bad_request", "unauthenticated", "permission_denied"}

    def _is_cache_valid(self, cached: _CandidateCache | None) -> bool:
        return cached is not None and self._clock() - cached.created_at < self.config.model_cache_ttl_seconds

    def _has_api_key(self) -> bool:
        return bool(self._api_key or os.environ.get("GEMINI_API_KEY"))

    def _discover_candidates(self, purpose: ModelPurpose) -> list[str]:
        required_action = "generatecontent" if purpose == "generate_content" else "embedcontent"
        discovered: list[str] = []
        for model in self._get_client().models.list():
            actions = getattr(model, "supported_actions", None) or getattr(
                model, "supported_generation_methods", []
            )
            normalized_actions = {str(action).replace("_", "").lower() for action in actions}
            if required_action not in normalized_actions:
                continue

            name = self._normalize_model_name(getattr(model, "name", ""))
            if not name or not self._is_allowed(name):
                continue
            discovered.append(name)

        return sorted(set(discovered), key=self._priority_key)

    def _configured_candidates(self, purpose: ModelPurpose) -> list[str]:
        configured = (
            self.config.chat_model_candidates if purpose == "generate_content" else self.config.embed_model_candidates
        )
        legacy = self.config.chat_model if purpose == "generate_content" else self.config.embed_model
        candidates = [self._normalize_model_name(model) for model in [*configured, legacy] if model]
        return self._exclude(list(dict.fromkeys(candidates)), set())

    def get_client(self) -> Any:
        """モデル一覧取得と推論で共有するGeminiクライアントを返す。"""
        return self._get_client()

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai

            api_key = self._api_key or os.environ.get("GEMINI_API_KEY")
            self._client = genai.Client(api_key=api_key)
        return self._client

    def _is_allowed(self, model: str) -> bool:
        lower_name = model.lower()
        if not self.config.allow_preview_models and "preview" in lower_name:
            return False
        if not self.config.allowed_models:
            return True
        return any(re.fullmatch(pattern.replace("*", ".*"), model) for pattern in self.config.allowed_models)

    @staticmethod
    def _normalize_model_name(model: str) -> str:
        return model.removeprefix("models/").strip()

    def _priority_key(self, model: str) -> tuple[bool, tuple[int, int, int], str]:
        version_match = re.search(r"gemini-(\d+)(?:\.(\d+))?(?:\.(\d+))?", model.lower())
        if version_match:
            groups = version_match.groups()
            version: tuple[int, int, int] = (
                int(groups[0] or 0),
                int(groups[1] or 0),
                int(groups[2] or 0),
            )
        else:
            version = (0, 0, 0)
        is_preview = "preview" in model.lower()
        return is_preview, (-version[0], -version[1], -version[2]), model

    @staticmethod
    def _exclude(candidates: list[str], excluded: set[str]) -> list[str]:
        return [candidate for candidate in candidates if candidate not in excluded]

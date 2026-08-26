"""ベクトル埋め込みとコサイン類似度による検索クエリの意味的クラスタリングモジュール。"""

from datetime import datetime, timezone
import logging
import math

from personal_knowledge.config_loader import load_config
from personal_knowledge.domain.models import SearchEntry, SearchSession

logger = logging.getLogger(__name__)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """2つのベクトル間のコサイン類似度を計算する。

    Args:
        vec_a: ベクトル A。
        vec_b: ベクトル B。

    Returns:
        float: コサイン類似度 (-1.0〜1.0)。いずれかがゼロベクトルの場合は 0.0。
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class SemanticClusterer:
    """Gemini Embedding API とコサイン類似度により、検索クエリを意味的セッションにクラスタリングするクラス。"""

    def __init__(
        self,
        embed_model: str = "models/text-embedding-004",
        similarity_threshold: float = 0.70,
        api_key: str | None = None,
    ) -> None:
        """SemanticClusterer を初期化する。

        Args:
            embed_model: 使用する Embedding モデル名。None の場合は config.json から読み込む。
            similarity_threshold: セッション統合を判定するコサイン類似度閾値。
            api_key: Gemini API キー。None の場合は環境変数 GEMINI_API_KEY を使用。
        """
        config = load_config()
        self.embed_model = embed_model or config.api.embed_model
        self.similarity_threshold = similarity_threshold
        self._api_key = api_key

    def _embed_text(self, text: str) -> list[float]:
        """Gemini Embedding API を用いてテキストをベクトル化する。

        API呼び出しに失敗した場合は、安全なデフォルトとしてゼロベクトルを返却する
        (サイレントフォールト)。

        Args:
            text: ベクトル化対象のテキスト。

        Returns:
            list[float]: 埋め込みベクトル。失敗時は空リスト。
        """
        try:
            from google import genai

            client = genai.Client(api_key=self._api_key) if self._api_key else genai.Client()
            result = client.models.embed_content(model=self.embed_model, contents=text)
            embeddings = getattr(result, "embeddings", None)
            if embeddings:
                values = getattr(embeddings[0], "values", None)
                if values:
                    return list(values)
            return []
        except Exception as e:
            logger.warning(f"Gemini Embedding API call failed for text '{text[:50]}': {e}. Returning zero vector.")
            return []

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        """タイムゾーン情報がない datetime に UTC を付与する。"""
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    def process_entries(self, entries: list[SearchEntry]) -> list[SearchSession]:
        """検索エントリ群を意味的類似度に基づいてセッションにクラスタリングする。

        各エントリの代表クエリ (各セッションの最初のクエリ) の Embedding ベクトルと
        コサイン類似度を比較し、閾値以上であれば既存セッションに統合、
        未満であれば新規セッションを作成する。

        Args:
            entries: 意図判定を通過した検索エントリ一覧 (時系列順を想定)。

        Returns:
            list[SearchSession]: 意味的クラスタリングされたセッション一覧。
        """
        if not entries:
            return []

        sorted_entries = sorted(entries, key=lambda e: self._ensure_utc(e.timestamp))

        # 各セッションの (代表ベクトル, エントリ群) を保持
        clusters: list[tuple[list[float], list[SearchEntry]]] = []

        for entry in sorted_entries:
            vector = self._embed_text(entry.keyword)

            best_score = -1.0
            best_cluster_idx: int | None = None
            for idx, (rep_vector, _) in enumerate(clusters):
                score = _cosine_similarity(vector, rep_vector)
                if score > best_score:
                    best_score = score
                    best_cluster_idx = idx

            if best_cluster_idx is not None and best_score >= self.similarity_threshold:
                clusters[best_cluster_idx][1].append(entry)
            else:
                clusters.append((vector, [entry]))

        sessions: list[SearchSession] = []
        for _, group in clusters:
            if len(group) < 1:
                continue

            start_time = self._ensure_utc(group[0].timestamp)
            end_time = self._ensure_utc(group[-1].timestamp)
            queries = [e.keyword for e in group]

            browsers_set: set[str] = set()
            for e in group:
                for b in e.source_browser.split(","):
                    cleaned_b = b.strip()
                    if cleaned_b:
                        browsers_set.add(cleaned_b)

            sessions.append(
                SearchSession(
                    start_time=start_time,
                    end_time=end_time,
                    queries=queries,
                    source_browsers=sorted(browsers_set),
                )
            )

        return sessions

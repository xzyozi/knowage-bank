"""SemanticClusterer の単体テスト。"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from personal_knowledge.domain.models import SearchEntry
from personal_knowledge.domain.semantic_clusterer import SemanticClusterer, _cosine_similarity


def test_cosine_similarity_identical_vectors() -> None:
    """同一ベクトル同士のコサイン類似度が 1.0 になること。"""
    vec = [1.0, 2.0, 3.0]
    assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal_vectors() -> None:
    """直交ベクトル同士のコサイン類似度が 0.0 になること。"""
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector_returns_zero() -> None:
    """ゼロベクトルが含まれる場合に 0.0 を返すこと (ゼロ除算回避)。"""
    assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert _cosine_similarity([], [1.0]) == 0.0


def test_process_entries_merges_similar_queries_into_one_session() -> None:
    """類似度が閾値以上のクエリが同一セッションに統合されること。"""
    clusterer = SemanticClusterer(similarity_threshold=0.70, api_key="dummy-key")

    entries = [
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc),
            keyword="Python asyncio タスクキャンセル",
            source_browser="chrome",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 10, 5, 0, tzinfo=timezone.utc),
            keyword="asyncio CancelledError ハンドリング",
            source_browser="chrome",
        ),
        SearchEntry(
            timestamp=datetime(2026, 8, 23, 11, 0, 0, tzinfo=timezone.utc),
            keyword="React useEffect クリーンアップ",
            source_browser="edge",
        ),
    ]

    # 最初の2件は類似ベクトル (類似度0.9以上)、3件目は無関係なベクトルを返すようモック
    vectors = [
        [1.0, 0.0, 0.0],
        [0.95, 0.31, 0.0],  # 1件目とコサイン類似度 ~0.95
        [0.0, 0.0, 1.0],  # 直交ベクトル (類似度0.0)
    ]

    with patch.object(clusterer, "_embed_text", side_effect=vectors):
        sessions = clusterer.process_entries(entries)

    assert len(sessions) == 2
    assert sessions[0].queries == ["Python asyncio タスクキャンセル", "asyncio CancelledError ハンドリング"]
    assert sessions[1].queries == ["React useEffect クリーンアップ"]


def test_process_entries_empty_list_returns_empty() -> None:
    """空の入力リストに対して空のセッションリストを返すこと。"""
    clusterer = SemanticClusterer(api_key="dummy-key")
    assert clusterer.process_entries([]) == []


def test_embed_text_returns_empty_list_on_api_error() -> None:
    """Gemini Embedding API呼び出しが失敗した場合、空リスト(ゼロベクトル相当)を返すこと。"""
    clusterer = SemanticClusterer(api_key="dummy-key")

    with patch("google.genai.Client", side_effect=RuntimeError("API unavailable")):
        result = clusterer._embed_text("some query")

    assert result == []


def test_embed_text_parses_embedding_response() -> None:
    """Gemini Embedding APIレスポンスからベクトル値を正しく抽出すること。"""
    clusterer = SemanticClusterer(api_key="dummy-key")

    mock_embedding = MagicMock()
    mock_embedding.values = [0.1, 0.2, 0.3]
    mock_result = MagicMock()
    mock_result.embeddings = [mock_embedding]

    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = mock_result

    with patch("google.genai.Client", return_value=mock_client):
        result = clusterer._embed_text("Python asyncio")

    assert result == [0.1, 0.2, 0.3]

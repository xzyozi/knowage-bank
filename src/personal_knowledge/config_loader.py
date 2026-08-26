"""パーソナル・ナレッジ自動生成システムのパイプライン設定ファイル (config.json) 読み込みモジュール。"""

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config/personal_knowledge_config.json")

DEFAULT_BLACKLISTED_KEYWORDS = ["天気", "乗り換え", "ログイン", "amazon", "youtube", "マップ"]

DEFAULT_LLM_SYSTEM_PROMPT = (
    "あなたは検索クエリの意図を分類するアシスタントです。"
    "提示された検索クエリが『知識の習得、概念の理解、単語の意味の調査、技術的な問題解決』を目的としている場合は "
    "'True' を出力してください。単なるサイトへの移動（ナビゲーション）、エンタメの消費、日常タスク"
    "（天気やルート検索）が目的である場合は 'False' を出力してください。"
    "出力は True または False のみとし、他の文字列を含めないでください。"
)


@dataclass
class ApiConfig:
    """`api` セクションの設定値。"""

    provider: str = "gemini"
    chat_model: str = "gemini-1.5-flash"
    embed_model: str = "models/text-embedding-004"


@dataclass
class ClusteringConfig:
    """`clustering` セクションの設定値。"""

    similarity_threshold: float = 0.70


@dataclass
class FilteringConfig:
    """`filtering` セクションの設定値。"""

    blacklisted_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_BLACKLISTED_KEYWORDS))
    llm_system_prompt: str = DEFAULT_LLM_SYSTEM_PROMPT


@dataclass
class GithubConfig:
    """`github` セクションの設定値。"""

    owner: str = ""
    repo: str = ""
    issue_similarity_threshold: float = 0.30


@dataclass
class PersonalKnowledgeConfig:
    """パイプライン設定ファイル全体を表すデータクラス。

    Attributes:
        api: API連携設定 (プロバイダ・モデル名)。
        clustering: Embeddingクラスタリング設定。
        filtering: 意図判定フィルタリング設定。
        github: GitHub連携設定。
    """

    api: ApiConfig = field(default_factory=ApiConfig)
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)
    filtering: FilteringConfig = field(default_factory=FilteringConfig)
    github: GithubConfig = field(default_factory=GithubConfig)


def load_config(config_path: Path | str | None = None) -> PersonalKnowledgeConfig:
    """`config.json` を読み込み、`PersonalKnowledgeConfig` を構築する。

    ファイルが存在しない場合や読み込みに失敗した場合は、サイレントに
    デフォルト値の `PersonalKnowledgeConfig` を返却する。

    Args:
        config_path: 設定ファイルパス。None の場合はデフォルトパス
            (`config/personal_knowledge_config.json`) を使用。

    Returns:
        PersonalKnowledgeConfig: 読み込まれた (またはデフォルトの) 設定。
    """
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH

    if not path.exists():
        logger.debug(f"Config file not found at {path}. Using default configuration.")
        return PersonalKnowledgeConfig()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load config file {path}: {e}. Using default configuration.")
        return PersonalKnowledgeConfig()

    api_data = data.get("api", {})
    clustering_data = data.get("clustering", {})
    filtering_data = data.get("filtering", {})
    github_data = data.get("github", {})

    return PersonalKnowledgeConfig(
        api=ApiConfig(
            provider=api_data.get("provider", ApiConfig.provider),
            chat_model=api_data.get("chat_model", ApiConfig.chat_model),
            embed_model=api_data.get("embed_model", ApiConfig.embed_model),
        ),
        clustering=ClusteringConfig(
            similarity_threshold=clustering_data.get("similarity_threshold", ClusteringConfig.similarity_threshold),
        ),
        filtering=FilteringConfig(
            blacklisted_keywords=filtering_data.get("blacklisted_keywords", list(DEFAULT_BLACKLISTED_KEYWORDS)),
            llm_system_prompt=filtering_data.get("llm_system_prompt", DEFAULT_LLM_SYSTEM_PROMPT),
        ),
        github=GithubConfig(
            owner=github_data.get("owner", ""),
            repo=github_data.get("repo", ""),
            issue_similarity_threshold=github_data.get(
                "issue_similarity_threshold", GithubConfig.issue_similarity_threshold
            ),
        ),
    )

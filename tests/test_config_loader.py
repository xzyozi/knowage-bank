"""config_loader モジュールの単体テスト。"""

from pathlib import Path
import tempfile

from personal_knowledge.config_loader import (
    DEFAULT_BLACKLISTED_KEYWORDS,
    PersonalKnowledgeConfig,
    load_config,
)


def test_load_config_returns_default_when_file_missing() -> None:
    """設定ファイルが存在しない場合、デフォルト値の PersonalKnowledgeConfig を返すこと。"""
    config = load_config(config_path="nonexistent_config.json")

    assert isinstance(config, PersonalKnowledgeConfig)
    assert config.api.provider == "gemini"
    assert config.api.chat_model == "gemini-1.5-flash"
    assert config.clustering.similarity_threshold == 0.70
    assert config.filtering.blacklisted_keywords == DEFAULT_BLACKLISTED_KEYWORDS
    assert config.github.issue_similarity_threshold == 0.30


def test_load_config_reads_custom_values_from_file() -> None:
    """設定ファイルに記載された値が正しく読み込まれること。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "custom_config.json"
        config_path.write_text(
            """{
                "api": {"provider": "ollama", "chat_model": "custom-model"},
                "clustering": {"similarity_threshold": 0.85},
                "filtering": {"blacklisted_keywords": ["foo", "bar"]},
                "github": {"owner": "myowner", "repo": "myrepo", "issue_similarity_threshold": 0.5}
            }""",
            encoding="utf-8",
        )

        config = load_config(config_path=config_path)

        assert config.api.provider == "ollama"
        assert config.api.chat_model == "custom-model"
        assert config.clustering.similarity_threshold == 0.85
        assert config.filtering.blacklisted_keywords == ["foo", "bar"]
        assert config.github.owner == "myowner"
        assert config.github.issue_similarity_threshold == 0.5


def test_load_config_returns_default_on_invalid_json() -> None:
    """設定ファイルの内容が不正なJSONの場合、サイレントにデフォルト値を返すこと。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "broken_config.json"
        config_path.write_text("{ invalid json", encoding="utf-8")

        config = load_config(config_path=config_path)

        assert config.api.provider == "gemini"

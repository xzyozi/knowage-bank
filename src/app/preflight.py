"""実行前設定を副作用なく診断するModule。"""

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
from typing import Literal

from app import config

PreflightTarget = Literal["issue-sync", "personal-knowledge"]


@dataclass(frozen=True)
class PreflightCheck:
    """個別の実行前診断結果。"""

    name: str
    is_error: bool
    message: str


def collect_preflight(target: PreflightTarget) -> list[PreflightCheck]:
    """指定した実行経路に必要なローカル設定と依存を確認する。"""
    if target not in ("issue-sync", "personal-knowledge"):
        raise ValueError(f"Unsupported preflight target: {target}")

    root_dir = Path(__file__).parents[2]
    checks = [
        PreflightCheck(
            "Python",
            sys.version_info < (3, 10),
            f"Python {sys.version_info.major}.{sys.version_info.minor} を使用中（3.10以上が必要）",
        ),
        PreflightCheck(
            ".env", not (root_dir / ".env").exists(), ".env が見つかりません。.env.sampleをコピーしてください。"
        ),
    ]

    if target == "issue-sync":
        checks.extend(
            [
                PreflightCheck("GitHub repository", not bool(config.GITHUB_REPOSITORY), "対象リポジトリが未設定です。"),
                PreflightCheck("LLM endpoint", not bool(config.OLLAMA_BASE_URL), "OLLAMA_BASE_URLが未設定です。"),
                PreflightCheck("LLM model", not bool(config.KNOWAGE_BANK_MODEL), "KNOWAGE_BANK_MODELが未設定です。"),
                PreflightCheck(
                    "MCP package", importlib.util.find_spec("mcp") is None, "mcpパッケージが見つかりません。"
                ),
                PreflightCheck(
                    "Deep Research",
                    False,
                    f"接続先: {config.DEEPRESEARCH_SSE_URL}（未接続時はIssue本文へフォールバック）",
                ),
            ]
        )
    else:
        checks.append(
            PreflightCheck("Gemini", False, "GEMINI_API_KEY未設定時は--no-geminiでローカルdry-runを実行できます。")
        )
    return checks


def has_errors(checks: list[PreflightCheck]) -> bool:
    """診断結果に実行を妨げる不足があるか返す。"""
    return any(check.is_error for check in checks)

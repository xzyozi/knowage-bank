"""
tools.base - LLM バックエンド、VRAM 管理、LLM クライアント、Aider 実行基盤モジュール。
"""

from tools.base.aider_base import (
    AiderBaseError,
    BaseAiderRunner,
    GitDiffBaseError,
    get_git_diff,
)
from tools.base.llm_client_base import (
    BaseLLMClient,
    extract_json_from_text,
)
from tools.base.vram_manager import (
    BackendAdapter,
    GpuLease,
    LlamaServerManager,
    OllamaController,
)

__all__ = [
    # VRAM & Backend
    "BackendAdapter",
    "GpuLease",
    "OllamaController",
    "LlamaServerManager",
    # LLM Client & JSON Parsing
    "BaseLLMClient",
    "extract_json_from_text",
    # Aider & Git
    "BaseAiderRunner",
    "get_git_diff",
    "AiderBaseError",
    "GitDiffBaseError",
]

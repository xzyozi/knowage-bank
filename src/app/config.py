import os
from dotenv import load_dotenv

# プロジェクトルートの .env をロード
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))

KNOWAGE_BANK_MODEL = os.getenv("KNOWAGE_BANK_MODEL") or os.getenv("KNOWLEGE_BANK_MODEL", "ollama/qwen3-coder:30b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# GitHub 連携用 (一意なプロジェクト用環境変数を優先しつつ、標準環境変数にフォールバック)
GITHUB_REPOSITORY = os.getenv("KNOWAGE_BANK_GITHUB_REPOSITORY") or os.getenv("GITHUB_REPOSITORY")
GITHUB_TOKEN = os.getenv("KNOWAGE_BANK_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")


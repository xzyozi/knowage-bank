import os
from dotenv import load_dotenv

# プロジェクトルートの .env をロード
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))

KNOWLEGE_BANK_MODEL = os.getenv("KNOWLEGE_BANK_MODEL", "ollama/qwen3-coder:30b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


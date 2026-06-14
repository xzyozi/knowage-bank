import os
from dotenv import load_dotenv

# プロジェクトルートの .env をロード
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LOCAL_MODEL_PATH = os.getenv("LOCAL_LLM_MODEL", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "")

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RUNTIME_DIR = ROOT / "runtime"
INCIDENTS_DIR = DATA_DIR / "incidents"
DB_PATH = RUNTIME_DIR / "transactions.db"
CHROMA_DIR = RUNTIME_DIR / "chroma"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen3.5:4b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "qwen3-embedding:0.6b")
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "10"))

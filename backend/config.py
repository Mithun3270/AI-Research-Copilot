import os
from pathlib import Path
from dotenv import load_dotenv

# Base Paths (Windows compatible)
BACKEND_DIR = Path(__file__).resolve().parent
BASE_DIR = BACKEND_DIR.parent
DATA_DIR = BASE_DIR / "data"
PAPERS_DIR = BASE_DIR / "research_papers"
EXTRACTED_TEXT_DIR = BASE_DIR / "extracted_text"
VECTOR_DB_DIR = BASE_DIR / "vector_db"
OUTPUTS_DIR = BASE_DIR / "outputs"
UPLOADS_DIR = BACKEND_DIR / "uploads"

# Ensure all vital runtime directories exist
for directory in [DATA_DIR, PAPERS_DIR, EXTRACTED_TEXT_DIR, VECTOR_DB_DIR, OUTPUTS_DIR, UPLOADS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE)
load_dotenv(dotenv_path=BACKEND_DIR / ".env")

class Settings:
    PROJECT_NAME: str = "AI Research Copilot"
    VERSION: str = "1.0.0"
    
    # Security / JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey_research_copilot_change_in_production_987654321")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24
    RESET_TOKEN_EXPIRE_HOURS: int = 1
    
    # Database (SQLite default stored in root/data/research_copilot.db)
    DEFAULT_SQLITE_URL = f"sqlite:///{str((DATA_DIR / 'research_copilot.db').as_posix())}"
    DATABASE_URL: str = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)
    
    # SMTP / Email
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "no-reply@airesearchcopilot.local")
    
    # Frontend URL (for verification & reset links)
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    # Local AI / LLM Configuration
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    CATEGORY_SIMILARITY_THRESHOLD: float = float(os.getenv("CATEGORY_SIMILARITY_THRESHOLD", "0.55"))

settings = Settings()

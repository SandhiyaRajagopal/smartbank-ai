"""Central settings, loaded once from environment variables / the .env file.

load_dotenv() runs first so that LangSmith's LANGSMITH_* variables are in
os.environ before any LangChain/LangGraph module is imported - that is all
LangSmith needs to start tracing every graph run automatically.
"""
import secrets
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    google_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    # Production on GCP: use Vertex AI with the service account instead of an API key.
    use_vertexai: bool = False
    gcp_project: str = ""
    gcp_location: str = "asia-south1"

    # empty -> a random secret is generated at startup (logins then reset when the server restarts)
    jwt_secret: str = ""
    jwt_expire_minutes: int = 12 * 60
    database_url: str = f"sqlite:///{(ROOT_DIR / 'data' / 'smartbank.db').as_posix()}"
    checkpoint_db: str = str(ROOT_DIR / "data" / "checkpoints.db")
    chroma_dir: str = str(ROOT_DIR / "data" / "chroma_store")
    policies_dir: str = str(ROOT_DIR / "docs" / "policies")
    frontend_dist: str = str(ROOT_DIR / "frontend" / "dist")

    simulator_enabled: bool = True
    simulator_interval: int = 20
    chat_rate_limit_per_min: int = 20

    @property
    def llm_configured(self) -> bool:
        return bool(self.google_api_key) or self.use_vertexai


settings = Settings()
if len(settings.jwt_secret) < 32:
    settings.jwt_secret = secrets.token_urlsafe(48)
(ROOT_DIR / "data").mkdir(exist_ok=True)

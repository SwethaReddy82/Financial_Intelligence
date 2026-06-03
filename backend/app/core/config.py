from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root .env — stable regardless of cwd when uvicorn starts
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    database_url: str = (
        "postgresql+asyncpg://wealth:wealth@localhost:5432/wealth_copilot"
    )

    backend_cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    sec_user_agent: str = "WealthCopilot contact@example.com"
    sec_tickers: str = "AAPL,RJF,JPM,MS,GS,SCHW"

    confidence_refuse_threshold: float = 0.35
    confidence_cautious_threshold: float = 0.55

    retrieval_top_k: int = 10
    retrieval_comparative_top_k: int = 12
    retrieval_candidate_k: int = 40
    retrieval_max_chunk_chars: int = 1800
    domain_relevance_threshold: float = 0.45
    retrieval_min_top_similarity: float = 0.55
    debug_retrieval: bool = True

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def ticker_list(self) -> list[str]:
        return [t.strip().upper() for t in self.sec_tickers.split(",") if t.strip()]

    @property
    def data_raw_dir(self) -> Path:
        return _PROJECT_ROOT / "data" / "raw"

    @property
    def openai_configured(self) -> bool:
        key = (self.openai_api_key or "").strip()
        if not key:
            return False
        placeholders = ("sk-your-key-here", "sk-your-", "changeme", "your-key")
        return not any(p in key.lower() for p in placeholders)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

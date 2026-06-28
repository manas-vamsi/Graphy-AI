"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    app_name: str = "Graphy AI"
    database_url: str = f"sqlite:///{(DATA_DIR / 'graphy.db').as_posix()}"
    chroma_path: str = str(DATA_DIR / "chroma")
    upload_dir: str = str(DATA_DIR / "uploads")
    evidence_dir: str = str(DATA_DIR / "evidence")

    # LLM provider abstraction: "gemini" | "groq" | "openrouter" | "ollama"
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "gemma4"
    ollama_embed_model: str = "embeddinggemma"

    # Embeddings: "local" (ChromaDB all-MiniLM-L6, no key) | "ollama"
    embed_backend: str = "local"

    # Scraping / discovery (Phase 2)
    scrapegraphai_api_key: str = ""
    jina_api_key: str = ""
    google_cse_api_key: str = ""
    google_cse_cx: str = ""

    # GitHub (Phase 2) — two accounts
    github_token: str = ""
    github_token_secondary: str = ""
    github_username: str = ""
    github_username_secondary: str = ""

    # Gmail (Phase 4)
    google_oauth_client_id: str = ""
    google_client_secrets: str = "./secrets/gmail_oauth.json"
    google_token_path: str = "./secrets/gmail_token.json"

    # ---- Security ----
    # Optional API-key gate for the backend. Empty = OFF (rely on 127.0.0.1 binding).
    # Set GRAPHY_API_KEY to require an X-API-Key header on mutating endpoints.
    api_key: str = ""
    # Fernet key for encrypting sensitive data at rest (credentials, OAuth tokens).
    # If empty, one is generated and stored in data/encryption.key (chmod 600).
    encryption_key: str = ""
    max_upload_mb: int = 10
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    def ensure_dirs(self) -> None:
        for p in (DATA_DIR, Path(self.upload_dir), Path(self.evidence_dir), Path(self.chroma_path)):
            Path(p).mkdir(parents=True, exist_ok=True)


settings = Settings()

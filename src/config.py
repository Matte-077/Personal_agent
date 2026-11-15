import os
from typing import Set, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application configuration via environment variables.
    """
    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    ALLOWED_TELEGRAM_USER_IDS: str = ""

    # Google Gemini AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"

    # Jina AI Reader Bridge
    JINA_API_KEY: Optional[str] = None
    JINA_TIMEOUT: float = 12.0

    # Instagram: session cookies from secondary/burner account for yt-dlp.
    # Accepts raw Netscape cookies.txt content or file path.
    # NEVER commit real cookies: configure only via environment variables.
    INSTAGRAM_COOKIES: Optional[str] = None
    IG_SESSIONID: Optional[str] = None
    IG_CSRFTOKEN: Optional[str] = None
    IG_USER_ID: Optional[str] = None

    # RapidAPI Instagram Scraper (Optional fallback, free tier sufficient)
    RAPIDAPI_KEY: Optional[str] = None
    RAPIDAPI_INSTAGRAM_HOST: str = "instagram-scraper-api2.p.rapidapi.com"
    INSTAGRAM_TIMEOUT: float = 12.0

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_SECRET_KEY: str = ""
    DEFAULT_MATCH_THRESHOLD: float = 0.30

    @property
    def supabase_key(self) -> str:
        """Returns backend key (accepts either SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY)."""
        return self.SUPABASE_SECRET_KEY or self.SUPABASE_SERVICE_ROLE_KEY

    # Operating Mode (Dual-Mode: Cloud vs Local)
    # BOT_MODE: 'webhook' (default for Render/Cloud) or 'polling' (for local PC, NAS, Raspberry Pi behind NAT)
    BOT_MODE: str = "webhook"

    # Database Provider: 'supabase' (Cloud PostgreSQL + pgvector) or 'sqlite' (100% autonomous local)
    DB_PROVIDER: str = "supabase"
    SQLITE_DB_PATH: str = "data/agente.db"
    LOCAL_STORAGE_DIR: str = "data/storage"

    # AI Provider: 'gemini' (default, cloud free-tier) or 'ollama' (100% offline local)
    AI_PROVIDER: str = "gemini"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    # Local Runner Options
    AUTO_OPEN_BROWSER: bool = False
    LOCAL_NOTIFY_ON_BOOT: bool = True

    # Server & Hosting (Render or Local)
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    WEBHOOK_URL: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_user_ids(self) -> Set[int]:
        """
        Returns a set of integers containing authorized Telegram IDs.
        Example: "12345, 67890" -> {12345, 67890}
        """
        if not self.ALLOWED_TELEGRAM_USER_IDS:
            return set()

        if isinstance(self.ALLOWED_TELEGRAM_USER_IDS, (list, set, tuple)):
            ids: Set[int] = set()
            for x in self.ALLOWED_TELEGRAM_USER_IDS:
                try:
                    ids.add(int(x))
                except (ValueError, TypeError):
                    pass
            return ids

        ids: Set[int] = set()
        for item in str(self.ALLOWED_TELEGRAM_USER_IDS).split(","):
            cleaned = item.strip()
            if cleaned and cleaned.isdigit():
                ids.add(int(cleaned))
        return ids

    def is_user_allowed(self, user_id: int | str | None) -> bool:
        """
        Checks whether a given Telegram user_id is in the allowlist.
        If allowlist is empty, denies all requests for security (fail-closed).
        """
        if user_id is None:
            return False
        
        allowed = self.allowed_user_ids
        if not allowed:
            return False
        
        try:
            return int(user_id) in allowed
        except (ValueError, TypeError):
            return False


settings = Settings()

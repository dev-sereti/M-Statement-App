from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Load .env, but do NOT auto-JSON-decode complex types (we'll parse ourselves)
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        enable_decoding=False,  # important: stops pydantic-settings from json.loads on lists
    )

    # Application
    APP_NAME: str = "MPesa Statement Processor"
    DEBUG: bool = False
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))

    # File handling
    MAX_FILE_SIZE_MB: int = 10
    UPLOAD_DIR: Path = Path("/tmp/mpesa_uploads")
    OUTPUT_DIR: Path = Path("/tmp/mpesa_outputs")
    FILE_RETENTION_MINUTES: int = 30

    # Security
    MAX_PIN_ATTEMPTS: int = 3
    RATE_LIMIT_PER_MINUTE: int = 10
    SESSION_EXPIRE_MINUTES: int = 30

    # Lists (we parse from env)
    ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    ALLOWED_HOSTS: List[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])

    @field_validator("ALLOWED_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def _parse_list_env(cls, v):
        """
        Accept:
          - JSON list: ["http://a","http://b"]
          - Comma-separated: http://a,http://b
          - Already-a-list (for tests/code)
        """
        if v is None:
            return v
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            # Try JSON first
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                pass
            # Fallback: comma-separated
            return [p.strip() for p in raw.split(",") if p.strip()]

        # Anything else -> force to list
        return [str(v).strip()]

    def ensure_dirs(self) -> None:
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
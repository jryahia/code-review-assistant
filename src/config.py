"""Application configuration using Pydantic Settings."""

from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path
from typing import List, Optional

from cryptography.fernet import Fernet
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Code Review Assistant"
    debug: bool = False
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8765

    # Database
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR}/reviews.db"

    # GitHub
    github_token: str = ""
    github_webhook_secret: str = ""

    # AI Provider
    ai_provider: str = "off"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    claude_api_key: str = ""
    claude_model: str = "claude-3-5-sonnet-20241022"

    # Analysis defaults
    default_categories: str = "bugs,security,style,performance,architecture"
    max_file_size_kb: int = 500
    poll_interval_seconds: int = 300

    # Encryption
    encryption_key: str = ""

    @property
    def default_categories_list(self) -> List[str]:
        return [c.strip() for c in self.default_categories.split(",") if c.strip()]

    @property
    def fernet(self) -> Fernet:
        key = self.encryption_key
        if not key:
            key_path = DATA_DIR / ".enc_key"
            if key_path.exists():
                key = key_path.read_text().strip()
            else:
                key = Fernet.generate_key().decode()
                key_path.write_text(key)
                key_path.chmod(0o600)
        if isinstance(key, str):
            key_bytes = key.encode()
        else:
            key_bytes = key
        # Validate it's a valid Fernet key
        try:
            return Fernet(key_bytes)
        except Exception:
            # Generate a new valid key if stored one is invalid
            new_key = Fernet.generate_key()
            key_path = DATA_DIR / ".enc_key"
            key_path.write_text(new_key.decode())
            key_path.chmod(0o600)
            return Fernet(new_key)

    def encrypt(self, value: str) -> str:
        if not value:
            return ""
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        if not value:
            return ""
        try:
            return self.fernet.decrypt(value.encode()).decode()
        except Exception:
            return value

    @property
    def data_dir(self) -> Path:
        return DATA_DIR

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.database_url or "postgres" in self.database_url


settings = Settings()

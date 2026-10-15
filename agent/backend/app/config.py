"""
Application configuration for EVA Agent Backend using pydantic-settings.
Enforces hard security invariants at boot time.
"""

from __future__ import annotations

import os
from typing import Literal
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../env/.env.example"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: Literal["dev", "eval", "prod"] = "dev"
    JWT_SECRET: str = "dev-jwt-secret-key-must-be-at-least-32-chars-long!"
    DATABASE_URL: str = "sqlite+aiosqlite:///./agent.db"
    WORKSPACE_ROOT: str = "./workspace"

    SEED_ADMIN_EMAIL: str = "admin@eva.local"
    SEED_ADMIN_PASSWORD: str = "AdminPassword123!"
    SEED_USER_EMAIL: str = "user@eva.local"
    SEED_USER_PASSWORD: str = "UserPassword123!"

    GMAIL_MODE: Literal["real", "mock"] = "mock"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/oauth/gmail/callback"
    TOKEN_ENC_KEY: str = "dGhpc2lzYTMyeS1ieXRlcy1mZXJuZXQta2V5LTEyMzQ1Njc="
    GMAIL_SEND_ALLOWLIST: str = ""

    OLLAMA_BASE_URL: str = "https://ollama.com"
    OLLAMA_API_KEY: str = ""
    OLLAMA_MODEL: str = "llama3.1"

    GUARD_TRANSPORT: Literal["inprocess", "http"] = "inprocess"
    GUARD_SERVICE_URL: str = "http://localhost:8100"
    GUARD_SERVICE_TOKEN: str = "dev-guard-token"
    GUARD_PROFILE: Literal["off", "basic", "full"] = "full"
    MAX_STEPS: int = 12

    # Failure injection hooks (only active when APP_ENV=eval)
    INJECT_TIER2_DOWN: bool = False
    INJECT_GUARD_UNREACHABLE: bool = False
    INJECT_LAYA_TIMEOUT: bool = False

    @model_validator(mode="after")
    def validate_security_invariants(self) -> Settings:
        # Hard Rule 1: GUARD_PROFILE=off|basic is allowed only when APP_ENV=eval
        if self.GUARD_PROFILE in ("off", "basic") and self.APP_ENV != "eval":
            raise ValueError(
                f"GUARD_PROFILE='{self.GUARD_PROFILE}' is forbidden when APP_ENV='{self.APP_ENV}'. "
                f"Only 'full' is permitted outside 'eval'."
            )

        # Hard Rule 2: Security tests/evals run only with GMAIL_MODE=mock
        if self.APP_ENV == "eval" and self.GMAIL_MODE == "real":
            raise ValueError(
                "Security eval environment (APP_ENV=eval) cannot run with GMAIL_MODE=real. "
                "Must be set to GMAIL_MODE=mock."
            )

        return self


settings = Settings()

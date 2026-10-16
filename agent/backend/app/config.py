"""
Application configuration for EVA Agent Backend using pydantic-settings.
Enforces hard security invariants at boot time.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_DIR = Path(__file__).resolve().parents[3] / "env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files override earlier ones; real process env vars override all files.
        # Resolved from this file, not the CWD: defaults < env/.env (git-ignored secrets) < ./.env.
        env_file=(str(_ENV_DIR / ".env.example"), str(_ENV_DIR / ".env"), ".env"),
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

    TELEGRAM_MODE: Literal["real", "mock"] = "mock"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ALLOWLIST: str = ""

    OLLAMA_BASE_URL: str = "https://ollama.com"
    OLLAMA_API_KEY: str = ""
    OLLAMA_MODEL: str = "gpt-oss:20b"

    # web.search backend: "mock" (default; always used in eval) or "ollama" (Ollama web-search API)
    WEB_SEARCH_PROVIDER: Literal["mock", "ollama"] = "mock"

    GUARD_TRANSPORT: Literal["inprocess", "http"] = "inprocess"
    GUARD_SERVICE_URL: str = "http://localhost:8100"
    GUARD_SERVICE_TOKEN: str = "dev-guard-token"
    GUARD_PROFILE: Literal["off", "basic", "full"] = "full"
    MAX_STEPS: int = 12

    # Failure injection hooks (only active when APP_ENV=eval)
    INJECT_TIER2_DOWN: bool = Field(False, validation_alias=AliasChoices("EVA_FAIL_TIER2_DOWN", "INJECT_TIER2_DOWN"))
    INJECT_GUARD_UNREACHABLE: bool = Field(
        False, validation_alias=AliasChoices("EVA_FAIL_GUARD_UNREACHABLE", "INJECT_GUARD_UNREACHABLE")
    )
    INJECT_LAYA_TIMEOUT: bool = Field(False, validation_alias=AliasChoices("EVA_FAIL_LAYA_TIMEOUT", "INJECT_LAYA_TIMEOUT"))

    @field_validator("DATABASE_URL")
    @classmethod
    def normalise_sqlite_driver(cls, v: str) -> str:
        """Accept plain sqlite:/// (as written in doc 03) and use the async driver."""
        if v.startswith("sqlite:///"):
            return "sqlite+aiosqlite:///" + v[len("sqlite:///"):]
        return v

    @model_validator(mode="after")
    def validate_security_invariants(self) -> Settings:
        # Hard Rule 1: GUARD_PROFILE=off|basic is allowed only when APP_ENV=eval
        if self.GUARD_PROFILE in ("off", "basic") and self.APP_ENV != "eval":
            raise ValueError(
                f"GUARD_PROFILE='{self.GUARD_PROFILE}' is forbidden when APP_ENV='{self.APP_ENV}'. "
                f"Only 'full' is permitted outside 'eval'."
            )

        # Failure-injection flags are refused outside eval (never silently honoured)
        if self.APP_ENV != "eval" and (
            self.INJECT_TIER2_DOWN or self.INJECT_GUARD_UNREACHABLE or self.INJECT_LAYA_TIMEOUT
        ):
            raise ValueError(
                f"EVA_FAIL_* failure-injection flags are forbidden when APP_ENV='{self.APP_ENV}'. "
                f"They are only permitted when APP_ENV='eval'."
            )

        if self.APP_ENV == "eval" and self.WEB_SEARCH_PROVIDER != "mock":
            raise ValueError("WEB_SEARCH_PROVIDER must be 'mock' when APP_ENV='eval' (mock web only).")

        # Hard Rule 2: Security tests/evals run only with GMAIL_MODE=mock and TELEGRAM_MODE=mock
        if self.APP_ENV == "eval" and self.GMAIL_MODE == "real":
            raise ValueError(
                "Security eval environment (APP_ENV=eval) cannot run with GMAIL_MODE=real. "
                "Must be set to GMAIL_MODE=mock."
            )
        if self.APP_ENV == "eval" and self.TELEGRAM_MODE == "real":
            raise ValueError(
                "Security eval environment (APP_ENV=eval) cannot run with TELEGRAM_MODE=real. "
                "Must be set to TELEGRAM_MODE=mock."
            )

        return self


settings = Settings()

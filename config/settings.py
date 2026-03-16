import re

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    CLOUDLENS_POLL_INTERVAL: int = 300
    CLOUDLENS_AUTH_DISABLED: bool = False
    CLOUDLENS_AUTH_PUBLIC_PATHS: str = (
        "/health,/metrics,/static,/docs,/openapi.json,/api/events,/api/auth/status"
    )
    CLOUDLENS_CORS_ORIGINS: str = "*"
    CLOUDLENS_API_KEY: str = ""
    ENABLED_PROVIDERS: str = "azure"
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL: str = "claude-sonnet-4-20250514"
    DB_PATH: str = "data/cloudlens.db"
    SNAPSHOT_RETENTION: int = 100

    model_config = {"env_prefix": "", "case_sensitive": True}


settings = Settings()


def get_env(account_name: str) -> str:
    """Derive environment from an account/subscription name suffix."""
    for e in ("dev", "stg", "prd", "global"):
        if account_name.endswith(f"-{e}") or account_name == e:
            return e
    return "other"


def derive_product(account_name: str) -> str:
    """Derive product name by stripping environment suffix."""
    return re.sub(r"-(dev|stg|prd|global)$", "", account_name)

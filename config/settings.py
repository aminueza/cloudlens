import re
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings

_BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    CLOUDLENS_POLL_INTERVAL: int = 300
    CLOUDLENS_AUTH_DISABLED: bool = False
    CLOUDLENS_AUTH_PUBLIC_PATHS: str = (
        "/health,/metrics,/static,/docs,/openapi.json,/api/events,/api/auth/status"
    )
    CLOUDLENS_CORS_ORIGINS: str = "*"
    ENABLED_PROVIDERS: str = "azure"
    ACCOUNTS_FILE: str = "config/accounts.yaml"
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL: str = "claude-sonnet-4-20250514"
    DB_PATH: str = "data/cloudlens.db"
    SNAPSHOT_RETENTION: int = 100

    model_config = {"env_prefix": "", "case_sensitive": True}


settings = Settings()


def _load_accounts(path: str | None = None) -> dict:
    p = Path(path) if path else _BASE_DIR / "accounts.yaml"
    with open(p) as f:
        data: dict = yaml.safe_load(f)
    return data.get("providers", {})


ACCOUNTS: dict = _load_accounts()


def _derive_account_names() -> list[str]:
    names: list[str] = []
    for provider_cfg in ACCOUNTS.values():
        if isinstance(provider_cfg, dict):
            for key in ("subscriptions", "accounts", "projects"):
                if key in provider_cfg:
                    section = provider_cfg[key]
                    if isinstance(section, dict):
                        names.extend(section.keys())
    return names


ALL_ACCOUNT_NAMES: list[str] = _derive_account_names()

ACCOUNT_TO_PRODUCT: dict[str, str] = {
    name: re.sub(r"-(dev|stg|prd|global)$", "", name) for name in ALL_ACCOUNT_NAMES
}

PRODUCTS: list[str] = sorted(set(ACCOUNT_TO_PRODUCT.values()))


def get_env(account_name: str) -> str:
    for e in ("dev", "stg", "prd", "global"):
        if account_name.endswith(f"-{e}") or account_name == e:
            return e
    return "other"


def get_azure_subscriptions() -> dict[str, str]:
    azure_cfg = ACCOUNTS.get("azure", {})
    subs: dict[str, str] = azure_cfg.get("subscriptions", {})
    return subs


def get_aws_accounts() -> dict[str, dict]:
    return ACCOUNTS.get("aws", {}).get("accounts", {})


def get_gcp_projects() -> dict[str, dict]:
    return ACCOUNTS.get("gcp", {}).get("projects", {})

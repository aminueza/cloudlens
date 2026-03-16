from config.settings import ACCOUNTS, ALL_ACCOUNT_NAMES, PRODUCTS, get_env


def test_accounts_loaded():
    assert len(ACCOUNTS) > 0


def test_products_derived():
    assert "webapp" in PRODUCTS
    assert "database" in PRODUCTS


def test_account_names():
    assert "webapp-dev" in ALL_ACCOUNT_NAMES
    assert "webapp-prd" in ALL_ACCOUNT_NAMES


def test_get_env():
    assert get_env("webapp-dev") == "dev"
    assert get_env("webapp-prd") == "prd"
    assert get_env("monitoring-global") == "global"
    assert get_env("something") == "other"

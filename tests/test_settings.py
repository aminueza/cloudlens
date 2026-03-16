from config.settings import ACCOUNTS, ALL_ACCOUNT_NAMES, PRODUCTS, get_env


def test_accounts_loaded():
    assert len(ACCOUNTS) > 0


def test_products_derived():
    assert "cnct" in PRODUCTS
    assert "aiplatform" in PRODUCTS


def test_account_names():
    assert "cnct-dev" in ALL_ACCOUNT_NAMES
    assert "cnct-prd" in ALL_ACCOUNT_NAMES


def test_get_env():
    assert get_env("cnct-dev") == "dev"
    assert get_env("cnct-prd") == "prd"
    assert get_env("connectivity-global") == "global"
    assert get_env("something") == "other"

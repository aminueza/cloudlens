from config.settings import derive_product, get_env


def test_get_env():
    assert get_env("webapp-dev") == "dev"
    assert get_env("webapp-prd") == "prd"
    assert get_env("monitoring-global") == "global"
    assert get_env("something") == "other"


def test_derive_product():
    assert derive_product("webapp-dev") == "webapp"
    assert derive_product("webapp-prd") == "webapp"
    assert derive_product("monitoring-global") == "monitoring"
    assert derive_product("standalone") == "standalone"

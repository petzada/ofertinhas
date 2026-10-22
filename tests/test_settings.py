import pytest

from ofertinhas.settings import Settings, SettingsError, new_token


def test_from_env_parses_values(tmp_path):
    s = Settings.from_env({
        "OFERTINHAS_DATA_DIR": str(tmp_path),
        "API_PORT": "9000",
        "EXTENSION_TOKEN": "tok",
        "ADMIN_CHAT_ID": "12345",
        "WHATSMIAU_API_KEY": "k",
        "WHATSMIAU_INSTANCE": "Ofertas01",
    })
    assert s.data_dir == tmp_path.resolve()
    assert s.api_port == 9000
    assert s.admin_chat_id == 12345
    assert s.whatsmiau_base_url == "https://api.whatsmiau.dev/v2"
    assert s.config_path.name == "config.yaml"


def test_missing_values_are_none():
    s = Settings.from_env({})
    assert s.extension_token is None and s.admin_chat_id is None
    assert s.api_port == 8765


def test_require_lists_missing_names():
    s = Settings.from_env({"EXTENSION_TOKEN": "tok"})
    with pytest.raises(SettingsError, match="TELEGRAM_BOT_TOKEN.*ADMIN_CHAT_ID"):
        s.require("EXTENSION_TOKEN", "TELEGRAM_BOT_TOKEN", "ADMIN_CHAT_ID")


def test_invalid_int_is_reported():
    with pytest.raises(SettingsError, match="ADMIN_CHAT_ID"):
        Settings.from_env({"ADMIN_CHAT_ID": "abc"})


def test_new_token_is_long_and_unique():
    a, b = new_token(), new_token()
    assert a != b and len(a) >= 40

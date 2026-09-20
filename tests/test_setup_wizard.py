import json
from unittest.mock import patch

from jev_local.setup_wizard import ask_api_key, auth_headers, save_config


def test_ask_api_key_returns_none_when_user_says_no():
    with patch("builtins.input", return_value="h"):
        assert ask_api_key() is None


def test_ask_api_key_reads_secret_with_getpass():
    with patch("builtins.input", return_value="e"), patch(
        "jev_local.setup_wizard.getpass", return_value="secret-key"
    ):
        assert ask_api_key() == "secret-key"


def test_auth_headers_only_adds_bearer_when_key_exists():
    assert auth_headers(None) == {}
    assert auth_headers("secret-key") == {"Authorization": "Bearer secret-key"}


def test_save_config_persists_key_and_restricts_permissions(tmp_path):
    provider = {"name": "Custom", "type": "openai"}
    config_file = save_config(
        provider,
        "model",
        8000,
        "http://localhost:8000",
        4096,
        "secret-key",
        config_dir=tmp_path,
    )

    data = json.loads(config_file.read_text())
    assert data["api_key"] == "secret-key"
    assert config_file.stat().st_mode & 0o777 == 0o600

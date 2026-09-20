from unittest.mock import patch

from jev_local.setup_wizard import ensure_port_available, select_jev_port


def test_select_jev_port_accepts_custom_port():
    with patch("builtins.input", return_value="5454"):
        assert select_jev_port() == 5454


def test_select_jev_port_uses_default():
    with patch("builtins.input", return_value=""):
        assert select_jev_port() == 3030


def test_ensure_port_available_stops_only_existing_jev_service():
    with patch("jev_local.setup_wizard.is_port_in_use", side_effect=[True, False]), patch(
        "jev_local.setup_wizard.subprocess.run"
    ) as run:
        ensure_port_available(5454)

    run.assert_called_once_with(
        ["systemctl", "--user", "stop", "jev-local.service"],
        check=False,
        capture_output=True,
        text=True,
    )


def test_ensure_port_available_refuses_to_kill_unrelated_listener():
    with patch("jev_local.setup_wizard.is_port_in_use", return_value=True), patch(
        "jev_local.setup_wizard.subprocess.run"
    ):
        try:
            ensure_port_available(5454)
        except RuntimeError as exc:
            assert "başka bir süreç" in str(exc)
        else:
            raise AssertionError("occupied port must fail safely")

# SPDX-License-Identifier: MIT
import sys
import pytest
from unittest.mock import patch, MagicMock

import vpn_switcher.cli as vpn_switcher_cli


@pytest.fixture(autouse=True)
def clear_config_file(tmp_path):
    # Override CONFIG_PATH to a temp file for isolation
    vpn_switcher_cli.CONFIG_PATH = tmp_path / "config.yaml"
    yield
    # Cleanup handled by tmp_path


def test_load_config_nonexistent_file(tmp_path):
    # If file doesn't exist, load_config returns {}
    vpn_switcher_cli.CONFIG_PATH = tmp_path / "nonexistent.yaml"
    assert vpn_switcher_cli.load_config() == {}


def test_load_config_existing_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("foo: bar\n")
    vpn_switcher_cli.CONFIG_PATH = config_path
    loaded = vpn_switcher_cli.load_config()
    assert loaded == {"foo": "bar"}


def test_save_config_writes_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    vpn_switcher_cli.CONFIG_PATH = config_path
    data = {"a": 1}
    vpn_switcher_cli.save_config(data)
    content = config_path.read_text()
    assert "a: 1" in content


@patch("vpn_switcher.cli.dbus.SystemBus")
def test_get_vpn_uuid_by_name_found(mock_system_bus):
    mock_bus = MagicMock()
    mock_system_bus.return_value = mock_bus

    mock_settings_obj = MagicMock()
    mock_iface = MagicMock()
    mock_bus.get_object.return_value = mock_settings_obj
    mock_iface.ListConnections.return_value = ["/conn1"]

    mock_conn_obj = MagicMock()
    mock_conn_iface = MagicMock()
    mock_bus.get_object.side_effect = [mock_settings_obj, mock_conn_obj]
    mock_conn_iface.GetSettings.return_value = {
        "connection": {
            "type": "vpn",
            "id": "vpn-name",
            "uuid": "vpn-uuid-123"
        }
    }

    # Patch Interface call to return mock_iface or mock_conn_iface accordingly
    def interface_side_effect(obj, iface_name):
        if iface_name == "org.freedesktop.NetworkManager.Settings":
            return mock_iface
        elif iface_name == "org.freedesktop.NetworkManager.Settings.Connection":
            return mock_conn_iface
        raise ValueError("Unexpected interface")

    with patch("vpn_switcher.cli.dbus.Interface", side_effect=interface_side_effect):
        uuid = vpn_switcher_cli.get_vpn_uuid_by_name("vpn-name")
        assert uuid == "vpn-uuid-123"


@patch("vpn_switcher.cli.dbus.SystemBus")
def test_get_vpn_uuid_by_name_not_found(mock_system_bus):
    mock_bus = MagicMock()
    mock_system_bus.return_value = mock_bus

    mock_settings_obj = MagicMock()
    mock_iface = MagicMock()
    mock_bus.get_object.return_value = mock_settings_obj
    mock_iface.ListConnections.return_value = ["/conn1"]

    mock_conn_obj = MagicMock()
    mock_conn_iface = MagicMock()
    mock_bus.get_object.side_effect = [mock_settings_obj, mock_conn_obj]
    mock_conn_iface.GetSettings.return_value = {
        "connection": {
            "type": "vpn",
            "id": "other-vpn",
            "uuid": "vpn-uuid-123"
        }
    }

    def interface_side_effect(obj, iface_name):
        if iface_name == "org.freedesktop.NetworkManager.Settings":
            return mock_iface
        elif iface_name == "org.freedesktop.NetworkManager.Settings.Connection":
            return mock_conn_iface
        raise ValueError("Unexpected interface")

    with patch("vpn_switcher.cli.dbus.Interface", side_effect=interface_side_effect):
        with pytest.raises(ValueError, match="No VPN found with name 'missing-vpn'"):
            vpn_switcher_cli.get_vpn_uuid_by_name("missing-vpn")


@patch("vpn_switcher.cli.save_config")
@patch("vpn_switcher.cli.get_vpn_uuid_by_name", return_value="uuid-123")
@patch("vpn_switcher.cli.load_config", return_value={})
def test_cmd_add(mock_load, mock_get_uuid, mock_save, capsys):
    class Args:
        ssid = "myssid"
        interface = None
        vpn = "vpnname"

    vpn_switcher_cli.cmd_add(Args())
    mock_save.assert_called_once()
    out = capsys.readouterr().out
    assert "Added rule" in out


@patch("vpn_switcher.cli.save_config")
@patch("vpn_switcher.cli.load_config", return_value={
    "trusted_connections": [
        {"ssid": "ssid1", "vpn_uuid": "uuid1"},
        {"interface": "eth0", "vpn_uuid": "uuid2"},
    ]
})
def test_cmd_remove(mock_load, mock_save, capsys):
    class Args:
        ssid = "ssid1"
        interface = None

    vpn_switcher_cli.cmd_remove(Args())
    mock_save.assert_called_once()
    out = capsys.readouterr().out
    assert "Removed 1 matching rule" in out


@patch("vpn_switcher.cli.load_config", return_value={
    "trusted_connections": [
        {"ssid": "ssid1", "vpn_uuid": "uuid1"},
        {"interface": "eth0", "vpn_uuid": "uuid2"},
    ],
    "fallback_vpn_uuid": "fallback-uuid"
})
def test_cmd_list(mock_load, capsys):
    class Args:
        pass

    vpn_switcher_cli.cmd_list(Args())
    out = capsys.readouterr().out
    assert "Trusted Connections:" in out
    assert "- {'ssid': 'ssid1', 'vpn_uuid': 'uuid1'}" in out or "- {'interface': 'eth0', 'vpn_uuid': 'uuid2'}" in out
    assert "Fallback VPN UUID: fallback-uuid" in out


@patch("vpn_switcher.cli.save_config")
@patch("vpn_switcher.cli.get_vpn_uuid_by_name", return_value="uuid-fallback")
@patch("vpn_switcher.cli.load_config", return_value={})
def test_cmd_set_fallback(mock_load, mock_get_uuid, mock_save, capsys):
    class Args:
        vpn = "vpnname"

    vpn_switcher_cli.cmd_set_fallback(Args())
    mock_save.assert_called_once()
    out = capsys.readouterr().out
    assert "Set fallback VPN to: uuid-fallback" in out


@patch("vpn_switcher.cli.cmd_add")
@patch("vpn_switcher.cli.cmd_remove")
@patch("vpn_switcher.cli.cmd_list")
@patch("vpn_switcher.cli.cmd_set_fallback")
def test_main_calls_correct_func(
        mock_set_fallback,
        mock_list,
        mock_remove,
        mock_add):
    parser = vpn_switcher_cli.argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    # Add subcommands like main()
    p_add = subparsers.add_parser("add")
    p_add.set_defaults(func=mock_add)

    p_remove = subparsers.add_parser("remove")
    p_remove.set_defaults(func=mock_remove)

    p_list = subparsers.add_parser("list")
    p_list.set_defaults(func=mock_list)

    p_fallback = subparsers.add_parser("set-fallback")
    p_fallback.set_defaults(func=mock_set_fallback)

    # Simulate command line args
    for cmd, mock_func in [("add", mock_add), ("remove", mock_remove),
                           ("list", mock_list), ("set-fallback", mock_set_fallback)]:
        args = parser.parse_args([cmd])
        args.func(args)
        mock_func.assert_called_once()
        mock_func.reset_mock()


def test_main_no_func(monkeypatch, capsys):
    # When no subcommand given, should print help
    monkeypatch.setattr(sys, "argv", ["prog"])
    with pytest.raises(SystemExit):
        vpn_switcher_cli.main()
    out = capsys.readouterr().out
    assert "usage:" in out

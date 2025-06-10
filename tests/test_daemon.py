# SPDX-License-Identifier: MIT
import pytest
import logging
from unittest.mock import MagicMock, patch
from vpn_switcher.daemon import (
    internet_available,
    get_active_connections,
    get_active_interface_info,
    deactivate_vpns,
    activate_vpn_by_uuid,
    is_correct_vpn_enabled,
    handle_connection_change
)


# ------------------------------------------------------------------------------
# Fixtures

@pytest.fixture
def config(monkeypatch):
    config = {
        'internet_check_url': 'http://test.com',
        'check_timeout_seconds': 5,
        'fallback_vpn_uuid': 'fallback-uuid',
        'trusted_connections': [
            {'ssid': 'trusted-wifi', 'vpn_uuid': 'trusted-vpn-uuid'},
            {'interface': 'eth0', 'vpn_uuid': 'wired-vpn-uuid'}
        ]
    }
    monkeypatch.setattr("vpn_switcher.daemon.config", config)
    return config


@pytest.fixture
def mock_info(mocker):
    """Patch get_active_interface_info."""
    return mocker.patch("vpn_switcher.daemon.get_active_interface_info")


@pytest.fixture(autouse=True)
def mock_dbus(monkeypatch):
    """Mock the D-Bus system interfaces."""
    mock_bus = MagicMock()
    mock_iface = MagicMock()

    monkeypatch.setattr("vpn_switcher.daemon.bus", mock_bus)
    monkeypatch.setattr("vpn_switcher.daemon.nm_iface", mock_iface)

    return mock_bus, mock_iface


# ------------------------------------------------------------------------------
# Test internet_available_success

def test_internet_available_success(mocker):
    mock_iface = mocker.patch("vpn_switcher.daemon.nm_iface")
    mock_iface.CheckConnectivity.return_value = 4
    assert internet_available() is True
    mock_iface.CheckConnectivity.assert_called_once()


# ------------------------------------------------------------------------------
# Test internet_available_failure_due_to_wrong_value

def test_internet_available_failure_due_to_wrong_value(mocker):
    mock_iface = mocker.patch("vpn_switcher.daemon.nm_iface")
    mock_iface.CheckConnectivity.return_value = 2  # not FULL connectivity
    assert internet_available() is False
    mock_iface.CheckConnectivity.assert_called_once()


# ------------------------------------------------------------------------------
# Test internet_available_failure_due_to_exception

def test_internet_available_failure_due_to_exception(mocker, caplog):
    mock_iface = mocker.patch("vpn_switcher.daemon.nm_iface")
    mock_iface.CheckConnectivity.side_effect = Exception("DBus error")
    with caplog.at_level(logging.WARNING):
        assert internet_available() is False
        assert "Connectivity check failed" in caplog.text


# ------------------------------------------------------------------------------
# Tests for get_active_connections

def test_get_active_connections(mocker):
    mock_nm_iface = mocker.patch("vpn_switcher.daemon.nm_iface")
    mock_bus = mocker.patch("vpn_switcher.daemon.bus")

    mock_nm_iface.Get.return_value = ['/org/path1', '/org/path2']
    mock_bus.get_object.side_effect = ['conn1', 'conn2']

    result = get_active_connections()
    assert result == ['conn1', 'conn2']
    assert mock_bus.get_object.call_count == 2


# ------------------------------------------------------------------------------
# Tests for get_active_interface_info

def test_get_active_interface_info_wifi(mock_dbus):
    mock_bus, _ = mock_dbus

    active_conn = MagicMock()
    props = MagicMock()
    dev = MagicMock()
    ap = MagicMock()

    # Set return values for properties
    props.Get.side_effect = [
        "802-11-wireless",  # conn_type
        "WiFiHome",         # conn_id
        "uuid-wifi",        # uuid
        ["/device/1"]       # devices
    ]

    dev_props = MagicMock()
    dev_props.Get.side_effect = [
        "wlan0",                # device interface
        "/ap/1",                # active access point
        [ord(c) for c in "MySSID"]  # SSID bytes
    ]

    ap_props = MagicMock()
    ap_props.Get.return_value = [ord(c) for c in "MySSID"]

    mock_bus.get_object.side_effect = [
        active_conn,  # get_active_connections
        dev,          # device
        ap            # access point
    ]

    with patch("dbus.Interface", side_effect=[props, dev_props, ap_props]):
        with patch("vpn_switcher.daemon.get_active_connections", return_value=[active_conn]):
            result = get_active_interface_info()
            assert result == [{
                "uuid": "uuid-wifi",
                "interface": "wlan0",
                "ssid": "MySSID",
                "type": "802-11-wireless"
            }]


# ------------------------------------------------------------------------------
# Tests for deactivate_vpns

def test_deactivate_vpns(mock_dbus):
    _, mock_iface = mock_dbus

    conn1 = MagicMock()
    conn2 = MagicMock()
    props1 = MagicMock()
    props2 = MagicMock()

    # Only conn1 is VPN
    props1.Get.return_value = "vpn"
    props2.Get.return_value = "ethernet"

    with patch("dbus.Interface", side_effect=[props1, props2]):
        with patch("vpn_switcher.daemon.get_active_connections", return_value=[conn1, conn2]):
            deactivate_vpns()
            mock_iface.DeactivateConnection.assert_called_once_with(
                conn1.object_path)


# ------------------------------------------------------------------------------
# Tests for activate_vpn_by_uuid

def test_activate_vpn_by_uuid_success(mock_dbus):
    _, mock_iface = mock_dbus

    mock_settings = MagicMock()
    mock_conn1 = MagicMock()
    mock_conn_iface1 = MagicMock()

    mock_conn_iface1.GetSettings.return_value = {
        "connection": {"uuid": "target-uuid"}
    }

    with patch.object(mock_conn1, "object_path", "/conn/1"):
        with patch("vpn_switcher.daemon.bus.get_object", side_effect=[mock_settings, mock_conn1]):
            with patch("dbus.Interface", side_effect=[MagicMock(ListConnections=lambda: ["/conn/1"]), mock_conn_iface1]):
                activate_vpn_by_uuid("target-uuid")
                mock_iface.ActivateConnection.assert_called_once_with(
                    "/conn/1", "/", "/"
                )


def test_activate_vpn_by_uuid_not_found(mock_dbus):
    _, mock_iface = mock_dbus

    mock_settings = MagicMock()
    mock_conn1 = MagicMock()
    mock_conn_iface1 = MagicMock()

    # Mismatch UUID
    mock_conn_iface1.GetSettings.return_value = {
        "connection": {"uuid": "some-other-uuid"}
    }

    with patch.object(mock_conn1, "object_path", "/conn/1"):
        with patch("vpn_switcher.daemon.bus.get_object", side_effect=[mock_settings, mock_conn1]):
            with patch("dbus.Interface", side_effect=[MagicMock(ListConnections=lambda: ["/conn/1"]), mock_conn_iface1]):
                activate_vpn_by_uuid("target-uuid")
                mock_iface.ActivateConnection.assert_not_called()


# ------------------------------------------------------------------------------
# Tests for handle_connection_change

def test_handle_connection_change(mocker, config):
    mock_get_interfaces = mocker.patch(
        "vpn_switcher.daemon.get_active_interface_info")
    mock_internet = mocker.patch("vpn_switcher.daemon.internet_available")
    mock_deactivate = mocker.patch("vpn_switcher.daemon.deactivate_vpns")
    mock_activate = mocker.patch("vpn_switcher.daemon.activate_vpn_by_uuid")
    mock_is_correct_vpn_enabled = mocker.patch(
        "vpn_switcher.daemon.is_correct_vpn_enabled")

    mock_get_interfaces.side_effect = [
        [{'ssid': 'trusted-wifi', 'interface': 'wlan0', 'type': 'some-type'}],
    ]
    mock_internet.return_value = True
    mock_is_correct_vpn_enabled.return_value = False

    state = 1

    result = handle_connection_change(state)
    assert result is False
    mock_deactivate.assert_called_once()
    mock_activate.assert_called_once()


# ------------------------------------------------------------------------------
# Tests for is_correct_vpn_enabled

def test_trusted_ssid_with_correct_vpn(mock_info, config):
    config["trusted_connections"] = [
        {"ssid": "HomeWiFi", "vpn_uuid": "vpn-123"}
    ]

    mock_info.side_effect = [
        [{"ssid": "HomeWiFi", "interface": "wlan0"}],
        [{"uuid": "vpn-123"}]
    ]

    assert is_correct_vpn_enabled() is True


def test_trusted_interface_with_wrong_vpn(mock_info, config):
    config["trusted_connections"] = [
        {"interface": "eth0", "vpn_uuid": "vpn-correct"}
    ]

    mock_info.side_effect = [
        [{"interface": "eth0"}],
        [{"uuid": "vpn-wrong"}]
    ]

    assert is_correct_vpn_enabled() is False


def test_untrusted_network_with_correct_fallback(mock_info, config):
    config["trusted_connections"] = []
    config["fallback_vpn_uuid"] = "fallback-uuid"

    mock_info.side_effect = [
        [{"interface": "usb0"}],
        [{"uuid": "fallback-uuid"}]
    ]

    assert is_correct_vpn_enabled() is True


def test_untrusted_network_with_wrong_fallback(mock_info, config):
    config["trusted_connections"] = []
    config["fallback_vpn_uuid"] = "fallback-uuid"

    mock_info.side_effect = [
        [{"interface": "usb0"}],
        [{"uuid": "wrong-uuid"}]
    ]

    assert is_correct_vpn_enabled() is False


def test_no_connection_and_no_vpn(mock_info, config):
    mock_info.side_effect = [
        [],  # No interfaces
        []   # No VPNs
    ]

    assert is_correct_vpn_enabled() is True


def test_no_connection_but_vpn_active(mock_info, config):
    mock_info.side_effect = [
        [],  # No interfaces
        [{"uuid": "vpn-active"}]
    ]

    assert is_correct_vpn_enabled() is False


def test_no_trusted_no_fallback_vpn_active(mock_info, config):
    config["trusted_connections"] = []
    config.pop("fallback_vpn_uuid", None)

    mock_info.side_effect = [
        [{"interface": "unknown0"}],
        [{"uuid": "vpn-unexpected"}]
    ]

    assert is_correct_vpn_enabled() is False


def test_no_trusted_no_fallback_no_vpn(mock_info, config):
    config["trusted_connections"] = []
    config.pop("fallback_vpn_uuid", None)

    mock_info.side_effect = [
        [{"interface": "unknown0"}],
        []
    ]

    assert is_correct_vpn_enabled() is True

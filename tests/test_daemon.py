# SPDX-License-Identifier: MIT
import pytest
import requests
from unittest.mock import MagicMock
from vpn_switcher.daemon import (
    internet_available,
    get_active_connections,
    get_active_interface_info,
    deactivate_vpns,
    activate_vpn_by_uuid,
    handle_connection_change
)


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


def test_internet_available_success(mocker, config):
    mock_resp = mocker.Mock()
    mock_resp.status_code = 204
    mock_get = mocker.patch("requests.get", return_value=mock_resp)
    assert internet_available()
    mock_get.assert_called_once()


def test_internet_available_failure(mocker, config):
    mock_get = mocker.patch(
        "requests.get",
        side_effect=requests.exceptions.RequestException)
    assert internet_available() is False


def test_get_active_connections(mocker):
    mock_nm_iface = mocker.patch("vpn_switcher.daemon.nm_iface")
    mock_bus = mocker.patch("vpn_switcher.daemon.bus")

    mock_nm_iface.Get.return_value = ['/org/path1', '/org/path2']
    mock_bus.get_object.side_effect = ['conn1', 'conn2']

    result = get_active_connections()
    assert result == ['conn1', 'conn2']
    assert mock_bus.get_object.call_count == 2


def test_handle_connection_change(mocker, config):
    mock_get_interfaces = mocker.patch(
        "vpn_switcher.daemon.get_active_interface_info")
    mock_internet = mocker.patch("vpn_switcher.daemon.internet_available")
    mock_deactivate = mocker.patch("vpn_switcher.daemon.deactivate_vpns")
    mock_activate = mocker.patch("vpn_switcher.daemon.activate_vpn_by_uuid")

    mock_get_interfaces.side_effect = [
        [{'ssid': 'trusted-wifi', 'interface': 'wlan0', 'type': 'some-type'}],
        []  # Return empty list on second call (simulate no VPN enabled)
    ]
    mock_internet.return_value = True

    state = 1

    result = handle_connection_change(state)
    assert result is False
    mock_deactivate.assert_called_once()
    mock_activate.assert_called_once()

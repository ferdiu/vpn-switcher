#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

import dbus
import dbus.mainloop.glib
import time
import yaml
import logging
import requests
import gi

gi.require_version('Gio', '2.0')
from gi.repository import GLib


# ------------------------------------------------------------------------------
# Constants

CONFIG_FILE = "config.yaml"
LOG_FILE = "/tmp/vpn-switcher.log"


# ------------------------------------------------------------------------------
# Logging

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)


# ------------------------------------------------------------------------------
# Global state

config = {}
bus = None
nm_iface = None


# ------------------------------------------------------------------------------
# Configuration

def load_config():
    """Load configuration from the YAML file."""
    global config
    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)


def internet_available():
    """"Check if the internet is available."""
    try:
        resp = requests.get(config['internet_check_url'], timeout=3)
        return resp.status_code == 204
    except Exception as e:
        logging.warning(f"Internet check failed: {e}")
        return False


# ------------------------------------------------------------------------------
# VPN Utilities

def get_active_connections():
    """Get active connections."""
    active = nm_iface.Get("org.freedesktop.NetworkManager", "ActiveConnections",
                          dbus_interface="org.freedesktop.DBus.Properties")
    return [bus.get_object('org.freedesktop.NetworkManager', path) for path in active]


def get_active_interface_info():
    """Get information about the active interface."""
    conns = get_active_connections()
    for conn_proxy in conns:
        props = dbus.Interface(conn_proxy, "org.freedesktop.DBus.Properties")
        try:
            conn_type = props.Get("org.freedesktop.NetworkManager.Connection.Active", "Type")
            conn_id = props.Get("org.freedesktop.NetworkManager.Connection.Active", "Id")
            devices = props.Get("org.freedesktop.NetworkManager.Connection.Active", "Devices")
            uuid = props.Get("org.freedesktop.NetworkManager.Connection.Active", "Uuid")
            if not devices:
                continue
            device_path = devices[0]
            device = bus.get_object("org.freedesktop.NetworkManager", device_path)
            dev_props = dbus.Interface(device, "org.freedesktop.DBus.Properties")
            iface = dev_props.Get("org.freedesktop.NetworkManager.Device", "Interface")

            # Get SSID if it's wireless
            ssid = None
            if conn_type == "802-11-wireless":
                active_ap = dev_props.Get('org.freedesktop.NetworkManager.Device.Wireless', 'ActiveAccessPoint')
                ap = bus.get_object('org.freedesktop.NetworkManager', active_ap)
                ap_props = dbus.Interface(ap, 'org.freedesktop.DBus.Properties')
                ssid_bytes = ap_props.Get('org.freedesktop.NetworkManager.AccessPoint', 'Ssid')
                ssid = ''.join([chr(b) for b in ssid_bytes])

            return {
                "uuid": uuid,
                "interface": iface,
                "ssid": ssid,
                "type": conn_type,
            }
        except Exception as e:
            logging.error(f"Failed to extract connection info: {e}")
    return {}


def deactivate_vpns():
    """Deactivate all active VPNs."""
    for conn_proxy in get_active_connections():
        props = dbus.Interface(conn_proxy, "org.freedesktop.DBus.Properties")
        try:
            if props.Get("org.freedesktop.NetworkManager.Connection.Active", "Type") == "vpn":
                nm_iface.DeactivateConnection(conn_proxy.object_path)
                logging.info("Deactivated active VPN.")
        except Exception as e:
            logging.warning(f"VPN deactivation error: {e}")


def activate_vpn_by_uuid(uuid):
    """Activate a VPN by UUID."""
    settings = bus.get_object('org.freedesktop.NetworkManager', '/org/freedesktop/NetworkManager/Settings')
    settings_iface = dbus.Interface(settings, 'org.freedesktop.NetworkManager.Settings')
    for conn_path in settings_iface.ListConnections():
        conn_proxy = bus.get_object('org.freedesktop.NetworkManager', conn_path)
        conn = dbus.Interface(conn_proxy, 'org.freedesktop.NetworkManager.Settings.Connection')
        try:
            settings = conn.GetSettings()
            if settings["connection"]["uuid"] == uuid:
                logging.info(f"Activating VPN with UUID: {uuid}")
                nm_iface.ActivateConnection(conn_path, dbus.ObjectPath('/'), dbus.ObjectPath('/'))
                return
        except Exception as e:
            logging.error(f"Could not activate VPN: {e}")


def on_nm_state_changed(state):
    """Handle state changes in NetworkManager."""
    GLib.timeout_add_seconds(5, handle_connection_change)
    return True


def handle_connection_change():
    """Handle connection changes."""
    info = get_active_interface_info()
    if not info:
        logging.info("No active connection found.")
        return False

    deactivate_vpns()

    for _ in range(config.get('check_timeout_seconds', 20)):
        if internet_available():
            vpn_uuid = config['fallback_vpn_uuid']  # default
            for rule in config.get('trusted_connections', []):
                if rule.get("ssid") == info.get("ssid") or rule.get("interface") == info.get("interface"):
                    vpn_uuid = rule.get("vpn_uuid")
                    break
            activate_vpn_by_uuid(vpn_uuid)
            return False
        time.sleep(1)
    logging.warning("Internet never became available.")
    return False


# ------------------------------------------------------------------------------
# Main

def main():
    global bus, nm_iface
    load_config()
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    nm = bus.get_object('org.freedesktop.NetworkManager', '/org/freedesktop/NetworkManager')
    nm_iface = dbus.Interface(nm, 'org.freedesktop.NetworkManager')

    bus.add_signal_receiver(
        on_nm_state_changed,
        dbus_interface="org.freedesktop.NetworkManager",
        signal_name="StateChanged"
    )

    logging.info("VPN switcher daemon started.")
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()

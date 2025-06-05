#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

from gi.repository import GLib
import sys
import argparse
import json
import dbus
import dbus.mainloop.glib
import time
import yaml
import logging
import requests
import signal
from sdnotify import SystemdNotifier
import gi

gi.require_version('GLib', '2.0')

# ref:
# https://people.freedesktop.org/~lkundrak/nm-docs/nm-dbus-types.html#NMState


# ------------------------------------------------------------------------------
# Constants

CONFIG_FILE = "config.yaml"
LOG_FILE = "/tmp/vpn-switcher.log"


# ------------------------------------------------------------------------------
# Global state

config = {}
bus = None
nm_iface = None
loop = None


# ------------------------------------------------------------------------------
# Systemd Notifier

notifier = SystemdNotifier()
notifier.notify("READY=1")


def watchdog_ping():
    notifier.notify("WATCHDOG=1")
    return True  # Continue calling


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
        return resp.status_code < 400 or resp.status_code >= 500
    except Exception as e:
        logging.warning(f"Internet check failed: {e}")
        return False


# ------------------------------------------------------------------------------
# VPN Utilities

def get_active_connections():
    """Get active connections."""
    active = nm_iface.Get(
        "org.freedesktop.NetworkManager",
        "ActiveConnections",
        dbus_interface="org.freedesktop.DBus.Properties")
    return [
        bus.get_object(
            'org.freedesktop.NetworkManager',
            path) for path in active]


def get_active_interface_info(
    only_types=[], skip_types=[
        "bridge", "loopback"]):
    """Get information about all active interfaces."""
    conns = get_active_connections()
    infos = []

    # Check if only types and skip types intersect
    if only_types and skip_types:
        if any(t in only_types for t in skip_types):
            raise ValueError("only_types and skip_types cannot intersect")

    for conn_proxy in conns:
        props = dbus.Interface(conn_proxy, "org.freedesktop.DBus.Properties")
        try:
            conn_type = props.Get(
                "org.freedesktop.NetworkManager.Connection.Active", "Type")
            conn_id = props.Get(
                "org.freedesktop.NetworkManager.Connection.Active", "Id")
            uuid = props.Get(
                "org.freedesktop.NetworkManager.Connection.Active", "Uuid")
            devices = props.Get(
                "org.freedesktop.NetworkManager.Connection.Active",
                "Devices")

            # Let pass only connections that are of the specified types
            if only_types and conn_type not in only_types:
                continue

            # Skip connections that are of the specified skip_type
            if conn_type in skip_types:
                continue

            for device_path in devices:
                device = bus.get_object(
                    "org.freedesktop.NetworkManager", device_path)
                dev_props = dbus.Interface(
                    device, "org.freedesktop.DBus.Properties")
                iface = dev_props.Get(
                    "org.freedesktop.NetworkManager.Device", "Interface")

                ssid = None
                if conn_type == "802-11-wireless":
                    try:
                        active_ap = dev_props.Get(
                            'org.freedesktop.NetworkManager.Device.Wireless', 'ActiveAccessPoint')
                        ap = bus.get_object(
                            'org.freedesktop.NetworkManager', active_ap)
                        ap_props = dbus.Interface(
                            ap, 'org.freedesktop.DBus.Properties')
                        ssid_bytes = ap_props.Get(
                            'org.freedesktop.NetworkManager.AccessPoint', 'Ssid')
                        ssid = ''.join([chr(b) for b in ssid_bytes])
                    except Exception as e:
                        logging.warning(f"Could not get SSID: {e}")

                infos.append({
                    "uuid": uuid,
                    "interface": iface,
                    "ssid": ssid,
                    "type": conn_type,
                })
        except Exception as e:
            logging.error(f"Failed to extract connection info: {e}")

    return infos


def deactivate_vpns():
    """Deactivate all active VPNs."""
    for conn_proxy in get_active_connections():
        props = dbus.Interface(conn_proxy, "org.freedesktop.DBus.Properties")
        try:
            if props.Get(
                "org.freedesktop.NetworkManager.Connection.Active",
                    "Type") in ["vpn", "wireguard"]:
                nm_iface.DeactivateConnection(conn_proxy.object_path)
                logging.info("Deactivated active VPN.")
        except Exception as e:
            logging.warning(f"VPN deactivation error: {e}")


def activate_vpn_by_uuid(uuid):
    """Activate a VPN by UUID."""
    settings = bus.get_object(
        'org.freedesktop.NetworkManager',
        '/org/freedesktop/NetworkManager/Settings')
    settings_iface = dbus.Interface(
        settings, 'org.freedesktop.NetworkManager.Settings')
    for conn_path in settings_iface.ListConnections():
        conn_proxy = bus.get_object(
            'org.freedesktop.NetworkManager', conn_path)
        conn = dbus.Interface(
            conn_proxy,
            'org.freedesktop.NetworkManager.Settings.Connection')
        try:
            settings = conn.GetSettings()
            if settings["connection"]["uuid"] == uuid:
                logging.info(f"Activating VPN with UUID: {uuid}")
                nm_iface.ActivateConnection(
                    conn_path, dbus.ObjectPath('/'), dbus.ObjectPath('/'))
                return
        except Exception as e:
            logging.error(f"Could not activate VPN: {e}")


def on_nm_state_changed(state):
    """Handle state changes in NetworkManager."""
    try:
        GLib.timeout_add_seconds(5, lambda: handle_connection_change(state))
    except Exception as e:
        logging.error(f"Error scheduling connection check: {e}")
    return True


def handle_connection_change(state):
    try:
        logging.debug(f"State changed to: {state}")
        logging.info("Checking for active connections...")
        interfaces = get_active_interface_info()
        if not interfaces:
            logging.info("No active connections found.")
            return False

        logging.debug(f"Active connections: {json.dumps(interfaces)}")

        # Do not do nothing if there is already a VPN enabled
        vpns = get_active_interface_info(only_types=["vpn", "wireguard"])
        print(vpns)
        if vpns:
            return False

        deactivate_vpns()

        for _ in range(config.get('check_timeout_seconds', 20)):
            if internet_available():
                vpn_uuid = config['fallback_vpn_uuid']
                for iface_info in interfaces:
                    for rule in config.get('trusted_connections', []):
                        if rule.get("ssid") == iface_info.get("ssid") or rule.get(
                                "interface") == iface_info.get("interface"):
                            vpn_uuid = rule.get("vpn_uuid")
                            break
                activate_vpn_by_uuid(vpn_uuid)
                return False
            time.sleep(1)

        logging.warning("Internet never became available.")
        return False
    except Exception as e:
        logging.error(f"Unexpected error during connection check: {e}")
        return False


def stop_loop(*args):
    logging.info("VPN switcher stopping gracefully.")
    loop.quit()


# ------------------------------------------------------------------------------
# Main

def main():
    parser = argparse.ArgumentParser(description='VPN switcher daemon.')
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode.')
    args = parser.parse_args()

    if args.debug:
        # Add a new handler
        logging.basicConfig(
            stream=sys.stdout,
            level=logging.DEBUG,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )
        logging.info("Debug mode enabled.")
    else:
        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )

    signal.signal(signal.SIGTERM, stop_loop)
    signal.signal(signal.SIGINT, stop_loop)

    logging.info("Starting VPN switcher daemon...")

    global bus, nm_iface
    load_config()
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    nm = bus.get_object(
        'org.freedesktop.NetworkManager',
        '/org/freedesktop/NetworkManager')
    nm_iface = dbus.Interface(nm, 'org.freedesktop.NetworkManager')

    bus.add_signal_receiver(
        on_nm_state_changed,
        dbus_interface="org.freedesktop.NetworkManager",
        signal_name="StateChanged"
    )

    # Start watchdog ping
    GLib.timeout_add_seconds(10, watchdog_ping)

    global loop
    logging.info("VPN switcher daemon started.")
    loop = GLib.MainLoop()
    loop.run()


if __name__ == "__main__":
    main()

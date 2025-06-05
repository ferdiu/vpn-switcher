#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

import argparse
import yaml
import os
import dbus


CONFIG_PATH = os.path.expanduser("~/.config/vpn-switcher/config.yaml")
os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)


# ------------------------------------------------------------------------------
# Configuration

def load_config():
    """Load configuration from the YAML file."""
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f) or {}


def save_config(cfg):
    """Save configuration to the YAML file."""
    with open(CONFIG_PATH, 'w') as f:
        yaml.dump(cfg, f)


# ------------------------------------------------------------------------------
# VPN Utilities

def get_vpn_uuid_by_name(vpn_name):
    """Get VPN UUID by its name."""
    bus = dbus.SystemBus()
    settings = bus.get_object("org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager/Settings")
    iface = dbus.Interface(settings, "org.freedesktop.NetworkManager.Settings")
    for path in iface.ListConnections():
        conn = bus.get_object("org.freedesktop.NetworkManager", path)
        settings_iface = dbus.Interface(conn, "org.freedesktop.NetworkManager.Settings.Connection")
        s = settings_iface.GetSettings()
        if s["connection"]["type"] == "vpn" and s["connection"]["id"] == vpn_name:
            return s["connection"]["uuid"]
    raise ValueError(f"No VPN found with name '{vpn_name}'")


def cmd_add(args):
    """Add a trusted connection rule."""
    cfg = load_config()
    if "trusted_connections" not in cfg:
        cfg["trusted_connections"] = []

    uuid = get_vpn_uuid_by_name(args.vpn)

    rule = {}
    if args.ssid:
        rule["ssid"] = args.ssid
    if args.interface:
        rule["interface"] = args.interface
    rule["vpn_uuid"] = uuid

    cfg["trusted_connections"].append(rule)
    save_config(cfg)
    print(f"Added rule: {rule}")


def cmd_remove(args):
    """Remove a trusted connection rule."""
    cfg = load_config()
    before = len(cfg.get("trusted_connections", []))
    cfg["trusted_connections"] = [
        r for r in cfg.get("trusted_connections", [])
        if r.get("ssid") != args.ssid and r.get("interface") != args.interface
    ]
    after = len(cfg["trusted_connections"])
    save_config(cfg)
    print(f"Removed {before - after} matching rule(s).")


def cmd_list(args):
    """List trusted connection rules."""
    cfg = load_config()
    print("Trusted Connections:")
    for rule in cfg.get("trusted_connections", []):
        print(f"  - {rule}")
    print(f"Fallback VPN UUID: {cfg.get('fallback_vpn_uuid')}")


def cmd_set_fallback(args):
    """Set the fallback VPN UUID."""
    cfg = load_config()
    uuid = get_vpn_uuid_by_name(args.vpn)
    cfg["fallback_vpn_uuid"] = uuid
    save_config(cfg)
    print(f"Set fallback VPN to: {uuid}")


# ------------------------------------------------------------------------------
# Main

def main():
    parser = argparse.ArgumentParser(description="Manage vpn-switcher configuration.")
    subparsers = parser.add_subparsers()

    # Add rule
    p_add = subparsers.add_parser("add", help="Add trusted SSID or interface mapping to a VPN")
    p_add.add_argument("--ssid", help="SSID name")
    p_add.add_argument("--interface", help="Interface name (e.g. eth0)")
    p_add.add_argument("--vpn", required=True, help="VPN connection name")
    p_add.set_defaults(func=cmd_add)

    # Remove rule
    p_remove = subparsers.add_parser("remove", help="Remove rule by SSID or interface")
    p_remove.add_argument("--ssid", help="SSID to remove")
    p_remove.add_argument("--interface", help="Interface to remove")
    p_remove.set_defaults(func=cmd_remove)

    # List rules
    p_list = subparsers.add_parser("list", help="List current config")
    p_list.set_defaults(func=cmd_list)

    # Set fallback
    p_fallback = subparsers.add_parser("set-fallback", help="Set fallback VPN by name")
    p_fallback.add_argument("--vpn", required=True, help="VPN connection name")
    p_fallback.set_defaults(func=cmd_set_fallback)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

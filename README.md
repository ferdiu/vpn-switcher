# VPN Switcher

Automatically manage your WireGuard (or other) VPN connections using NetworkManager rules based on the network you're connected to.

---

## 🚀 Overview

`vpn-switcher` is a Linux daemon + CLI tool that:

- Monitors your network connection status
- Automatically activates a VPN profile when connected to specific Wi-Fi SSIDs or interfaces
- Falls back to a default VPN if the current connection is not trusted
- Waits for full internet connectivity before enabling VPN (avoids captive portals / auth walls)
- Stores configuration in a simple YAML file

It supports NetworkManager and WireGuard via D-Bus (no subprocess `nmcli` calls!).

---

## 🧱 Components

### 1. `vpn_switcher.cli` — CLI tool

Use this to manage trusted SSIDs/interfaces and assign them to VPNs.

```bash
vpn-switcher add --ssid "Home-WiFi" --vpn "MyVPN"
vpn-switcher add --interface "eth0" --vpn "WorkVPN"
vpn-switcher set-fallback --vpn "FallbackVPN"
vpn-switcher list
vpn-switcher remove --ssid "Home-WiFi"
```

### 2. `vpn_switcher.daemon` — D-Bus Daemon

Watches NetworkManager for connection changes, determines whether to enable a specific VPN, or fall back to a default.

### 3. `vpn-switcher.service` — systemd user service

Runs the daemon in the background when you log in.

---

## 📦 Installation (via Hatch)

```bash
# Clone the project
git clone https://github.com/yourusername/vpn-switcher.git
cd vpn-switcher

# Install build tool
pip install hatch

# Install as editable dev package
pip install -e .

# OR build and install the wheel
hatch build
pip install dist/vpn_switcher-*.whl
```

---

## 🔧 Setup and Usage

### 1. Create and Configure VPNs

Use `nmcli` or `nmtui` to create and test your VPN connections. Example:

```bash
nmcli connection import type wireguard file myvpn.conf
nmcli connection up MyVPN
```

> ⚠️ **Secrets Handling:**
> Do NOT store secrets in the switcher config. Let NetworkManager manage VPN secrets securely via its connection files.

---

### 2. Configure with CLI

```bash
# Map SSID to VPN
vpn-switcher add --ssid "Home" --vpn "HomeVPN"

# Map Ethernet interface to VPN
vpn-switcher add --interface "eth0" --vpn "WorkVPN"

# Set fallback VPN
vpn-switcher set-fallback --vpn "FallbackVPN"

# View configuration
vpn-switcher list
```

Config is stored at:

```
~/.config/vpn-switcher/config.yaml
```

---

### 3. Enable and Start the Daemon

Install the systemd **user service**:

```bash
# Copy the service file (adjust path if needed)
mkdir -p ~/.config/systemd/user/
cp vpn-switcher.service ~/.config/systemd/user/

# Enable and start the service
systemctl --user daemon-reexec
systemctl --user enable --now vpn-switcher.service

# View logs
journalctl --user -u vpn-switcher.service -f
```

---

## 🧪 Behavior

- If you're connected to a known SSID or interface → Connect assigned VPN
- If you're connected to anything else → Connect fallback VPN (if set)
- If you're offline or behind a captive portal → Wait until full internet access
- If your connection changes → VPN is automatically updated

---

## 🛠 Autocompletion (optional)

Install autocompletion for Bash or Zsh:

```bash
pip install argcomplete

# Bash
activate-global-python-argcomplete

# Zsh (~/.zshrc)
autoload -U bashcompinit
bashcompinit
eval "$(register-python-argcomplete vpn-switcher)"
```

---

## 📁 Config Format

Example `~/.config/vpn-switcher/config.yaml`:

```yaml
trusted_connections:
  - ssid: Home
    vpn_uuid: 11111111-1111-1111-1111-111111111111
  - interface: eth0
    vpn_uuid: 22222222-2222-2222-2222-222222222222
fallback_vpn_uuid: 33333333-3333-3333-3333-333333333333
```

The CLI manages this for you — no manual editing needed.

---

## 🧩 Supported VPN Types

- WireGuard (recommended)
- OpenVPN / IPsec (via NetworkManager VPN plugins)

---

## 🙋 FAQ

### How does it know when internet is "available"?

It uses D-Bus to query NetworkManager's full connectivity status (not just DNS/ping). This avoids premature VPN activation when behind captive portals or institutional login pages.

---

### Can I use this with `nmcli`-created VPNs?

Yes. Just make sure they are named appropriately and secrets are saved to disk.

---

### How do I uninstall?

```bash
systemctl --user disable --now vpn-switcher.service
pip uninstall vpn-switcher
```

---

## 🧑‍💻 Contributing

PRs welcome! Especially for:

- More VPN backends
- IPv6 support
- GUI config tool

---

## 📜 License

MIT License

---

## 🌐 Author

Created by Federico Manzella – Inspired by the need for smart VPN automation on Linux.

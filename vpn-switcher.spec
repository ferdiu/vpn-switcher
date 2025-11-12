%global debug_package       %{nil}
%define major_version       0.1.3
%define release_version     1

Name:           vpn-switcher
Version:        %{major_version}
Release:        %{release_version}%{?dist}
Summary:        Automatic VPN switcher using NetworkManager
License:        MIT
URL:            https://github.com/ferdiu/vpn-switcher
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz#/vpn-switcher-v%{version}.tar.gz
BuildArch:      noarch

Provides:       vpn-switcher vpn-switcherd
BuildRequires:  python3-devel
BuildRequires:  python3-hatchling
BuildRequires:  pyproject-rpm-macros
Requires:       NetworkManager
Requires:       python3-PyYAML
Requires:       python3-gobject
Requires:       python3-requests
Requires:       python3-dbus
Requires:       python3-sdnotify

%description
Automatic VPN switcher using NetworkManager.

%prep
%autosetup

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
install -D -m 0644 ./vpn-switcher.service %{buildroot}%{_unitdir}/vpn-switcher.service
install -D -m 0644 ./config.yaml %{buildroot}%{_sysconfdir}/vpn-switcher/config.yaml
%pyproject_install

%files
%license LICENSE
%doc README.md
%{python3_sitelib}/vpn_switcher*
%{_bindir}/vpn-switcher
%{_bindir}/vpn-switcherd
/usr/lib/systemd/system/vpn-switcher.service
%config(noreplace) %{_sysconfdir}/vpn-switcher/config.yaml

%changelog
* Tue Jun 10 2025 Federico Manzella <ferdiu.manzella@gmail.com> - 0.1.3-1
- Initial public release of vpn-switcher 0.1.3
  * Added fallback VPN support (connects to default when on untrusted network)
  * Uses D-Bus interface of NetworkManager to detect full Internet connectivity (avoids captive portal pitfalls)
  * Supports WireGuard and other NetworkManager VPN types
  * Introduced CLI commands: `vpn-switcher add`, `vpn-switcher set-fallback`, `vpn-switcher list`, `vpn-switcher remove`
  * Added `vpn-switcher.service` systemd user unit
  * Configuration via `~/.config/vpn-switcher/config.yaml` with “trusted_connections” & “fallback_vpn_uuid”
  * Code packaged with `pyproject.toml` / Hatch build system
  * License: MIT

* Fri Jun 6 2025 Federico Manzella <ferdiu.manzella@gmail.com> - 0.1.2-1
- Improved interface detection: differentiate between WiFi SSIDs and Ethernet interfaces
- Added example usage in README for mapping SSID/interface to VPN
- Minor bugfix: ensure daemon waits for “connected” + “full” state in NetworkManager
- Documentation updates

* Fri Jun 6 2025 Federico Manzella <ferdiu.manzella@gmail.com> - 0.1.1-1
- Initial prototype release: monitors NetworkManager connection changes and triggers appropriate VPN
- Basic CLI implementation
- YAML config support for trusted connections
- Support for fallback behavior when no trusted network found
- Rough edge-case handling for captive portals

* Thu Jun 5 2025 Federico Manzella <ferdiu.manzella@gmail.com> - 0.1.0-1
- Project inception: created repository, added core daemon and CLI scaffolding
- Defined architecture: daemon + CLI + systemd user service
- Outlined README and license

# Snap & Flathub packaging design

**Date:** 2026-08-25  
**Status:** Approved  
**Version:** 0.1.0

## Goal

Publish Hosts Manager on the Snap Store and Flathub while preserving polkit-based writes to `/etc/hosts`.

## Approach

**Classic Snap + host-integrated Flatpak** (Approach A):

| Channel  | Confinement | Privileged write |
|----------|-------------|------------------|
| Snap     | `classic`   | Install hook copies helper + policy to `/usr/local` |
| Flatpak  | `--filesystem=host` + PolicyKit | First `pkexec` installs helper + policy to `/usr/local` |

## App identity

- ID: `com.deepvelop.HostsManager`
- Desktop: `data/com.deepvelop.HostsManager.desktop`
- Metainfo: `data/com.deepvelop.HostsManager.metainfo.xml`
- License: Apache-2.0

## Layout (staged install)

`scripts/stage-install.sh` installs:

- `/bin/hosts-manager` — launcher script
- `/libexec/hosts-manager-helper`
- `/share/hosts-manager/` — Python app
- `/share/polkit-1/actions/` — policy (helper path substituted)
- `/share/applications/`, `/share/metainfo/`, `/share/icons/`

## Snap

- `snap/snapcraft.yaml` — classic, core24
- `snap/hooks/install` — registers host helper under `/usr/local`

## Flatpak

- `flatpak/com.deepvelop.HostsManager.yml` — GNOME Platform 46
- `hosts_manager/bootstrap.py` — first-run host install via `pkexec`

## Out of scope

- Automated store submission / CI publish
- Screenshots in metainfo (recommended before Flathub merge)

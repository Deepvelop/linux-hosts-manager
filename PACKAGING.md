# Packaging Hosts Manager

This document describes how to build packages for the **Snap Store** and **Flathub**, and what reviewers need to know about privileged access.

> **Note:** the `snap/` and `flatpak/` packaging files are currently kept out of the
> published repository (see `.gitignore`). This document applies once those files
> are released alongside the source.

Application ID: `com.deepvelop.HostsManager`  
Version: `0.1.0`

## Approach (classic / host integration)

Both packages use **Approach A** from the packaging design:

- **Snap**: `confinement: classic` so `pkexec`, polkit, and `/etc/hosts` work like a native install.
- **Flatpak**: host filesystem + PolicyKit D-Bus; on first privileged write the app installs its helper and polkit policy to `/usr/local` via `pkexec`.

The GUI never runs as root. Only the small helper writes `/etc/hosts` after polkit authorization.

## Prerequisites

### Snap

```bash
sudo snap install snapcraft --classic
sudo snap install lxd
sudo lxd init --auto   # first time only
```

### Flatpak

```bash
sudo apt install flatpak flatpak-builder
flatpak install -y flathub org.gnome.Platform//46 org.gnome.Sdk//46
```

## Build Snap (classic)

From the repository root:

```bash
cd snap
snapcraft pack --use-lxd
```

Output: `hosts-manager_0.1.0_amd64.snap` (name may vary by architecture).

Install locally:

```bash
sudo snap install --classic --dangerous ../hosts-manager_*.snap
```

On install, the snap **install hook** registers the privileged helper and polkit policy on the host under `/usr/local`.

Launch:

```bash
com.deepvelop.hostsmanager
# or from the app grid: Hosts Manager
```

### Snap Store submission notes

Include in the store listing / reviewer notes:

- **Confinement**: classic — required to modify `/etc/hosts` and invoke `pkexec`.
- **Purpose**: system hosts file management with polkit, same category as other system tools.
- **Security**: GUI is unprivileged; helper validates input, backs up, and writes atomically.

Upload with [Snapcraft](https://snapcraft.io/docs/snapcraft-upload) after creating a store account.

## Build Flatpak

From the repository root:

```bash
flatpak-builder --user --install --force-clean flatpak-build flatpak/com.deepvelop.HostsManager.yml
```

Run:

```bash
flatpak run com.deepvelop.HostsManager
```

### First privileged write (Flatpak)

When you first save or toggle Active, Flatpak will prompt to install:

- `/usr/local/libexec/hosts-manager-helper`
- `/usr/local/share/polkit-1/actions/com.deepvelop.HostsManager.policy`

This is a one-time `pkexec` step. Later writes reuse the session authorization.

### Flathub submission

1. Fork [flathub/flathub](https://github.com/flathub/flathub) and open a PR adding `com.deepvelop.HostsManager`.
2. Point the manifest at this repository (tagged release recommended).
3. In the PR description, explain:
   - `--filesystem=host` — read/write `/etc/hosts` via polkit helper
   - `--talk-name=org.freedesktop.PolicyKit1` — authorization UI
   - One-time host helper install to `/usr/local`

Validate locally before submitting:

```bash
flatpak run org.freedesktop.appstream.cli validate data/com.deepvelop.HostsManager.metainfo.xml
./scripts/stage-install.sh /tmp/hm-validate /usr/local .
desktop-file-validate /tmp/hm-validate/usr/local/share/applications/com.deepvelop.HostsManager.desktop
```

## AppStream & desktop

- Metainfo: `data/com.deepvelop.HostsManager.metainfo.xml`
- Desktop entry: `data/com.deepvelop.HostsManager.desktop.in` (installed with absolute `Exec`/`TryExec` paths for launchers like Ulauncher)

## Manual system install (reference)

```bash
sudo ./install.sh
# or
sudo PREFIX=/usr ./install.sh
```

## Store checklist

- [ ] Tag release `v0.1.0` on GitHub
- [ ] Update metainfo release date if needed
- [ ] Add screenshots to metainfo (recommended for Flathub)
- [ ] Create Snap Store application entry
- [ ] Open Flathub PR with manifest URL
- [ ] Test on clean Ubuntu 24.04 VM (Snap + Flatpak)

## License

Apache-2.0 — see [LICENSE](LICENSE).

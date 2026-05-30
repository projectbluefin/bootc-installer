<div align="center">
    <img src="data/icons/hicolor/scalable/apps/org.bootcos.Installer.svg" height="64">
    <h1>BootcOS Installer</h1>
    <p>A GTK 4 / Libadwaita Flatpak installer for <a href="https://github.com/tuna-os">BootcOS</a> and other <a href="https://universal-blue.org">Universal Blue</a> bootc images.</p>
    <hr />
</div>

## Installing

### Production

```bash
curl -Lo installer.flatpak \
  https://github.com/tuna-os/bootc-installer/releases/download/continuous/org.bootcinstaller.Installer.flatpak \
  && sudo flatpak uninstall -y org.bootcinstaller.Installer org.bootcos.Installer 2>/dev/null; sudo flatpak install --bundle -y installer.flatpak
```

### Devel (latest `dev` branch build)

```bash
curl -Lo installer-devel.flatpak \
  https://github.com/tuna-os/bootc-installer/releases/download/continuous-dev/org.bootcinstaller.Installer.Devel.flatpak \
  && sudo flatpak uninstall -y org.bootcinstaller.Installer.Devel 2>/dev/null; sudo flatpak install --bundle -y installer-devel.flatpak
```

---

## Recipe Format

The installer drives the `fisherman` backend with a JSON recipe file. The wizard generates one automatically, but you can write one by hand for automation or liveISO customisation.

### Minimal recipe (BootcOS GNOME 50, XFS, no encryption)

```json
{
  "disk": "/dev/sda",
  "filesystem": "xfs",
  "btrfsSubvolumes": false,
  "encryption": { "type": "none" },
  "image": "ghcr.io/tuna-os/yellowfin:gnome50",
  "targetImgref": "ghcr.io/tuna-os/yellowfin:gnome50",
  "selinuxDisabled": false,
  "unifiedStorage": true,
  "composeFsBackend": false,
  "bootloader": "grub2",
  "hostname": "bootcos",
  "flatpaks": [],
  "user": {
    "username": "james",
    "fullname": "James",
    "password": "hunter2",
    "groups": ["wheel"]
  }
}
```

### Btrfs + TPM2/LUKS encryption

```json
{
  "disk": "/dev/nvme0n1",
  "filesystem": "btrfs",
  "btrfsSubvolumes": true,
  "encryption": { "type": "tpm2-luks" },
  "image": "ghcr.io/tuna-os/yellowfin:gnome50",
  "targetImgref": "ghcr.io/tuna-os/yellowfin:gnome50",
  "selinuxDisabled": false,
  "unifiedStorage": true,
  "composeFsBackend": false,
  "bootloader": "grub2",
  "hostname": "bootcos",
  "flatpaks": ["org.mozilla.firefox", "org.gnome.Console"],
  "user": {
    "username": "james",
    "fullname": "James",
    "password": "hunter2",
    "groups": ["wheel"]
  }
}
```

### LUKS with passphrase fallback + TPM2

```json
{
  "disk": "/dev/sda",
  "filesystem": "xfs",
  "btrfsSubvolumes": false,
  "encryption": {
    "type": "tpm2-luks-passphrase",
    "passphrase": "my-recovery-passphrase"
  },
  "image": "ghcr.io/tuna-os/yellowfin:gnome50",
  "targetImgref": "ghcr.io/tuna-os/yellowfin:gnome50",
  "selinuxDisabled": false,
  "unifiedStorage": true,
  "composeFsBackend": false,
  "bootloader": "grub2",
  "hostname": "bootcos",
  "flatpaks": [],
  "user": { "username": "", "fullname": "", "password": "", "groups": [] }
}
```

### Bluefin / Dakota (composefs + systemd-boot)

```json
{
  "disk": "/dev/nvme0n1",
  "filesystem": "btrfs",
  "btrfsSubvolumes": false,
  "encryption": { "type": "none" },
  "image": "ghcr.io/projectbluefin/dakota:latest",
  "targetImgref": "ghcr.io/projectbluefin/dakota:latest",
  "selinuxDisabled": false,
  "unifiedStorage": true,
  "composeFsBackend": true,
  "bootloader": "systemd",
  "hostname": "bootcos",
  "flatpaks": [],
  "user": { "username": "", "fullname": "", "password": "", "groups": [] }
}
```

### Recipe field reference

| Field | Type | Description |
|---|---|---|
| `disk` | string | Block device to partition and install to (e.g. `"/dev/sda"`) |
| `filesystem` | string | Root filesystem: `"xfs"` or `"btrfs"` |
| `btrfsSubvolumes` | bool | Create `@`, `@home`, `@snapshots` subvolumes (btrfs only) |
| `encryption.type` | string | `"none"`, `"luks-passphrase"`, `"tpm2-luks"`, or `"tpm2-luks-passphrase"` |
| `encryption.passphrase` | string | Required for `luks-passphrase` and `tpm2-luks-passphrase` |
| `image` | string | Source OCI image to install (pulled by podman) |
| `targetImgref` | string | Update-tracking ref written into the deployed OS (usually same as `image`) |
| `selinuxDisabled` | bool | Pass `--disable-selinux` to bootc (needed for cross-distro installs) |
| `unifiedStorage` | bool | Pass `--experimental-unified-storage` to bootc (default: `true`) |
| `composeFsBackend` | bool | Pass `--composefs-backend` to bootc (required for composefs-native images like Dakota) |
| `bootloader` | string | `"grub2"` (default) or `"systemd"` (for systemd-boot images) |
| `hostname` | string | Hostname written into the installed OS |
| `flatpaks` | array | Flatpak app IDs to copy from the live system into the target |
| `user.username` | string | Username to create; leave empty to skip user creation |
| `user.fullname` | string | Full display name |
| `user.password` | string | Plain-text password (hashed during install) |
| `user.groups` | array | Additional groups (e.g. `["wheel", "docker"]`) |

---

## Autoinstall (unattended)

Pass a recipe directly to skip the wizard entirely:

```bash
flatpak run org.bootcinstaller.Installer --autoinstall /path/to/recipe.json
```

This is the primary mechanism for liveISO pre-configuration (see below).

---

## Image / Distro Customisation

Any image or distro shipping this installer — whether on a **liveISO**, as part of a **bootc image** (Bluefin, Bazzite, etc.), or as a **custom appliance** — can pre-configure both the image catalog and the default recipe by dropping files into `/etc/bootc-installer/` in their OS tree. The installer reads these at runtime from the host filesystem.

| Override path | Scope |
|---|---|
| `/etc/bootc-installer/images.json` | Image catalog — replaces the bundled catalog entirely |
| `/etc/bootc-installer/recipe.json` | Sys-recipe — sets default values merged with the wizard output |
| `$XDG_CONFIG_HOME/bootc-installer/images.json` | Per-user catalog override (dev/testing) |

### Customising the image catalog

Override `images.json` to show only your own images and hide the default catalog:

**`/etc/bootc-installer/images.json`**
```json
{
  "default_image": "ghcr.io/my-org/my-image:stable",
  "fallback_flatpaks": [],
  "images": [
    {
      "name": "My Distro",
      "icon": "/usr/share/pixmaps/my-distro.svg",
      "needs_user_creation": true,
      "children": [
        {
          "name": "Stable",
          "imgref": "ghcr.io/my-org/my-image:stable",
          "desc": "The stable release"
        },
        {
          "name": "Nightly",
          "imgref": "ghcr.io/my-org/my-image:nightly",
          "desc": "Latest nightly build"
        }
      ]
    }
  ]
}
```

**Bluefin example** — only show Bluefin variants, pre-select the LTS:

```json
{
  "default_image": "ghcr.io/ublue-os/bluefin:lts",
  "fallback_flatpaks": [],
  "images": [
    {
      "name": "Bluefin",
      "icon": "/usr/share/pixmaps/bluefin.png",
      "flatpaks": "https://raw.githubusercontent.com/projectbluefin/common/refs/heads/main/system_files/bluefin/usr/share/ublue-os/homebrew/system-flatpaks.Brewfile",
      "needs_user_creation": true,
      "children": [
        {
          "name": "Stable",
          "imgref": "ghcr.io/ublue-os/bluefin:stable"
        },
        {
          "name": "LTS",
          "imgref": "ghcr.io/ublue-os/bluefin:lts"
        },
        {
          "name": "Dakota (experimental)",
          "imgref": "ghcr.io/projectbluefin/dakota:latest",
          "composefs": true,
          "bootloader": "systemd",
          "filesystem": "btrfs",
          "needs_user_creation": false
        }
      ]
    }
  ]
}
```

### Setting recipe defaults (sys-recipe)

Drop a **partial** recipe at `/etc/bootc-installer/recipe.json`. It is merged with the wizard output — the user can still change anything, but these values are used as defaults for fields they don't touch:

**`/etc/bootc-installer/recipe.json`**
```json
{
  "hostname": "bluefin",
  "selinuxDisabled": false,
  "unifiedStorage": true,
  "flatpaks": [
    "org.mozilla.firefox",
    "org.gnome.Console"
  ]
}
```

**Bazzite example** — force btrfs + TPM2 LUKS as the default, pre-fill hostname:

```json
{
  "hostname": "bazzite",
  "filesystem": "btrfs",
  "btrfsSubvolumes": true,
  "encryption": { "type": "tpm2-luks" },
  "unifiedStorage": true
}
```

### Unattended / autoinstall

For a fully hands-free install (e.g. a liveISO that installs automatically), pass `--autoinstall` with a complete recipe — the wizard is skipped entirely:

```bash
flatpak run org.bootcinstaller.Installer --autoinstall /etc/bootc-installer/autoinstall.json
```

Example systemd unit to trigger this on boot:

**`/usr/lib/systemd/system/bootc-installer-auto.service`**
```ini
[Unit]
Description=Unattended bootc install
After=graphical.target

[Service]
ExecStart=flatpak run org.bootcinstaller.Installer --autoinstall /etc/bootc-installer/autoinstall.json
```

---

## Contributing Images

The installer's image catalog is defined in [`fisherman/data/images.json`](fisherman/data/images.json). Adding a new image means adding an entry to that file. The structure is a recursive tree of groups and leaves:

```jsonc
{
  "name": "My Distro",
  "subtitle": "Optional subtitle",
  "icon": "resource:///org/bootcinstaller/Installer/images/my-distro.svg",
  "flatpaks": ["org.mozilla.firefox", "org.gnome.Console"],
  "needs_user_creation": true,
  "children": [
    {
      "name": "Stable",
      "imgref": "ghcr.io/my-org/my-image:latest",
      "desc": "Optional description shown as tooltip"
    },
    {
      "name": "Composefs Edition",
      "imgref": "ghcr.io/my-org/my-image-composefs:latest",
      "composefs": true,
      "bootloader": "systemd",
      "filesystem": "btrfs",
      "needs_user_creation": false
    }
  ]
}
```

**Inheritable group fields** (children inherit the nearest ancestor's value):

| Field | Description |
|---|---|
| `flatpaks` | Flatpak list URL or app ID array |
| `icon` | `resource:///…/images/name.svg`, absolute path, or XDG icon name |
| `needs_user_creation` | Whether the installer shows the user creation step (default: `false`) |
| `composefs` | Enable composefs deployment backend |
| `bootloader` | `"grub2"` or `"systemd"` |
| `filesystem` | `"xfs"` or `"btrfs"` |

Drop your SVG/PNG into `fisherman/data/images/` and add it to `bootc_installer/bootc-installer.gresource.xml`.

PRs to add new images, icons, or flatpak lists are very welcome!

---

## Building

### Flatpak (recommended)

```bash
flatpak run org.flatpak.Builder --force-clean --user --install _build flatpak/org.bootcinstaller.Installer.json
flatpak run org.bootcinstaller.Installer
```

### Meson (development)

```bash
meson setup build
ninja -C build
sudo ninja -C build install
bootc-installer
```

### Demo / preview loop

For day-to-day UI work, use the repo launcher:

```bash
./run-dev.sh
```

It runs the local build with `BOOTC_DEMO=1`, so the full wizard can be walked
without launching fisherman or touching a disk.

To jump directly to an individual screen during local iteration, set
`BOOTC_PREVIEW_SCREEN` before launching:

```bash
BOOTC_PREVIEW_SCREEN=confirm ./run-dev.sh
BOOTC_PREVIEW_SCREEN=progress ./run-dev.sh
```

`progress` starts the demo install sequence automatically when `BOOTC_DEMO=1`
is enabled.

### Dependencies

- meson, ninja
- libadwaita-1-dev
- gettext, desktop-file-utils
- libgnome-desktop-4-dev
- python3-requests
- Go ≥ 1.22 (for fisherman)

## Testing and release qualification

Software-only validation that is already wired into this repo:

```bash
./QUALIFY_SOFTWARE.sh
```

Optional local install/boot smoke coverage also exists in `tests/integration/test_e2e_install.py` for root + QEMU environments:

```bash
sudo FISHERMAN_BIN=/path/to/fisherman pytest tests/integration/test_e2e_install.py -v -s
sudo FISHERMAN_BIN=/path/to/fisherman BOOT_VERIFY=1 pytest tests/integration/test_e2e_install.py -v -s
```

Real release qualification still requires destructive installs on lab hardware for TPM2, physical boot prompts, recovery-key/passphrase fallback, Windows slurp, and offline ISO paths. Use the repo runbook in [`.github/CI_CD_GUIDE.md`](.github/CI_CD_GUIDE.md#release-qualification-runbook) to separate what can be verified now from what remains hardware-only.

# Rebuild trigger: 1778728267

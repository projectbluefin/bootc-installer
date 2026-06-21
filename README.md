<div align="center">
    <img src="data/icons/hicolor/scalable/apps/org.bootcinstaller.Installer.svg" height="64">
    <h1>bootc-installer</h1>
    <p>A GTK 4 / Libadwaita Flatpak installer for <a href="https://projectbluefin.io">Project Bluefin</a> and other <a href="https://universal-blue.org">Universal Blue</a> bootc images.</p>
    <hr />
</div>

bootc-installer is a guided graphical installer for [bootc](https://containers.github.io/bootc/) container-native OS images. It handles everything from disk partitioning and encryption setup to post-install personalisation — including importing your files and settings from an existing Windows installation.

It supports two distinct boot stacks:

| Stack | Images | Bootloader | Root FS | Layout |
|---|---|---|---|---|
| **systemd-boot** | [Dakota](https://github.com/projectbluefin/dakota) | systemd-boot + UKI | btrfs + composefs | 2-partition (EFI + root) |
| **GRUB2** | Bluefin, Bluefin-LTS, Bazzite | GRUB2 | XFS or btrfs | 3-partition (EFI + `/boot` + root) |

## Features

### Install pipeline

The `fisherman` Go backend executes a 9-step pipeline entirely from a JSON recipe:

1. **Partition** — layout depends on the target boot stack:
   - **systemd-boot (Dakota):** 2-partition GPT — EFI (1 GiB FAT32) + root. systemd-boot reads the FAT32 ESP directly; no separate `/boot` partition is needed. The root partition is tagged with the architecture-specific GPT type GUID so systemd-boot can auto-discover it.
   - **GRUB2 (Bluefin, Bluefin-LTS):** 3-partition GPT — EFI (FAT32) + `/boot` (ext4) + root. The separate ext4 `/boot` is required because GRUB's built-in XFS driver cannot read modern XFS features (`nrext64`, `exchange`, `rmapbt`), and `bootupctl` needs to find the `/boot` UUID from a raw block device rather than a LUKS mapper device.
2. **Format** — EFI (`mkfs.fat -F32`) and, for GRUB2 images only, `/boot` (`mkfs.ext4`)
3. **LUKS encryption** (optional) — `cryptsetup luksFormat` + `luksOpen`
4. **Format root** — `mkfs.xfs` or `mkfs.btrfs` (with optional named subvolumes)
5. **Mount** — everything assembled under `/mnt/fisherman-target`
6. **bootc install** — `podman run --privileged bootc install to-filesystem --skip-finalize` writes the OS into the mounted root. `--skip-finalize` keeps the target writable so post-install steps can still write files.
7. **Post-install** — hostname, Flatpak copy, Bluetooth/WiFi persistence, audio device naming, OEM detection, cache warming
8. **Windows data migration** (optional) — imports documents, photos, music, bookmarks, fonts, and wallpapers from an existing Windows partition
9. **Finalize** — `fstrim` → remount read-only → `fsfreeze`/`fsthaw`. This replicates what `bootc install finalize` would do (it is currently a no-op upstream), ensuring a clean filesystem state before reboot.

> **Scratch space note:** fisherman uses `/var/fisherman-tmp` (disk-backed, bind-mounted to `/var/tmp`) as scratch space for OCI blob downloads. `/run` is a tmpfs capped at ~50% RAM and is too small for large images — do not redirect scratch there.

### Dakota / systemd-boot images

[Dakota](https://github.com/projectbluefin/dakota) is the next-generation Project Bluefin variant built on a modern sealed-image stack. The installer handles it as a first-class target with a different code path from GRUB2-based images:

| Feature | Dakota |
|---|---|
| **Bootloader** | systemd-boot + UKI (Unified Kernel Image) |
| **Deployment backend** | composefs (`--composefs-backend`) |
| **Root filesystem** | btrfs |
| **Partition layout** | 2-partition GPT: EFI (1 GiB FAT32) + root |
| **GPT auto-discovery** | Root partition tagged with the x86-64 Linux root GUID so systemd-boot finds it without explicit configuration |
| **User creation** | Not required — dakota ships a first-boot user-setup flow |
| **Recipe fields** | `"bootloader": "systemd"`, `"composeFsBackend": true` |

> **Bluefin / Bluefin-LTS** continue to use the GRUB2 + 3-partition + XFS/ext4 stack. The installer auto-selects the correct path based on `bootloader` and `composeFsBackend` in the recipe — no manual steps needed.

### Encryption

| Mode | Description |
|------|-------------|
| `none` | Unencrypted install |
| `luks-passphrase` | LUKS2 with user-supplied passphrase |
| `tpm2-luks` | LUKS2 auto-unlocked by TPM2 at boot (no passphrase prompt) |
| `tpm2-luks-passphrase` | TPM2 primary + passphrase fallback. A recovery key is shown on screen and must be acknowledged before proceeding. |

### Instant first boot

These run automatically during every install — no user action required:

| Feature | What it does |
|---------|-------------|
| **Bluetooth persistence** | Copies `/var/lib/bluetooth` into the installed OS so previously-paired devices reconnect immediately on first boot |
| **WiFi persistence** | Copies NetworkManager `.nmconnection` files so saved networks reconnect automatically |
| **Audio device naming** | Installs WirePlumber rules that rename ugly ALSA identifiers (e.g. `alsa_output.pci-0000_00_1f.3.analog-stereo`) to human-readable names, and hides S/PDIF and Pro Audio sinks |
| **Live audio fix** | Applies the same audio naming rules to the live session immediately, so headphones work before you even reboot |
| **OEM detection** | Detects ASUS, Framework, and TUXEDO hardware and queues the appropriate first-boot brew packages |
| **Cache warming** | Pre-generates font, icon, pixbuf, GIO, ldconfig, man-db, and Flatpak caches so the first boot feels instant rather than spending 30+ seconds regenerating them |
| **Print services** | Enables `cups-browsed`, `avahi-daemon`, and `ipp-usb` so USB printers and AirPrint work out of the box |

### Windows data migration (Slurp)

When an existing Windows partition is detected, the installer offers to import your data. A scan runs asynchronously and shows per-user category checkboxes with size estimates:

| Category | What's imported |
|----------|----------------|
| Documents | Files from `Documents`, `Desktop`, `Downloads` |
| Photos | Files from `Pictures` |
| Music | Files from `Music` |
| Bookmarks | Chrome/Edge browser bookmarks |
| Fonts | User-installed fonts from `AppData\Local\Microsoft\Windows\Fonts` |
| **Wallpaper** | Current and recent Windows wallpapers — always imported as a silent easter egg even if the slurp step is skipped |

A RAM budget warning appears if the selected categories would exceed available memory. Wallpaper thumbnails for the GNOME wallpaper picker are pre-generated during install.

### Phone companion

During installation, the installer starts a local HTTPS server (port 8443, self-signed cert) and displays a QR code. Scanning it with your phone opens a page where you can fill in account details and preferences from your phone instead of typing on the installer screen. Configuration is submitted as JSON and fed directly into the recipe.

### Video playback during install

The progress screen plays a branded AV1/VP9 video during the install. Distributions can provide their own video at `/etc/bootc-installer/install-video.webm`. The installer validates GStreamer codec availability before attempting playback and falls back gracefully to a static progress display if the required codecs are missing.

### Offline / live ISO install

When the installer detects it is running on a live ISO (via `/etc/bootc-installer/live-iso-mode`), it switches to offline mode: the pre-embedded OCI image in the ISO's VFS containers-storage is passed to fisherman via `additionalImageStores` so no network pull is required.

---

## Installing

### Production

```bash
curl -Lo installer.flatpak \
  https://github.com/projectbluefin/bootc-installer/releases/latest/download/org.bootcinstaller.Installer.flatpak \
  && sudo flatpak uninstall -y org.bootcinstaller.Installer org.bootcos.Installer 2>/dev/null; sudo flatpak install --bundle -y installer.flatpak
```

### Devel (latest `dev` branch build)

```bash
curl -Lo installer-devel.flatpak \
  https://github.com/projectbluefin/bootc-installer/releases/download/latest-dev/org.bootcinstaller.Installer.Devel.flatpak \
  && sudo flatpak uninstall -y org.bootcinstaller.Installer.Devel 2>/dev/null; sudo flatpak install --bundle -y installer-devel.flatpak
```

---

## Recipe Format

The installer drives the `fisherman` backend with a JSON recipe file. The wizard generates one automatically, but you can write one by hand for automation or liveISO customisation.

### Minimal recipe (Bluefin / Bluefin-LTS, XFS, GRUB2, no encryption)

```json
{
  "disk": "/dev/sda",
  "filesystem": "xfs",
  "btrfsSubvolumes": false,
  "encryption": { "type": "none" },
  "image": "ghcr.io/projectbluefin/bootcos:latest",
  "targetImgref": "ghcr.io/projectbluefin/bootcos:latest",
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

### Dakota (systemd-boot + composefs + btrfs)

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

`bootloader: "systemd"` selects the 2-partition layout (EFI + root) and enables GPT auto-discovery root retagging. `composeFsBackend: true` passes `--composefs-backend` to bootc. User creation is skipped for Dakota because it ships its own first-boot setup flow.

### Btrfs + TPM2/LUKS encryption (Bluefin-LTS)

```json
{
  "disk": "/dev/nvme0n1",
  "filesystem": "btrfs",
  "btrfsSubvolumes": true,
  "encryption": { "type": "tpm2-luks" },
  "image": "ghcr.io/projectbluefin/bootcos:latest",
  "targetImgref": "ghcr.io/projectbluefin/bootcos:latest",
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
  "image": "ghcr.io/projectbluefin/bootcos:latest",
  "targetImgref": "ghcr.io/projectbluefin/bootcos:latest",
  "selinuxDisabled": false,
  "unifiedStorage": true,
  "composeFsBackend": false,
  "bootloader": "grub2",
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
git submodule update --init --recursive
flatpak run org.flatpak.Builder --force-clean --user --install _build flatpak/org.bootcinstaller.Installer.json
flatpak run org.bootcinstaller.Installer
```

### Meson (development)

```bash
git submodule update --init --recursive
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


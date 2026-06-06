# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

**bootc-installer** is a multi-variant Flatpak GUI installer for bootc container images. It ships three desktop-environment variants (GNOME/GTK4/Adwaita, XFCE/GTK4, KDE/Qt-Kirigami) from a single Python codebase, backed by the `fisherman` Go install backend (git submodule).

## Build commands

```bash
# Build and install the GNOME Flatpak locally (~10 min first time, cached after)
flatpak run org.flatpak.Builder --force-clean --user --install _build \
  flatpak/org.bootcinstaller.Installer.json

# Build all three variants (GNOME + XFCE + KDE) at once
./BUILD_ALL_VARIANTS.sh --install

# Native (non-Flatpak) build — variant selectable
meson setup build -Dvariant=gnome -Dbuild-fisherman=false && ninja -C build

# Local dev loop (toolbox + BOOTC_DEMO=1)
./run-dev.sh           # auto-rebuild if sources changed, launch with demo mode
./run-dev.sh --rebuild # force full rebuild
./run-dev.sh --logs    # tail debug log only
```

## fisherman (Go submodule) commands

```bash
cd fisherman/fisherman
go build ./cmd/fisherman/    # compile check
go vet ./...                  # lint

# Run fisherman directly (needs root for disk ops)
go build -o /tmp/fisherman ./cmd/fisherman/
sudo /tmp/fisherman /path/to/recipe.json
```

## Two-component architecture

### fisherman (Go, `fisherman/fisherman/`)
Root-level CLI that reads a JSON recipe and executes a 9-step disk install pipeline. Emits newline-delimited JSON progress to stdout:
```json
{"type":"step","step":2,"total_steps":9,"step_name":"Formatting EFI partition"}
{"type":"substep","message":"Pulling container image"}
{"type":"complete","message":"Installation complete!"}
```

Steps: partition disk → format EFI + /boot → LUKS setup (optional) → format root → mount → `bootc install to-filesystem` (podman) → copy Flatpaks → write hostname → finalize.

**Critical design constraints:**
- Always **3-partition GPT** (EFI + ext4 `/boot` + root), even for unencrypted installs. The separate ext4 `/boot` is required because GRUB cannot read modern XFS features (`nrext64`, `exchange`, `rmapbt`), and `bootupctl` inside its bwrap sandbox needs to find `/boot` UUID from a raw block device.
- Scratch space is `/var/fisherman-tmp` (disk-backed, bind-mounted to `/var/tmp`). Do NOT change to `/run/*` — `/run` is tmpfs and too small for large image blobs.
- `--skip-finalize` is passed to bootc so step 9 can manually finalize (fstrim → remount ro → fsfreeze/thaw), because `bootc install finalize` is a no-op upstream.

### bootc-installer (Python, `bootc_installer/`)

Multi-variant GUI that collects user choices, writes a recipe JSON, then launches fisherman and parses its JSON progress output.

**Variants:**
| Variant | Entry point | Flatpak ID |
|---------|-------------|------------|
| GNOME (default) | `main.py` (GTK4/Adwaita) | `org.bootcinstaller.Installer` |
| XFCE | `main.py` (GTK4) | `org.xfceinstaller.Installer` |
| KDE | `main_qt.py` (Qt/Kirigami) | `org.kdeinstaller.Installer` |

**Module layout:**
- `core/` — shared business logic (disks, system, keymaps, locales)
- `defaults/` — wizard step widgets
- `views/` — progress, done, confirm, recovery-key, tour screens
- `widgets/` — reusable GTK4 widgets
- `windows/` — main window, dialogs, hardware warning windows
- `layouts/` — generic layout wrappers (yes_no, preferences)
- `utils/` — builder, processor, recipe, finals, codec_check, phone_companion, progress_parser
- `gtk/` — Blueprint UI files (.blp) for GNOME/XFCE
- `kde/` — QML UI + Python backend for KDE

**Flatpak sandbox constraints:**
- fisherman is staged to `~/.cache/bootc-installer/fisherman` by `_stage_fisherman_on_host()` in `progress.py` (host-visible via `--filesystem=host`).
- fisherman runs on the **host** via `flatpak-spawn --host pkexec <path>`.
- Reboot must use `flatpak-spawn --host systemctl reboot` (see `done.py`).

**Recipe JSON fields:** `disk`, `filesystem` (`xfs`/`btrfs`), `btrfsSubvolumes`, `encryption` (type + passphrase), `image`, `targetImgref`, `selinuxDisabled`, `hostname`, `flatpaks[]`.
Encryption types: `none`, `luks-passphrase`, `tpm2-luks`, `tpm2-luks-passphrase`.

## fisherman submodule workflow

fisherman (`fisherman/`) is a separate git repo (`projectbluefin/fisherman`). Changes there must be committed and pushed **separately**, then the parent repo's submodule pointer updated:

```bash
# 1. Commit in submodule
cd fisherman/fisherman && git add -A && git commit -m "..." && git push

# 2. Update pointer in parent repo
cd ~/src/bootc-installer
git add fisherman && git commit -m "chore: update fisherman submodule (...)" && git push
```

CI checks out submodules recursively — always verify CI passes after both pushes.

## Image catalog

`fisherman/data/images.json` is a recursive JSON tree of distro groups/leaves. Distros can override it at `/etc/bootc-installer/images.json` (system) or `$XDG_CONFIG_HOME/bootc-installer/images.json` (user).

## Testing

```bash
pytest tests/unit/ -q                     # unit tests (no display)
xvfb-run -a pytest tests/ui/ -q           # UI tests (Xvfb required)
python3 -m ruff check bootc_installer/ tests/  # lint
```

CI gate: `--cov-fail-under=47` (currently measuring 48%).

## Known issues

- **TPM2 enrolment:** ✅ Fixed in fisherman v0.2.0-34 — recovery key now emitted and shown in GUI.
- **KDE variant:** QML UI in progress — not all wizard screens implemented yet.

## Useful diagnostic commands (on install target)

```bash
tail -f ~/.cache/bootc-installer/fisherman-output.log
ls -lt ~/.cache/bootc-installer/bootc-recipe-*.json | head -1 | xargs cat
sudo lsblk -o NAME,SIZE,FSTYPE,LABEL,UUID /dev/nvme0n1
```

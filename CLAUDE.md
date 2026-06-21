# CLAUDE.md

bootc-installer is a GTK4/Libadwaita Flatpak GUI installer for BootcOS and Universal Blue bootc container images. Python GTK4 frontend + Go backend (fisherman, a git submodule).

## Build commands

```bash
# Build and install Flatpak locally (~10 min first time, cached after)
flatpak run org.flatpak.Builder --force-clean --user --install _build flatpak/org.bootcinstaller.Installer.json

# fisherman (Go submodule)
cd fisherman/fisherman
go build ./cmd/fisherman/    # compile check
go vet ./...                  # lint
```

## Two-component architecture

### fisherman (Go, `fisherman/fisherman/`)
Root-level CLI that reads a JSON recipe and executes a 9-step disk install pipeline. Emits newline-delimited JSON progress to stdout.

**Critical design constraints:**
- Always **3-partition GPT** (EFI + ext4 `/boot` + root), even unencrypted. The separate ext4 `/boot` is required because GRUB cannot read modern XFS features (`nrext64`, `exchange`, `rmapbt`), and `bootupctl` inside bwrap needs `/boot` UUID from a raw block device.
- Scratch space is `/var/fisherman-tmp` (disk-backed, bind-mounted to `/var/tmp`). Do NOT change to `/run/*` — `/run` is tmpfs and too small.
- `--skip-finalize` is passed to bootc so step 9 can manually finalize (fstrim → remount ro → fsfreeze/thaw), because `bootc install finalize` is a no-op upstream.

### bootc-installer (Python, `bootc_installer/`)
GTK4/Adwaita GUI that collects user choices, writes a recipe JSON, launches fisherman via VTE terminal.

**Flatpak sandbox constraints:**
- fisherman runs on the **host** via `flatpak-spawn --host pkexec <path>`.
- Reboot must use `flatpak-spawn --host systemctl reboot`.
- fisherman is staged to `~/.cache/bootc-installer/fisherman` on the host.

## fisherman submodule workflow

fisherman is a separate repo (`projectbluefin/fisherman`). Changes must be committed and pushed **separately**, then the parent repo's submodule pointer updated:

```bash
cd fisherman/fisherman && git add -A && git commit -m "..." && git push
cd ~/src/bootc-installer
git add fisherman && git commit -m "chore: update fisherman submodule (...)" && git push
```

CI checks out submodules recursively — always verify CI passes after both pushes.

## Known issues

- **UI freeze during blob download**: `__on_vte_contents_changed` in `progress.py` scrapes the entire VTE buffer on every character change.
- **TPM2 enrolment:** Fixed in fisherman v0.2.0-34 — recovery key now emitted and shown in GUI.

## Don'ts

- **Don't change the 3-partition GPT layout.** The separate ext4 `/boot` is non-negotiable.
- **Don't use `/run/*` for scratch space.** Always use `/var/fisherman-tmp`.
- **Don't skip the submodule push.** Changes in `fisherman/` must be pushed before updating the parent pointer, or CI breaks.
- **Don't pass recipe directly to fisherman from filesystem.** The Flatpak sandbox can't see it — use the host staging path.

## References
- `fisherman/data/images.json` — recursive distro image catalog
- `flatpak/org.bootcinstaller.Installer.json` — Flatpak manifest
- Recipe JSON fields: `disk`, `filesystem`, `encryption`, `image`, `targetImgref`, `hostname`, `flatpaks[]`

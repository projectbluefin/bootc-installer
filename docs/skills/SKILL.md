---
name: bootc-installer
description: bootc-installer — GTK4/Adwaita Flatpak installer for bootc images. Dev setup, build loop, testing, CI/release, and dakota-iso integration. Load when working in projectbluefin/bootc-installer.
---

# bootc-installer Skill

## Powerlevel

- **Level:** 2


Full dev, test, and release workflow for `projectbluefin/bootc-installer`.

## When to Use

- Working in `~/src/bootc-installer` (`projectbluefin/bootc-installer`)
- Adding or modifying a wizard step (defaults/, views/, windows/)
- Changing the fisherman Go backend (submodule at `fisherman/`)
- Debugging the install pipeline, progress parsing, or Flatpak sandbox
- Writing or fixing unit tests for GTK4 code without a display
- Building or deploying the GNOME Flatpak
- Working on the live-ISO integration with `dakota-iso`

## When NOT to Use

- The dakota BuildStream image — use `dakota-buildstream` / `dakota-add-package`
- Fisherman-only changes with no GUI impact — commit directly in the submodule
- Generic Python debugging not specific to this codebase

---

## Quick Commands

| Goal | Command |
|------|---------|
| Run unit tests | `cd ~/src/bootc-installer && pytest tests/unit/ -q` |
| Run UI tests (Xvfb) | `xvfb-run -a pytest tests/ui/ -q` |
| Run integration tests (root + QEMU) | `sudo FISHERMAN_BIN=/tmp/fisherman-test pytest tests/integration/ -v -s` |
| Lint | `python3 -m ruff check bootc_installer/ tests/` |
| Coverage report | `pytest tests/unit/ -q --cov=bootc_installer --cov-report=term-missing 2>&1 \| tail -5` |
| Dev loop (toolbox) | `./run-dev.sh` |
| Force rebuild | `./run-dev.sh --rebuild` |
| Tail debug log | `./run-dev.sh --logs` |
| Build Flatpak | `flatpak run org.flatpak.Builder --force-clean --user --install _build flatpak/org.bootcinstaller.Installer.json` |
| Build fisherman | `cd fisherman/fisherman && go build -o /var/tmp/fisherman-test ./cmd/fisherman/` |
| Lint fisherman | `cd fisherman/fisherman && go vet ./...` |
| Watch install log | `tail -f ~/.cache/bootc-installer/fisherman-output.log` |

---

## Architecture

### Two-Component Model

```
Python GUI  →  wizard finals  →  Processor  →  recipe.json
                                                    ↓
                                    fisherman (Go, runs as root via pkexec)
                                         ↓
                                    9-step disk install
```

### GUI: GNOME (GTK4/Adwaita)

Single variant: `org.bootcinstaller.Installer`. Entry point: `main.py`. Blueprint `.blp` files live in `gtk/`.

### fisherman Install Pipeline (9 steps)

| Step | Action |
|------|--------|
| 1 | Partition disk (3-partition GPT: EFI + ext4 `/boot` + root) |
| 2 | Format EFI (`mkfs.fat`) + `/boot` (`mkfs.ext4`) |
| 3 | LUKS setup (optional: `cryptsetup luksFormat` + `luksOpen`) |
| 4 | Format root (`mkfs.xfs` or `mkfs.btrfs`) |
| 5 | Mount at `/mnt/fisherman-target` |
| 6 | `bootc install to-filesystem` via `podman run --privileged` |
| 7 | Copy system Flatpaks, write hostname, WiFi/BT persistence, audio, OEM, caches |
| 8 | Windows data migration (`slurp`) if requested |
| 9 | Finalize: fstrim → remount ro → fsfreeze/thaw |

**Why 3-partition layout always?** GRUB cannot read modern XFS (`nrext64`, `exchange`, `rmapbt`), so `/boot` must be ext4. `bootupctl` in its bwrap sandbox also needs to find `/boot` UUID from a raw block device (fails on LUKS mapper).

**Scratch space:** `/var/fisherman-tmp` (disk-backed, bind-mounted to `/var/tmp`). Never `/run/*` — that's tmpfs and too small for large OCI blobs.

### Flatpak Sandbox Constraints

- fisherman is staged to `~/.cache/bootc-installer/fisherman` by `_stage_fisherman_on_host()` in `progress.py`
- fisherman runs on the **host** via `flatpak-spawn --host pkexec <path>`
- Reboot uses `flatpak-spawn --host systemctl reboot` (see `done.py`)
- Log: `~/.cache/bootc-installer/fisherman-output.log`

---

## Module Map

```
bootc_installer/
├── core/         disks.py, system.py, keymaps.py, locale.py, locales/
├── defaults/     disk.py, encryption.py, user.py, image.py, welcome.py,
│                 network.py, keyboard.py, language.py, timezone.py,
│                 conn_check.py, nvidia.py, theme.py, vm.py,
│                 qr_companion.py, slurp.py
├── views/        progress.py, done.py, confirm.py, confirm_data.py,
│                 recovery_key.py, tour.py
├── widgets/      page_header.py
├── windows/      main_window.py, dialog.py, dialog_credits.py,
│                 dialog_output.py, dialog_poweroff.py, dialog_recovery.py,
│                 window_cpu.py, window_ram.py, window_unsupported.py
├── layouts/      yes_no.py, preferences.py
├── utils/        processor.py, recipe.py, finals.py, builder.py,
│                 codec_check.py, progress_parser.py, phone_companion.py,
│                 run_async.py
├── gtk/          *.blp   (Blueprint UI files)
└── main.py       GTK4 entry point
```

**Key data flows:**
- `defaults/*.py` → `get_finals()` → `main_window.update_finals()` → `processor.py` → `recipe.json` → fisherman
- `progress.py` tails the log file and feeds events to `utils/progress_parser.py` → `apply_progress_event()`
- `utils/recipe.py` (`RecipeLoader`) loads `recipe.json` with override priority: `/etc/bootc-installer/` > `$XDG_CONFIG_HOME/bootc-installer/` > bundled GResource

---

## Dev Loop

### First-time setup

```bash
# Requires dakota-lab toolbox
toolbox list  # confirm dakota-lab exists

cd ~/src/bootc-installer
git submodule update --init --recursive

# Build fisherman
cd fisherman/fisherman && go build -o /var/tmp/fisherman-test ./cmd/fisherman/

# Install build deps (one-time)
toolbox run --container dakota-lab sudo dnf install -y \
  meson ninja-build python3-gobject python3-devel \
  blueprint-compiler libadwaita-devel desktop-file-utils mutter

# Build and install
cd ~/src/bootc-installer
toolbox run --container dakota-lab meson setup build \
  --prefix=/tmp/bootc-installer-dev -Dbuild-fisherman=false
toolbox run --container dakota-lab ninja -C build && \
toolbox run --container dakota-lab meson install -C build
```

### Daily dev loop

```bash
./run-dev.sh           # rebuild if sources changed, launch with BOOTC_DEMO=1
./run-dev.sh --rebuild # force full rebuild
./run-dev.sh --logs    # tail debug log only
```

`BOOTC_DEMO=1` intercepts at `on_installation_confirmed()` in `main_window.py` and calls `progress.start_demo()` — no fisherman, no disk touched.

**After editing `.blp` files:** `ninja -C build` recompiles blueprints automatically.  
**After editing fisherman:** `cd fisherman/fisherman && go build -o /var/tmp/fisherman-test ./cmd/fisherman/`

### toolbox background launch

`toolbox run` must be in foreground. For timed testing:
```bash
toolbox run --container dakota-lab bash /tmp/launch-installer.sh &
sleep 4 && kill %1
```
Do NOT use `nohup` or `setsid` with `toolbox run` — they silently fail to connect to Wayland.

---

## Testing

### Test suite

```
tests/
├── unit/    662 tests, no display required (pytest tests/unit/ -q)
├── ui/      GTK integration tests (xvfb-run -a pytest tests/ui/ -q)
└── integration/  E2E fisherman install (root + QEMU/NBD; not in CI)
```

**CI gate:** `--cov-fail-under=51` (currently measuring 52%, 5675 stmts, 712 tests)  
**Ruff:** run before every commit — `python3 -m ruff check bootc_installer/ tests/`

### Key unit test files

| File | What it covers |
|------|----------------|
| `test_processor.py` | 185+ recipe assembly paths |
| `test_progress_parser.py` | `apply_progress_event`, `new_progress_state` (100%) |
| `test_recipe.py` | `RecipeLoader` (100%) |
| `test_builder.py` | `Builder` class (99%) |
| `test_disk.py` | `defaults/disk.py` pure logic |
| `test_encryption.py` | Passphrase strength, `get_finals` |
| `test_meson_sources.py` | Every `.py` listed in `meson.build` (regression guard) |
| `test_main_window.py` | `page.delta` getattr safety regression |
| `test_network_helpers.py` | `defaults/network.py` (NM stubbed) |
| `test_disks.py` | Boot disk filtering |

### GTK unit testing without a display

GTK subclasses cannot be instantiated without a display. Use:

```python
def _build_gi_stubs():
    # Install sys.modules stubs for gi.repository.*
    ...

def _import_MyClass_fresh():
    _build_gi_stubs()
    sys.modules.pop("bootc_installer.defaults.mymodule", None)
    return importlib.import_module("bootc_installer.defaults.mymodule")

class TestMyClass(unittest.TestCase):
    def setUp(self):
        mod = _import_MyClass_fresh()
        self.obj = mod.MyClass.__new__(mod.MyClass)
        self.obj._MyClass__some_attr = ...       # name-mangled private attr
        self.obj.some_widget = MagicMock()       # mock child widgets
```

See `test_disk.py`, `test_encryption.py`, `test_timezone.py` for canonical examples.

**⚠️ GTK stub contamination:** Always call `_build_gi_stubs()` inside `_import_X_fresh()`, not once at module level — test files run alphabetically and earlier stubs bleed into later ones. See `PITFALLS.md` for the full pattern.

### Coverage gate ratchet

Never raise `--cov-fail-under` above the measured value:
```bash
pytest tests/unit/ -q --cov=bootc_installer --cov-report=term-missing 2>&1 | tail -5
```
Use the integer floor of the measured decimal (e.g. `47` for `47.57%`).

---

## fisherman Submodule Workflow

fisherman at `fisherman/` is a **separate git repo** (`projectbluefin/fisherman`). Commits must land there first, then the parent pointer is updated.

```bash
# 1. Edit + commit in submodule
cd ~/src/bootc-installer/fisherman/fisherman
# ... make changes ...
go build ./cmd/fisherman/     # compile check
go vet ./...                  # lint
git add -A && git commit -m "fix: describe" && git push

# 2. Update pointer in parent repo
cd ~/src/bootc-installer
git add fisherman
git commit -m "chore: update fisherman submodule (describe)" && git push
```

CI uses `submodules: recursive` — always push both before opening a PR.

---

## CI / Releases

| Trigger | Job | Output |
|---------|-----|--------|
| Push to `dev` | `devel` | `org.bootcinstaller.Installer.Devel.flatpak` → `continuous-dev` release |
| Push to `prod` | `production` | `org.bootcinstaller.Installer.flatpak` → `continuous` release |
| `v*` tag | both | Flatpak attached to tagged GitHub release |
| Any push | `python-test.yml` | Unit (cov gate 47%) + UI (Xvfb) tests |

Branch strategy: `feature/xyz → dev → prod`. Never open PRs directly against `prod`.

---

## ISO Integration

The live ISO (`projectbluefin/dakota-iso`) fetches the installer from the GitHub release:
```bash
RELEASE_TAG="continuous"     # stable
RELEASE_TAG="continuous-dev" # dev
```

The ISO overrides branding at runtime via:
- `/etc/bootc-installer/images.json` — overrides bundled image catalog
- `/etc/bootc-installer/recipe.json` — overrides distro name, welcome text, imgref

`RecipeLoader` applies these at the three-level priority chain: `/etc/bootc-installer/` > `$XDG_CONFIG_HOME/bootc-installer/` > bundled GResource.

---

## Key Design Constraints

1. **Always 3-partition GPT** — even for unencrypted installs (GRUB ext4 + bootupctl UUID requirement)
2. **Scratch at `/var/fisherman-tmp`** — never `/run/*` (tmpfs, too small)
3. **`--skip-finalize` to bootc** — step 9 does fstrim/remount ro/fsfreeze manually
4. **Flatpak archive sources only** — `"type": "archive"` with SHA256 in manifests; `git` sources fail in Flatpak sandbox (`safe.bareRepository=explicit`)
5. **GStreamer video deferred to `map` signal** — call `set_muted()`/`play()` only after the widget's `map` signal fires to avoid `GstPlayer` CRITICAL errors
6. **meson.build sources list** — every new `.py` file must be added to its subpackage's `sources = [...]` in `meson.build` or the Flatpak will fail with `ModuleNotFoundError` (caught by `test_meson_sources.py`)

---

## Key Quality Findings (2026-06-10 audit)

| Area | Finding |
|---|---|
| `conn_check.py` | Never check `github.com`; probe `ghcr.io:443` then `8.8.8.8:53` via socket — github.com is blocked in corporate/geo-filtered envs |
| `fisherman checkRequiredTools` | Must include ALL tools used anywhere in the pipeline — `systemd-cryptenroll` was missing for TPM2; disk wiped before failure surfaced |
| Python escape sequences | Raw strings required for any `\|` in string literals (`keyboard.py` had `"Czech (with <\|> key)"` → `SyntaxError` in Python 3.14+) |
| composefs user creation | `CreateUser` uses `root=sysroot` for composefs-native; correct path is `ComposeFsDeployEtcDirFn`. Latent — no current images use composefs+user creation but will matter when they do |
| Dead code | `keyboard.py`, `language.py`, `timezone.py` are NOT registered in `builder.py` — keyboard/language/timezone are not applied during install |
| Loop devices in k8s pods | `BLKRRPART` ioctl fails in containers; fisherman's `loopRescan()` doesn't create partition nodes in Argo pods — test infra limitation only, not a real-install bug |

## Pitfalls Reference

For detailed GTK testing patterns, stub contamination, Gio patching, ruff gotchas, conn_check socket pattern, TPM2 preflight rules, and loop device container limitations:

```bash
cat ~/src/bootc-installer/docs/skills/PITFALLS.md
```

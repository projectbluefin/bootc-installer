# AGENTS.md — AI Agent Guide for bootc-installer

This document describes the architecture, dev workflow, and key commands needed
to work on this project as an AI agent. Read it before making changes.

**Skills index:** [`docs/skills/INDEX.md`](docs/skills/INDEX.md) — engineering gotchas, architectural facts, composefs-native path layout, GTK testing patterns.

---

## Repository layout

```
bootc-installer/               ← this repo (projectbluefin/bootc-installer)
├── bootc_installer/          ← Python installer GUI (GTK4/Adwaita + Qt/KDE variants)
│   ├── core/                 ← shared business logic (disks, system, keymaps, locales)
│   ├── defaults/             ← wizard step widgets (disk, encryption, user, image, slurp…)
│   ├── views/                ← screens: progress.py, done.py, confirm.py, confirm_data.py, recovery_key.py, tour.py
│   ├── widgets/              ← reusable GTK4 widgets (page_header.py)
│   ├── windows/              ← main_window.py + dialogs (credits, output, poweroff, recovery)
│   │                           + hardware warning windows (window_cpu, window_ram, window_unsupported)
│   ├── layouts/              ← generic layout wrappers (yes_no.py, preferences.py)
│   ├── utils/                ← builder.py, processor.py, recipe.py, finals.py, codec_check.py, phone_companion.py…
│   ├── gtk/                  ← Blueprint UI files (.blp) for GNOME/XFCE variant
│   ├── kde/                  ← QML UI + Python backend for KDE/Kirigami variant
│   ├── main.py               ← GTK4/Adwaita entry point (GNOME + XFCE)
│   └── main_qt.py            ← Qt/Kirigami entry point (KDE)
├── fisherman/                ← git submodule → projectbluefin/fisherman (Go backend)
│   └── fisherman/
│       ├── cmd/fisherman/main.go          ← install pipeline (steps 1-9)
│       └── internal/
│           ├── disk/         ← partition, format, mount, finalize
│           ├── luks/         ← LUKS format, open, TPM2 enrol
│           ├── install/      ← bootc install to-filesystem (podman run)
│           ├── post/         ← hostname, flatpak copy, bluetooth, wifi, audio, OEM, caches
│           ├── progress/     ← JSON-line progress emitter
│           ├── recipe/       ← recipe.go schema + Validate()
│           ├── slurp/        ← Windows data migration (wallpapers, scan, extract)
│           └── runner/       ← Run() helper (exec + set-x logging)
├── flatpak/
│   ├── org.bootcinstaller.Installer.json        ← GNOME Flatpak manifest (GNOME 50 runtime)
│   ├── org.bootcinstaller.Installer.Devel.json  ← GNOME Devel manifest
│   ├── org.xfceinstaller.Installer.json         ← XFCE variant (xfce-platform runtime)
│   └── org.kdeinstaller.Installer.json          ← KDE variant (kde-platform runtime)
├── data/                     ← GSchema, desktop files, icons, polkit policies (all three variants)
├── docs/                     ← feature docs, test plans, live-iso.md, superpowers specs
├── po/                       ← translations
├── run-dev.sh                ← local dev launcher (toolbox + dakota-lab, BOOTC_DEMO=1)
├── BUILD_ALL_VARIANTS.sh     ← build GNOME + XFCE + KDE Flatpaks in one shot
├── MULTI_VARIANT_BUILD.md    ← guide for the three-variant build system
├── QUALIFY_SOFTWARE.sh       ← software-only release qualification script
└── .github/workflows/flatpak.yml   ← CI: builds + publishes "continuous" pre-release
```

---

## Two-component architecture

### fisherman (Go, submodule)

fisherman is a root-level CLI that reads a JSON recipe and executes the full
disk install pipeline. It emits newline-delimited JSON progress to stdout:

```json
{"type":"step","step":2,"total_steps":9,"step_name":"Formatting EFI partition"}
{"type":"substep","message":"Pulling container image"}
{"type":"info","message":"Writing hostname: bootcos"}
{"type":"complete","message":"Installation complete!"}
```

**Install pipeline (main.go):**

| Step | Action |
|------|--------|
| 1 | Partition disk (`sgdisk` via `disk.Partition` / `disk.PartitionEncrypted`) |
| 2 | Format EFI (`mkfs.fat -F32`) and optionally /boot (`mkfs.ext4`) |
| 3 | Set up LUKS (optional: `cryptsetup luksFormat` + `luksOpen`) |
| 4 | Format root filesystem (`mkfs.xfs` or `mkfs.btrfs`) |
| 5 | Mount everything at `/mnt/fisherman-target` |
| 6 | `bootc install to-filesystem` via `podman run --privileged` |
| 7 | Copy system Flatpaks (`/var/lib/flatpak` → target) |
| 8 | Write `/etc/hostname` into the ostree deployment |
| 9 | Finalize: fstrim → remount ro → fsfreeze/thaw |

**Key design decisions:**
- `--skip-finalize` is passed to bootc so the target stays writable for step 8.
  Step 9 manually replicates `bootc`'s internal `finalize_filesystem()`.
- Scratch space for bootc blob downloads is `/var/fisherman-tmp` (disk-backed),
  bind-mounted to `/var/tmp` on the host. Do NOT change this to `/run/*` —
  `/run` is a tmpfs (~50% RAM) and too small for large images.
- Partition layout: always **3-partition** (EFI + `/boot` ext4 + root). The
  separate ext4 `/boot` is required for two reasons: (1) GRUB's built-in XFS
  driver cannot read el10 XFS features (`nrext64`, `exchange`, `rmapbt`), so
  GRUB must only ever read ext4; (2) for encrypted installs, `bootupctl` (inside
  its bwrap sandbox) must be able to find the `/boot` UUID from a raw block
  device rather than a LUKS mapper. Both `Partition()` and
  `PartitionEncrypted()` produce the same 3-partition GPT table; the difference
  is that encrypted installs additionally set up LUKS on p3.

### bootc-installer (Python, multi-variant GUI)

The installer ships in three desktop-environment variants that share the same
Python core, fisherman backend, and wizard step logic:

| Variant | Entry point | Flatpak ID | Runtime |
|---------|-------------|------------|---------|
| **GNOME** (default) | `main.py` (GTK4/Adwaita) | `org.bootcinstaller.Installer` | GNOME 50 |
| **XFCE** | `main.py` (GTK4) | `org.xfceinstaller.Installer` | xfce-platform |
| **KDE** | `main_qt.py` (Qt/Kirigami) | `org.kdeinstaller.Installer` | kde-platform |

The GUI collects user choices and writes a recipe JSON, then launches fisherman
and tails its JSON log output (via a `GLib.timeout_add` polling loop in
`progress.py`).

**Flatpak sandbox constraints:**
- fisherman is staged to `~/.cache/bootc-installer/fisherman` (host-visible via
  `--filesystem=host`) by `_stage_fisherman_on_host()` in `progress.py`.
- fisherman runs on the **host** via `flatpak-spawn --host pkexec <path>`.
- `systemctl reboot` must be called as `flatpak-spawn --host systemctl reboot`
  from inside the sandbox (see `done.py`).
- The installer log is written to `~/.cache/bootc-installer/fisherman-output.log`.

**Recipe JSON written by the GUI:**

```json
{
  "disk": "/dev/nvme0n1",
  "filesystem": "xfs",
  "btrfsSubvolumes": false,
  "encryption": {
    "type": "tpm2-luks-passphrase",
    "passphrase": "hunter2"
  },
  "image": "ghcr.io/projectbluefin/bootcos:latest",
  "targetImgref": "ghcr.io/projectbluefin/bootcos:latest",
  "selinuxDisabled": true,
  "hostname": "bootcos",
  "flatpaks": ["org.mozilla.firefox", "..."]
}
```

Encryption types: `"none"`, `"luks-passphrase"`, `"tpm2-luks"`, `"tpm2-luks-passphrase"`.

---

## Development workflow

Work directly on `projectbluefin/bootc-installer` — there is no fork.
The single remote is `origin → git@github.com:projectbluefin/bootc-installer.git`.

```bash
# Standard branch-and-PR workflow
git checkout -b my-feature origin/dev
# ... make changes ...
git push origin my-feature
gh pr create --base dev
```

### Making changes to fisherman

fisherman lives at `fisherman/` and is a **git submodule** pointing to
`github.com/projectbluefin/fisherman`. You must commit and push changes there
**separately** before updating the parent repo's submodule pointer.

```bash
# 1. Edit files inside fisherman/fisherman/
cd fisherman/fisherman
# ... make changes ...
go build ./cmd/fisherman/   # quick compile check
go vet ./...                # lint

# 2. Commit + push fisherman
git add -A && git commit -m "fix: describe the change"
git push

# 3. Update the submodule pointer in the parent repo
cd /path/to/bootc-installer
git add fisherman
git commit -m "chore: update fisherman submodule (describe the change)"
git push
```

### Making changes to the Python GUI

```bash
cd /path/to/bootc-installer
# edit bootc_installer/views/*.py or other files

# Lint before committing
python3 -m ruff check bootc_installer/ tests/

git add -A && git commit -m "fix: describe the change"
git push
```

### Building and deploying the Flatpak locally

```bash
cd /path/to/bootc-installer

# Build and install locally (takes ~10 min first time; cached after)
flatpak run org.flatpak.Builder \
  --force-clean --user --install \
  _build flatpak/org.bootcinstaller.Installer.json

# Bundle for deployment to a remote machine
flatpak build-bundle \
  ~/.local/share/flatpak/repo \
  org.bootcinstaller.Installer.flatpak \
  org.bootcinstaller.Installer

# Deploy to a remote machine
scp org.bootcinstaller.Installer.flatpak user@<machine>:~
ssh user@<machine> \
  "flatpak uninstall --user -y org.bootcinstaller.Installer; \
   flatpak install --user --bundle -y ~/org.bootcinstaller.Installer.flatpak"
```

### Running the installer (on a live machine)

```bash
flatpak run org.bootcinstaller.Installer
# XFCE variant:
flatpak run org.xfceinstaller.Installer
# KDE variant:
flatpak run org.kdeinstaller.Installer
# Or with a local fisherman binary (dev/test):
BOOTC_FISHERMAN_PATH=/path/to/fisherman flatpak run org.bootcinstaller.Installer
```

### Local dev loop (toolbox)

```bash
# Requires a dakota-lab toolbox container
./run-dev.sh           # auto-rebuild if sources changed, launch with BOOTC_DEMO=1
./run-dev.sh --rebuild # force full rebuild
./run-dev.sh --logs    # tail debug log only

# Build all three variants as Flatpaks in one shot
./BUILD_ALL_VARIANTS.sh --install
```

`BOOTC_DEMO=1` intercepts at `on_installation_confirmed()` and runs a fake 5-step
progress sequence — no fisherman launched, no disk touched.  
Debug log: `~/.cache/bootc-installer/installer-debug.log`

### Invoking fisherman directly (for testing)

```bash
# Build fisherman
cd fisherman/fisherman
go build -o /tmp/fisherman ./cmd/fisherman/

# Run with a recipe (as root — fisherman needs root for disk ops)
sudo /tmp/fisherman /path/to/recipe.json

# Watch the log on a remote machine
ssh james@192.168.0.119 "tail -f ~/.cache/bootc-installer/fisherman-output.log"
```

---

## CI / releases

- **Every push to `dev`** triggers `.github/workflows/flatpak.yml` which builds
  the Flatpak and publishes it as the `continuous-dev` pre-release on GitHub (pushes to `prod` publish the `continuous` pre-release).
- **`.github/workflows/python-test.yml`** runs on every push: 665+ unit tests
  (no display) + GTK UI integration tests (Xvfb). Coverage gate: 47% unit.
- **Tagged pushes** (`v*`) publish a named release.
- Container: `ghcr.io/flathub-infra/flatpak-github-actions:gnome-50`
- The submodule is checked out recursively by CI (`submodules: recursive`).

Always verify CI passes after pushing both submodule + parent repo commits.

---

## Testing

### Test suite layout

```
tests/
├── unit/
│   ├── test_processor.py       ← 185+ pure-Python tests for processor.py (no display)
│   ├── test_image_helpers.py   ← 55+ tests for defaults/image.py pure helpers (_imgref_to_pretty_name, _count_leaves, _fetch_remote_flatpak_list, _load_manifest overrides)
│   ├── test_system.py          ← 40 tests for core/system.py (generate_hostname, has_nvidia_gpu, is_uefi, is_ram_enough)
│   ├── test_confirm_helpers.py ← 21 tests for confirm.py pure logic (_ENC_LABELS, quotes)
│   ├── test_slurp_helpers.py   ← 45+ tests for slurp.py pure logic (_fmt_bytes, get_finals, etc.)
│   ├── test_defaults_misc.py   ← tests for vm, nvidia, theme, network, conn_check defaults
│   ├── test_conn_check.py      ← tests for conn_check.py: should_show() offline/online, async check, env bypass
│   ├── test_codec_check.py     ← tests for utils/codec_check.py: GStreamer VP9/AV1 probe logic (100% coverage)
│   ├── test_done.py            ← D-Bus reboot contract, apply_icon, warmup_registry, icon extraction
│   ├── test_recipe.py          ← tests for utils/recipe.py RecipeLoader (100% coverage)
│   ├── test_recipe_loader.py   ← tests for utils/recipe loader logic incl. Flatpak live-ISO path
│   ├── test_run_async.py       ← tests for utils/run_async helpers
│   ├── test_recovery_key.py    ← set_recovery_key, ack_toggled, on_copy, on_continue (79% coverage)
│   ├── test_welcome.py         ← _needs_bluetooth_pairing() all branches, get_finals, should_show (68% coverage)
│   ├── test_user_validation.py ← username derivation, password strength, get_finals()
│   ├── test_locale.py          ← tests for defaults/locale.py keyboard/locale enumeration
│   ├── test_diskutils.py       ← core/disks.py: Disk/Partition/DisksManager via __new__ + injection (99% coverage)
│   ├── test_disks.py           ← DisksManager boot-disk filtering: excludes boot disk, removable media
│   ├── test_keymaps.py         ← tests for keymaps module layout
│   ├── test_main_args.py       ← tests for __main__.py CLI argument parsing
│   ├── test_main_window.py     ← main_window navigation regression: page.delta getattr safety
│   ├── test_meson_sources.py   ← guard: every .py in each subpackage must be listed in meson.build
│   ├── test_network_helpers.py ← defaults/network.py pure logic (NM-stubbed, no D-Bus)
│   ├── test_pastry_compat.py   ← tests for libpastry integration compat layer
│   ├── test_progress.py        ← views/progress.py: _fisherman_argv_direct, staged binary helpers
│   ├── test_progress_parser.py ← utils/progress_parser.py: apply_progress_event, new_progress_state (100% coverage)
│   ├── test_qr_companion.py    ← tests for qr_companion.py / phone_companion.py (CompanionServer, get_local_ip, QR step logic)
│   ├── test_phone_companion.py ← CompanionServer lifecycle, get_local_ip, TLS setup, handler GET/POST (all mocked — no network)
│   ├── test_finals.py          ← _extract_icon_and_name() edge cases (empty, split fields, first-occurrence)
│   ├── test_builder.py         ← Builder class: load, display-conditions, get_finals, distro_info (99% coverage)
│   ├── test_disk.py            ← defaults/disk.py pure logic: should_show, get_finals, auto_select, partition recipe
│   ├── test_timezone.py        ← BootcDefaultTimezone get_finals, timezone_verify, gen/del_deltas
│   ├── test_language.py        ← BootcDefaultLanguage get_finals, gen/del_deltas
│   ├── test_keyboard.py        ← BootcDefaultKeyboard get_finals, layout selection
│   ├── test_encryption.py      ← BootcDefaultEncryption get_finals, passphrase strength (Weak/Fair/Strong), btn_next logic
│   ├── test_dialog_recovery.py ← _host_binary_exists() subprocess helper (61% coverage)
│   ├── test_layouts.py         ← BootcLayoutYesNo/BootcLayoutPreferences: get_finals, should_show, __next_step, __on_response, __on_info
│   ├── test_tour_helpers.py    ← BootcTour.__build_ui() asset URI routing (resource:///, resource://, abs path, GResource path)
│   └── test_branding_parity.py ← parity guard: all wizard steps must be importable
├── ui/
│   ├── conftest.py             ← GResource loader + Adw.init() for headless GTK
│   ├── test_wizard.py          ← GTK integration tests (real widgets via Xvfb)
│   ├── test_should_show.py     ← tests for should_show() step visibility pattern
│   ├── test_done_credits.py    ← tests for done screen and credits dialog
│   ├── test_demo_e2e.py        ← end-to-end demo flow tests
│   └── test_confirm_progress.py ← GTK integration: confirm.py screen rendering + BootcProgress widget
└── integration/
    └── test_e2e_install.py     ← end-to-end fisherman install tests (requires root + QEMU/NBD; not run in standard CI)
```

Run unit tests:
```bash
pytest tests/unit/ -q
```

Run UI tests (requires a display — use Xvfb in CI or a live X session locally):
```bash
xvfb-run -a pytest tests/ui/ -q
```

Run integration tests (requires root, fisherman binary, QEMU+NBD):
```bash
# See tests/integration/test_e2e_install.py for full prerequisites
sudo FISHERMAN_BIN=/tmp/fisherman-test pytest tests/integration/ -v -s
```

### Coverage baseline

Current measured coverage (as of 2026-06-10, post quality audit):
- **Unit tests**: 52% of `bootc_installer/` (712 tests, 5675 stmts) — CI gate: `--cov-fail-under=51`
- **UI tests**: not measured locally (requires meson/ninja build for GResources)

Key per-module baselines:
| Module | Coverage |
|--------|----------|
| `utils/processor.py` | 100% |
| `utils/progress_parser.py` | 100% |
| `utils/codec_check.py` | 100% |
| `utils/finals.py` | 100% |
| `utils/recipe.py` | 100% |
| `views/confirm_data.py` | 100% |
| `core/system.py` | 100% |
| `core/disks.py` | 99% |
| `utils/builder.py` | 99% |
| `utils/phone_companion.py` | 97% |
| `utils/run_async.py` | 94% |
| `utils/pastry_compat.py` | 93% |
| `views/tour.py` | 83% |
| `defaults/timezone.py` | 85% |
| `views/recovery_key.py` | 79% |
| `defaults/welcome.py` | 68% |
| `defaults/language.py` | 69% |
| `defaults/nvidia.py` | 69% |
| `defaults/user.py` | 65% |
| `defaults/image.py` | 61% |
| `defaults/keyboard.py` | 62% |
| `windows/dialog_recovery.py` | 61% |
| `layouts/preferences.py` | 61% |
| `defaults/qr_companion.py` | 59% |
| `defaults/theme.py` | 59% |
| `layouts/yes_no.py` | 58% |
| `views/done.py` | 53% |
| `windows/dialog_credits.py` | 45% |
| `defaults/conn_check.py` | 72% |
| `defaults/encryption.py` | 73% |
| `defaults/vm.py` | 67% |
| `views/progress.py` | 20% (GTK-heavy, unit-test only via mocks) |
| `defaults/disk.py` | 31% (GTK-heavy) |
| `defaults/slurp.py` | 29% (GTK-heavy) |
| `defaults/network.py` | 26% (GTK-heavy) |
| `windows/main_window.py` | 0% (GTK-heavy, covered by UI tests) |
| `main_qt.py` | 0% (KDE variant — covered manually) |

The CI coverage gate (`--cov-fail-under`) is a ratchet — it should only go up. To measure before raising the gate:
```bash
pytest tests/unit/ -q --cov=bootc_installer --cov-report=term-missing 2>&1 | tail -5
xvfb-run -a pytest tests/ui/ -q --cov=bootc_installer --cov-report=term-missing 2>&1 | tail -5
```
Never raise the gate above the *measured* value — use the actual number as the new floor, not an aspirational target.

### Rules for keeping tests in sync with UI changes

**When you change `bootc_installer/utils/processor.py`:**
- Update `tests/unit/test_processor.py` to cover new fields or changed logic.
- Every new recipe field emitted by `processor.py` should have at least one
  parametrized test asserting the correct JSON value in the output recipe.

**When you change `bootc_installer/utils/finals.py`:**
- Update `tests/unit/test_finals.py` — covers all `_extract_icon_and_name()` edge cases
  (empty list, non-dict entries, fields split across dicts, first-occurrence wins, early break).

**When you add or change `bootc_installer/utils/codec_check.py`:**
- Update `tests/unit/test_codec_check.py` — covers GStreamer element probe, missing-codec error path, and fallback behavior.

**When you change `bootc_installer/defaults/image.py` pure helpers:**
- Update `tests/unit/test_image_helpers.py` — covers `_find_icon_for_imgref`, `_resolve_aliases`, `_imgref_to_pretty_name`, `_count_leaves`, `_fetch_remote_flatpak_list`, and `_load_manifest` override paths.
- Note: `_imgref_to_pretty_name` returns slashless input unchanged (not title-cased).

**When you change `bootc_installer/core/system.py`:**
- Update `tests/unit/test_system.py` — covers `generate_hostname` (DMI + fallbacks), `has_nvidia_gpu`, `is_uefi`, `is_ram_enough`, `is_cpu_enough`.

**When you change a wizard step's `get_finals()` output (e.g. `defaults/image.py`,
`defaults/disk.py`, `defaults/encryption.py`, `defaults/user.py`):**
- Update the corresponding `tests/unit/test_disk.py`, `test_encryption.py`, etc. if the
  changed step has a dedicated test file.
- Update `tests/ui/test_wizard.py` if the changed step is covered there.
- If a new `get_finals()` key is added, add an assertion for it in the
  relevant `TestXxxStep` class.

**When you add or change `bootc_installer/utils/recipe.py`:**
- Update `tests/unit/test_recipe.py` — covers RecipeLoader (100% coverage).

**When you add or change meson.build source lists:**
- `tests/unit/test_meson_sources.py` automatically validates that every `.py` in each subpackage is listed. Fix the meson.build, not the test.

**When you change `bootc_installer/defaults/network.py` pure helpers:**
- Update `tests/unit/test_network_helpers.py` — NM is stubbed, no D-Bus required.

**When you change `bootc_installer/core/disks.py` boot-disk logic:**
- Update `tests/unit/test_disks.py` (boot disk filtering) AND `tests/unit/test_diskutils.py` (Disk/Partition/DisksManager via `__new__`).

**When you change `bootc_installer/utils/progress_parser.py`:**
- Update `tests/unit/test_progress_parser.py` — covers `apply_progress_event` and `new_progress_state` (100% coverage).

**When you change `bootc_installer/views/progress.py` argv/staging helpers:**
- Update `tests/unit/test_progress.py` — covers `_fisherman_argv_direct` and staged binary path helpers without a display.

**When you add a new `.py` file to any subpackage:**
- Also add it to the `sources = [...]` list in the subpackage's `meson.build` — `test_meson_sources.py` will catch it otherwise.

**When you add a new wizard step:**
- Add the step to `_SYS_RECIPE["steps"]` in `tests/ui/test_wizard.py` only if
  its template widgets are available in the CI libadwaita version (Ubuntu 24.04
  ships libadwaita 1.5.x — `Adw.ButtonRow` and other ≥ 1.6 widgets will fail).
  If in doubt, leave the step out of the test recipe and test via unit tests only.
- Add unit test coverage in `test_processor.py` for any new recipe fields the
  step produces.
- Add the step's module to `test_branding_parity.py` — that test guards that all
  wizard step modules are importable without a display.

**When you add a new defaults/ module with `should_show()` logic:**
- Add a test in `test_conn_check.py` (or a peer file) covering both the True
  and False branches, including any offline/env-flag bypass paths.

**When you change `fisherman/fisherman/internal/recipe/recipe.go`:**
- Update `fisherman/fisherman/internal/recipe/recipe_test.go` — add valid and
  invalid cases for any new fields or validation rules.

---

## Key files to know

| File | Purpose |
|------|---------|
| `fisherman/fisherman/cmd/fisherman/main.go` | Install pipeline, step ordering, totalSteps, `scan` subcommand |
| `fisherman/fisherman/internal/disk/format.go` | `FinalizeFilesystem`, `FormatBoot`, `MountEFI`, `BindMount` |
| `fisherman/fisherman/internal/disk/partition.go` | `Partition` (2-part), `PartitionEncrypted` (3-part) |
| `fisherman/fisherman/internal/luks/luks.go` | LUKS format, open, close, `EnrollTPM2` |
| `fisherman/fisherman/internal/install/install.go` | `BootcInstall` → podman command |
| `fisherman/fisherman/internal/post/post.go` | `WriteHostname`, `CopyFlatpaks`, `CopyBluetoothPairings`, `CopyWiFiConnections`, `EnablePrintServices`, `Cleanup` |
| `fisherman/fisherman/internal/post/audio.go` | WirePlumber friendly device names, hide S/PDIF, live+persist |
| `fisherman/fisherman/internal/post/caches.go` | `WarmCaches` — pre-generate 8 system caches for instant first boot |
| `fisherman/fisherman/internal/post/oem.go` | OEM vendor detection (ASUS/Framework/TUXEDO), first-boot brew packages |
| `fisherman/fisherman/internal/slurp/wallpaper.go` | NTFS detect, wallpaper extraction/injection, thumbnail generation |
| `fisherman/fisherman/internal/slurp/scan.go` | `Scan()` enumerates Windows user data by category, `ScanJSON()` for CLI |
| `fisherman/fisherman/internal/slurp/data.go` | `ExtractData`/`InjectData` with RAM budget enforcement |
| `fisherman/fisherman/internal/recipe/recipe.go` | Recipe struct, `SlurpSpec`, `Validate()` |
| `bootc_installer/views/progress.py` | Video player, fisherman launch, JSON progress parsing |
| `bootc_installer/views/confirm.py` | Pre-install confirmation screen |
| `bootc_installer/views/confirm_data.py` | Data confirmation view helper |
| `bootc_installer/views/recovery_key.py` | Recovery key screen (post-encrypted-install) |
| `bootc_installer/views/done.py` | Final screen, reboot button, log viewer, `warmup_registry()` (post-install skopeo warmup) |
| `bootc_installer/views/tour.py` | Post-install feature tour |
| `bootc_installer/widgets/page_header.py` | Reusable page header widget |
| `bootc_installer/defaults/conn_check.py` | Connection check — skipped when offline_install=True |
| `bootc_installer/windows/main_window.py` | Wizard, `_is_offline_install()`, context builder, `update_finals()` |
| `bootc_installer/windows/dialog_credits.py` | Credits dialog |
| `bootc_installer/windows/dialog_output.py` | Output/log viewer dialog |
| `bootc_installer/windows/dialog_poweroff.py` | Power-off confirmation dialog |
| `bootc_installer/windows/dialog_recovery.py` | Recovery key display dialog |
| `bootc_installer/windows/window_cpu.py` | CPU hardware warning window |
| `bootc_installer/windows/window_ram.py` | RAM hardware warning window |
| `bootc_installer/windows/window_unsupported.py` | Unsupported hardware warning window |
| `bootc_installer/utils/processor.py` | Recipe assembly: slurpWallpapers, additionalImageStores |
| `bootc_installer/utils/finals.py` | `_extract_icon_and_name()` — pure helper used by `main_window.update_finals()` |
| `bootc_installer/utils/recipe.py` | `RecipeLoader` — loads and validates recipe.json from multiple override paths |
| `bootc_installer/utils/codec_check.py` | GStreamer VP9/AV1 codec probe — called by progress.py before video playback |
| `bootc_installer/utils/progress_parser.py` | Pure parser: `apply_progress_event()`, `new_progress_state()` — no GTK dependency |
| `bootc_installer/defaults/qr_companion.py` | QR Phone Companion wizard step (`BootcDefaultQrCompanion`): starts CompanionServer, shows QR code, polls for phone config |
| `bootc_installer/utils/phone_companion.py` | `CompanionServer` (HTTPS/8443), `get_local_ip()`, `CONFIG_RECEIVED_EVENT` — must be mocked in tests |
| `bootc_installer/defaults/slurp.py` | Windows data slurp wizard step: async fisherman scan, category checkboxes, budget warning |
| `bootc_installer/kde/` | Qt/Kirigami entry point and QML UI for KDE variant |
| `bootc_installer/main_qt.py` | Qt/Kirigami Python entry point for KDE variant |
| `flatpak/org.bootcinstaller.Installer.json` | GNOME Flatpak manifest (GNOME 50 runtime) |
| `flatpak/org.bootcinstaller.Installer.Devel.json` | Devel Flatpak manifest (GNOME 50 runtime) |
| `flatpak/org.xfceinstaller.Installer.json` | XFCE Flatpak manifest |
| `flatpak/org.kdeinstaller.Installer.json` | KDE Flatpak manifest |
| `run-dev.sh` | Local dev launcher: toolbox build + `BOOTC_DEMO=1`, `--rebuild` and `--logs` flags |
| `BUILD_ALL_VARIANTS.sh` | Build all three variants (GNOME + XFCE + KDE) as Flatpaks |
| `MULTI_VARIANT_BUILD.md` | Guide for the multi-variant build system |
| `QUALIFY_SOFTWARE.sh` | Software-only release qualification (all unit + UI tests + ruff) |
| `docs/live-iso.md` | How to build a bootable live ISO with bootc-installer |
| `docs/features/` | Per-feature design docs (GStreamer codec validation, libpastry, QR companion, soundtrack QR) |
| `docs/test-plans/` | Test plans: E2E verification, encryption matrix, failure paths, release qualification |
| `.github/workflows/flatpak.yml` | CI build + publish workflow |
| `.github/workflows/python-test.yml` | CI unit + GTK UI integration tests |
| `tests/unit/test_processor.py` | 185+ unit tests for processor paths, disk variants, image fallbacks (no display) |
| `tests/unit/test_slurp_helpers.py` | 45+ unit tests for slurp.py pure logic (no display) |
| `tests/unit/test_codec_check.py` | unit tests for GStreamer codec probe (no display) |
| `tests/unit/test_conn_check.py` | unit tests for conn_check.py should_show() + offline bypass |
| `tests/unit/test_done.py` | D-Bus reboot contract, apply_icon, warmup_registry, icon extraction |
| `tests/unit/test_finals.py` | _extract_icon_and_name() all edge cases (empty, split, first-wins) |
| `tests/unit/test_builder.py` | Builder class: load, conditions, get_finals, distro_info (99% coverage) |
| `tests/unit/test_phone_companion.py` | CompanionServer lifecycle + handler GET/POST; all network mocked |
| `tests/unit/test_disk.py` | defaults/disk.py pure logic: should_show, get_finals, auto_select |
| `tests/unit/test_encryption.py` | BootcDefaultEncryption: get_finals, passphrase strength, btn_next |
| `tests/unit/test_timezone.py` | BootcDefaultTimezone: get_finals, gen/del_deltas |
| `tests/unit/test_language.py` | BootcDefaultLanguage: get_finals, gen/del_deltas |
| `tests/unit/test_keyboard.py` | BootcDefaultKeyboard: get_finals, layout selection |
| `tests/unit/test_qr_companion.py` | QR step logic (mocked — no network) |
| `tests/unit/test_diskutils.py` | core/disks.py: Disk/Partition/DisksManager pure logic (99% coverage) via `__new__` + injection |
| `tests/unit/test_disks.py` | DisksManager boot-disk filtering (excludes boot disk + removable media) |
| `tests/unit/test_recovery_key.py` | recovery_key.py: set_recovery_key, ack_toggled, on_copy, on_continue (79% coverage) |
| `tests/unit/test_welcome.py` | welcome.py: _needs_bluetooth_pairing() all branches, get_finals, should_show |
| `tests/unit/test_defaults_misc.py` | vm/nvidia/theme/conn_check/network step logic (no display) |
| `tests/unit/test_network_helpers.py` | defaults/network.py pure logic (NM stubbed, no D-Bus) |
| `tests/unit/test_progress.py` | views/progress.py: _fisherman_argv_direct, staged binary helpers |
| `tests/unit/test_progress_parser.py` | utils/progress_parser.py: apply_progress_event + new_progress_state (100%) |
| `tests/unit/test_recipe.py` | utils/recipe.py RecipeLoader: load, validate, override paths (100%) |
| `tests/unit/test_main_window.py` | main_window.py navigation regression: page.delta getattr safety |
| `tests/unit/test_meson_sources.py` | guard: every .py in each subpackage listed in meson.build |
| `tests/ui/conftest.py` | GResource loader + `Adw.init()` for headless GTK tests |
| `tests/ui/test_wizard.py` | GTK integration tests (image step finals, E2E recipe gen) |
| `tests/ui/test_should_show.py` | Tests for should_show() step visibility pattern |
| `tests/ui/test_confirm_progress.py` | GTK integration: confirm.py screen + BootcProgress widget |
| `tests/integration/test_e2e_install.py` | E2E fisherman install tests (root + QEMU/NBD; not in standard CI) |

---

## Known issues / in-progress work

- **`bootc install finalize` is a no-op upstream**: We replicate the real finalization
  ops in `disk.FinalizeFilesystem()` ourselves (fstrim, remount ro, fsfreeze/thaw).
- **Windows data slurp GUI**: Fully implemented (#22, closed). Backend (`fisherman scan`,
  `ExtractData`, `InjectData`) and GUI wizard step (`bootc_installer/defaults/slurp.py`)
  are both complete. The step runs `fisherman scan` asynchronously, presents per-user
  category checkboxes with size estimates, enforces a RAM budget warning, and emits a
  `slurp` recipe key for fisherman to consume.
- **Flatpak builder bare repo issue**: git sources in Flatpak manifests fail due to
  `safe.bareRepository=explicit` in the sandbox. Workaround: use `archive` sources
  with SHA256 instead of `git` sources.
- **gi stub contamination in unit tests (fixed)**: When multiple test modules install
  `sys.modules` stubs for `gi.repository.*`, earlier stubs can bleed into later test files
  run in the same process. **Definitive three-part pattern**:
  1. Each `_import_X_fresh()` helper calls `_build_gi_stubs()` before popping and
     reimporting, so the correct stubs are always active at reimport time.
  2. Clear the parent package attribute — pop `sys.modules["bootc_installer.views.done"]`
     **and** `delattr(views_pkg, "done")` (Python can return a stale cached attr even after
     `sys.modules` is cleaned). Use `importlib.import_module()` rather than a plain import.
  3. For `gi` C-extension attrs that can bypass stubs (e.g. `done_mod.Gio`), use a
     structured stub: `gio_stub = MagicMock(); gio_stub.BusType = types.SimpleNamespace(SYSTEM=sentinel)`.
     Assign `done_mod.Gio = gio_stub` in `setUp()` so `patch.object` always targets a
     controllable object and typos like `Gio.BusTyp` surface as failures.
  Fixed in #67 and hardened across `test_done.py` / `test_branding_parity.py`.
- **`patch("module.Gio.method")` fails when real GIO is loaded first**: When
  `test_builder.py` (or any module that imports real GTK) runs before a test that tries to
  patch `bootc_installer.defaults.image.Gio.resources_lookup_data`, the patch silently
  fails — the real C-extension method is called instead. **Fix**: use `_import_image_fresh()`
  to reload the module with gi stubs, then set `fresh_mod.Gio.resources_lookup_data = MagicMock(...)`
  directly on the reloaded module's attribute. Never use `patch("...Gio.some_method", ...)` 
  when the test file might run after one that loads the real Gio. See
  `tests/unit/test_image_helpers.py::TestLoadManifestOverrides` for the canonical pattern.
  Fixed in PR #164.
- **`CompanionServer.start()` global reset (fixed in #106)**: `GLOBAL_CONFIG = None`
  inside a method creates a local variable, not a module-level reset. Always add
  `global GLOBAL_CONFIG` before the assignment when resetting module-level state.
- **Rebase + force-push for overlapping test PRs**: When merging multiple PRs that
  all add to the same test files (`test_branding_parity.py`, `test_done.py`,
  `test_network_helpers.py`, `test_slurp_helpers.py`), always rebase onto the latest
  `dev` and **run `pytest tests/unit/ -q` after resolving any conflict** before
  pushing. "Keeping both sides" of an additive conflict looks safe but can
  introduce subtle import/indentation errors that only surface at runtime.
- **GitHub Actions won't trigger `pull_request` events on conflicting branches**: If
  a PR branch has merge conflicts with the target branch, GitHub silently skips the
  `pull_request` event — no check runs appear. Always rebase onto `dev` before
  investigating why CI isn't triggering.
- **`CompanionServer` / `get_local_ip` must be mocked in UI tests**: Any test that
  navigates past the QR Companion wizard step (via `window.next()` or `carousel.page-changed`)
  will call `__start_companion()` which runs `openssl` subprocess + UDP socket to `8.8.8.8`.
  Both block in CI. Always add to the patcher list:
  `patch("bootc_installer.defaults.qr_companion.CompanionServer")` and
  `patch("bootc_installer.defaults.qr_companion.get_local_ip", return_value="127.0.0.1")`.
- **GTK widget unit testing — `__new__` + attribute injection**: GTK subclasses (`Adw.Bin`,
  `Adw.ActionRow`, etc.) cannot be instantiated via `__init__` without a display. Use
  `cls.__new__(cls)` then manually inject private attributes (Python name-mangling:
  `obj._ClassName__attr = ...`) and mock widget children (`obj.hostname_entry = MagicMock()`).
  Combined with `_build_gi_stubs()` at module level this lets you test `get_finals()`,
  `should_show()`, passphrase strength logic, and other pure methods without Xvfb.
  See `tests/unit/test_disk.py`, `test_encryption.py`, `test_timezone.py` for canonical examples.
- **Dialog stub staleness across multiple `_build_gi_stubs()` calls**: Each call to
  `_build_gi_stubs()` (one per `_import_X_fresh()`) creates a **new** `BootcDialog = MagicMock()`
  and stores it in `sys.modules["bootc_installer.windows.dialog"]`. Modules that already ran
  `from bootc_installer.windows.dialog import BootcDialog` hold the **old** reference. If a
  test tracks the dialog via `sys.modules["bootc_installer.windows.dialog"].BootcDialog`, it
  gets the current (newer) stub — which was never called — and the assertion fails. **Fix:**
  Always reference the dialog mock via the module's own attribute: `_yn_mod.BootcDialog` (not
  `sys.modules["bootc_installer.windows.dialog"].BootcDialog`). See `test_layouts.py` for
  the canonical pattern.
- **`pytest-cov --cov-fail-under` rounding quirk**: 47.57% is displayed as "48%" in terminal
  output and the FAIL message prints "Total coverage: 47.57%" while exiting with code 0 when
  `--cov-fail-under=48`. This is because pytest-cov 7.1.0 rounds the displayed value before
  comparing. Set the gate one point below the displayed integer (e.g., `--cov-fail-under=47`
  for 47.57% measured coverage) so the intent is unambiguous and the exit code is clean.

---

## Post-install "instant first boot" features

These run automatically during the install pipeline (main.go) and require no user input:

| Feature | File | What it does |
|---------|------|--------------|
| Bluetooth persistence | `post.go` | Copies `/var/lib/bluetooth` → target so paired devices reconnect |
| WiFi persistence | `post.go` | Copies NM `.nmconnection` files → target for auto-reconnect |
| Audio device naming | `audio.go` | WirePlumber rules: rename ugly ALSA names, hide S/PDIF/Pro Audio |
| Live audio fix | `audio.go` | `ApplyAudioConfigLive()` — fixes names in live session immediately |
| OEM detection | `oem.go` | Detects ASUS/Framework/TUXEDO, queues first-boot brew packages |
| Cache warming | `caches.go` | Pre-generates font, icon, pixbuf, GIO, ldconfig, man-db, flatpak caches |
| Wallpaper slurp | `slurp/wallpaper.go` | Extracts Windows wallpapers, injects into target |
| Wallpaper thumbnails | `slurp/wallpaper.go` | Pre-generates GNOME wallpaper capplet thumbnails |
| Data slurp | `slurp/data.go` | Migrates documents/photos/music/bookmarks/fonts from Windows |
| Print services | `post.go` | Enables cups-browsed, avahi-daemon, ipp-usb for USB/AirPrint support |

---

## Useful diagnostic commands (on a remote install target)

```bash
# Watch the live install log
tail -f ~/.cache/bootc-installer/fisherman-output.log

# Check the most recent recipe used
ls -lt ~/.cache/bootc-installer/bootc-recipe-*.json | head -1 | xargs cat

# Inspect the installed disk after install (replace nvme0n1 with actual disk)
sudo lsblk -o NAME,SIZE,FSTYPE,LABEL,UUID /dev/nvme0n1
sudo mount /dev/nvme0n1p2 /tmp/ir && sudo mount /dev/nvme0n1p1 /tmp/ie
cat /tmp/ir/boot/grub2/grub.cfg
cat /tmp/ie/EFI/almalinux/bootuuid.cfg
ls /tmp/ir/boot/loader/entries/
sudo umount /tmp/ie /tmp/ir

# Check EFI boot entries
efibootmgr

# Check bootupd state on installed root
sudo mount /dev/nvme0n1p2 /tmp/ir
cat /tmp/ir/boot/bootupd-state.json
sudo umount /tmp/ir
```

## Future Architectural Considerations

- **Multi-variant installer (Done)**: Single codebase now ships GNOME (GTK4/Adwaita), XFCE (GTK4), and KDE (Qt/Kirigami) variants. `meson_options.txt` controls the `variant=` selector. See `MULTI_VARIANT_BUILD.md` for the full build guide.
- **Move `images.json` to `fisherman` (Done)**: The image registry (`fisherman/data/images.json`) now lives in the `fisherman` backend. This allows `fisherman` to act as a universal registry of BootC images, containing not just the OCI references but also the specific installation requirements for each image (e.g., whether it requires manual user creation, specific kernel arguments, or filesystem defaults).
- **Universal BootC Registry**: Evolving the image manifest into a standard format that other installers or tools could consume to understand the "metadata" of a BootC image.
- **Dynamic Installation Carousel**: Replaced with video playback (Gtk.Video + AV1/VP9). Distribution can provide a branded video via `/etc/bootc-installer/install-video.webm`.
- **Windows Data Slurp (Done — #22)**: Backend (`fisherman scan`, `ExtractData`, `InjectData`) and GUI wizard step (`bootc_installer/defaults/slurp.py`) are fully implemented. The step runs an async scan, presents per-user category checkboxes with size estimates, and enforces a RAM budget warning. Wallpaper extraction also runs as an always-on easter egg.
- **Offline-first Install (Done — #16)**: `_is_offline_install()` detects live ISO mode; `additionalImageStores` passes pre-baked OCI stores from the ISO to fisherman/podman.
- **GStreamer VP9/AV1 codec validation (Done — #72)**: Validates that required video codecs are present before playback begins, surfacing a clear error instead of a silent blank video.
- **libpastry integration (Done — #71)**: Integrates libpastry for install-time configuration generation.
- **QR soundtrack codes (Done — #73)**: Pre-generates QR codes for soundtrack tracks at build time so they display instantly during the installation carousel.
- **QR Phone Companion MVP (Done — #70)**: Serves a local HTTPS companion server during install; the user can scan a QR code with their phone to follow along. `CompanionServer` in `bootc_installer/utils/phone_companion.py`. `BootcDefaultQrCompanion` wizard step in `bootc_installer/defaults/qr_companion.py`.
- **DX groups on first install (Done — #74)**: `docker`, `incus-admin`, `libvirt`, and `dialout` added to `_DEFAULT_GROUPS` in `bootc_installer/defaults/user.py` so newly-created users have full developer access from first boot without needing `ujust dx-group`.

---

## Branch strategy

```
feature/xyz  ──►  dev  ──►  prod
```

- **`dev`** is the integration branch. All feature PRs target `dev`.
- **`prod`** is the release branch. It is promoted wholesale from `dev` when `dev` is in a shippable state — no cherry-picks, no partial merges.
- Never open PRs directly against `prod`. Features land on `dev` first.
- The merge queue is enabled for `dev`. Use `gh pr merge --squash <number>` or enqueue via the GitHub UI.

### Querying features in flight (targeting `dev`)

To view active pull requests and their current check status:
1. Run `gh pr list --base dev` in your terminal to see open pull requests targeting the `dev` branch.
2. View the open pull requests directly on the GitHub UI at [GitHub Pull Requests](https://github.com/projectbluefin/bootc-installer/pulls).

---

## GitHub org context

- **`projectbluefin/bootc-installer`** — this repo (work directly here, no fork)
- **`projectbluefin/fisherman`** — Go backend (submodule at `fisherman/`)
- Images are published to `ghcr.io/projectbluefin/`

# GitHub Copilot Instructions — bootc-installer

This is `projectbluefin/bootc-installer`: a multi-variant Flatpak GUI installer for bootc images, backed by the `fisherman` Go backend.

## Read before doing any work

**Full agent guide:** [`AGENTS.md`](../AGENTS.md)  
**Testing pitfalls:** `cat ~/src/skills/bootc-installer/PITFALLS.md`

## Key facts

- **Repo:** `projectbluefin/bootc-installer` — work directly here, no fork
- **fisherman:** git submodule at `fisherman/` → `projectbluefin/fisherman`. Push changes there separately, then update the pointer here
- **Branch strategy:** `feature/xyz → dev → prod`. All PRs target `dev`
- **CI gate:** `--cov-fail-under=47` for Python unit tests; Go coverage gate: 20%
- **Linting:** `python3 -m ruff check bootc_installer/ tests/` — run before every commit
- **Tests:** `pytest tests/unit/ -q` (unit), `xvfb-run -a pytest tests/ui/ -q` (UI)

## Three variants, one codebase

| Variant | Entry point | Flatpak ID |
|---------|-------------|------------|
| GNOME (default) | `main.py` | `org.bootcinstaller.Installer` |
| XFCE | `main.py` | `org.xfceinstaller.Installer` |
| KDE | `main_qt.py` | `org.kdeinstaller.Installer` |

When adding `.py` files, also add them to `sources = [...]` in the subpackage's `meson.build` or the Flatpak install will fail (`test_meson_sources.py` catches this).

## Python module map

```
bootc_installer/
├── core/       disks, system, keymaps, locales
├── defaults/   wizard steps (disk, encryption, user, image, slurp…)
├── views/      progress, done, confirm, recovery_key, tour, confirm_data
├── widgets/    page_header
├── windows/    main_window, dialogs, hardware warning windows
├── layouts/    yes_no, preferences
├── utils/      processor, recipe, finals, builder, codec_check,
│               progress_parser, phone_companion, pastry_compat, run_async
├── gtk/        Blueprint .blp files (GNOME/XFCE)
├── kde/        QML + Python (KDE)
├── main.py     GTK4 entry point
└── main_qt.py  Qt/Kirigami entry point
```

## Dev loop

```bash
./run-dev.sh           # rebuild if sources changed, launch with BOOTC_DEMO=1
./run-dev.sh --rebuild # force full rebuild
./run-dev.sh --logs    # tail debug log only
```

`BOOTC_DEMO=1` intercepts at `on_installation_confirmed()` — no fisherman, no disk.

## CI workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `python-test.yml` | every push/PR | Unit tests (cov 47%) + UI tests (Xvfb) |
| `go-test.yml` | every push/PR | fisherman `go vet` + tests + race detector |
| `flatpak.yml` | dev/prod/tags | GNOME Flatpak build + publish |
| `build-flatpaks.yml` | dev/prod/tags | All 3 variants (GNOME + XFCE + KDE) |
| `validate-flatpak.yml` | manifest changes | JSON lint + appstream check |
| `nightly.yml` | 06:00 UTC daily | fisherman tests on both branches + race detector |

## Critical constraints

1. **Always 3-partition GPT** (EFI + ext4 `/boot` + root) — GRUB can't read modern XFS
2. **Scratch at `/var/fisherman-tmp`** — never `/run/*` (tmpfs, too small)
3. **Flatpak manifests:** use `"type": "archive"` with SHA256, never `"type": "git"` (sandbox rejects bare git repos)
4. **GTK unit tests:** use `Cls.__new__(Cls)` + attribute injection with `_build_gi_stubs()` — never instantiate GTK widgets without a display
5. **New `.py` files** must be in `meson.build` `sources = [...]` or the Flatpak build breaks

# Contributing to bootc-installer

bootc-installer is a GTK4/Libadwaita Flatpak installer for [bootc](https://containers.github.io/bootc/) container-native OS images, backed by the `fisherman` Go install backend.

## Getting started

```bash
git clone --recurse-submodules https://github.com/projectbluefin/bootc-installer
cd bootc-installer
```

> **Important:** `fisherman` is a git submodule. Always clone with `--recurse-submodules`, or run `git submodule update --init --recursive` after a plain clone. Without this, `fisherman/` is empty and all build paths fail immediately.

## Prerequisites

- `flatpak` + `org.flatpak.Builder` — for the recommended Flatpak build
- `meson`, `ninja` — for native (non-Flatpak) builds
- Go ≥ 1.22 — for `fisherman` (the install backend, in the submodule)
- Python ≥ 3.10 — for the GUI codebase
- `libadwaita-1-dev`, `gettext`, `desktop-file-utils`, `libgnome-desktop-4-dev`

## Building

### Flatpak (recommended)

```bash
git submodule update --init --recursive   # Required — fisherman is a submodule
flatpak run org.flatpak.Builder --force-clean --user --install _build flatpak/org.bootcinstaller.Installer.json
flatpak run org.bootcinstaller.Installer
```

### Meson (development)

```bash
git submodule update --init --recursive   # Required — fisherman is a submodule
meson setup build
ninja -C build
sudo ninja -C build install
bootc-installer
```

### Dev loop

```bash
./run-dev.sh                               # Rebuild and launch with BOOTC_DEMO=1 (no disk writes)
BOOTC_PREVIEW_SCREEN=confirm ./run-dev.sh  # Jump to a specific screen
```

## Running tests

```bash
pytest tests/unit/ -q                           # Unit tests (no display required)
xvfb-run -a pytest tests/ui/ -q                 # UI tests
python3 -m ruff check bootc_installer/ tests/   # Lint
./QUALIFY_SOFTWARE.sh                           # Full qualification suite
```

CI gate: `--cov-fail-under=51` (minimum unit test coverage).

## Branch workflow

- Default branch: **`dev`**
- **Open all PRs against `dev`** — do not target `main`
- Follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages
- PR title format: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`

## Adding images to the catalog

The image catalog lives in [`fisherman/data/images.json`](fisherman/data/images.json). See the README for the full JSON schema.

> `fisherman/` is a git submodule pointing to [`projectbluefin/fisherman`](https://github.com/projectbluefin/fisherman). Changes to the catalog must be committed and pushed **separately** to the fisherman repo, then the submodule pointer updated here.

## Architecture overview

| Component | Language | Role |
|---|---|---|
| `fisherman/fisherman/` | Go | Root-level CLI; reads JSON recipe, executes 9-step disk install pipeline |
| `bootc_installer/` | Python | GTK4/Adwaita GUI; collects user choices, writes recipe JSON, drives fisherman |

See [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md) for deeper architecture documentation.

## Code style

- Python: [Ruff](https://docs.astral.sh/ruff/) (`python3 -m ruff check`)
- Go: `gofmt` + `go vet`
- Commit messages: Conventional Commits

## Security

Report vulnerabilities via [GitHub Private Vulnerability Reporting](https://github.com/projectbluefin/bootc-installer/security/advisories/new). Do not open public issues for security bugs.

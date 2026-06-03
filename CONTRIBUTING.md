# Contributing

Thanks for contributing to bootc-installer. This project is a GTK4/Libadwaita app written in Python, with the `fisherman/` Go backend and a Meson-based build.

## Prerequisites

- flatpak and flatpak-builder
- Go 1.22+
- meson and ninja
- libadwaita
- python3
- gettext and desktop-file-utils
- libgnome-desktop-4
- python3-requests

## Development setup

```bash
git clone https://github.com/projectbluefin/bootc-installer.git
cd bootc-installer
git submodule update --init --recursive
```

The submodule step is required because `fisherman/` is tracked as a git submodule.

## Building

Recommended Flatpak path:

```bash
git submodule update --init --recursive
flatpak run org.flatpak.Builder --force-clean --user --install _build flatpak/org.bootcinstaller.Installer.json
```

Meson development path:

```bash
git submodule update --init --recursive
meson setup build
ninja -C build
sudo ninja -C build install
```

## Running

- Demo / preview mode: `python -m bootc_installer --demo`
- Tests: `pytest tests/`

## Pull requests

- Target the `main` branch
- Use conventional commits when possible (`fix:`, `docs:`, `feat:`)
- Open a normal PR; no special branch model is required

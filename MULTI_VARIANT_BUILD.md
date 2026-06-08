# bootc-installer Build Guide

bootc-installer ships a single **GNOME** (GTK4/Libadwaita) variant.

## Building the Flatpak

```bash
flatpak run org.flatpak.Builder --force-clean --user --install \
  _build flatpak/org.bootcinstaller.Installer.json
flatpak run org.bootcinstaller.Installer
```

## Building with Meson (development)

```bash
meson setup build -Dbuild-fisherman=false
ninja -C build
```

## Daily dev loop

```bash
./run-dev.sh           # rebuild if sources changed, launch with BOOTC_DEMO=1
./run-dev.sh --rebuild # force full rebuild
```

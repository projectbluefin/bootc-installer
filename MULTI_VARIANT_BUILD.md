# Multi-Variant bootc-installer Build Guide

The bootc-installer project now supports building three desktop environment variants from a single unified codebase:

1. **GNOME** (default) - GTK4/Libadwaita
2. **XFCE** - GTK4 with XFCE styling  
3. **KDE Plasma** - Qt/Kirigami native

## Quick Start: Build All Variants

```bash
chmod +x BUILD_ALL_VARIANTS.sh
./BUILD_ALL_VARIANTS.sh --install
```

This will build and install all three variants as Flatpaks.

## Building Individual Variants

### GNOME (Default - GTK4/Libadwaita)

**Meson:**
```bash
meson setup build -Dvariant=gnome -Dbuild-fisherman=false
ninja -C build
```

**Flatpak:**
```bash
flatpak run org.flatpak.Builder --force-clean --user --install _build \
  flatpak/org.bootcinstaller.Installer.json
```

**Launch:**
```bash
flatpak run org.bootcinstaller.Installer
```

---

### XFCE (GTK4 with XFCE Theming)

**Meson:**
```bash
meson setup build-xfce -Dvariant=xfce -Dbuild-fisherman=false
ninja -C build-xfce
```

**Flatpak:**
```bash
flatpak run org.flatpak.Builder --force-clean --user --install _build-xfce \
  flatpak/org.xfceinstaller.Installer.json
```

**Launch:**
```bash
flatpak run org.xfceinstaller.Installer
xfce-bootc-installer  # If installed non-Flatpak
```

---

### KDE Plasma (Qt/Kirigami)

**Meson:**
```bash
meson setup build-kde -Dvariant=kde -Dbuild-fisherman=false
ninja -C build-kde
```

**Flatpak:**
```bash
flatpak run org.flatpak.Builder --force-clean --user --install _build-kde \
  flatpak/org.kdeinstaller.Installer.json
```

**Launch:**
```bash
flatpak run org.kdeinstaller.Installer
kde-bootc-installer  # If installed non-Flatpak
```

---

## Architecture

### Single Codebase, Multiple Variants

```
tuna-installer/
├── bootc_installer/
│   ├── core/            # Shared business logic
│   ├── utils/           # Shared utilities
│   ├── views/           # GTK4 views (GNOME + XFCE)
│   ├── widgets/         # GTK4 widgets (GNOME + XFCE)
│   ├── windows/         # GTK4 windows (GNOME + XFCE)
│   ├── gtk/             # GTK4 Blueprint UI files
│   ├── kde/             # QML UI (KDE only)
│   ├── main.py          # GTK4 entry point
│   ├── main_qt.py       # Qt/Kirigami entry point
│   ├── gnome-bootc-installer.in    # (not needed, same as bootc-installer.in)
│   ├── xfce-bootc-installer.in     # XFCE launcher
│   └── kde-bootc-installer.in      # KDE launcher
├── data/
│   ├── org.bootcinstaller.Installer.desktop.in
│   ├── org.xfceinstaller.Installer.desktop.in
│   ├── org.kdeinstaller.Installer.desktop.in
│   ├── org.bootcinstaller.Installer.appdata.xml.in
│   ├── org.xfceinstaller.Installer.appdata.xml.in
│   ├── org.kdeinstaller.Installer.appdata.xml.in
│   ├── polkit/
│   │   ├── org.bootcinstaller.Installer.policy
│   │   ├── org.xfceinstaller.Installer.policy
│   │   └── org.kdeinstaller.Installer.policy
│   └── icons/           # Shared icon assets
├── flatpak/
│   ├── org.bootcinstaller.Installer.json     # GNOME
│   ├── org.xfceinstaller.Installer.json      # XFCE (xfce-platform)
│   └── org.kdeinstaller.Installer.json       # KDE (kde-platform)
├── meson.build          # Main build config with variant option
├── meson_options.txt    # variant option definition
└── BUILD_ALL_VARIANTS.sh  # Script to build all three
```

### Variant Detection

The build variant is controlled via:

```bash
meson setup build -Dvariant=<gnome|xfce|kde>
```

The meson build system conditionally includes:
- Launcher scripts (xfce-bootc-installer, kde-bootc-installer)
- Desktop files and app metadata
- Polkit policies  
- UI resources (GTK4 Blueprints or KDE QML)
- Flatpak manifests (different runtimes)

## CI/CD Integration

For GitHub Actions or other CI systems:

```yaml
- name: Build all bootc-installer variants
  run: |
    chmod +x BUILD_ALL_VARIANTS.sh
    ./BUILD_ALL_VARIANTS.sh --clean --install
```

Or build individually:

```yaml
- name: Build XFCE variant
  run: |
    flatpak run org.flatpak.Builder --force-clean --user --install _build-xfce \
      flatpak/org.xfceinstaller.Installer.json
```

## Testing

### Test all three simultaneously

```bash
# Terminal 1 - GNOME
flatpak run org.bootcinstaller.Installer

# Terminal 2 - XFCE
flatpak run org.xfceinstaller.Installer

# Terminal 3 - KDE
flatpak run org.kdeinstaller.Installer
```

### Verify installation

```bash
flatpak list --app --user | grep installer
```

Expected output:
```
org.bootcinstaller.Installer     0.1.0       system,user
org.xfceinstaller.Installer      0.1.0       system,user
org.kdeinstaller.Installer       0.1.0       system,user
```

### Debug logs

```bash
# GNOME
tail -f ~/.cache/tuna-installer/installer-debug.log

# All variants write to same log, but environment shows variant:
BOOTC_INSTALLER_DEBUG=1 flatpak run org.xfceinstaller.Installer
```

## Development Workflow

### Modifying Shared Logic

Changes to `core/`, `utils/`, `fisherman/`, etc. affect all three variants automatically.

### Adding a New Variant Page

1. **GNOME/XFCE:** Add `.blp` file to `bootc_installer/gtk/`, Python class to appropriate `views/`/`widgets/`/`windows/`
2. **KDE:** Add QML component, update `kde/main.qml`, add Python backend to `main_qt.py`

### Variant-Specific Changes

Each variant can have its own:
- Desktop file (`.desktop.in`)
- AppData metadata (`.appdata.xml.in`)
- Launcher script (`.in`)
- Polkit policy (`.policy`)
- Flatpak manifest (`.json`)

## Deployment

### Individual Distribution

Each variant can be distributed separately:

- **GNOME:** `org.bootcinstaller.Installer` - standard bootc-installer
- **XFCE:** `org.xfceinstaller.Installer` - for XFCE desktops
- **KDE:** `org.kdeinstaller.Installer` - for KDE Plasma desktops

### Unified Repository

All three variants can be pushed to:

```bash
git push origin dev    # Single main branch with all variants
```

### Per-Variant Repos

Or maintain separate forks:

```bash
git checkout feat/xfce-frontend && git push origin feat/xfce-frontend
git checkout feat/kde-frontend && git push origin feat/kde-frontend
git checkout dev && git push origin dev
```

## Troubleshooting

### Build fails with "blueprint-compiler not found"

This is expected for local Meson builds. Build via Flatpak instead, which provides all dependencies.

### Build fails with "PyQt6 not found"

KDE variant requires PyQt6. Install via:
```bash
pip install PyQt6
```

Or build via Flatpak (all dependencies provided).

### Flatpak build fails

Check the full Flatpak build logs:
```bash
tail -f _build/build.log
```

## Next Steps

- [ ] Expand KDE QML UI with all installer screens
- [ ] Add XFCE-specific theming and colors
- [ ] Package all three variants in a single Flathub submission
- [ ] Integrate with dakota-iso CI/CD for multi-variant builds
- [ ] Update project documentation with variant information

## Links

- **Kirigami:** https://develop.kde.org/
- **GTK/Libadwaita:** https://gnome.pages.gitlab.gnome.org/libadwaita/
- **Blueprint:** https://jwestman.pages.gitlab.gnome.org/blueprint-compiler/

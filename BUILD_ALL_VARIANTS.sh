#!/bin/bash
# Build all three bootc-installer variants as Flatpaks
# Usage: ./BUILD_ALL_VARIANTS.sh [--clean] [--install]

set -e

CLEAN=false
INSTALL=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --clean) CLEAN=true; shift ;;
    --install) INSTALL=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

VARIANTS=(
  "flatpak/org.bootcinstaller.Installer.json:GNOME"
  "flatpak/org.xfceinstaller.Installer.json:XFCE"
  "flatpak/org.kdeinstaller.Installer.json:KDE"
)

echo "=========================================="
echo "Building bootc-installer for all variants"
echo "=========================================="

for manifest_pair in "${VARIANTS[@]}"; do
  IFS=: read manifest name <<< "$manifest_pair"
  echo ""
  echo ">>> Building $name variant ($manifest)"
  echo "=========================================="

  build_dir="_build-$name"

  if [ "$CLEAN" = true ]; then
    echo "Cleaning build directory: $build_dir"
    rm -rf "$build_dir"
  fi

  flatpak run org.flatpak.Builder \
    --force-clean \
    --user \
    $([ "$INSTALL" = true ] && echo "--install" || echo "") \
    "$build_dir" \
    "$manifest"

  if [ $? -eq 0 ]; then
    echo "✓ $name variant built successfully"
  else
    echo "✗ $name variant build FAILED"
    exit 1
  fi
done

echo ""
echo "=========================================="
echo "All variants built successfully!"
echo "=========================================="
echo ""
echo "Installed Flatpaks:"
flatpak list --app --user | grep -E "org\.(bootc|xfce|kde)installer"

echo ""
echo "To test a variant, run:"
echo "  flatpak run org.bootcinstaller.Installer    # GNOME"
echo "  flatpak run org.xfceinstaller.Installer     # XFCE"
echo "  flatpak run org.kdeinstaller.Installer      # KDE"

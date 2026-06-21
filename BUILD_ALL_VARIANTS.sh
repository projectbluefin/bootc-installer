#!/bin/bash
# Build bootc-installer (GNOME variant)
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

echo "=========================================="
echo "Building bootc-installer (GNOME)"
echo "=========================================="

build_dir="_build-GNOME"

if [ "$CLEAN" = true ]; then
  echo "Cleaning build directory: $build_dir"
  rm -rf "$build_dir"
fi

flatpak run org.flatpak.Builder \
  --force-clean \
  --user \
  $([ "$INSTALL" = true ] && echo "--install" || echo "") \
  "$build_dir" \
  flatpak/org.bootcinstaller.Installer.json

echo ""
echo "=========================================="
echo "Build complete!"
echo "=========================================="

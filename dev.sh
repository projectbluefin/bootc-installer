#!/usr/bin/bash
# dev.sh — Flatpak dev loop for bootc-installer
#
# Builds into _build/ via flatpak-builder, then runs directly from there.
# No user or system flatpak install needed.
#
# Usage:
#   ./dev.sh                       # rebuild if sources changed, then launch
#   ./dev.sh --rebuild             # force full rebuild, then launch
#   ./dev.sh --run                 # skip rebuild, just launch
#   ./dev.sh --screen progress     # preview a specific screen (no install)
#   ./dev.sh --logs                # tail the debug log only

set -e

MANIFEST="flatpak/org.bootcinstaller.Installer.Devel.json"
BUILD_DIR="_build"
DEBUG_LOG="$HOME/.var/app/org.bootcinstaller.Installer.Devel/cache/bootc-installer/installer-debug.log"

# ── Logs-only mode ────────────────────────────────────────────────────────────
if [[ "$1" == "--logs" ]]; then
    exec tail -f "$DEBUG_LOG"
fi

# ── Decide whether to rebuild ─────────────────────────────────────────────────
_rebuild=0
[[ "$1" == "--rebuild" ]] && _rebuild=1

# First time — no build dir yet
[[ ! -d "$BUILD_DIR/files" ]] && _rebuild=1

# Sources changed since last gresource build
if [[ $_rebuild -eq 0 ]]; then
    _gresource=$(find "$BUILD_DIR/files/share" -name "*.gresource" 2>/dev/null | head -1)
    if [[ -n "$_gresource" ]] && \
       find bootc_installer -newer "$_gresource" \( -name "*.py" -o -name "*.blp" -o -name "*.xml" \) 2>/dev/null | grep -q .; then
        echo "[dev] Sources changed — rebuilding..."
        _rebuild=1
    fi
fi

# ── Build ─────────────────────────────────────────────────────────────────────
if [[ "$1" != "--run" ]] && [[ $_rebuild -eq 1 ]]; then
    echo "[dev] Building with flatpak-builder (this is slow once; fast after)..."
    flatpak run org.flatpak.Builder \
        --ccache \
        --force-clean \
        "$BUILD_DIR" \
        "$MANIFEST"
    echo "[dev] Build complete."
fi

# ── Launch ────────────────────────────────────────────────────────────────────
SCREEN=""
if [[ "$1" == "--screen" ]]; then
    SCREEN="$2"
fi

echo "[dev] Launching bootc-installer (BOOTC_DEMO=1)..."
[[ -n "$SCREEN" ]] && echo "[dev] Preview screen: $SCREEN"

flatpak run org.flatpak.Builder --run "$BUILD_DIR" "$MANIFEST" \
    sh -c "BOOTC_DEMO=1 ${SCREEN:+BOOTC_PREVIEW_SCREEN=$SCREEN} /app/bin/bootc-installer" &

disown
echo "[dev] Launched. Tailing debug log (Ctrl-C to stop tailing; app keeps running)..."
sleep 2
tail -f "$DEBUG_LOG"

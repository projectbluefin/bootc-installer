#!/usr/bin/bash
# run-dev.sh — run bootc-installer from the local build for development
#
# Usage:
#   ./run-dev.sh           # launch the installer window
#   ./run-dev.sh --rebuild # force full rebuild before launching
#   ./run-dev.sh --logs    # tail the log only (don't launch)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="/tmp/bootc-installer-dev"
FISHERMAN="${TUNA_FISHERMAN_PATH:-/var/tmp/fisherman-test}"
RECIPE="${VANILLA_CUSTOM_RECIPE:-$SCRIPT_DIR/recipe.json}"
RUN_LOG="/tmp/bootc-installer-run.log"
DEBUG_LOG="$HOME/.cache/tuna-installer/installer-debug.log"

if [[ "$1" == "--logs" ]]; then
    tail -f "$DEBUG_LOG"
    exit 0
fi

# ── Rebuild check ─────────────────────────────────────────────────────────────
_needs_rebuild=0
if [[ "$1" == "--rebuild" ]] || [[ ! -f "$PREFIX/bin/bootc-installer" ]]; then
    _needs_rebuild=1
elif find "$SCRIPT_DIR/bootc_installer" -newer "$PREFIX/share/org.bootcinstaller.Installer/bootc-installer.gresource" \( -name "*.py" -o -name "*.blp" \) 2>/dev/null | grep -q .; then
    echo "[run-dev] Sources changed — rebuilding..."
    _needs_rebuild=1
fi

if [[ "$_needs_rebuild" == "1" ]]; then
    cd "$SCRIPT_DIR"
    toolbox run --container dakota-lab bash -c "
        meson setup build --prefix=/tmp/bootc-installer-dev -Dvariant=gnome -Dbuild-fisherman=false --reconfigure 2>/dev/null || true
        ninja -C build
        meson install -C build
    "
fi

# ── Kill any existing instance ────────────────────────────────────────────────
pkill -f "python3 $PREFIX/bin/bootc-installer" 2>/dev/null; sleep 0.5

# ── Launch ────────────────────────────────────────────────────────────────────
echo "[run-dev] Starting bootc-installer (Project Bluefin Dakota)"
echo "  recipe   : $RECIPE"
echo "  fisherman: $FISHERMAN"
echo "  run log  : $RUN_LOG"
echo "  debug log: $DEBUG_LOG"
echo ""
echo "  To follow logs: ./run-dev.sh --logs"
echo ""

toolbox run --container dakota-lab bash << EOF &
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0}
export TUNA_FISHERMAN_PATH=$FISHERMAN
export GSETTINGS_SCHEMA_DIR=$PREFIX/share/glib-2.0/schemas:/usr/share/glib-2.0/schemas
export XDG_DATA_DIRS=$PREFIX/share:/usr/share
export VANILLA_CUSTOM_RECIPE=$RECIPE
export BOOTC_DEMO=1
python3 $PREFIX/bin/bootc-installer >> $RUN_LOG 2>&1
EOF
disown

echo "[run-dev] Launched (PID $!). Tailing debug log..."
sleep 2
tail -f "$DEBUG_LOG"

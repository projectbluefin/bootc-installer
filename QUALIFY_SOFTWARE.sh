#!/usr/bin/bash
# Run the repeatable software-only release qualification checks for bootc-installer.
#
# Usage:
#   ./QUALIFY_SOFTWARE.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_step() {
  local name="$1"
  shift

  echo
  echo ">>> $name"
  echo "=========================================="
  "$@"
}

cd "$SCRIPT_DIR"

run_step "Validating Flatpak manifest JSON" bash -c '
  python3 -m json.tool flatpak/org.bootcinstaller.Installer.json >/dev/null
  python3 -m json.tool flatpak/org.bootcinstaller.Installer.Devel.json >/dev/null
  python3 -m json.tool flatpak/org.xfceinstaller.Installer.json >/dev/null
  python3 -m json.tool flatpak/org.kdeinstaller.Installer.json >/dev/null
'

run_step "Running Python unit tests" pytest tests/unit -q
run_step "Running GTK UI tests" xvfb-run -a pytest tests/ui -q
run_step "Running fisherman Go checks" bash -c '
  cd fisherman/fisherman
  go vet ./...
  go test -count=1 -timeout=60s ./...
'

run_step "Building production Flatpak" \
  flatpak run org.flatpak.Builder --force-clean --user --install \
  _build-qualify-prod flatpak/org.bootcinstaller.Installer.json

run_step "Building devel Flatpak" \
  flatpak run org.flatpak.Builder --force-clean --user --install \
  _build-qualify-devel flatpak/org.bootcinstaller.Installer.Devel.json

echo
echo "=========================================="
echo "Software qualification passed"
echo "=========================================="

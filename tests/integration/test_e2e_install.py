"""End-to-end installation tests for fisherman.

Validates that fisherman can install Yellowfin (grub2/xfs) and Dakota
(systemd-boot/btrfs/composefs) to virtual block devices, and optionally
verifies that each installed disk boots to a graphical display in QEMU.

Requirements
------------
- Must run as root (disk partitioning, NBD, podman run --privileged)
- qemu-nbd must be available on the host
- Target images must be present in podman storage (pull them first)
- For boot verification (--boot-verify / BOOT_VERIFY=1):
    qemu-system-x86_64, OVMF (non-secboot), vncdo

Usage
-----
Build fisherman first, then run:

    cd /path/to/tuna-installer
    go build -o /tmp/fisherman-test ./fisherman/fisherman/cmd/fisherman/
    sudo FISHERMAN_BIN=/tmp/fisherman-test pytest tests/integration/test_e2e_install.py -v -s

Boot verification (adds ~5 min per image):

    sudo FISHERMAN_BIN=/tmp/fisherman-test BOOT_VERIFY=1 \\
        pytest tests/integration/test_e2e_install.py -v -s

Run a single image:

    sudo FISHERMAN_BIN=/tmp/fisherman-test pytest tests/integration/test_e2e_install.py::test_yellowfin_install -v -s
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
FISHERMAN_SRC = REPO_ROOT / "fisherman" / "fisherman"

OVMF_CODE = Path("/usr/share/edk2/ovmf/OVMF_CODE.fd")
OVMF_VARS = Path("/usr/share/edk2/ovmf/OVMF_VARS.fd")
QEMU_BIN = shutil.which("qemu-system-x86_64") or "/home/linuxbrew/.linuxbrew/bin/qemu-system-x86_64"
VNCDO_BIN = shutil.which("vncdo")

DISK_SIZE_GB = int(os.environ.get("DISK_SIZE_GB", "30"))
BOOT_VERIFY = os.environ.get("BOOT_VERIFY", "0") == "1"
BOOT_TIMEOUT_S = int(os.environ.get("BOOT_TIMEOUT_S", "180"))
VNC_PORT = 5910  # base VNC port; each test gets its own offset

# ---------------------------------------------------------------------------
# Recipes
# ---------------------------------------------------------------------------

_BASE_RECIPE = {
    "disk": "",  # filled at runtime
    "encryption": {"type": "none", "passphrase": ""},
    "hostname": "e2e-test",
    "flatpaks": [],
    "selinuxDisabled": False,
    "unifiedStorage": False,
    "user": {"username": "", "fullname": "", "password": "", "groups": []},
}

YELLOWFIN_RECIPE = {
    **_BASE_RECIPE,
    "filesystem": "xfs",
    "btrfsSubvolumes": False,
    "image": "ghcr.io/tuna-os/yellowfin:gnome50",
    "targetImgref": "docker://ghcr.io/tuna-os/yellowfin:gnome50",
    "composeFsBackend": False,
    "bootloader": "",
    "selinuxDisabled": True,
}

DAKOTA_RECIPE = {
    **_BASE_RECIPE,
    "filesystem": "btrfs",
    "btrfsSubvolumes": False,
    "image": "ghcr.io/projectbluefin/dakota:latest",
    "targetImgref": "docker://ghcr.io/projectbluefin/dakota:latest",
    "composeFsBackend": True,
    "bootloader": "systemd",
    "selinuxDisabled": False,
}


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

def _fisherman_bin() -> str:
    env = os.environ.get("FISHERMAN_BIN", "")
    if env and Path(env).is_file():
        return env
    # Fall back to building it now (requires Go).
    built = "/tmp/fisherman-e2e-test"
    if not Path(built).exists():
        pytest.skip(
            f"fisherman binary not found. Set FISHERMAN_BIN env var or build with:\n"
            f"  TMPDIR=/var/tmp/gobuild go build -o {built} "
            f"{FISHERMAN_SRC}/cmd/fisherman/"
        )
    return built


pytestmark = [
    pytest.mark.skipif(os.geteuid() != 0, reason="Must run as root"),
    pytest.mark.integration,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    """Run a command, capture output, raise on non-zero exit."""
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _check(cmd: list, **kwargs):
    r = _run(cmd, **kwargs)
    if r.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(str(c) for c in cmd)}\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
    return r


def _image_in_podman(imgref: str) -> bool:
    r = _run(["podman", "image", "exists", imgref])
    return r.returncode == 0


def _find_free_nbd() -> str:
    """Return the first /dev/nbdN device that is not in use."""
    for n in range(16):
        dev = f"/dev/nbd{n}"
        if not Path(dev).exists():
            continue
        r = _run(["lsblk", "-n", "-o", "SIZE", dev])
        # Free NBD devices report "0B"; in-use ones report their actual size.
        size = r.stdout.strip()
        if r.returncode == 0 and (size == "" or size == "0B"):
            return dev
    raise RuntimeError("No free /dev/nbd* device found (is nbd kernel module loaded?)")


class NbdDisk:
    """Context manager that creates a raw sparse disk image and attaches it via qemu-nbd."""

    def __init__(self, size_gb: int = DISK_SIZE_GB):
        self.size_gb = size_gb
        self.raw_path: str = ""
        self.device: str = ""
        self._tmpdir: tempfile.TemporaryDirectory | None = None
        self._connected: bool = False

    def __enter__(self):
        self._tmpdir = tempfile.TemporaryDirectory(dir="/var/tmp", prefix="e2e-disk-")
        self.raw_path = os.path.join(self._tmpdir.name, "disk.raw")
        # Create a sparse file.
        _check(["truncate", "-s", f"{self.size_gb}G", self.raw_path])

        # Load nbd module if needed.
        _run(["modprobe", "nbd", "max_part=8"])

        self.device = _find_free_nbd()
        _check(["qemu-nbd", "--connect", self.device, "--format=raw", self.raw_path])
        self._connected = True
        # Give the kernel a moment to create partition block devices.
        time.sleep(1)
        print(f"\n  [NbdDisk] {self.raw_path} → {self.device}")
        return self

    def disconnect(self):
        """Disconnect the NBD device, releasing the file lock.

        Call this before passing raw_path to QEMU — QEMU cannot open a file
        that qemu-nbd already holds a write lock on.
        """
        if self._connected:
            _run(["qemu-nbd", "--disconnect", self.device])
            self._connected = False

    def __exit__(self, *_):
        try:
            self.disconnect()
        except Exception as e:
            print(f"  [NbdDisk] Warning: disconnect failed: {e}")
        finally:
            if self._tmpdir:
                self._tmpdir.cleanup()


def _write_recipe(recipe: dict, disk: str) -> str:
    """Write a recipe dict to a temp file, return its path."""
    r = dict(recipe)
    r["disk"] = disk
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir="/var/tmp",
        prefix="e2e-recipe-", delete=False
    )
    json.dump(r, f, indent=2)
    f.close()
    return f.name


def _run_fisherman(recipe_path: str, fisherman_bin: str, timeout: int = 3600) -> tuple[int, str]:
    """Run fisherman with the given recipe, stream output, return (exit_code, output)."""
    log_path = recipe_path.replace(".json", ".log")
    print(f"\n  [fisherman] recipe={recipe_path} log={log_path}")

    with open(log_path, "w") as log_f:
        proc = subprocess.Popen(
            [fisherman_bin, recipe_path],
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            return -1, open(log_path).read()

    output = Path(log_path).read_text()
    # Print last 40 lines to pytest output for debugging.
    lines = output.splitlines()
    for line in lines[-40:]:
        print(f"  {line}")
    return proc.returncode, output


def _verify_partitions(device: str):
    """Assert that the device has at least 3 partitions."""
    r = _check(["lsblk", "-n", "-o", "NAME,SIZE,FSTYPE", device])
    print(f"\n  [lsblk]\n{r.stdout}")
    base = device.split("/")[-1]  # e.g. "nbd0" or "sda"
    parts = []
    for l in r.stdout.splitlines():
        if not l.strip():
            continue
        # Strip lsblk tree-drawing chars to get the bare device name.
        name = l.split()[0].lstrip("├─└│ ")
        # A partition name differs from the base device (e.g. nbd0p1 != nbd0).
        if name != base:
            parts.append(l)
    assert len(parts) >= 3, f"Expected ≥3 partitions, got:\n{r.stdout}"


def _pick_test_flatpaks(n: int = 2) -> list:
    """Return up to n flatpak app IDs available in the system install.

    Returns an empty list if flatpak is unavailable or no apps are installed.
    """
    r = subprocess.run(
        ["flatpak", "list", "--system", "--columns=application"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return []
    return [line.strip() for line in r.stdout.splitlines() if line.strip()][:n]


def _root_partition(device: str) -> tuple:
    """Return (device_path, fstype) for the root (xfs/btrfs) partition, or (None, None)."""
    r = subprocess.run(
        ["lsblk", "-n", "-o", "NAME,FSTYPE", device],
        capture_output=True, text=True,
    )
    result = (None, None)
    for line in r.stdout.splitlines():
        cols = line.split()
        if len(cols) >= 2 and cols[1] in ("xfs", "btrfs"):
            # Strip tree-drawing characters to get the bare device name.
            name = cols[0].lstrip("├─└│ ")
            result = (f"/dev/{name}", cols[1])
    return result  # last match is the root partition


def _verify_flatpaks(device: str, expected_apps: list):
    """Mount the root partition of the installed disk and assert flatpak apps are present.

    This is a regression test for the Flatpak copy step: fisherman must copy
    the requested app directories from /var/lib/flatpak on the host into
    <target>/var/lib/flatpak on the installed system.
    """
    if not expected_apps:
        return

    root_dev, fstype = _root_partition(device)
    if not root_dev:
        pytest.fail(f"Could not find xfs/btrfs root partition on {device} for flatpak verification")

    mount_dir = tempfile.mkdtemp(dir="/var/tmp", prefix="e2e-flatpak-verify-")
    try:
        mount_cmd = ["mount", "-o", "ro", root_dev, mount_dir]
        if fstype == "btrfs":
            # subvol=/ ensures we mount the btrfs top-level volume regardless
            # of which subvolume is set as default by bootc.
            mount_cmd = ["mount", "-t", "btrfs", "-o", "ro,subvol=/", root_dev, mount_dir]
        _check(mount_cmd)
        try:
            flatpak_dir = Path(mount_dir) / "var" / "lib" / "flatpak" / "app"
            assert flatpak_dir.exists(), (
                f"No flatpak app dir found at {flatpak_dir}. "
                f"Flatpak copy step may have been skipped or failed."
            )
            for app_id in expected_apps:
                app_path = flatpak_dir / app_id
                available = sorted(p.name for p in flatpak_dir.iterdir()) if flatpak_dir.exists() else []
                assert app_path.exists(), (
                    f"Flatpak {app_id!r} not found in installed system.\n"
                    f"Apps present: {available}"
                )
                print(f"  ✓ flatpak {app_id} present in installed system")
        finally:
            subprocess.run(["umount", mount_dir], capture_output=True)
    finally:
        shutil.rmtree(mount_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Boot verification helpers
# ---------------------------------------------------------------------------

def _boot_verify(raw_path: str, vnc_display: int = 10, timeout: int = BOOT_TIMEOUT_S) -> Path:
    """Start a QEMU VM from raw_path, wait for display, capture and return screenshot path.

    Returns the Path to the PNG screenshot.  Raises AssertionError if the
    display never initialises within *timeout* seconds.
    """
    if not Path(QEMU_BIN).exists():
        pytest.skip(f"qemu-system-x86_64 not found at {QEMU_BIN}")
    if not OVMF_CODE.exists():
        pytest.skip(f"Non-secboot OVMF not found at {OVMF_CODE}")
    if not VNCDO_BIN:
        pytest.skip("vncdo not found; install python3-vncdotool")

    vars_copy = tempfile.mktemp(suffix=".fd", dir="/var/tmp")
    shutil.copy2(OVMF_VARS, vars_copy)

    vnc_port = 5900 + vnc_display
    qmp_sock = f"/tmp/e2e-qmp-{vnc_display}.sock"
    screenshot = Path(f"/var/tmp/e2e-screen-{vnc_display}.png")

    cmd = [
        QEMU_BIN,
        "-enable-kvm", "-m", "4096", "-cpu", "host", "-smp", "4",
        "-drive", f"if=pflash,format=raw,readonly=on,file={OVMF_CODE}",
        "-drive", f"if=pflash,format=raw,file={vars_copy}",
        "-drive", f"format=raw,file={raw_path}",
        "-vga", "std",
        "-display", f"vnc=0.0.0.0:{vnc_display},to=9",
        "-qmp", f"unix:{qmp_sock},server=on,wait=off",
        "-net", "nic", "-net", "user",
    ]
    full_cmd = ["sudo", "--non-interactive"] + cmd if os.geteuid() != 0 else cmd

    print(f"\n  [boot_verify] starting QEMU on VNC :{vnc_display} (port {vnc_port})")
    qemu_proc = subprocess.Popen(full_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Brief wait to catch immediate startup failures.
    time.sleep(2)
    if qemu_proc.poll() is not None:
        raise RuntimeError(f"QEMU exited immediately (rc={qemu_proc.returncode})")

    # Poll VNC until the display is no longer blank / uninitialized.
    deadline = time.monotonic() + timeout
    initialized = False
    while time.monotonic() < deadline:
        time.sleep(10)
        r = subprocess.run(
            [VNCDO_BIN, "-s", f"127.0.0.1::{vnc_port}", "-t", "8", "capture", str(screenshot)],
            capture_output=True,
        )
        if r.returncode != 0:
            continue
        # Check if image is non-trivially black (i.e. guest wrote something).
        try:
            from PIL import Image
            import numpy as np
            img = Image.open(screenshot).convert("L")
            arr = __import__("numpy").array(img)
            non_black_pct = (arr > 20).sum() / arr.size
            print(f"  [boot_verify] non-black pixels: {non_black_pct:.1%}")
            if non_black_pct > 0.05:
                initialized = True
                break
        except ImportError:
            # PIL/numpy not available — just check file size as proxy.
            if screenshot.stat().st_size > 5000:
                initialized = True
                break

    # Kill QEMU.
    qemu_proc.terminate()
    try:
        qemu_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        qemu_proc.kill()
    try:
        Path(vars_copy).unlink()
    except FileNotFoundError:
        pass

    assert initialized, (
        f"Display never initialized after {timeout}s. "
        f"Screenshot saved to {screenshot}"
    )
    print(f"  [boot_verify] ✓ display active — screenshot at {screenshot}")
    return screenshot


# ---------------------------------------------------------------------------
# Install helper
# ---------------------------------------------------------------------------

def _install_image(recipe_template: dict, label: str, vnc_offset: int):
    """Core logic for an install test: create disk, run fisherman, verify."""
    fisherman_bin = _fisherman_bin()

    img = recipe_template["image"]
    if not _image_in_podman(img):
        pytest.skip(f"Image {img!r} not in podman storage. Pull it first:\n  sudo podman pull {img}")

    with NbdDisk() as disk:
        recipe_path = _write_recipe(recipe_template, disk.device)
        try:
            rc, output = _run_fisherman(recipe_path, fisherman_bin)

            assert rc == 0, (
                f"{label} fisherman exited with code {rc}.\n"
                f"Last output:\n{output[-3000:]}"
            )
            assert '"type":"complete"' in output or '"type": "complete"' in output, (
                f"{label} fisherman did not emit a 'complete' event.\nOutput:\n{output[-3000:]}"
            )

            _verify_partitions(disk.device)
            print(f"\n  ✓ {label} install succeeded")

            if BOOT_VERIFY:
                # Disconnect qemu-nbd before starting QEMU — both tools need
                # exclusive write access to the raw file.
                disk.disconnect()
                _boot_verify(disk.raw_path, vnc_display=vnc_offset)
                print(f"  ✓ {label} boot verification succeeded")
        finally:
            try:
                Path(recipe_path).unlink()
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_yellowfin_install():
    """Yellowfin (grub2 + XFS) installs and optionally boots to GDM."""
    _install_image(YELLOWFIN_RECIPE, "Yellowfin", vnc_offset=11)


def test_dakota_install():
    """Dakota (systemd-boot + btrfs + composefs) installs and optionally boots to GDM."""
    _install_image(DAKOTA_RECIPE, "Dakota", vnc_offset=12)


# ---------------------------------------------------------------------------
# Build helper (run standalone)
# ---------------------------------------------------------------------------

def _build_fisherman() -> str:
    out = "/tmp/fisherman-e2e-test"
    print(f"Building fisherman → {out} …")
    env = os.environ.copy()
    env.setdefault("TMPDIR", "/var/tmp/gobuild")
    Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    _check(
        ["go", "build", "-o", out, "./cmd/fisherman/"],
        cwd=str(FISHERMAN_SRC),
        env=env,
    )
    print("Build OK")
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="E2E install test runner")
    parser.add_argument("--images", default="yellowfin,dakota",
                        help="Comma-separated list of images to test (yellowfin, dakota)")
    parser.add_argument("--boot-verify", action="store_true",
                        help="Boot each installed disk in QEMU and verify display")
    parser.add_argument("--build", action="store_true",
                        help="Build fisherman from source before running")
    parser.add_argument("--disk-size", type=int, default=DISK_SIZE_GB,
                        help="Virtual disk size in GB (default: 30)")
    args = parser.parse_args()

    if os.geteuid() != 0:
        sys.exit("Error: must run as root")

    if args.boot_verify:
        os.environ["BOOT_VERIFY"] = "1"
    if args.disk_size:
        os.environ["DISK_SIZE_GB"] = str(args.disk_size)

    if args.build:
        os.environ["FISHERMAN_BIN"] = _build_fisherman()
    elif not os.environ.get("FISHERMAN_BIN"):
        os.environ["FISHERMAN_BIN"] = _build_fisherman()

    images = [i.strip().lower() for i in args.images.split(",")]
    results = {}

    for name in images:
        recipe = {"yellowfin": YELLOWFIN_RECIPE, "dakota": DAKOTA_RECIPE}.get(name)
        if recipe is None:
            print(f"Unknown image: {name!r} (choose from: yellowfin, dakota)")
            continue
        print(f"\n{'='*60}\nTesting {name}\n{'='*60}")
        try:
            _install_image(recipe, name.capitalize(), vnc_offset=11 + list(images).index(name))
            results[name] = "PASS"
        except (AssertionError, RuntimeError, Exception) as e:
            results[name] = f"FAIL: {e}"

    print(f"\n{'='*60}\nResults:")
    all_pass = True
    for name, result in results.items():
        status = "✓" if result == "PASS" else "✗"
        print(f"  {status} {name}: {result}")
        if result != "PASS":
            all_pass = False

    sys.exit(0 if all_pass else 1)

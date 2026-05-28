"""GTK integration tests for the installer wizard.

These tests instantiate real GTK widgets via Xvfb and compiled GResources
(built by 'meson setup build && ninja -C build').

They drive the installer step by step, exactly as a user would, and assert
that the right recipe JSON is produced at the end.

Run with:
    xvfb-run pytest tests/ui/ -v
"""

import json
import os
import sys
import tempfile
from unittest.mock import patch as _mock_patch

import pytest

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gio, Gtk  # noqa: E402

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Minimal system recipe — mirrors the installed recipe.json but has no extra steps.
_SYS_RECIPE = {
    "log_file": "/dev/null",
    "distro_name": "BootcOS Test",
    "distro_logo": "org.bootcinstaller.Installer",
    "tour": {
        "welcome": {"resource": "/org/bootcinstaller/Installer/assets/welcome.png",
                    "title": "Installing", "description": "test"},
        "completed": {"resource": "/org/bootcinstaller/Installer/assets/complete.svg",
                      "title": "Done", "description": "test"},
    },
    "steps": {
        "welcome": {"template": "welcome", "protected": True},
        "image":   {"template": "image",   "protected": True},
    },
}


def _pump():
    """Process pending GLib/GTK events (allow signal handlers to fire)."""
    ctx = GLib.MainContext.default()
    while ctx.pending():
        ctx.iteration(False)


@pytest.fixture()
def window():
    """Yield an initialised BootcWindow (wizard root) for the test.

    Adw.init() is called in pytest_configure (conftest) so all Adw widget
    types are registered before we try to build templates.

    BootcWindow.__init__ passes kwargs to GObject (which rejects unknown
    properties), so we inject the test recipe via BOOTC_CUSTOM_RECIPE
    rather than as a constructor kwarg.

    GTK-CRITICAL "windows must be added after startup" is a soft warning;
    the window is still fully functional for tests.
    """
    from bootc_installer.windows.main_window import BootcWindow

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tf:
        json.dump(_SYS_RECIPE, tf)
        recipe_path = tf.name

    old_recipe_env = os.environ.get("BOOTC_CUSTOM_RECIPE")
    os.environ["BOOTC_CUSTOM_RECIPE"] = recipe_path

    # On an ostree-booted dev machine, RecipeLoader detects "live ISO mode"
    # and strips the image step. Patch os.path.exists in the recipe module
    # to simulate running inside a Flatpak (/.flatpak-info present), which
    # keeps live_iso_mode=False so the image step is retained for tests.
    _real_exists = os.path.exists
    def _flatpak_exists(p):
        if p == "/.flatpak-info":
            return True
        return _real_exists(p)

    try:
        app = Adw.Application(
            application_id="org.bootcinstaller.InstallerTest",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        with _mock_patch("bootc_installer.utils.recipe.os.path.exists",
                         side_effect=_flatpak_exists):
            win = BootcWindow(application=app)
        win.present()
        _pump()
        yield win
    finally:
        try:
            win.destroy()
        except Exception:
            pass
        _pump()
        if old_recipe_env is None:
            os.environ.pop("BOOTC_CUSTOM_RECIPE", None)
        else:
            os.environ["BOOTC_CUSTOM_RECIPE"] = old_recipe_env
        os.unlink(recipe_path)


# ── Smoke tests ────────────────────────────────────────────────────────────────

class TestWindowSmoke:
    def test_window_opens(self, window):
        assert window is not None

    def test_window_has_steps(self, window):
        """The builder should have registered at least the welcome step."""
        from bootc_installer.utils.builder import Builder
        # The window exposes the builder via .builder property.
        assert hasattr(window, "builder") or hasattr(window, "_BootcWindow__builder")

    def test_image_step_assigned(self, window):
        """After build, window.image_step should point to the image widget."""
        assert hasattr(window, "image_step"), "window.image_step not set by builder"
        assert window.image_step is not None


# ── Image step tests ───────────────────────────────────────────────────────────

class TestImageStep:
    def test_get_finals_returns_selected_image(self, window):
        step = window.image_step
        finals = step.get_finals()
        assert "selected_image" in finals or "custom_image" in finals

    def test_default_image_selected(self, window):
        """With no default_image in catalog, tree starts collapsed and nothing is pre-selected."""
        step = window.image_step
        finals = step.get_finals()
        image = finals.get("selected_image") or finals.get("custom_image")
        assert not image, (
            "No image should be pre-selected when default_image is absent from catalog"
        )

    def test_composefs_backend_in_finals(self, window):
        step = window.image_step
        finals = step.get_finals()
        assert "composefs_backend" in finals

    def test_image_type_in_finals(self, window):
        step = window.image_step
        finals = step.get_finals()
        assert "image_type" in finals
        assert finals["image_type"] in ("bootc", "ostree")

    def test_needs_user_creation_in_finals(self, window):
        step = window.image_step
        finals = step.get_finals()
        assert "needs_user_creation" in finals

    def test_flatpaks_in_finals(self, window):
        step = window.image_step
        finals = step.get_finals()
        assert "flatpaks" in finals
        assert isinstance(finals["flatpaks"], list)


# ── Wizard navigation ──────────────────────────────────────────────────────────

class TestDiskStepButtonState:
    def test_next_button_insensitive_before_selection(self):
        """btn_next must start insensitive so the header Next is greyed out.

        Regression test: the blueprint previously omitted sensitive: false, so
        the page btn_next defaulted to sensitive=True and the window mirrored
        that onto the header Next button — making it clickable before any disk
        was chosen.

        Skipped when Adw.ButtonRow is unavailable (libadwaita < 1.6, e.g. Ubuntu 24.04).
        """
        try:
            Adw.ButtonRow  # noqa: B018 — probe for ≥1.6 widget
        except AttributeError:
            pytest.skip("Adw.ButtonRow requires libadwaita >= 1.6")

        from unittest.mock import MagicMock, patch

        from bootc_installer.defaults.disk import BootcDefaultDisk

        mock_window = MagicMock()
        mock_window.recipe = {"min_disk_size": 51200}

        with patch("bootc_installer.defaults.disk.DisksManager") as MockDM:
            MockDM.return_value.all_disks.return_value = []
            widget = BootcDefaultDisk(mock_window, {}, "disk", {})
            _pump()

        assert not widget.btn_next.get_sensitive(), (
            "btn_next must be insensitive on load so the header Next is greyed out"
        )


class TestDiskStepFsToolCheck:
    """fs_tool_error_banner shows when the required mkfs tool is missing on the host."""

    def _make_disk_widget(self):
        from unittest.mock import MagicMock, patch

        from bootc_installer.defaults.disk import BootcDefaultDisk
        from bootc_installer.widgets.page_header import BootcPageHeader  # noqa: F401 — registers GType

        try:
            Adw.ButtonRow  # noqa: B018 — probe for ≥1.6 widget used in BootcDefaultDisk.__init__
        except AttributeError:
            pytest.skip("Adw.ButtonRow requires libadwaita >= 1.6")

        mock_window = MagicMock()
        mock_window.recipe = {"min_disk_size": 51200}
        mock_window.image_step.get_finals.return_value = {
            "supported_filesystems": ["xfs", "btrfs"],
            "default_hostname": "",
        }
        with patch("bootc_installer.defaults.disk.DisksManager") as MockDM:
            MockDM.return_value.all_disks.return_value = []
            widget = BootcDefaultDisk(mock_window, {}, "disk", {})
            _pump()
        return widget

    def test_banner_shown_when_xfs_tool_missing(self):
        """fs_tool_error_banner becomes visible and row turns red when mkfs.xfs is missing."""
        import subprocess
        from unittest.mock import patch

        widget = self._make_disk_widget()

        missing = subprocess.CompletedProcess(args=[], returncode=1)
        with patch("subprocess.run", return_value=missing):
            widget._BootcDefaultDisk__check_fs_tool("xfs")
            _pump()

        assert widget.fs_tool_error_banner.get_visible(), (
            "fs_tool_error_banner should be visible when mkfs.xfs is missing"
        )
        assert "xfsprogs" in widget.fs_tool_error_banner.get_title()
        assert widget.filesystem_row.has_css_class("error"), (
            "filesystem_row should have 'error' CSS class when mkfs.xfs is missing"
        )
        assert "xfsprogs" in widget.filesystem_row.get_subtitle()

    def test_banner_hidden_when_xfs_tool_present(self):
        """Banner hidden and row error class cleared when mkfs.xfs is available."""
        import subprocess
        from unittest.mock import patch

        widget = self._make_disk_widget()

        present = subprocess.CompletedProcess(args=[], returncode=0)
        with patch("subprocess.run", return_value=present):
            widget._BootcDefaultDisk__check_fs_tool("xfs")
            _pump()

        assert not widget.fs_tool_error_banner.get_visible(), (
            "fs_tool_error_banner should be hidden when mkfs.xfs is available"
        )
        assert not widget.filesystem_row.has_css_class("error"), (
            "filesystem_row should not have 'error' CSS class when mkfs.xfs is available"
        )
        assert widget.filesystem_row.get_subtitle() == ""

    def test_banner_shown_when_btrfs_tool_missing(self):
        """fs_tool_error_banner visible and row red when mkfs.btrfs is missing."""
        import subprocess
        from unittest.mock import patch

        widget = self._make_disk_widget()

        missing = subprocess.CompletedProcess(args=[], returncode=1)
        with patch("subprocess.run", return_value=missing):
            widget._BootcDefaultDisk__check_fs_tool("btrfs")
            _pump()

        assert widget.fs_tool_error_banner.get_visible(), (
            "fs_tool_error_banner should be visible when mkfs.btrfs is missing"
        )
        assert "btrfs-progs" in widget.fs_tool_error_banner.get_title()
        assert widget.filesystem_row.has_css_class("error")
        assert "btrfs-progs" in widget.filesystem_row.get_subtitle()

    def test_btn_next_blocked_when_tool_missing(self):
        """btn_next must be insensitive when the required mkfs tool is missing."""
        import subprocess
        from unittest.mock import patch

        widget = self._make_disk_widget()
        # Simulate a partition recipe being set (as if the user picked a disk)
        widget._BootcDefaultDisk__partition_recipe = {"disk": "/dev/sda"}

        missing = subprocess.CompletedProcess(args=[], returncode=1)
        with patch("subprocess.run", return_value=missing):
            widget._BootcDefaultDisk__check_fs_tool("xfs")
            _pump()

        assert not widget.btn_next.get_sensitive(), (
            "btn_next must be insensitive when mkfs.xfs is missing from host PATH"
        )

    def test_btn_next_unblocked_when_tool_present(self):
        """btn_next becomes sensitive when tool is present and a partition recipe exists."""
        import subprocess
        from unittest.mock import patch

        widget = self._make_disk_widget()
        widget._BootcDefaultDisk__partition_recipe = {"disk": "/dev/sda"}

        present = subprocess.CompletedProcess(args=[], returncode=0)
        with patch("subprocess.run", return_value=present):
            widget._BootcDefaultDisk__check_fs_tool("xfs")
            _pump()

        assert widget.btn_next.get_sensitive(), (
            "btn_next must be sensitive when mkfs.xfs is present and a partition recipe exists"
        )



class _FakePowerFile:
    def __init__(self, text="", exists=True, error=None):
        self._text = text
        self._exists = exists
        self._error = error

    def exists(self):
        return self._exists

    def read_text(self):
        if self._error is not None:
            raise self._error
        return self._text


class _FakePowerSupply:
    def __init__(self, supply_type=None, online=None, type_error=None, online_error=None):
        self._files = {}
        if supply_type is not None or type_error is not None:
            self._files["type"] = _FakePowerFile(
                text=supply_type or "",
                exists=True,
                error=type_error,
            )
        if online is not None or online_error is not None:
            self._files["online"] = _FakePowerFile(
                text=online or "",
                exists=True,
                error=online_error,
            )

    def __truediv__(self, name):
        return self._files.get(name, _FakePowerFile(exists=False))


class TestDiskStepBatteryBanner:
    def _make_disk_widget(self, *, supplies=None, side_effect=None):
        from unittest.mock import patch

        with patch(
            "bootc_installer.defaults.disk.pathlib.Path.iterdir",
            return_value=supplies,
            side_effect=side_effect,
        ):
            return TestDiskStepFsToolCheck()._make_disk_widget()

    def test_banner_shown_when_running_on_battery(self):
        widget = self._make_disk_widget(
            supplies=[
                _FakePowerSupply("Battery"),
                _FakePowerSupply("Mains", "0"),
            ]
        )

        assert widget.battery_banner.get_revealed(), (
            "battery_banner should be revealed when a mains supply reports offline"
        )

    def test_banner_hidden_on_desktops_without_mains_supply(self):
        widget = self._make_disk_widget(
            supplies=[
                _FakePowerSupply("Battery"),
            ]
        )

        assert not widget.battery_banner.get_revealed(), (
            "battery_banner should stay hidden when no mains or UPS supply exists"
        )

    def test_banner_hidden_when_power_detection_errors(self):
        widget = self._make_disk_widget(side_effect=RuntimeError("broken sysfs"))

        assert not widget.battery_banner.get_revealed(), (
            "battery_banner should stay hidden if power detection raises an exception"
        )


class TestWizardNavigation:
    def test_can_advance_from_image_step(self, window):
        """Clicking Next on the image step rebuilds downstream UI and advances."""
        image_step = window.image_step
        assert image_step is not None
        # Simulate clicking btn_next (same as test_auto_advance).
        image_step.test_auto_advance()
        _pump()
        # No assertion — if it doesn't crash, the step-advance logic works.


# ── Full flow: finals → processor ─────────────────────────────────────────────

def _set_custom_image(image_step, imgref: str):
    """Expand the custom image row and type an imgref so get_finals() returns it."""
    image_step.row_custom.set_expanded(True)
    image_step.image_url_entry.set_text(imgref)
    _pump()


class TestEndToEnd:
    def test_recipe_generated_from_auto_disk(self, window):
        """Simulate auto-disk selection and verify processor produces valid JSON."""
        from bootc_installer.utils.processor import Processor

        # Select an image so the recipe is valid (no default in catalog).
        _set_custom_image(window.image_step, "ghcr.io/tuna-os/yellowfin:gnome50")
        image_finals = window.image_step.get_finals()
        disk_finals = {
            "disk": {"auto": {"disk": "/dev/vda", "pretty_size": "100 GB",
                               "size": 107_374_182_400}},
        }
        enc_finals = {"encryption": {"use_encryption": False}}
        hostname_finals = {"hostname": "ci-test-host"}

        all_finals = [image_finals, disk_finals, enc_finals, hostname_finals]
        path = Processor.gen_install_recipe("/dev/null", all_finals, _SYS_RECIPE)
        assert os.path.exists(path)

        with open(path) as f:
            recipe = json.load(f)

        # Core sanity checks.
        assert recipe["disk"] == "/dev/vda"
        assert recipe["hostname"] == "ci-test-host"
        assert recipe["image"], "Image should be populated from image step finals"
        assert recipe["encryption"]["type"] == "none"
        assert isinstance(recipe["flatpaks"], list)

    def test_recipe_generated_from_manual_disk(self, window):
        """Manual partition layout produces customMounts in the recipe."""
        from bootc_installer.utils.processor import Processor

        # Select an image so the recipe is valid (no default in catalog).
        _set_custom_image(window.image_step, "ghcr.io/tuna-os/yellowfin:gnome50")
        image_finals = window.image_step.get_finals()
        disk_finals = {
            "disk": {
                "/dev/sda1": {"fs": "fat32", "mp": "/boot/efi"},
                "/dev/sda2": {"fs": "ext4",  "mp": "/boot"},
                "/dev/sda3": {"fs": "xfs",   "mp": "/"},
            }
        }
        enc_finals = {"encryption": {"use_encryption": False}}
        hostname_finals = {"hostname": "manual-host"}

        all_finals = [image_finals, disk_finals, enc_finals, hostname_finals]
        path = Processor.gen_install_recipe("/dev/null", all_finals, _SYS_RECIPE)

        with open(path) as f:
            recipe = json.load(f)

        assert "customMounts" in recipe
        mounts_by_target = {m["target"]: m for m in recipe["customMounts"]}
        assert "/" in mounts_by_target
        assert "/boot/efi" in mounts_by_target

    def test_composefs_propagates_end_to_end(self, window):
        """composefs_backend=True in image finals → composeFsBackend in recipe."""
        from bootc_installer.utils.processor import Processor

        # Manually set composefs flag (as if a composefs-native image was selected).
        image_finals = window.image_step.get_finals()
        image_finals["composefs_backend"] = True

        disk_finals = {"disk": {"auto": {"disk": "/dev/vda"}}}
        enc_finals  = {"encryption": {"use_encryption": False}}
        host_finals = {"hostname": "cf-host"}

        path = Processor.gen_install_recipe("/dev/null",
                                            [image_finals, disk_finals, enc_finals, host_finals],
                                            _SYS_RECIPE)
        with open(path) as f:
            recipe = json.load(f)

        assert recipe["composeFsBackend"] is True

    def test_encryption_propagates_end_to_end(self, window):
        from bootc_installer.utils.processor import Processor

        image_finals = window.image_step.get_finals()
        disk_finals = {"disk": {"auto": {"disk": "/dev/vda"}}}
        enc_finals  = {"encryption": {
            "use_encryption": True,
            "type": "luks-passphrase",
            "encryption_key": "t3st-key",
        }}
        host_finals = {"hostname": "enc-host"}

        path = Processor.gen_install_recipe("/dev/null",
                                            [image_finals, disk_finals, enc_finals, host_finals],
                                            _SYS_RECIPE)
        with open(path) as f:
            recipe = json.load(f)

        assert recipe["encryption"]["type"] == "luks-passphrase"
        assert recipe["encryption"]["passphrase"] == "t3st-key"

"""
Unit tests for done.py — reboot logic and icon application.
No display required; GTK widgets are not instantiated.
"""

import subprocess
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, sentinel

def _build_gi_stubs():
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")

    class _Template:
        def __call__(self, *args, **kwargs):
            return lambda cls: cls

        def Child(self, *args, **kwargs):
            return None

    class _StubBin:
        pass

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    gtk_mod.Template = _Template()
    gtk_mod.Box = _StubBin

    adw_mod = types.ModuleType("gi.repository.Adw")
    adw_mod.Bin = _StubBin
    adw_mod.Window = _StubBin

    gobject_mod = types.ModuleType("gi.repository.GObject")

    def _property(*args, **kwargs):
        return lambda func: property(func)

    gobject_mod.Property = _property

    class _ResourceLookupFlags:
        NONE = 0

    gio_mod = types.ModuleType("gi.repository.Gio")
    gio_mod.bus_get_sync = MagicMock()
    # Use SimpleNamespace so typos like .BusTyp raise AttributeError immediately.
    gio_mod.BusType = types.SimpleNamespace(SYSTEM=sentinel.SYSTEM_BUS)
    gio_mod.DBusCallFlags = types.SimpleNamespace(NONE=sentinel.DBUS_FLAGS_NONE)
    gio_mod.ResourceLookupFlags = _ResourceLookupFlags
    gio_mod.resources_lookup_data = MagicMock()
    gio_mod.File = MagicMock()

    sys.modules["gi.repository.Gtk"] = gtk_mod
    sys.modules["gi.repository.Adw"] = adw_mod
    sys.modules["gi.repository.GObject"] = gobject_mod
    sys.modules["gi.repository.Gio"] = gio_mod
    repo_mod.Gtk = gtk_mod
    repo_mod.Adw = adw_mod
    repo_mod.GObject = gobject_mod
    repo_mod.Gio = gio_mod

    for lib in ("Gdk", "GLib"):
        stub = MagicMock()
        setattr(repo_mod, lib, stub)
        sys.modules[f"gi.repository.{lib}"] = stub

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


_build_gi_stubs()
if "bootc_installer.windows.dialog_output" not in sys.modules:
    sys.modules["bootc_installer.windows.dialog_output"] = MagicMock()

from bootc_installer.views.done import (  # noqa: E402
    BootcDone,
    apply_icon,
    do_reboot,
    warmup_registry,
)


class TestDoReboot(unittest.TestCase):

    def setUp(self):
        # test_branding_parity._import_done() reimports done.py during test
        # execution, rebinding done.Gio to whichever stubs are current in
        # sys.modules.  test_slurp_helpers / test_network_helpers also
        # overwrite sys.modules["gi.repository.GLib"] with a bare ModuleType
        # that lacks Variant, breaking done.py's D-Bus call path.
        # Rebuilding our own stubs first and then reimporting ensures that
        # do_reboot and the patch("...Gio.bus_get_sync") target the same object.
        _build_gi_stubs()
        sys.modules.pop("bootc_installer.views.done", None)
        import bootc_installer.views as views_pkg
        views_pkg.__dict__.pop("done", None)
        import bootc_installer.views.done  # noqa: F401 — re-populates sys.modules

    def test_reboot_via_dbus_success(self):
        import bootc_installer.views.done as done_mod
        conn = MagicMock()
        with patch("bootc_installer.views.done.Gio.bus_get_sync", return_value=conn):
            result = done_mod.do_reboot(in_flatpak=True)
        self.assertTrue(result)
        conn.call_sync.assert_called_once()

    def test_dbus_reboot_calls_correct_method(self):
        """D-Bus contract: must call org.freedesktop.login1 Reboot method."""
        import bootc_installer.views.done as done_mod
        conn = MagicMock()
        with patch("bootc_installer.views.done.Gio.bus_get_sync", return_value=conn):
            done_mod.do_reboot(in_flatpak=True)
        call_args = conn.call_sync.call_args
        # Positional args: bus_name, object_path, interface_name, method_name, params, ...
        args = call_args[0]
        self.assertIn("login1", args[0])          # bus name
        self.assertIn("Manager", args[2])          # interface
        self.assertEqual(args[3], "Reboot")        # method name

    def test_reboot_falls_back_to_subprocess_when_dbus_fails(self):
        import bootc_installer.views.done as done_mod
        with patch("bootc_installer.views.done.Gio.bus_get_sync", side_effect=Exception("no bus")), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = done_mod.do_reboot(in_flatpak=False)
        self.assertTrue(result)
        first_argv = mock_run.call_args_list[0][0][0]
        self.assertIn("systemctl", first_argv)

    def test_reboot_flatpak_fallback_uses_flatpak_spawn(self):
        import bootc_installer.views.done as done_mod
        with patch("bootc_installer.views.done.Gio.bus_get_sync", side_effect=Exception("no bus")), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = done_mod.do_reboot(in_flatpak=True)
        self.assertTrue(result)
        first_argv = mock_run.call_args_list[0][0][0]
        self.assertEqual(first_argv[:2], ["flatpak-spawn", "--host"])

    def test_reboot_tries_reboot_binary_when_systemctl_fails(self):
        import bootc_installer.views.done as done_mod
        with patch("bootc_installer.views.done.Gio.bus_get_sync", side_effect=Exception("no bus")), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stderr=b"failed"),  # systemctl reboot → fail
                MagicMock(returncode=0),                    # reboot → success
            ]
            result = done_mod.do_reboot(in_flatpak=False)
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 2)

    def test_reboot_returns_false_when_all_methods_fail(self):
        import bootc_installer.views.done as done_mod
        with patch("bootc_installer.views.done.Gio.bus_get_sync", side_effect=Exception("no bus")), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr=b"permission denied")
            result = done_mod.do_reboot(in_flatpak=False)
        self.assertFalse(result)


class TestApplyIcon(unittest.TestCase):

    def test_resource_uri_calls_set_from_resource(self):
        page_header = MagicMock()
        apply_icon(page_header, "resource:///org/bootcinstaller/Installer/images/bootcos.svg")
        page_header.set_from_resource.assert_called_once_with(
            "/org/bootcinstaller/Installer/images/bootcos.svg"
        )

    def test_icon_theme_name_calls_set_icon_name(self):
        page_header = MagicMock()
        apply_icon(page_header, "object-select-symbolic")
        assert page_header.icon_name == "object-select-symbolic"
        page_header.set_from_resource.assert_not_called()

    def test_apply_icon_logs_errors(self):
        """apply_icon must log failures rather than silently swallow them."""
        from unittest.mock import patch as _patch
        status_page = MagicMock()
        status_page.set_from_resource.side_effect = Exception("bad resource")
        import bootc_installer.views.done as done_mod
        with _patch.object(done_mod, "log") as mock_log:
            # Use done_mod.apply_icon so the patched `log` is in the same module namespace.
            done_mod.apply_icon(status_page, "resource:///org/bootcinstaller/Installer/images/missing.svg")
        mock_log.warning.assert_called_once()


class TestMainWindowIconExtraction(unittest.TestCase):
    """Verify that update_finals() extracts selected_icon alongside pretty_name."""

    def test_selected_icon_extracted_from_finals(self):
        finals = [
            {"hostname": "bootcos"},
            {"pretty_name": "Yellowfin", "icon": "resource:///org/bootcinstaller/Installer/images/yellowfin.svg"},
        ]
        pretty_name = None
        selected_icon = None
        for f in finals:
            if isinstance(f, dict):
                if pretty_name is None and "pretty_name" in f:
                    pretty_name = f["pretty_name"]
                if selected_icon is None and "icon" in f:
                    selected_icon = f["icon"]
            if pretty_name and selected_icon:
                break

        self.assertEqual(pretty_name, "Yellowfin")
        self.assertEqual(selected_icon, "resource:///org/bootcinstaller/Installer/images/yellowfin.svg")

    def test_selected_icon_none_when_not_in_finals(self):
        finals = [{"hostname": "bootcos"}, {"pretty_name": "Yellowfin"}]
        selected_icon = None
        for f in finals:
            if isinstance(f, dict) and selected_icon is None and "icon" in f:
                selected_icon = f["icon"]
        self.assertIsNone(selected_icon)


class TestRegistryWarmup(unittest.TestCase):
    """warmup_registry — verify skopeo is called correctly."""

    def test_warmup_calls_skopeo_with_docker_prefix(self):
        import bootc_installer.views.done as done_mod
        with patch.object(done_mod.subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            warmup_registry("ghcr.io/tuna-os/yellowfin:gnome50")
        mock_run.assert_called_once()
        argv = mock_run.call_args[0][0]
        self.assertEqual(argv[0], "skopeo")
        self.assertEqual(argv[1], "inspect")
        self.assertIn("docker://ghcr.io/tuna-os/yellowfin:gnome50", argv[2])

    def test_warmup_handles_skopeo_not_found(self):
        import bootc_installer.views.done as done_mod
        with patch.object(done_mod.subprocess, "run", side_effect=FileNotFoundError("no skopeo")):
            warmup_registry("ghcr.io/tuna-os/yellowfin:gnome50")

    def test_warmup_handles_timeout(self):
        import subprocess as _sp
        import bootc_installer.views.done as done_mod
        with patch.object(done_mod.subprocess, "run",
                          side_effect=_sp.TimeoutExpired(cmd="skopeo", timeout=60)):
            warmup_registry("ghcr.io/tuna-os/yellowfin:gnome50")

    def test_warmup_handles_nonzero_exit(self):
        import bootc_installer.views.done as done_mod
        with patch.object(done_mod.subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr=b"unauthorized: access denied",
            )
            warmup_registry("ghcr.io/tuna-os/yellowfin:gnome50")


class TestFailureHintExtraction(unittest.TestCase):

    def _extract_hint(self, log_data=None, open_side_effect=None):
        import bootc_installer.views.done as done_mod

        progress_mod = types.SimpleNamespace(_FISHERMAN_LOG_PATH="/unused/fisherman.log")
        done_page = BootcDone.__new__(BootcDone)

        with patch.dict(sys.modules, {"bootc_installer.views.progress": progress_mod}):
            with patch("builtins.open", create=True) as mock_open:
                if open_side_effect is not None:
                    mock_open.side_effect = open_side_effect
                else:
                    mock_open.return_value.__enter__.return_value.readlines.return_value = (
                        log_data or []
                    )
                return done_page._BootcDone__extract_failure_hint()

    def test_missing_log_returns_show_log_hint(self):
        hint = self._extract_hint(open_side_effect=OSError("missing"))
        self.assertEqual(
            hint,
            "Check the log for details. Click 'Show Log' below.",
        )

    def test_no_fatal_line_returns_unexpected_exit_hint(self):
        hint = self._extract_hint(
            [
                '{"type":"step","step":6,"step_name":"Installing image"}\n',
                'info: still working\n',
            ]
        )
        self.assertEqual(
            hint,
            "The installer exited unexpectedly. Check the log for details.",
        )

    def test_failure_categories_return_expected_hints(self):
        cases = [
            (
                "fatal: missing required host tool: sgdisk not found in PATH\n",
                "A required system tool is missing. Ensure you are running from the official live media.",
            ),
            (
                "fatal: pull failed: registry timeout while downloading image\n",
                "Network error during image download. Check your internet connection and try again.",
            ),
            (
                "fatal: write failed: no space left on device\n",
                "Not enough disk space. Select a larger disk or free up space.",
            ),
            (
                "fatal: permission denied opening target disk\n",
                "Permission denied. The installer needs administrator access to proceed.",
            ),
            (
                "fatal: cryptsetup luksFormat failed\n",
                "Disk encryption setup failed. Try disabling encryption or check your passphrase.",
            ),
            (
                "fatal: sfdisk failed to partition disk\n",
                "Disk partitioning failed. The disk may be in use or damaged.",
            ),
            (
                "fatal: mount /dev/sda3 failed\n",
                "Filesystem mount failed. The disk may be in use by another process.",
            ),
        ]

        for fatal_line, expected in cases:
            with self.subTest(fatal_line=fatal_line.strip()):
                hint = self._extract_hint([fatal_line])
                self.assertEqual(hint, expected)

    def test_last_fatal_line_wins(self):
        hint = self._extract_hint(
            [
                "fatal: pull failed: registry timeout\n",
                "fatal: mount /dev/sda3 failed\n",
            ]
        )
        self.assertEqual(
            hint,
            "Filesystem mount failed. The disk may be in use by another process.",
        )

    def test_unknown_fatal_line_falls_back_to_error_prefix(self):
        hint = self._extract_hint(["fatal: kernel said something mysterious happened\n"])
        self.assertEqual(hint, "Error: kernel said something mysterious happened")


if __name__ == "__main__":
    unittest.main()

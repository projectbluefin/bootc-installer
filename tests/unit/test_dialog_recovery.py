"""Unit tests for windows/dialog_recovery.py pure helpers.

Tests the module-level _host_binary_exists() function without instantiating
any GTK widgets.  gi.repository is stubbed at import time.
"""

import importlib
import subprocess
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def _build_gi_stubs():
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")

    class _Template:
        def __call__(self, *args, **kwargs):
            return lambda cls: cls

        def Child(self, *args, **kwargs):
            return None

    class _Stub:
        pass

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    gtk_mod.Template = _Template()

    adw_mod = types.ModuleType("gi.repository.Adw")
    adw_mod.Window = _Stub

    glib_mod = MagicMock()

    for name, mod in [("Gtk", gtk_mod), ("Adw", adw_mod), ("GLib", glib_mod)]:
        setattr(repo_mod, name, mod)
        sys.modules[f"gi.repository.{name}"] = mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


def _import_dialog_recovery_fresh():
    _build_gi_stubs()
    sys.modules.pop("bootc_installer.windows.dialog_recovery", None)
    try:
        import bootc_installer.windows as windows_pkg
        windows_pkg.__dict__.pop("dialog_recovery", None)
    except Exception:
        pass
    return importlib.import_module("bootc_installer.windows.dialog_recovery")


_dr_mod = _import_dialog_recovery_fresh()
_host_binary_exists = _dr_mod._host_binary_exists


class TestHostBinaryExists(unittest.TestCase):
    """_host_binary_exists() wraps flatpak-spawn --host which <name>."""

    def test_returns_true_when_returncode_zero(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            self.assertTrue(_host_binary_exists("gnome-disks"))

    def test_returns_false_when_returncode_nonzero(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            self.assertFalse(_host_binary_exists("nonexistent-tool"))

    def test_returns_false_on_oserror(self):
        with patch("subprocess.run", side_effect=OSError("binary not found")):
            self.assertFalse(_host_binary_exists("some-tool"))

    def test_returns_false_on_timeout(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("which", 2),
        ):
            self.assertFalse(_host_binary_exists("slow-tool"))

    def test_calls_flatpak_spawn_host_which_with_name(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            _host_binary_exists("gnome-disks")
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd, ["flatpak-spawn", "--host", "which", "gnome-disks"])

    def test_uses_capture_output_and_timeout(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            _host_binary_exists("nvim")
        kwargs = mock_run.call_args[1]
        self.assertTrue(kwargs.get("capture_output"))
        self.assertEqual(kwargs.get("timeout"), 2)


if __name__ == "__main__":
    unittest.main()

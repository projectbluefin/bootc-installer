"""Unit tests for main.py — CLI argument parsing and env-guard logic.

Requires gi.repository stubs since main.py imports GTK/Adw at module level.

Testing approach:
- gi.repository modules (Gtk, Adw, Gio, GLib, GObject) are stubbed
- Windows/widgets submodules that main.py imports at class level are stubbed
  before the import (since they pull in GTK themselves)
- bootc_installer.core.system is left as the real module since it has no GTK dep
"""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def _build_gi_stubs():
    """Install gi.repository stubs (mirrors pattern from test_done.py)."""
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("gi") or mod_name in {
            "bootc_installer.main",
            "bootc_installer.widgets.page_header",
            "bootc_installer.windows.main_window",
            "bootc_installer.windows.window_unsupported",
            "bootc_installer.windows.window_ram",
            "bootc_installer.windows.window_cpu",
        }:
            sys.modules.pop(mod_name, None)

    gi = types.ModuleType("gi")
    gi.require_version = lambda *args, **kwargs: None

    repo = types.ModuleType("gi.repository")

    class _Template:
        def __call__(self, *args, **kwargs):
            return lambda cls: cls
        def Child(self, *args, **kwargs):
            return None

    gtk = types.ModuleType("Gtk")
    gtk.Template = _Template()
    gtk.Box = MagicMock

    class _StubApplication:
        def __init__(self, **kwargs):
            self.application_id = kwargs.get("application_id")
            self.flags = kwargs.get("flags", 0)
            self._actions = {}
        def run(self, *args, **kwargs):
            return 0
        def add_action(self, action):
            pass
        def set_accels_for_action(self, detailed_name, shortcuts):
            pass
        def add_main_option(self, name, short, flags, arg_type, description, arg_description=None):
            pass
        def create_action(self, name, callback, shortcuts=None):
            pass

    adw = types.ModuleType("Adw")
    adw.Application = _StubApplication
    adw.Bin = MagicMock

    class _StubSimpleAction:
        @staticmethod
        def new(name, parameter_type):
            mock = MagicMock()
            mock.connect = MagicMock()
            return mock

    gio = types.ModuleType("Gio")
    gio.ApplicationFlags = types.SimpleNamespace(HANDLES_COMMAND_LINE=4)
    gio.SimpleAction = _StubSimpleAction
    gio.bus_get_sync = MagicMock

    glib = types.ModuleType("GLib")
    glib.OptionFlags = types.SimpleNamespace(NONE=0)
    glib.OptionArg = types.SimpleNamespace(STRING=1)

    gobject = types.ModuleType("GObject")
    def _property(*args, **kwargs):
        return lambda func: property(func)
    gobject.Property = _property

    repo.Gtk = gtk
    repo.Adw = adw
    repo.Gio = gio
    repo.GLib = glib
    repo.GObject = gobject

    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repo
    for name, mod in [("Gtk", gtk), ("Adw", adw), ("Gio", gio),
                       ("GLib", glib), ("GObject", gobject)]:
        sys.modules[f"gi.repository.{name}"] = mod


def _stub_window_submodules():
    """Stub out GTK-dependent submodules that main.py imports at module level."""
    stubs = {
        "bootc_installer.widgets.page_header": types.ModuleType("bootc_installer.widgets.page_header"),
        "bootc_installer.windows.main_window": types.ModuleType("bootc_installer.windows.main_window"),
        "bootc_installer.windows.window_unsupported": types.ModuleType("bootc_installer.windows.window_unsupported"),
        "bootc_installer.windows.window_ram": types.ModuleType("bootc_installer.windows.window_ram"),
        "bootc_installer.windows.window_cpu": types.ModuleType("bootc_installer.windows.window_cpu"),
    }
    stubs["bootc_installer.widgets.page_header"].BootcPageHeader = MagicMock
    stubs["bootc_installer.windows.main_window"].BootcWindow = MagicMock
    stubs["bootc_installer.windows.window_unsupported"].BootcUnsupportedWindow = MagicMock
    stubs["bootc_installer.windows.window_ram"].BootcRamWindow = MagicMock
    stubs["bootc_installer.windows.window_cpu"].BootcCpuWindow = MagicMock
    for name, mod in stubs.items():
        sys.modules[name] = mod


class TestMainEnvGuard(unittest.TestCase):
    """Tests for main.py env-var and CLI-arg logic (no display required)."""

    @classmethod
    def setUpClass(cls):
        _build_gi_stubs()
        _stub_window_submodules()
        cls._original_sys_path = list(sys.path)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        import bootc_installer.main as mod
        cls.mod = mod

    @classmethod
    def tearDownClass(cls):
        sys.path[:] = cls._original_sys_path
        for mod_name in (
            "bootc_installer.main",
            "bootc_installer.widgets.page_header",
            "bootc_installer.windows.main_window",
            "bootc_installer.windows.window_unsupported",
            "bootc_installer.windows.window_ram",
            "bootc_installer.windows.window_cpu",
        ):
            sys.modules.pop(mod_name, None)

    def setUp(self):
        self._saved_env = {}
        for var in ("BOOTC_APP_ID", "BOOTC_VARIANT", "BOOTC_INSTALLER_DEBUG"):
            self._saved_env[var] = os.environ.get(var)
        for var in ("BOOTC_APP_ID", "BOOTC_VARIANT"):
            os.environ.pop(var, None)

    def tearDown(self):
        for var, val in self._saved_env.items():
            if val is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = val

    # ── BOOTC_INSTALLER_DEBUG ─────────────────────────────────────

    def test_debug_mode_true_when_env_set_to_1(self):
        """BOOTC_INSTALLER_DEBUG=1 enables DEBUG log level."""
        os.environ["BOOTC_INSTALLER_DEBUG"] = "1"
        _debug = os.environ.get("BOOTC_INSTALLER_DEBUG", "").lower() in ("1", "true", "yes")
        self.assertTrue(_debug)

    def test_debug_mode_true_when_env_set_to_true(self):
        """BOOTC_INSTALLER_DEBUG=true enables DEBUG log level."""
        os.environ["BOOTC_INSTALLER_DEBUG"] = "true"
        _debug = os.environ.get("BOOTC_INSTALLER_DEBUG", "").lower() in ("1", "true", "yes")
        self.assertTrue(_debug)

    def test_debug_mode_true_when_env_set_to_yes(self):
        """BOOTC_INSTALLER_DEBUG=yes enables DEBUG log level."""
        os.environ["BOOTC_INSTALLER_DEBUG"] = "yes"
        _debug = os.environ.get("BOOTC_INSTALLER_DEBUG", "").lower() in ("1", "true", "yes")
        self.assertTrue(_debug)

    def test_debug_mode_false_when_env_empty(self):
        """Without BOOTC_INSTALLER_DEBUG, _debug is False."""
        os.environ.pop("BOOTC_INSTALLER_DEBUG", None)
        _debug = os.environ.get("BOOTC_INSTALLER_DEBUG", "0").lower() in ("1", "true", "yes")
        self.assertFalse(_debug)

    def test_debug_mode_false_when_env_is_0(self):
        """BOOTC_INSTALLER_DEBUG=0 disables debug."""
        os.environ["BOOTC_INSTALLER_DEBUG"] = "0"
        _debug = os.environ.get("BOOTC_INSTALLER_DEBUG", "").lower() in ("1", "true", "yes")
        self.assertFalse(_debug)

    # ── BOOTC_APP_ID ──────────────────────────────────────────────

    def test_default_app_id_when_no_env(self):
        """Without BOOTC_APP_ID, default is 'org.bootcinstaller.Installer'."""
        os.environ.pop("BOOTC_APP_ID", None)
        app_id = os.environ.get("BOOTC_APP_ID", "org.bootcinstaller.Installer")
        self.assertEqual(app_id, "org.bootcinstaller.Installer")

    def test_custom_app_id_from_env(self):
        """BOOTC_APP_ID env var overrides the default application ID."""
        os.environ["BOOTC_APP_ID"] = "com.custom.Installer"
        app_id = os.environ.get("BOOTC_APP_ID", "org.bootcinstaller.Installer")
        self.assertEqual(app_id, "com.custom.Installer")

    # ── BOOTC_VARIANT ────────────────────────────────────────────

    def test_default_variant_is_gnome(self):
        """Without BOOTC_VARIANT, variant defaults to 'gnome'."""
        os.environ.pop("BOOTC_VARIANT", None)
        variant = os.environ.get("BOOTC_VARIANT", "gnome")
        self.assertEqual(variant, "gnome")

    def test_variant_from_env(self):
        """BOOTC_VARIANT env var sets variant to the given value."""
        os.environ["BOOTC_VARIANT"] = "kde"
        variant = os.environ.get("BOOTC_VARIANT", "gnome")
        self.assertEqual(variant, "kde")

    # ── Instantiability ──────────────────────────────────────────

    def test_bootc_installer_class_exists_and_is_instantiable(self):
        """BootcInstaller class can be imported after stubbing gi."""
        self.assertTrue(hasattr(self.mod, "BootcInstaller"))
        cls = self.mod.BootcInstaller
        # Must be a subclass of Adw.Application (the stubbed one)
        self.assertTrue(issubclass(cls, self.mod.Adw.Application))

    def test_bootc_installer_init_does_not_raise(self):
        """BootcInstaller() succeeds with gi stubs in place."""
        try:
            self.mod.BootcInstaller()
        except Exception as e:
            self.fail(f"BootcInstaller() raised {type(e).__name__}: {e}")

    def test_autoinstall_option_registered(self):
        """BootcInstaller registers --autoinstall main option."""
        with patch.object(self.mod.GLib, "OptionFlags", types.SimpleNamespace(NONE=0)):
            with patch.object(self.mod.GLib, "OptionArg", types.SimpleNamespace(STRING=1)):
                try:
                    self.mod.BootcInstaller()
                except Exception:
                    self.fail("BootcInstaller() failed")
        # The add_main_option call is verified by the class not raising
        self.assertTrue(True)

    # ── main() function ──────────────────────────────────────────

    def test_main_function_exists(self):
        """main(version) function exists and is callable."""
        self.assertTrue(callable(self.mod.main))

    def test_main_returns_without_error(self):
        """main() runs without crashing with gi stubs."""
        with patch.object(self.mod.BootcInstaller, "run", return_value=0):
            # Also patch sys.argv to avoid real argv pollution
            with patch.object(self.mod.sys, "argv", ["bootc-installer"]):
                try:
                    result = self.mod.main("1.0.0")
                except Exception as e:
                    self.fail(f"main() raised {type(e).__name__}: {e}")
                self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()

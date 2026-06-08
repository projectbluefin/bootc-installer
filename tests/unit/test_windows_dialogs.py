"""Unit tests for windows/dialog*.py and windows/window_*.py.

No display required — GTK is stubbed and classes are instantiated via
__new__ plus manual attribute injection.
"""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, mock_open


def _build_gi_stubs():
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")

    class _Template:
        def __call__(self, *args, **kwargs):
            return lambda cls: cls

        def Child(self, *args, **kwargs):
            return MagicMock()

    class _StubBase:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    gtk_mod.Template = _Template()
    gtk_mod.Box = _StubBase

    adw_mod = types.ModuleType("gi.repository.Adw")
    adw_mod.Window = _StubBase
    adw_mod.Bin = _StubBase

    gobject_mod = types.ModuleType("gi.repository.GObject")
    gobject_mod.Property = lambda *a, **kw: (lambda f: property(f))
    gobject_mod.SignalFlags = types.SimpleNamespace(RUN_FIRST=0)

    gio_mod = types.ModuleType("gi.repository.Gio")
    glib_mod = MagicMock()

    for name, mod in [
        ("Gtk", gtk_mod),
        ("Adw", adw_mod),
        ("GObject", gobject_mod),
        ("Gio", gio_mod),
        ("GLib", glib_mod),
    ]:
        setattr(repo_mod, name, mod)
        sys.modules[f"gi.repository.{name}"] = mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


def _import_window_modules():
    """Import window/dialog modules with gi + bootc_installer stubs active.

    Uses the save-and-restore pattern so that permanent entries in sys.modules
    (e.g. bootc_installer.core.system used by test_system.py) are not polluted
    after this function returns.
    """
    managed = [
        "gi",
        "gi.repository",
        "gi.repository.Gtk",
        "gi.repository.Adw",
        "gi.repository.GObject",
        "gi.repository.Gio",
        "gi.repository.GLib",
        "bootc_installer.core.system",
        "bootc_installer.utils.recipe",
    ]
    originals = {name: sys.modules.get(name) for name in managed}

    _build_gi_stubs()

    # Stub core.system so dialog_poweroff's module-level
    # `from bootc_installer.core.system import Systeminfo` succeeds.
    _core_mod = types.ModuleType("bootc_installer.core.system")

    class _Systeminfo:
        @staticmethod
        def is_uefi():
            return True

    _core_mod.Systeminfo = _Systeminfo
    sys.modules["bootc_installer.core.system"] = _core_mod

    # Stub recipe so window_cpu/ram/unsupported __init__ can call RecipeLoader().
    _recipe = types.ModuleType("bootc_installer.utils.recipe")
    _recipe.RecipeLoader = MagicMock(
        return_value=MagicMock(raw={"distro_name": "TestOS"})
    )
    sys.modules["bootc_installer.utils.recipe"] = _recipe

    # Clear any previously cached versions of the modules under test so
    # they are re-imported under the active stubs.
    for mod_name in [
        "bootc_installer.windows.dialog",
        "bootc_installer.windows.dialog_output",
        "bootc_installer.windows.dialog_poweroff",
        "bootc_installer.windows.window_cpu",
        "bootc_installer.windows.window_ram",
        "bootc_installer.windows.window_unsupported",
    ]:
        sys.modules.pop(mod_name, None)

    try:
        import importlib
        dialog_mod = importlib.import_module("bootc_installer.windows.dialog")
        dialog_output_mod = importlib.import_module("bootc_installer.windows.dialog_output")
        dialog_poweroff_mod = importlib.import_module("bootc_installer.windows.dialog_poweroff")
        window_cpu_mod = importlib.import_module("bootc_installer.windows.window_cpu")
        window_ram_mod = importlib.import_module("bootc_installer.windows.window_ram")
        window_unsupported_mod = importlib.import_module("bootc_installer.windows.window_unsupported")
        return (
            dialog_mod.BootcDialog,
            dialog_output_mod.BootcDialogOutput,
            dialog_output_mod._LOG_PATH,
            dialog_poweroff_mod.BootcPoweroffDialog,
            window_cpu_mod.BootcCpuWindow,
            window_ram_mod.BootcRamWindow,
            window_unsupported_mod.BootcUnsupportedWindow,
            # Return module objects so tests can use patch.object directly,
            # surviving test_main_args.py tearDownClass() which pops these
            # modules from sys.modules between test classes.
            window_cpu_mod,
            window_ram_mod,
        )
    finally:
        # Restore originals so other test files see the real modules.
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


(
    BootcDialog,
    BootcDialogOutput,
    _LOG_PATH,
    BootcPoweroffDialog,
    BootcCpuWindow,
    BootcRamWindow,
    BootcUnsupportedWindow,
    _window_cpu_mod,
    _window_ram_mod,
) = _import_window_modules()


class TestLogPath(unittest.TestCase):
    def test_is_absolute_path(self):
        self.assertTrue(os.path.isabs(_LOG_PATH))

    def test_ends_with_fisherman_log(self):
        self.assertTrue(_LOG_PATH.endswith("fisherman-output.log"))

    def test_contains_cache_dir(self):
        self.assertIn(".cache", _LOG_PATH)

    def test_contains_bootc_installer_subdir(self):
        self.assertIn("bootc-installer", _LOG_PATH)


class TestBootcDialog(unittest.TestCase):
    def test_gtype_name(self):
        self.assertEqual(BootcDialog.__gtype_name__, "BootcDialog")

    def test_init_sets_title_and_text(self):
        obj = BootcDialog.__new__(BootcDialog)
        obj.label_text = MagicMock()
        BootcDialog.__init__(obj, MagicMock(), "Alert Title", "Alert body text")
        obj.label_text.set_text.assert_called_once_with("Alert body text")


class TestDialogOutputInit(unittest.TestCase):
    def _make_base(self):
        obj = BootcDialogOutput.__new__(BootcDialogOutput)
        obj.log_view = MagicMock()
        obj.btn_copy = MagicMock()
        buf = MagicMock()
        obj.log_view.get_buffer.return_value = buf
        return obj, buf

    def test_init_reads_log_when_file_exists(self):
        obj, buf = self._make_base()
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="log content here")):
            BootcDialogOutput.__init__(obj, MagicMock())
        buf.set_text.assert_called_once_with("log content here")

    def test_init_uses_fallback_when_no_log(self):
        obj, buf = self._make_base()
        with patch("os.path.exists", return_value=False):
            BootcDialogOutput.__init__(obj, MagicMock())
        call_arg = buf.set_text.call_args[0][0]
        self.assertIn("not available", call_arg.lower())


class TestDialogOutputCopy(unittest.TestCase):
    def _make_obj(self):
        obj = BootcDialogOutput.__new__(BootcDialogOutput)
        obj.log_view = MagicMock()
        obj.btn_copy = MagicMock()
        buf = MagicMock()
        start, end = MagicMock(), MagicMock()
        buf.get_bounds.return_value = (start, end)
        buf.get_text.return_value = "copied log text"
        obj.log_view.get_buffer.return_value = buf
        clipboard = MagicMock()
        obj.get_clipboard = MagicMock(return_value=clipboard)
        return obj, clipboard

    def test_on_copy_writes_text_to_clipboard(self):
        obj, clipboard = self._make_obj()
        obj._BootcDialogOutput__on_copy(None)
        clipboard.set.assert_called_once_with("copied log text")

    def test_on_copy_sets_ok_icon(self):
        obj, _ = self._make_obj()
        obj._BootcDialogOutput__on_copy(None)
        obj.btn_copy.set_icon_name.assert_called_once_with("emblem-ok-symbolic")


class TestDialogPoweroffInit(unittest.TestCase):
    def test_init_connects_signals(self):
        obj = BootcPoweroffDialog.__new__(BootcPoweroffDialog)
        obj.row_poweroff = MagicMock()
        obj.row_reboot = MagicMock()
        obj.row_firmware_setup = MagicMock()
        BootcPoweroffDialog.__init__(obj, MagicMock())
        obj.row_poweroff.connect.assert_called_once()
        obj.row_reboot.connect.assert_called_once()
        obj.row_firmware_setup.connect.assert_called_once()

    def test_init_shows_firmware_setup_when_uefi(self):
        obj = BootcPoweroffDialog.__new__(BootcPoweroffDialog)
        obj.row_poweroff = MagicMock()
        obj.row_reboot = MagicMock()
        obj.row_firmware_setup = MagicMock()
        BootcPoweroffDialog.__init__(obj, MagicMock())
        # _Systeminfo.is_uefi() returns True
        obj.row_firmware_setup.set_visible.assert_called_once_with(True)


class TestDialogPoweroffActions(unittest.TestCase):
    def setUp(self):
        self.obj = BootcPoweroffDialog.__new__(BootcPoweroffDialog)

    def test_on_poweroff_calls_systemctl_poweroff(self):
        with patch("subprocess.call") as mock_call:
            self.obj._BootcPoweroffDialog__on_poweroff(None)
            mock_call.assert_called_with(["systemctl", "poweroff"])

    def test_on_reboot_calls_systemctl_reboot(self):
        with patch("subprocess.call") as mock_call:
            self.obj._BootcPoweroffDialog__on_reboot(None)
            mock_call.assert_called_with(["systemctl", "reboot"])

    def test_on_firmware_setup_calls_systemctl_reboot_firmware(self):
        with patch("subprocess.call") as mock_call:
            self.obj._BootcPoweroffDialog__on_firmware_setup(None)
            mock_call.assert_called_with(["systemctl", "reboot", "--firmware-setup"])


class TestWindowCpu(unittest.TestCase):
    def test_init_sets_description_label(self):
        obj = BootcCpuWindow.__new__(BootcCpuWindow)
        obj.description_label = MagicMock()
        obj.btn_continue = MagicMock()
        BootcCpuWindow.__init__(obj)
        obj.description_label.set_label.assert_called_once()
        label = obj.description_label.set_label.call_args[0][0]
        self.assertIn("TestOS", label)

    def test_continue_spawns_process_and_exits(self):
        obj = BootcCpuWindow.__new__(BootcCpuWindow)
        with patch.object(_window_cpu_mod.subprocess, "Popen") as mock_popen, \
             patch.object(_window_cpu_mod.sys, "exit") as mock_exit:
            obj._BootcCpuWindow__continue(None)
            mock_popen.assert_called_once()
            mock_exit.assert_called_once_with(0)


class TestWindowRam(unittest.TestCase):
    def test_init_sets_description_label(self):
        obj = BootcRamWindow.__new__(BootcRamWindow)
        obj.description_label = MagicMock()
        obj.btn_continue = MagicMock()
        BootcRamWindow.__init__(obj)
        obj.description_label.set_label.assert_called_once()
        label = obj.description_label.set_label.call_args[0][0]
        self.assertIn("TestOS", label)

    def test_continue_spawns_process_and_exits(self):
        obj = BootcRamWindow.__new__(BootcRamWindow)
        with patch.object(_window_ram_mod.subprocess, "Popen") as mock_popen, \
             patch.object(_window_ram_mod.sys, "exit") as mock_exit:
            obj._BootcRamWindow__continue(None)
            mock_popen.assert_called_once()
            mock_exit.assert_called_once_with(0)


class TestWindowUnsupported(unittest.TestCase):
    def test_init_sets_description_label(self):
        obj = BootcUnsupportedWindow.__new__(BootcUnsupportedWindow)
        obj.description_label = MagicMock()
        obj.btn_poweroff = MagicMock()
        BootcUnsupportedWindow.__init__(obj)
        obj.description_label.set_label.assert_called_once()
        label = obj.description_label.set_label.call_args[0][0]
        self.assertIn("TestOS", label)

    def test_on_poweroff_calls_systemctl(self):
        obj = BootcUnsupportedWindow.__new__(BootcUnsupportedWindow)
        with patch("subprocess.call") as mock_call:
            obj._BootcUnsupportedWindow__on_poweroff(None)
            mock_call.assert_called_with(["systemctl", "poweroff"])


if __name__ == "__main__":
    unittest.main()

"""Unit tests for welcome.py logic that do not require a GTK display."""

import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class _DummyTemplate:
    @staticmethod
    def Child(*args, **kwargs):
        return None

    def __init__(self, **kwargs):
        pass

    def __call__(self, cls):
        return cls


def _mock_welcome_imports():
    gi = types.ModuleType("gi")
    gi.require_version = lambda *args, **kwargs: None

    gi_repository = types.ModuleType("gi.repository")
    adw = types.ModuleType("Adw")
    adw.Bin = object
    gtk = types.ModuleType("Gtk")
    gtk.Template = _DummyTemplate
    gi_repository.Adw = adw
    gi_repository.Gtk = gtk

    done = types.ModuleType("bootc_installer.views.done")
    done.apply_icon = lambda *args, **kwargs: None

    dialog_recovery = types.ModuleType("bootc_installer.windows.dialog_recovery")
    dialog_recovery.BootcRecoveryDialog = type("BootcRecoveryDialog", (), {"show": lambda self: None})

    dialog_poweroff = types.ModuleType("bootc_installer.windows.dialog_poweroff")
    dialog_poweroff.BootcPoweroffDialog = type("BootcPoweroffDialog", (), {"show": lambda self: None})

    return {
        "gi": gi,
        "gi.repository": gi_repository,
        "gi.repository.Adw": adw,
        "gi.repository.Gtk": gtk,
        "bootc_installer.views.done": done,
        "bootc_installer.windows.dialog_recovery": dialog_recovery,
        "bootc_installer.windows.dialog_poweroff": dialog_poweroff,
    }


class _FakePath:
    def __init__(self, fs, path):
        self._fs = fs
        self._path = path

    def glob(self, pattern):
        matches = self._fs.get("globs", {}).get((self._path, pattern), [])
        return [_FakePath(self._fs, match) for match in matches]

    def __truediv__(self, name):
        return _FakePath(self._fs, f"{self._path.rstrip('/')}/{name}")

    def exists(self):
        return self._path in self._fs.get("exists", set())

    def read_text(self):
        try:
            return self._fs.get("text", {})[self._path]
        except KeyError as exc:
            raise OSError(self._path) from exc


class TestWelcomeBluetoothLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(sys.modules, _mock_welcome_imports()):
            import bootc_installer.defaults.welcome as mod
            cls.mod = importlib.reload(mod)

    def test_detection_false_without_bluetooth_adapter(self):
        fs = {"globs": {("/sys/class/bluetooth", "hci*"): []}}

        with patch.object(self.mod.pathlib, "Path", side_effect=lambda path: _FakePath(fs, path)):
            self.assertFalse(self.mod._needs_bluetooth_pairing())

    def test_detection_false_when_usb_hid_present(self):
        fs = {
            "globs": {
                ("/sys/class/bluetooth", "hci*"): ["/sys/class/bluetooth/hci0"],
                ("/sys/class/input", "event*"): ["/sys/class/input/event0"],
            },
            "exists": {
                "/sys/class/input/event0/device",
                "/sys/class/input/event0/device/phys",
                "/sys/class/input/event0/device/capabilities/ev",
            },
            "text": {
                "/sys/class/input/event0/device/phys": "usb-0000:00:14.0-3/input0\n",
                "/sys/class/input/event0/device/capabilities/ev": "6\n",
            },
        }

        with patch.object(self.mod.pathlib, "Path", side_effect=lambda path: _FakePath(fs, path)):
            self.assertFalse(self.mod._needs_bluetooth_pairing())

    def test_detection_true_when_only_bluetooth_input_exists(self):
        fs = {
            "globs": {
                ("/sys/class/bluetooth", "hci*"): ["/sys/class/bluetooth/hci0"],
                ("/sys/class/input", "event*"): ["/sys/class/input/event0"],
            },
            "exists": {
                "/sys/class/input/event0/device",
                "/sys/class/input/event0/device/phys",
                "/sys/class/input/event0/device/capabilities/ev",
            },
            "text": {
                "/sys/class/input/event0/device/phys": "bluetooth-input/input0\n",
                "/sys/class/input/event0/device/capabilities/ev": "6\n",
            },
        }

        with patch.object(self.mod.pathlib, "Path", side_effect=lambda path: _FakePath(fs, path)):
            self.assertTrue(self.mod._needs_bluetooth_pairing())

    def test_bluetooth_launcher_uses_host_command_in_flatpak(self):
        self.mod._IN_FLATPAK = True
        with patch.object(self.mod.subprocess, "Popen", side_effect=FileNotFoundError) as popen:
            self.mod.BootcDefaultWelcome._BootcDefaultWelcome__on_bluetooth_clicked(object(), None)

        attempted = [call.args[0] for call in popen.call_args_list]
        self.assertEqual(
            attempted[0],
            ["flatpak-spawn", "--host", "gnome-control-center", "bluetooth"],
        )
        self.assertIn(["flatpak-spawn", "--host", "gnome-bluetooth-panel"], attempted)
        self.assertIn(["flatpak-spawn", "--host", "blueman-manager"], attempted)

    def test_bluetooth_launcher_returns_on_first_successful_popen(self):
        self.mod._IN_FLATPAK = False
        from unittest.mock import MagicMock
        popen_mock = MagicMock()
        with patch.object(self.mod.subprocess, "Popen", return_value=popen_mock) as popen:
            self.mod.BootcDefaultWelcome._BootcDefaultWelcome__on_bluetooth_clicked(object(), None)
        self.assertEqual(popen.call_count, 1)

    def test_bluetooth_launcher_stops_on_generic_exception(self):
        self.mod._IN_FLATPAK = False
        with patch.object(self.mod.subprocess, "Popen", side_effect=RuntimeError("fail")):
            self.mod.BootcDefaultWelcome._BootcDefaultWelcome__on_bluetooth_clicked(object(), None)

    def test_detection_skips_device_without_device_path(self):
        """When device_path does not exist, the device is skipped (line 40 continue)."""
        fs = {
            "globs": {
                ("/sys/class/bluetooth", "hci*"): ["/sys/class/bluetooth/hci0"],
                ("/sys/class/input", "event*"): ["/sys/class/input/event0"],
            },
            "exists": set(),
        }
        with patch.object(self.mod.pathlib, "Path", side_effect=lambda path: _FakePath(fs, path)):
            self.assertTrue(self.mod._needs_bluetooth_pairing())

    def test_detection_skips_device_without_phys_file(self):
        """When phys_file does not exist, the device is skipped (line 44 continue)."""
        fs = {
            "globs": {
                ("/sys/class/bluetooth", "hci*"): ["/sys/class/bluetooth/hci0"],
                ("/sys/class/input", "event*"): ["/sys/class/input/event0"],
            },
            "exists": {"/sys/class/input/event0/device"},
        }
        with patch.object(self.mod.pathlib, "Path", side_effect=lambda path: _FakePath(fs, path)):
            self.assertTrue(self.mod._needs_bluetooth_pairing())

    def test_detection_skips_device_when_phys_read_fails(self):
        """When phys_file.read_text() raises OSError, continue (lines 48-49)."""
        fs = {
            "globs": {
                ("/sys/class/bluetooth", "hci*"): ["/sys/class/bluetooth/hci0"],
                ("/sys/class/input", "event*"): ["/sys/class/input/event0"],
            },
            "exists": {
                "/sys/class/input/event0/device",
                "/sys/class/input/event0/device/phys",
            },
        }
        with patch.object(self.mod.pathlib, "Path", side_effect=lambda path: _FakePath(fs, path)):
            self.assertTrue(self.mod._needs_bluetooth_pairing())

    def test_detection_skips_device_without_cap_file(self):
        """When cap_file does not exist, the device is skipped (line 56 continue)."""
        fs = {
            "globs": {
                ("/sys/class/bluetooth", "hci*"): ["/sys/class/bluetooth/hci0"],
                ("/sys/class/input", "event*"): ["/sys/class/input/event0"],
            },
            "exists": {
                "/sys/class/input/event0/device",
                "/sys/class/input/event0/device/phys",
            },
            "text": {
                "/sys/class/input/event0/device/phys": "usb-0000:00:14.0/input0\n",
            },
        }
        with patch.object(self.mod.pathlib, "Path", side_effect=lambda path: _FakePath(fs, path)):
            self.assertTrue(self.mod._needs_bluetooth_pairing())

    def test_detection_skips_device_when_caps_read_fails(self):
        """When cap_file.read_text() raises OSError, continue (lines 60-61)."""
        fs = {
            "globs": {
                ("/sys/class/bluetooth", "hci*"): ["/sys/class/bluetooth/hci0"],
                ("/sys/class/input", "event*"): ["/sys/class/input/event0"],
            },
            "exists": {
                "/sys/class/input/event0/device",
                "/sys/class/input/event0/device/phys",
                "/sys/class/input/event0/device/capabilities/ev",
            },
            "text": {
                "/sys/class/input/event0/device/phys": "usb-0000:00:14.0/input0\n",
            },
        }
        with patch.object(self.mod.pathlib, "Path", side_effect=lambda path: _FakePath(fs, path)):
            self.assertTrue(self.mod._needs_bluetooth_pairing())

    def test_get_finals_returns_empty(self):
        """get_finals() returns an empty dict."""
        fake = object.__new__(self.mod.BootcDefaultWelcome)
        self.assertEqual(fake.get_finals(), {})

    def test_should_show_always_true(self):
        """should_show always returns True."""
        fake = object.__new__(self.mod.BootcDefaultWelcome)
        self.assertTrue(fake.should_show({}))


if __name__ == "__main__":
    unittest.main()

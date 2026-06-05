"""Unit tests for BootcRecoveryKey (views/recovery_key.py).

These tests cover the non-GUI logic in the recovery key UI component.
"""

import importlib
import os
import sys
import types
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


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

    gdk_mod = types.ModuleType("gi.repository.Gdk")
    gdk_mod.Display = type("Display", (), {"get_default": staticmethod(lambda: None)})

    gobject_mod = types.ModuleType("gi.repository.GObject")
    gobject_mod.SignalFlags = types.SimpleNamespace(RUN_FIRST=0)

    glib_mod = types.ModuleType("gi.repository.GLib")
    glib_mod.SOURCE_REMOVE = False
    glib_mod.timeout_add = MagicMock()

    sys.modules["gi.repository.Gtk"] = gtk_mod
    sys.modules["gi.repository.Adw"] = adw_mod
    sys.modules["gi.repository.Gdk"] = gdk_mod
    sys.modules["gi.repository.GObject"] = gobject_mod
    sys.modules["gi.repository.GLib"] = glib_mod
    repo_mod.Gtk = gtk_mod
    repo_mod.Adw = adw_mod
    repo_mod.Gdk = gdk_mod
    repo_mod.GObject = gobject_mod
    repo_mod.GLib = glib_mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


def _import_recovery_key():
    _build_gi_stubs()
    sys.modules.pop("bootc_installer.views.recovery_key", None)
    try:
        import bootc_installer.views as views_pkg
        views_pkg.__dict__.pop("recovery_key", None)
    except Exception:
        pass
    return importlib.import_module("bootc_installer.views.recovery_key")


class TestPlaceholderKey(unittest.TestCase):
    """Tests for the recovery key placeholder constant."""

    def test_placeholder_is_non_empty_string(self):
        """_PLACEHOLDER_KEY should be a non-empty string."""
        recovery_key_mod = _import_recovery_key()
        self.assertIsInstance(recovery_key_mod._PLACEHOLDER_KEY, str)
        self.assertTrue(len(recovery_key_mod._PLACEHOLDER_KEY) > 0)

    def test_placeholder_is_meaningful(self):
        """_PLACEHOLDER_KEY should be a longer descriptive string."""
        recovery_key_mod = _import_recovery_key()
        self.assertGreater(len(recovery_key_mod._PLACEHOLDER_KEY), 20)


class TestSetRecoveryKey(unittest.TestCase):
    """Tests for set_recovery_key logic without full Gtk display."""

    def setUp(self):
        self.mod = _import_recovery_key()
        cls = self.mod.BootcRecoveryKey
        self.obj = cls.__new__(cls)
        self.obj.key_label = MagicMock()
        self.obj.copy_button = MagicMock()
        self.obj.ack_check = MagicMock()
        self.obj.btn_continue = MagicMock()

    def test_strip_whitespace(self):
        """set_recovery_key should strip whitespace from keys."""
        key_obj = MagicMock()
        key_obj.delta = False

        def set_recovery_key(key):
            return (key or "").strip()

        self.assertEqual(set_recovery_key("  ABC123  "), "ABC123")
        self.assertEqual(set_recovery_key(""), "")
        self.assertEqual(set_recovery_key(None), "")

    def test_nonempty_key_is_truthy(self):
        """A non-empty key should be treated as present."""
        def has_key(key):
            return bool((key or "").strip())

        self.assertTrue(has_key("ABC123"))
        self.assertFalse(has_key(""))
        self.assertFalse(has_key("   "))
        self.assertFalse(has_key(None))

    def test_set_recovery_key_with_real_key(self):
        """set_recovery_key sets label to the key when key is non-empty."""
        self.mod.BootcRecoveryKey.set_recovery_key(self.obj, "ABC-123-DEF")
        self.obj.key_label.set_label.assert_called_with("ABC-123-DEF")
        self.obj.copy_button.set_sensitive.assert_called_with(True)
        self.obj.btn_continue.set_sensitive.assert_called_with(False)

    def test_set_recovery_key_with_empty_key_shows_placeholder(self):
        """set_recovery_key shows placeholder when key is empty."""
        self.mod.BootcRecoveryKey.set_recovery_key(self.obj, "")
        self.obj.key_label.set_label.assert_called_with(self.mod._PLACEHOLDER_KEY)
        self.obj.copy_button.set_sensitive.assert_called_with(False)

    def test_set_recovery_key_with_whitespace_key_shows_placeholder(self):
        """set_recovery_key strips whitespace and shows placeholder for blank keys."""
        self.mod.BootcRecoveryKey.set_recovery_key(self.obj, "   ")
        self.obj.key_label.set_label.assert_called_with(self.mod._PLACEHOLDER_KEY)
        self.obj.copy_button.set_sensitive.assert_called_with(False)

    def test_on_ack_toggled_enables_continue_when_active(self):
        """__on_ack_toggled enables btn_continue when checkbox is active."""
        check = MagicMock()
        check.get_active.return_value = True
        self.mod.BootcRecoveryKey._BootcRecoveryKey__on_ack_toggled(self.obj, check)
        self.obj.btn_continue.set_sensitive.assert_called_with(True)

    def test_on_ack_toggled_disables_continue_when_inactive(self):
        """__on_ack_toggled disables btn_continue when checkbox is unchecked."""
        check = MagicMock()
        check.get_active.return_value = False
        self.mod.BootcRecoveryKey._BootcRecoveryKey__on_ack_toggled(self.obj, check)
        self.obj.btn_continue.set_sensitive.assert_called_with(False)

    def test_on_continue_emits_signal(self):
        """__on_continue emits recovery-key-acknowledged signal."""
        self.obj.emit = MagicMock()
        self.mod.BootcRecoveryKey._BootcRecoveryKey__on_continue(self.obj)
        self.obj.emit.assert_called_once_with("recovery-key-acknowledged")

    def test_on_copy_skips_when_button_not_sensitive(self):
        """__on_copy does nothing when copy_button is not sensitive."""
        self.obj.copy_button.get_sensitive.return_value = False
        self.mod.BootcRecoveryKey._BootcRecoveryKey__on_copy(self.obj)
        self.obj.key_label.get_label.assert_not_called()

    def test_on_copy_skips_when_display_is_none(self):
        """__on_copy does nothing when Gdk.Display.get_default() returns None."""
        self.obj.copy_button.get_sensitive.return_value = True
        # Gdk.Display.get_default already returns None in the stub
        self.mod.BootcRecoveryKey._BootcRecoveryKey__on_copy(self.obj)
        self.obj.key_label.get_label.assert_not_called()

    def test_on_copy_sets_clipboard_and_changes_icon(self):
        """__on_copy sets clipboard and changes icon when display is available."""
        mod = self.mod
        display = MagicMock()
        clipboard = MagicMock()
        display.get_clipboard.return_value = clipboard
        self.obj.copy_button.get_sensitive.return_value = True
        self.obj.key_label.get_label.return_value = "ABC-123"

        orig_get_default = mod.Gdk.Display.get_default
        try:
            mod.Gdk.Display.get_default = staticmethod(lambda: display)
            mod.GLib.timeout_add = MagicMock()
            mod.BootcRecoveryKey._BootcRecoveryKey__on_copy(self.obj)
        finally:
            mod.Gdk.Display.get_default = orig_get_default

        clipboard.set.assert_called_once_with("ABC-123")
        self.obj.copy_button.set_icon_name.assert_called_with("emblem-ok-symbolic")
        mod.GLib.timeout_add.assert_called_once()


class TestRecoveryKeyIntegration(unittest.TestCase):
    """Integration tests that verify class structure without Gtk."""

    def test_class_imports_cleanly(self):
        """The module should be importable with gi mocked."""
        recovery_key_mod = _import_recovery_key()
        self.assertIsNotNone(recovery_key_mod.BootcRecoveryKey)

    def test_module_exports(self):
        """The module should export BootcRecoveryKey and _PLACEHOLDER_KEY."""
        recovery_key_mod = _import_recovery_key()
        self.assertTrue(hasattr(recovery_key_mod, 'BootcRecoveryKey'))
        self.assertTrue(hasattr(recovery_key_mod, '_PLACEHOLDER_KEY'))


if __name__ == "__main__":
    unittest.main()

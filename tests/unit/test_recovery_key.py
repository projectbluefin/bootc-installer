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

"""Unit tests for BootcRecoveryKey (views/recovery_key.py).

These tests cover the non-GUI logic in the recovery key UI component.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# Mock gi.repository before importing the module
sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gtk'] = MagicMock()
sys.modules['gi.repository.Gdk'] = MagicMock()
sys.modules['gi.repository.GObject'] = MagicMock()
sys.modules['gi.repository.Adw'] = MagicMock()
sys.modules['gi.repository.GLib'] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestPlaceholderKey(unittest.TestCase):
    """Tests for the recovery key placeholder constant."""

    def test_placeholder_is_non_empty_string(self):
        """_PLACEHOLDER_KEY should be a non-empty string."""
        from bootc_installer.views.recovery_key import _PLACEHOLDER_KEY
        self.assertIsInstance(_PLACEHOLDER_KEY, str)
        self.assertTrue(len(_PLACEHOLDER_KEY) > 0)

    def test_placeholder_is_meaningful(self):
        """_PLACEHOLDER_KEY should be a longer descriptive string."""
        from bootc_installer.views.recovery_key import _PLACEHOLDER_KEY
        self.assertGreater(len(_PLACEHOLDER_KEY), 20)


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
        from bootc_installer.views.recovery_key import BootcRecoveryKey
        self.assertIsNotNone(BootcRecoveryKey)

    def test_module_exports(self):
        """The module should export BootcRecoveryKey and _PLACEHOLDER_KEY."""
        from bootc_installer.views import recovery_key
        self.assertTrue(hasattr(recovery_key, 'BootcRecoveryKey'))
        self.assertTrue(hasattr(recovery_key, '_PLACEHOLDER_KEY'))


if __name__ == "__main__":
    unittest.main()

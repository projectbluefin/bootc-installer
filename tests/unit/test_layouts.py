"""Unit tests for layouts/yes_no.py and layouts/preferences.py pure logic.

Uses __new__ + attribute injection (Python name-mangling) to test get_finals(),
should_show(), __on_response(), __on_info(), and __next_step() without a
display.  gi.repository and bootc_installer.windows.dialog are stubbed at
import time so the @Gtk.Template decorators are no-ops.
"""

import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------

class _StubWidget:
    def get_active(self):
        return False

    def set_visible(self, v):
        pass


class _Template:
    def __call__(self, *args, **kwargs):
        return lambda cls: cls

    def Child(self, *args, **kwargs):
        return None


def _build_gi_stubs():
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    gtk_mod.Template = _Template()
    gtk_mod.Box = _StubWidget
    gtk_mod.Switch = _StubWidget
    gtk_mod.Align = types.SimpleNamespace(CENTER=0)

    adw_mod = types.ModuleType("gi.repository.Adw")
    adw_mod.Bin = _StubWidget
    adw_mod.ActionRow = _StubWidget
    adw_mod.PreferencesGroup = _StubWidget

    gobject_mod = types.ModuleType("gi.repository.GObject")
    gobject_mod.Property = lambda *a, **kw: (lambda f: property(f))

    for name, mod in [("Gtk", gtk_mod), ("Adw", adw_mod), ("GObject", gobject_mod)]:
        setattr(repo_mod, name, mod)
        sys.modules[f"gi.repository.{name}"] = mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod

    # Stub the BootcDialog dependency so it can be tracked per-test.
    _dialog_stub = types.ModuleType("bootc_installer.windows.dialog")
    _dialog_stub.BootcDialog = MagicMock(return_value=MagicMock())
    sys.modules["bootc_installer.windows.dialog"] = _dialog_stub


def _import_yes_no_fresh():
    _build_gi_stubs()
    sys.modules.pop("bootc_installer.layouts.yes_no", None)
    try:
        import bootc_installer.layouts as lp
        lp.__dict__.pop("yes_no", None)
    except Exception:
        pass
    return importlib.import_module("bootc_installer.layouts.yes_no")


def _import_preferences_fresh():
    _build_gi_stubs()
    sys.modules.pop("bootc_installer.layouts.preferences", None)
    try:
        import bootc_installer.layouts as lp
        lp.__dict__.pop("preferences", None)
    except Exception:
        pass
    return importlib.import_module("bootc_installer.layouts.preferences")


_yn_mod = _import_yes_no_fresh()
_pref_mod = _import_preferences_fresh()


# ---------------------------------------------------------------------------
# BootcLayoutYesNo
# ---------------------------------------------------------------------------

class TestYesNoGetFinals(unittest.TestCase):
    """get_finals() returns the correct vars/funcs structure."""

    def _make_obj(self, key="accepted", response=False, funcs=None):
        obj = object.__new__(_yn_mod.BootcLayoutYesNo)
        obj._BootcLayoutYesNo__key = key
        obj._BootcLayoutYesNo__response = response
        obj._BootcLayoutYesNo__step = {"final": funcs or []}
        return obj

    def test_response_false_reflected(self):
        finals = self._make_obj(response=False).get_finals()
        self.assertFalse(finals["vars"]["accepted"])

    def test_response_true_reflected(self):
        finals = self._make_obj(response=True).get_finals()
        self.assertTrue(finals["vars"]["accepted"])

    def test_custom_key(self):
        finals = self._make_obj(key="my_flag", response=True).get_finals()
        self.assertIn("my_flag", finals["vars"])
        self.assertTrue(finals["vars"]["my_flag"])

    def test_funcs_from_step(self):
        finals = self._make_obj(funcs=["process_yes"]).get_finals()
        self.assertEqual(finals["funcs"], ["process_yes"])

    def test_empty_funcs(self):
        self.assertEqual(self._make_obj().get_finals()["funcs"], [])

    def test_result_has_vars_and_funcs_keys(self):
        result = self._make_obj().get_finals()
        self.assertIn("vars", result)
        self.assertIn("funcs", result)


class TestYesNoShouldShow(unittest.TestCase):
    """should_show() always returns True regardless of context."""

    def _obj(self):
        return object.__new__(_yn_mod.BootcLayoutYesNo)

    def test_true_with_empty_context(self):
        self.assertTrue(self._obj().should_show({}))

    def test_true_with_populated_context(self):
        self.assertTrue(self._obj().should_show({"encryption": "none", "disk": "/dev/sda"}))


class TestYesNoOnResponse(unittest.TestCase):
    """__on_response() stores the answer and advances the wizard."""

    def _make_obj(self):
        obj = object.__new__(_yn_mod.BootcLayoutYesNo)
        obj._BootcLayoutYesNo__response = False
        obj._BootcLayoutYesNo__step = {"final": []}
        obj._BootcLayoutYesNo__window = MagicMock()
        return obj

    def test_stores_true(self):
        obj = self._make_obj()
        obj._BootcLayoutYesNo__on_response(None, True)
        self.assertTrue(obj._BootcLayoutYesNo__response)

    def test_stores_false(self):
        obj = self._make_obj()
        obj._BootcLayoutYesNo__response = True
        obj._BootcLayoutYesNo__on_response(None, False)
        self.assertFalse(obj._BootcLayoutYesNo__response)

    def test_advances_window(self):
        obj = self._make_obj()
        obj._BootcLayoutYesNo__on_response(None, True)
        obj._BootcLayoutYesNo__window.next.assert_called_once()


class TestYesNoOnInfo(unittest.TestCase):
    """__on_info() shows a dialog only when 'info' key is present in buttons."""

    def _make_obj(self, buttons):
        obj = object.__new__(_yn_mod.BootcLayoutYesNo)
        obj._BootcLayoutYesNo__window = MagicMock()
        obj._BootcLayoutYesNo__step = {"buttons": buttons, "final": []}
        return obj

    def _dialog_mock(self):
        # Use the module's own imported reference — sys.modules may have been
        # replaced by a later _build_gi_stubs() call.
        return _yn_mod.BootcDialog

    def test_no_info_key_returns_without_dialog(self):
        obj = self._make_obj({"yes": "Yes", "no": "No"})
        self._dialog_mock().reset_mock()
        obj._BootcLayoutYesNo__on_info(None)
        self._dialog_mock().assert_not_called()

    def test_info_key_present_shows_dialog(self):
        obj = self._make_obj(
            {
                "yes": "Yes",
                "no": "No",
                "info": {"title": "Details", "text": "Here is more info."},
            }
        )
        self._dialog_mock().reset_mock()
        obj._BootcLayoutYesNo__on_info(None)
        self._dialog_mock().assert_called_once()


# ---------------------------------------------------------------------------
# BootcLayoutPreferences
# ---------------------------------------------------------------------------

def _sw(active: bool):
    """Return a minimal switcher mock."""
    m = MagicMock()
    m.get_active.return_value = active
    return m


class TestPreferencesGetFinals(unittest.TestCase):
    """get_finals() returns correct vars/funcs and handles _managed edge case."""

    def _make_obj(self, switchers, step):
        obj = object.__new__(_pref_mod.BootcLayoutPreferences)
        obj._BootcLayoutPreferences__step = step
        obj._BootcLayoutPreferences__register_widgets = switchers
        return obj

    def test_active_switcher_reflected_as_true(self):
        finals = self._make_obj(
            [("pref_a", _sw(True))],
            {"final": [], "without_selection": {}},
        ).get_finals()
        self.assertTrue(finals["vars"]["pref_a"])

    def test_inactive_switcher_reflected_as_false(self):
        finals = self._make_obj(
            [("pref_b", _sw(False))],
            {"final": [], "without_selection": {}},
        ).get_finals()
        self.assertFalse(finals["vars"]["pref_b"])

    def test_managed_key_added_when_all_inactive_and_allowed_with_final(self):
        finals = self._make_obj(
            [("p", _sw(False))],
            {
                "final": ["default_fn"],
                "without_selection": {"allowed": True, "final": ["fallback_fn"]},
            },
        ).get_finals()
        self.assertTrue(finals["vars"]["_managed"])
        self.assertIn("fallback_fn", finals["funcs"])

    def test_managed_key_not_added_when_not_allowed(self):
        finals = self._make_obj(
            [("p", _sw(False))],
            {"final": [], "without_selection": {"allowed": False}},
        ).get_finals()
        self.assertNotIn("_managed", finals["vars"])

    def test_managed_key_not_added_when_no_fallback_final(self):
        finals = self._make_obj(
            [("p", _sw(False))],
            {"final": [], "without_selection": {"allowed": True}},
        ).get_finals()
        self.assertNotIn("_managed", finals["vars"])

    def test_funcs_from_step_final(self):
        finals = self._make_obj(
            [("p", _sw(True))],
            {"final": ["fn_a", "fn_b"], "without_selection": {}},
        ).get_finals()
        self.assertEqual(finals["funcs"], ["fn_a", "fn_b"])

    def test_multiple_switchers_all_reflected(self):
        finals = self._make_obj(
            [("x", _sw(True)), ("y", _sw(False))],
            {"final": [], "without_selection": {}},
        ).get_finals()
        self.assertTrue(finals["vars"]["x"])
        self.assertFalse(finals["vars"]["y"])

    def test_managed_not_added_when_at_least_one_active(self):
        finals = self._make_obj(
            [("a", _sw(True)), ("b", _sw(False))],
            {
                "final": [],
                "without_selection": {"allowed": True, "final": ["fallback"]},
            },
        ).get_finals()
        self.assertNotIn("_managed", finals["vars"])


class TestPreferencesNextStep(unittest.TestCase):
    """__next_step() enforces selection policy and advances the wizard."""

    def _make_obj(self, switchers, step):
        obj = object.__new__(_pref_mod.BootcLayoutPreferences)
        obj._BootcLayoutPreferences__step = step
        obj._BootcLayoutPreferences__register_widgets = switchers
        obj._BootcLayoutPreferences__window = MagicMock()
        return obj

    def _dialog_mock(self):
        # Use the module's own imported reference — sys.modules may have been
        # replaced by a later _build_gi_stubs() call.
        return _pref_mod.BootcDialog

    def test_active_selection_advances(self):
        obj = self._make_obj(
            [("a", _sw(True))],
            {"final": [], "without_selection": {}},
        )
        obj._BootcLayoutPreferences__next_step(None)
        obj._BootcLayoutPreferences__window.next.assert_called_once()

    def test_no_selection_not_allowed_shows_toast_no_advance(self):
        obj = self._make_obj(
            [("a", _sw(False))],
            {"final": [], "without_selection": {"allowed": False}},
        )
        obj._BootcLayoutPreferences__next_step(None)
        obj._BootcLayoutPreferences__window.toast.assert_called_once()
        obj._BootcLayoutPreferences__window.next.assert_not_called()

    def test_no_selection_allowed_advances(self):
        obj = self._make_obj(
            [("a", _sw(False))],
            {"final": [], "without_selection": {"allowed": True}},
        )
        obj._BootcLayoutPreferences__next_step(None)
        obj._BootcLayoutPreferences__window.next.assert_called_once()

    def test_no_selection_with_message_shows_dialog_and_advances(self):
        obj = self._make_obj(
            [("a", _sw(False))],
            {
                "final": [],
                "without_selection": {
                    "allowed": True,
                    "title": "Heads up",
                    "message": "No options selected.",
                },
            },
        )
        self._dialog_mock().reset_mock()
        obj._BootcLayoutPreferences__next_step(None)
        self._dialog_mock().assert_called_once()
        obj._BootcLayoutPreferences__window.next.assert_called_once()

    def test_no_selection_without_message_does_not_show_dialog(self):
        obj = self._make_obj(
            [("a", _sw(False))],
            {"final": [], "without_selection": {"allowed": True}},
        )
        self._dialog_mock().reset_mock()
        obj._BootcLayoutPreferences__next_step(None)
        self._dialog_mock().assert_not_called()


if __name__ == "__main__":
    unittest.main()

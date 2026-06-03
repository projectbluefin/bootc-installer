"""Unit tests for defaults/user.py username suggestion and validation logic."""

import importlib
import os
import sys
import types
import unittest
from contextlib import contextmanager
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class _Template:
    def __call__(self, *args, **kwargs):
        return lambda cls: cls

    def Child(self, *args, **kwargs):
        return None


class _FakeEntry:
    def __init__(self, text=""):
        self.text = text
        self.css_classes = set()

    def get_text(self):
        return self.text

    def set_text(self, text):
        self.text = text

    def add_css_class(self, css_class):
        self.css_classes.add(css_class)

    def remove_css_class(self, css_class):
        self.css_classes.discard(css_class)


class _FakeButton:
    def __init__(self):
        self.sensitive = None

    def set_sensitive(self, sensitive):
        self.sensitive = sensitive


class _FakeRow:
    def __init__(self):
        self.visible = None

    def set_visible(self, visible):
        self.visible = visible


class _FakeLabel:
    def __init__(self):
        self.label = None
        self.css_classes = set()

    def set_label(self, label):
        self.label = label

    def add_css_class(self, css_class):
        self.css_classes.add(css_class)

    def remove_css_class(self, css_class):
        self.css_classes.discard(css_class)


@contextmanager
def _import_user_module_fresh():
    managed = [
        "gi",
        "gi.repository",
        "gi.repository.Adw",
        "gi.repository.Gtk",
        "bootc_installer.defaults.user",
    ]
    saved = {name: sys.modules.get(name) for name in managed}

    for name in managed:
        sys.modules.pop(name, None)

    template = _Template()
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    gtk_mod.Template = template

    adw_mod = types.ModuleType("gi.repository.Adw")
    adw_mod.Bin = object

    repo_mod.Gtk = gtk_mod
    repo_mod.Adw = adw_mod
    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *args, **kwargs: None

    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod
    sys.modules["gi.repository.Gtk"] = gtk_mod
    sys.modules["gi.repository.Adw"] = adw_mod

    defaults_pkg = importlib.import_module("bootc_installer.defaults")
    if hasattr(defaults_pkg, "user"):
        delattr(defaults_pkg, "user")

    try:
        yield importlib.import_module("bootc_installer.defaults.user")
    finally:
        if hasattr(defaults_pkg, "user"):
            delattr(defaults_pkg, "user")
        for name in managed:
            sys.modules.pop(name, None)
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module


def _make_user_step(mod, *, fullname="", username="", password="", confirm=""):
    step = SimpleNamespace(
        fullname_entry=_FakeEntry(fullname),
        username_entry=_FakeEntry(username),
        password_entry=_FakeEntry(password),
        password_confirmation=_FakeEntry(confirm),
        password_strength_row=_FakeRow(),
        password_strength_label=_FakeLabel(),
        btn_next=_FakeButton(),
    )
    for method_name in (
        "_BootcDefaultUsers__suggested_username",
        "_BootcDefaultUsers__on_field_changed",
        "_BootcDefaultUsers__on_fullname_changed",
        "_BootcDefaultUsers__update_password_strength",
        "_BootcDefaultUsers__update_btn_next",
        "get_finals",
    ):
        setattr(step, method_name, getattr(mod.BootcDefaultUsers, method_name).__get__(step, type(step)))
    return step


class TestSuggestedUsername(unittest.TestCase):
    def test_empty_full_name_suggests_empty_username(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod)
            self.assertEqual(step._BootcDefaultUsers__suggested_username(""), "")

    def test_full_name_with_spaces_uses_first_token_lowercased(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod)
            self.assertEqual(step._BootcDefaultUsers__suggested_username("Jane Doe"), "jane")

    def test_unicode_characters_are_stripped_to_ascii_subset(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod)
            self.assertEqual(step._BootcDefaultUsers__suggested_username("José Ángel"), "jos")

    def test_numbers_are_preserved_in_suggested_username(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod)
            self.assertEqual(step._BootcDefaultUsers__suggested_username("R2D2 Unit"), "r2d2")


class TestUsernameAutofillBehavior(unittest.TestCase):
    def test_full_name_change_autofills_blank_username(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod, fullname="Jane Doe")
            step._BootcDefaultUsers__on_fullname_changed(step.fullname_entry)
            self.assertEqual(step.username_entry.get_text(), "jane")

    def test_full_name_change_updates_previous_auto_suggestion(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod, fullname="Alice Example", username="jane")
            step._BootcDefaultUsers__prev_fullname = "Jane Doe"
            step._BootcDefaultUsers__on_fullname_changed(step.fullname_entry)
            self.assertEqual(step.username_entry.get_text(), "alice")

    def test_full_name_change_keeps_manual_username_override(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod, fullname="Alice Example", username="custom-user")
            step._BootcDefaultUsers__prev_fullname = "Jane Doe"
            step._BootcDefaultUsers__on_fullname_changed(step.fullname_entry)
            self.assertEqual(step.username_entry.get_text(), "custom-user")


class TestUsernameValidation(unittest.TestCase):
    def test_invalid_characters_mark_username_error_and_disable_next(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod, username="john@doe", password="Valid1!A", confirm="Valid1!A")
            step._BootcDefaultUsers__on_field_changed()
            self.assertIn("error", step.username_entry.css_classes)
            self.assertFalse(step.btn_next.sensitive)

    def test_single_character_username_is_accepted(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod, username="a", password="abc", confirm="abc")
            step._BootcDefaultUsers__on_field_changed()
            self.assertNotIn("error", step.username_entry.css_classes)
            self.assertTrue(step.btn_next.sensitive)

    def test_username_starting_with_number_is_rejected(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod, username="1user", password="abc", confirm="abc")
            step._BootcDefaultUsers__on_field_changed()
            self.assertIn("error", step.username_entry.css_classes)
            self.assertFalse(step.btn_next.sensitive)


class TestPasswordStrength(unittest.TestCase):
    def test_empty_password_hides_strength_row(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod)
            step._BootcDefaultUsers__update_password_strength("")
            self.assertFalse(step.password_strength_row.visible)

    def test_lowercase_only_password_is_marked_weak(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod)
            step._BootcDefaultUsers__update_password_strength("lowercase")
            self.assertTrue(step.password_strength_row.visible)
            self.assertEqual(step.password_strength_label.label, "Weak")
            self.assertEqual(step.password_strength_label.css_classes, {"error"})

    def test_password_with_special_characters_can_be_strong(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod)
            step._BootcDefaultUsers__update_password_strength("Valid1!A")
            self.assertEqual(step.password_strength_label.label, "Strong")
            self.assertEqual(step.password_strength_label.css_classes, {"success"})

    def test_mismatched_confirmation_marks_error_and_disables_next(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod, username="jane", password="Valid1!A", confirm="nope")
            step._BootcDefaultUsers__on_field_changed()
            self.assertIn("error", step.password_confirmation.css_classes)
            self.assertFalse(step.btn_next.sensitive)

    def test_short_matching_password_still_enables_next_but_shows_weak_strength(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod, username="jane", password="abc", confirm="abc")
            step._BootcDefaultUsers__on_field_changed()
            self.assertEqual(step.password_strength_label.label, "Weak")
            self.assertTrue(step.btn_next.sensitive)


class TestGetFinals(unittest.TestCase):
    def test_blank_username_returns_empty_user_payload(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(mod, fullname="Jane Doe", password="secret")
            self.assertEqual(
                step.get_finals(),
                {"user": {"username": "", "fullname": "", "password": "", "groups": []}},
            )

    def test_filled_username_returns_stripped_fullname_password_and_default_groups(self):
        with _import_user_module_fresh() as mod:
            step = _make_user_step(
                mod,
                fullname="  Jane Doe  ",
                username="jane",
                password="Valid1!A",
            )
            self.assertEqual(
                step.get_finals(),
                {
                    "user": {
                        "username": "jane",
                        "fullname": "Jane Doe",
                        "password": "Valid1!A",
                        "groups": mod._DEFAULT_GROUPS,
                    }
                },
            )


if __name__ == "__main__":
    unittest.main()

"""Unit tests for defaults/keyboard.py pure logic."""

import importlib
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class _StubWidget:
    def __init__(self, *args, **kwargs):
        pass

    def get_text(self):
        return ""

    def set_text(self, value):
        pass

    def get_active(self):
        return False

    def set_visible(self, value):
        pass

    def set_sensitive(self, value):
        pass

    def remove_css_class(self, css_class):
        pass

    def add_css_class(self, css_class):
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
    gtk_mod.EventControllerKey = types.SimpleNamespace(new=lambda: MagicMock())
    gtk_mod.EventControllerFocus = types.SimpleNamespace(new=lambda: MagicMock())

    adw_mod = types.ModuleType("gi.repository.Adw")
    for widget in [
        "Bin",
        "ActionRow",
        "Window",
        "EntryRow",
        "ComboRow",
        "SwitchRow",
        "PreferencesGroup",
        "PreferencesPage",
        "ExpanderRow",
    ]:
        setattr(adw_mod, widget, _StubWidget)

    gobject_mod = types.ModuleType("gi.repository.GObject")
    gobject_mod.Property = lambda *args, **kwargs: (lambda f: property(f))

    gio_mod = types.ModuleType("gi.repository.Gio")
    glib_mod = types.ModuleType("gi.repository.GLib")
    glib_mod.Variant = types.SimpleNamespace(
        new_string=lambda value: value,
        new_tuple=lambda *values: tuple(values),
        new_array=lambda _variant_type, values: list(values),
    )
    glib_mod.VariantType = lambda value: value

    for name, mod in [
        ("Gtk", gtk_mod),
        ("Adw", adw_mod),
        ("GObject", gobject_mod),
        ("Gio", gio_mod),
        ("GLib", glib_mod),
        ("Gdk", MagicMock()),
    ]:
        setattr(repo_mod, name, mod)
        sys.modules[f"gi.repository.{name}"] = mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *args, **kwargs: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


def _build_keymap_stub():
    keymaps_mod = types.ModuleType("bootc_installer.core.keymaps")

    class _KeyMaps:
        def __init__(self):
            self.list_all = {}

    keymaps_mod.KeyMaps = _KeyMaps
    sys.modules["bootc_installer.core.keymaps"] = keymaps_mod


def _import_keyboard_fresh():
    managed_modules = [
        "gi",
        "gi.repository",
        "gi.repository.Gtk",
        "gi.repository.Adw",
        "gi.repository.GObject",
        "gi.repository.Gio",
        "gi.repository.GLib",
        "gi.repository.Gdk",
        "bootc_installer.core.keymaps",
    ]
    originals = {name: sys.modules.get(name) for name in managed_modules}

    _build_gi_stubs()
    _build_keymap_stub()
    sys.modules.pop("bootc_installer.defaults.keyboard", None)
    import bootc_installer.defaults as defaults_pkg

    defaults_pkg.__dict__.pop("keyboard", None)

    try:
        return importlib.import_module("bootc_installer.defaults.keyboard")
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class TestBootcDefaultKeyboardGetFinals(unittest.TestCase):
    def setUp(self):
        self.mod = _import_keyboard_fresh()

    def test_get_finals_returns_fallback_when_no_keyboard_selected(self):
        obj = self.mod.BootcDefaultKeyboard.__new__(self.mod.BootcDefaultKeyboard)
        obj.selected_keyboard = []

        self.assertEqual(
            obj.get_finals(),
            {"keyboard": [{"layout": "us", "model": "pc105", "variant": ""}]},
        )

    def test_get_finals_returns_selected_keyboard_list(self):
        obj = self.mod.BootcDefaultKeyboard.__new__(self.mod.BootcDefaultKeyboard)
        obj.selected_keyboard = [{"layout": "de", "model": "pc105", "variant": "neo"}]

        self.assertEqual(
            obj.get_finals(),
            {"keyboard": [{"layout": "de", "model": "pc105", "variant": "neo"}]},
        )


class TestBootcDefaultKeyboardLayoutArray(unittest.TestCase):
    def setUp(self):
        self.mod = _import_keyboard_fresh()

    def test_create_keyboard_layout_array_formats_variants_for_gsettings(self):
        obj = self.mod.BootcDefaultKeyboard.__new__(self.mod.BootcDefaultKeyboard)

        with patch.object(
            self.mod.GLib,
            "Variant",
            types.SimpleNamespace(
                new_string=lambda value: ("string", value),
                new_tuple=lambda *values: ("tuple", values),
            ),
        ):
            result = obj._BootcDefaultKeyboard__create_keyboard_layout_array(
                [
                    {"layout": "us", "model": "pc105", "variant": ""},
                    {"layout": "de", "model": "pc105", "variant": "neo"},
                ]
            )

        self.assertEqual(
            result,
            [
                ("tuple", (("string", "xkb"), ("string", "us"))),
                ("tuple", (("string", "xkb"), ("string", "de+neo"))),
            ],
        )


class TestBootcDefaultKeyboardWidgetGeneration(unittest.TestCase):
    def setUp(self):
        self.mod = _import_keyboard_fresh()

    def test_generate_keyboard_list_widgets_renames_czech_bksl_entry(self):
        obj = self.mod.BootcDefaultKeyboard.__new__(self.mod.BootcDefaultKeyboard)
        obj._BootcDefaultKeyboard__keymaps = SimpleNamespace(
            list_all={
                "Czechia": {
                    "cz-bksl": {
                        "display_name": "Czech (with <\\|> key)",
                        "xkb_layout": "cz",
                        "xkb_variant": "bksl",
                    }
                },
                "United States": {
                    "us": {
                        "display_name": "English (US)",
                        "xkb_layout": "us",
                        "xkb_variant": "",
                    }
                },
            }
        )

        created = []

        def _fake_keyboard_row(title, subtitle, layout, variant, key, selected_keyboard):
            created.append(
                {
                    "title": title,
                    "subtitle": subtitle,
                    "layout": layout,
                    "variant": variant,
                    "key": key,
                    "selected_keyboard": selected_keyboard,
                }
            )
            return created[-1]

        with patch.object(self.mod, "KeyboardRow", side_effect=_fake_keyboard_row):
            widgets = obj._BootcDefaultKeyboard__generate_keyboard_list_widgets([])

        self.assertEqual(len(widgets), 2)
        self.assertIn(
            {
                "title": "Czech (bksl)",
                "subtitle": "Czechia",
                "layout": "cz",
                "variant": "bksl",
                "key": "cz-bksl",
                "selected_keyboard": [],
            },
            created,
        )
        self.assertIn(
            {
                "title": "English (US)",
                "subtitle": "United States",
                "layout": "us",
                "variant": "",
                "key": "us",
                "selected_keyboard": [],
            },
            created,
        )


class TestBootcDefaultKeyboardDeltas(unittest.TestCase):
    def setUp(self):
        self.mod = _import_keyboard_fresh()

    def _make_obj(self):
        obj = self.mod.BootcDefaultKeyboard.__new__(self.mod.BootcDefaultKeyboard)
        obj._BootcDefaultKeyboard__keyboard_rows = [MagicMock(name="row1"), MagicMock(name="row2")]
        obj.all_keyboards_group = MagicMock()
        obj.entry_search_keyboard = MagicMock()
        obj.entry_test = MagicMock()
        obj.btn_next = MagicMock()
        obj.search_controller = MagicMock()
        obj.test_focus_controller = MagicMock()
        obj._BootcDefaultKeyboard__window = SimpleNamespace(carousel=MagicMock())
        return obj

    def test_gen_deltas_appends_rows_and_connects_handlers(self):
        obj = self._make_obj()

        with patch.dict(os.environ, {}, clear=True):
            obj.gen_deltas()

        self.assertEqual(obj.all_keyboards_group.append.call_count, 2)
        obj.entry_search_keyboard.add_controller.assert_called_once_with(obj.search_controller)
        obj.entry_test.add_controller.assert_called_once_with(obj.test_focus_controller)
        obj.btn_next.connect.assert_called_once()
        self.assertEqual(obj.all_keyboards_group.connect.call_count, 3)
        obj._BootcDefaultKeyboard__window.carousel.connect.assert_called_once_with(
            "page-changed", obj._BootcDefaultKeyboard__keyboard_verify
        )
        obj.search_controller.connect.assert_called_once_with(
            "key-released", obj._BootcDefaultKeyboard__on_search_key_pressed
        )
        obj.test_focus_controller.connect.assert_called_once_with(
            "enter", obj._BootcDefaultKeyboard__apply_layout
        )

    def test_gen_deltas_skips_apply_layout_hook_when_env_disables_xkb(self):
        obj = self._make_obj()

        with patch.dict(os.environ, {"VANILLA_NO_APPLY_XKB": "1"}, clear=True):
            obj.gen_deltas()

        obj.test_focus_controller.connect.assert_not_called()

    def test_del_deltas_removes_all_keyboard_rows(self):
        obj = self._make_obj()

        obj.del_deltas()

        obj.all_keyboards_group.remove_all.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

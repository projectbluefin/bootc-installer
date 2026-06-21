"""Unit tests for defaults/language.py pure logic."""

import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class _StubWidget:
    def __init__(self, *args, **kwargs):
        self._title = ""
        self._subtitle = ""
        self._label = ""
        self._visible = None
        self._active = False
        self.rows = []
        self._parent = None

    def connect(self, *args, **kwargs):
        pass

    def add_controller(self, controller):
        pass

    def set_title(self, value):
        self._title = value

    def get_title(self):
        return self._title

    def set_subtitle(self, value):
        self._subtitle = value

    def get_subtitle(self):
        return self._subtitle

    def set_label(self, value):
        self._label = value

    def get_label(self):
        return self._label

    def set_visible(self, value):
        self._visible = value

    def get_visible(self):
        return self._visible

    def set_group(self, value):
        self.group = value

    def set_active(self, value):
        self._active = value

    def get_active(self):
        return self._active

    def set_sensitive(self, value):
        self._sensitive = value

    def append(self, row):
        row._parent = self
        self.rows.append(row)

    def remove_all(self):
        self.rows.clear()

    def __iter__(self):
        return iter(self.rows)

    def emit(self, signal_name):
        self.last_signal = signal_name

    def get_parent(self):
        return self._parent


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
    gtk_mod.EventControllerKey = types.SimpleNamespace(new=lambda: _StubWidget())

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

    for name, mod in [("Gtk", gtk_mod), ("Adw", adw_mod)]:
        setattr(repo_mod, name, mod)
        sys.modules[f"gi.repository.{name}"] = mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


def _build_language_stubs():
    language_mod = types.ModuleType("bootc_installer.core.languages")
    language_mod.all_languages = {
        "en_US": "English (United States)",
        "it_IT": "Italiano",
        "pt_BR": "Português (Brasil)",
    }
    language_mod.current_language = "en_US"
    sys.modules["bootc_installer.core.languages"] = language_mod


def _import_language_fresh():
    managed_modules = [
        "gi",
        "gi.repository",
        "gi.repository.Gtk",
        "gi.repository.Adw",
        "bootc_installer.core.languages",
    ]
    originals = {name: sys.modules.get(name) for name in managed_modules}

    _build_gi_stubs()
    _build_language_stubs()
    sys.modules.pop("bootc_installer.defaults.language", None)
    import bootc_installer.defaults as defaults_pkg
    defaults_pkg.__dict__.pop("language", None)

    try:
        return importlib.import_module("bootc_installer.defaults.language")
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class TestLanguageRow(unittest.TestCase):
    def setUp(self):
        self.mod = _import_language_fresh()

    def test_on_check_button_toggled_updates_selected_language_and_emits_signal(self):
        selected_language = {"language_title": None, "language_subtitle": None}
        parent = MagicMock()
        row = self.mod.LanguageRow.__new__(self.mod.LanguageRow)
        setattr(row, "_LanguageRow__title", "English (United States)")
        setattr(row, "_LanguageRow__subtitle", "en_US")
        setattr(row, "_LanguageRow__selected_language", selected_language)
        row.get_parent = MagicMock(return_value=parent)

        getattr(row, "_LanguageRow__on_check_button_toggled")(MagicMock())

        self.assertEqual(
            selected_language,
            {
                "language_title": "English (United States)",
                "language_subtitle": "en_US",
            },
        )
        parent.emit.assert_called_once_with("selected-rows-changed")


class TestBootcDefaultLanguage(unittest.TestCase):
    def setUp(self):
        self.mod = _import_language_fresh()

    def test_gen_deltas_appends_all_language_rows(self):
        obj = self.mod.BootcDefaultLanguage.__new__(self.mod.BootcDefaultLanguage)
        row_one = object()
        row_two = object()
        setattr(obj, "_BootcDefaultLanguage__language_rows", [row_one, row_two])
        obj.all_languages_group = MagicMock()

        obj.gen_deltas()

        obj.all_languages_group.append.assert_any_call(row_one)
        obj.all_languages_group.append.assert_any_call(row_two)

    def test_del_deltas_removes_all_rows(self):
        obj = self.mod.BootcDefaultLanguage.__new__(self.mod.BootcDefaultLanguage)
        obj.all_languages_group = MagicMock()

        obj.del_deltas()

        obj.all_languages_group.remove_all.assert_called_once_with()

    def test_language_verify_enables_next_when_language_is_selected(self):
        obj = self.mod.BootcDefaultLanguage.__new__(self.mod.BootcDefaultLanguage)
        obj.selected_language = {
            "language_title": "Italiano",
            "language_subtitle": "it_IT",
        }
        obj.btn_next = MagicMock()

        getattr(obj, "_BootcDefaultLanguage__language_verify")()

        obj.btn_next.set_sensitive.assert_called_once_with(True)

    def test_language_verify_disables_next_when_language_is_not_selected(self):
        obj = self.mod.BootcDefaultLanguage.__new__(self.mod.BootcDefaultLanguage)
        obj.selected_language = {
            "language_title": None,
            "language_subtitle": None,
        }
        obj.btn_next = MagicMock()

        getattr(obj, "_BootcDefaultLanguage__language_verify")()

        obj.btn_next.set_sensitive.assert_called_once_with(False)

    def test_generate_language_list_widgets_groups_rows_and_selects_current_language(self):
        obj = self.mod.BootcDefaultLanguage.__new__(self.mod.BootcDefaultLanguage)
        setattr(obj, "_BootcDefaultLanguage__language_rows", [])
        obj.selected_language = {
            "language_title": None,
            "language_subtitle": None,
        }
        first_row = types.SimpleNamespace(select_button=MagicMock())
        second_row = types.SimpleNamespace(select_button=MagicMock())

        with patch.object(
            self.mod,
            "all_languages",
            {"en_US": "English (United States)", "it_IT": "Italiano"},
        ), patch.object(self.mod, "current_language", "it_IT"), patch.object(
            self.mod,
            "LanguageRow",
            side_effect=[first_row, second_row],
        ):
            getattr(obj, "_BootcDefaultLanguage__generate_language_list_widgets")()

        self.assertEqual(len(getattr(obj, "_BootcDefaultLanguage__language_rows")), 2)
        first_row.select_button.set_group.assert_not_called()
        second_row.select_button.set_group.assert_called_once_with(first_row.select_button)
        second_row.select_button.set_active.assert_called_once_with(True)
        self.assertEqual(
            obj.selected_language,
            {"language_title": "Italiano", "language_subtitle": "it_IT"},
        )

    def test_get_finals_returns_selected_language_code(self):
        obj = self.mod.BootcDefaultLanguage.__new__(self.mod.BootcDefaultLanguage)
        obj.selected_language = {
            "language_title": "Português (Brasil)",
            "language_subtitle": "pt_BR",
        }

        result = obj.get_finals()

        self.assertEqual(result, {"language": "pt_BR"})

    def test_search_key_pressed_filters_by_sanitized_title_and_code(self):
        obj = self.mod.BootcDefaultLanguage.__new__(self.mod.BootcDefaultLanguage)
        obj.entry_search_language = MagicMock()
        obj.entry_search_language.get_text.return_value = "english united!"

        row_one = MagicMock()
        row_one.get_title.return_value = "English (United States)"
        row_one.suffix_bin.get_label.return_value = "en_US"

        row_two = MagicMock()
        row_two.get_title.return_value = "Italiano"
        row_two.suffix_bin.get_label.return_value = "it_IT"

        obj.all_languages_group = [row_one, row_two]

        getattr(obj, "_BootcDefaultLanguage__on_search_key_pressed")()

        row_one.set_visible.assert_called_once_with(True)
        row_two.set_visible.assert_called_once_with(False)


if __name__ == "__main__":
    unittest.main()

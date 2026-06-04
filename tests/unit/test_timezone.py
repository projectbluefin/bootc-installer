"""Unit tests for defaults/timezone.py pure logic."""

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
        self._expanded = None
        self._active = False
        self._sensitive = None
        self._parent = None
        self.rows = []

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

    def set_markup(self, value):
        self._label = value

    def set_visible(self, value):
        self._visible = value

    def get_visible(self):
        return self._visible

    def set_expanded(self, value):
        self._expanded = value

    def get_expanded(self):
        return self._expanded

    def set_group(self, value):
        self.group = value

    def set_active(self, value):
        self._active = value

    def get_active(self):
        return self._active

    def set_sensitive(self, value):
        self._sensitive = value

    def add_row(self, row):
        row._parent = self
        self.rows.append(row)

    def add(self, row):
        row._parent = self
        self.rows.append(row)

    def remove(self, row):
        self.rows.remove(row)

    def __iter__(self):
        return iter(self.rows)

    def get_parent(self):
        return self._parent


class _Template:
    def __call__(self, *args, **kwargs):
        return lambda cls: cls

    def Child(self, *args, **kwargs):
        return None


class _FakeResourceData:
    def __init__(self, payload):
        self._payload = payload

    def get_data(self):
        return self._payload


class _FakeThread:
    def __init__(self, target=None, args=()):
        self._target = target
        self._args = args

    def start(self):
        self._target(*self._args)


class _FakeLocation:
    def __init__(self, city, country):
        self._city = city
        self._country = country

    def get_city_name(self):
        return self._city

    def get_country_name(self):
        return self._country


class _IndexErrorSelection(dict):
    def __getitem__(self, key):
        raise IndexError


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
    adw_mod.ExpanderRow = types.SimpleNamespace(new=lambda: _StubWidget())

    gio_mod = types.ModuleType("gi.repository.Gio")
    gio_mod.resources_lookup_data = lambda *a, **kw: _FakeResourceData(b"{}")

    glib_mod = types.ModuleType("gi.repository.GLib")
    glib_mod.idle_add = lambda func, *args: func(*args)

    for name, mod in [
        ("Gtk", gtk_mod),
        ("Adw", adw_mod),
        ("Gio", gio_mod),
        ("GLib", glib_mod),
    ]:
        setattr(repo_mod, name, mod)
        sys.modules[f"gi.repository.{name}"] = mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


def _build_timezone_stubs():
    tz_mod = types.ModuleType("bootc_installer.core.timezones")
    tz_mod.all_timezones = {
        "Europe": {"Italy": {"Rome": "Europe/Rome"}},
        "America": {"United States": {"New York": "America/New_York"}},
    }
    tz_mod.get_location = lambda callback: None
    tz_mod.get_timezone_preview = lambda tz_name: ("12:34", "2024-06-03")
    sys.modules["bootc_installer.core.timezones"] = tz_mod


def _import_timezone_fresh():
    managed_modules = [
        "gi",
        "gi.repository",
        "gi.repository.Gtk",
        "gi.repository.Adw",
        "gi.repository.Gio",
        "gi.repository.GLib",
        "bootc_installer.core.timezones",
    ]
    originals = {name: sys.modules.get(name) for name in managed_modules}

    _build_gi_stubs()
    _build_timezone_stubs()
    sys.modules.pop("bootc_installer.defaults.timezone", None)
    import bootc_installer.defaults as defaults_pkg
    defaults_pkg.__dict__.pop("timezone", None)

    try:
        return importlib.import_module("bootc_installer.defaults.timezone")
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class TestLoadDinosaurs(unittest.TestCase):
    def setUp(self):
        self.mod = _import_timezone_fresh()

    def test_load_dinosaurs_reads_gresource_json(self):
        payload = b'{"United States": {"name": "T. rex", "location": "Montana"}}'

        with patch.object(
            self.mod.Gio,
            "resources_lookup_data",
            return_value=_FakeResourceData(payload),
        ):
            result = self.mod._load_dinosaurs()

        self.assertEqual(result["United States"]["name"], "T. rex")

    def test_load_dinosaurs_falls_back_to_dev_file(self):
        with patch.object(
            self.mod.Gio,
            "resources_lookup_data",
            side_effect=Exception("no gresource"),
        ), patch.object(
            self.mod.pathlib.Path,
            "read_text",
            return_value='{"Italy": {"name": "Scipionyx", "location": "Campania"}}',
        ):
            result = self.mod._load_dinosaurs()

        self.assertEqual(result["Italy"]["location"], "Campania")

    def test_load_dinosaurs_returns_empty_dict_when_all_sources_fail(self):
        with patch.object(
            self.mod.Gio,
            "resources_lookup_data",
            side_effect=Exception("no gresource"),
        ), patch.object(
            self.mod.pathlib.Path,
            "read_text",
            side_effect=Exception("no file"),
        ):
            result = self.mod._load_dinosaurs()

        self.assertEqual(result, {})


class TestBootcDefaultTimezone(unittest.TestCase):
    def setUp(self):
        self.mod = _import_timezone_fresh()

    def test_gen_deltas_resets_lists_and_generates_widgets(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        setattr(obj, "_BootcDefaultTimezone__expanders", [object()])
        setattr(obj, "_BootcDefaultTimezone__tz_entries", [object()])
        generator = MagicMock()
        setattr(obj, "_BootcDefaultTimezone__generate_timezone_list_widgets", generator)

        obj.gen_deltas()

        self.assertEqual(getattr(obj, "_BootcDefaultTimezone__expanders"), [])
        self.assertEqual(getattr(obj, "_BootcDefaultTimezone__tz_entries"), [])
        generator.assert_called_once_with()

    def test_del_deltas_removes_all_expanders_and_clears_state(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        expander_one = object()
        expander_two = object()
        setattr(obj, "_BootcDefaultTimezone__tz_entries", [object()])
        setattr(obj, "_BootcDefaultTimezone__expanders", [expander_one, expander_two])
        obj.all_timezones_group = MagicMock()

        obj.del_deltas()

        self.assertEqual(getattr(obj, "_BootcDefaultTimezone__tz_entries"), [])
        self.assertEqual(getattr(obj, "_BootcDefaultTimezone__expanders"), [])
        obj.all_timezones_group.remove.assert_any_call(expander_one)
        obj.all_timezones_group.remove.assert_any_call(expander_two)

    def test_get_finals_returns_selected_timezone(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        obj.selected_timezone = {"region": "America", "zone": "New_York"}

        result = obj.get_finals()

        self.assertEqual(
            result,
            {"timezone": {"region": "America", "zone": "New_York"}},
        )

    def test_get_finals_falls_back_when_selection_raises_index_error(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        obj.selected_timezone = _IndexErrorSelection()

        result = obj.get_finals()

        self.assertEqual(
            result,
            {"timezone": {"region": "Europe", "zone": "London"}},
        )

    def test_timezone_verify_ignores_other_pages(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        setattr(obj, "_BootcDefaultTimezone__step_num", 2)

        with patch.object(self.mod.threading, "Thread") as thread_cls:
            obj.timezone_verify(idx=1)

        thread_cls.assert_not_called()

    def test_timezone_verify_selects_matching_timezone(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        setattr(obj, "_BootcDefaultTimezone__step_num", 3)
        obj.selected_timezone = {"region": "Europe", "zone": None}
        entry = types.SimpleNamespace(
            title="New York",
            subtitle="United States",
            select_button=MagicMock(),
        )
        setattr(obj, "_BootcDefaultTimezone__tz_entries", [entry])
        obj.btn_next = MagicMock()

        def _fake_get_location(callback):
            callback(_FakeLocation("New York", "United States"))

        with patch.object(self.mod, "get_location", side_effect=_fake_get_location), patch.object(
            self.mod.threading,
            "Thread",
            side_effect=lambda target, args: _FakeThread(target, args),
        ):
            obj.timezone_verify(idx=3)

        self.assertEqual(
            obj.selected_timezone,
            {"region": "United States", "zone": "New York"},
        )
        entry.select_button.set_active.assert_called_once_with(True)
        obj.btn_next.set_sensitive.assert_not_called()

    def test_timezone_verify_enables_next_when_detection_does_not_match(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        setattr(obj, "_BootcDefaultTimezone__step_num", 1)
        setattr(
            obj,
            "_BootcDefaultTimezone__tz_entries",
            [
                types.SimpleNamespace(
                    title="Rome",
                    subtitle="Italy",
                    select_button=MagicMock(),
                )
            ],
        )
        obj.btn_next = MagicMock()

        def _fake_get_location(callback):
            callback(_FakeLocation("New York", "United States"))

        with patch.object(self.mod, "get_location", side_effect=_fake_get_location), patch.object(
            self.mod.threading,
            "Thread",
            side_effect=lambda target, args: _FakeThread(target, args),
        ):
            obj.timezone_verify(idx=1)

        obj.btn_next.set_sensitive.assert_called_once_with(True)

    def test_search_key_pressed_resets_all_expanders_for_empty_query(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        expander_one = MagicMock()
        expander_two = MagicMock()
        setattr(obj, "_BootcDefaultTimezone__expanders", [expander_one, expander_two])
        setattr(obj, "_BootcDefaultTimezone__tz_entries", [])
        obj.entry_search_timezone = MagicMock()
        obj.entry_search_timezone.get_text.return_value = ""

        getattr(obj, "_BootcDefaultTimezone__on_search_key_pressed")()

        for expander in (expander_one, expander_two):
            expander.set_visible.assert_called_once_with(True)
            expander.set_expanded.assert_called_once_with(False)

    def test_search_key_pressed_matches_accented_titles(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        expander = MagicMock()
        next_expander = MagicMock()
        setattr(obj, "_BootcDefaultTimezone__expanders", [expander, next_expander])

        row_one = MagicMock()
        row_one.subtitle = "Brazil"
        row_one.get_title.return_value = "São Paulo"

        row_two = MagicMock()
        row_two.subtitle = "Brazil"
        row_two.get_title.return_value = "Rio de Janeiro"

        row_three = MagicMock()
        row_three.subtitle = "Italy"
        row_three.get_title.return_value = "Milan"

        setattr(obj, "_BootcDefaultTimezone__tz_entries", [row_one, row_two, row_three])
        obj.entry_search_timezone = MagicMock()
        obj.entry_search_timezone.get_text.return_value = "sao"

        getattr(obj, "_BootcDefaultTimezone__on_search_key_pressed")()

        row_one.set_visible.assert_called_once_with(True)
        row_two.set_visible.assert_called_once_with(False)
        row_three.set_visible.assert_called_once_with(False)
        expander.set_expanded.assert_called_once_with(True)
        expander.set_visible.assert_called_once_with(True)
        next_expander.set_expanded.assert_not_called()

    def test_row_toggle_updates_labels_and_shows_matching_dinosaur(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        obj.selected_timezone = {"region": None, "zone": None}
        obj.current_tz_label = MagicMock()
        obj.current_location_label = MagicMock()
        obj.dinosaur_label = MagicMock()
        obj.btn_next = MagicMock()
        widget = types.SimpleNamespace(
            tz_name="America/New_York",
            title="New York",
            subtitle="United States",
        )

        with patch.object(
            self.mod,
            "_DINOSAURS",
            {"United States": {"name": "T. rex", "location": "Montana"}},
        ):
            getattr(obj, "_BootcDefaultTimezone__on_row_toggle")(None, widget)

        self.assertEqual(
            obj.selected_timezone,
            {"region": "America", "zone": "New_York"},
        )
        obj.current_tz_label.set_label.assert_called_once_with("America/New_York")
        obj.current_location_label.set_label.assert_called_once()
        obj.dinosaur_label.set_markup.assert_called_once()
        obj.dinosaur_label.set_visible.assert_called_once_with(True)
        obj.btn_next.set_sensitive.assert_called_once_with(True)

    def test_row_toggle_hides_dinosaur_when_country_has_no_entry(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        obj.selected_timezone = {"region": None, "zone": None}
        obj.current_tz_label = MagicMock()
        obj.current_location_label = MagicMock()
        obj.dinosaur_label = MagicMock()
        obj.btn_next = MagicMock()
        widget = types.SimpleNamespace(
            tz_name="Europe/Rome",
            title="Rome",
            subtitle="Italy",
        )

        with patch.object(self.mod, "_DINOSAURS", {}):
            getattr(obj, "_BootcDefaultTimezone__on_row_toggle")(None, widget)

        obj.dinosaur_label.set_label.assert_called_once_with("")
        obj.dinosaur_label.set_visible.assert_called_once_with(False)

    def test_generate_timezone_list_widgets_builds_expanders_and_rows(self):
        obj = self.mod.BootcDefaultTimezone.__new__(self.mod.BootcDefaultTimezone)
        obj.expanders_list = {"Italy": "Europe"}
        obj.all_timezones_group = MagicMock()
        setattr(obj, "_BootcDefaultTimezone__expanders", [])
        setattr(obj, "_BootcDefaultTimezone__tz_entries", [])

        expander = MagicMock()
        first_row = types.SimpleNamespace(select_button=MagicMock())
        second_row = types.SimpleNamespace(select_button=MagicMock())

        with patch.object(
            self.mod,
            "all_timezones",
            {"Europe": {"Italy": {"Rome": "Europe/Rome", "Milan": "Europe/Milan"}}},
        ), patch.object(
            self.mod.Adw.ExpanderRow,
            "new",
            return_value=expander,
        ), patch.object(
            self.mod,
            "TimezoneRow",
            side_effect=[first_row, second_row],
        ), patch.object(
            self.mod.GLib,
            "idle_add",
            side_effect=lambda func, *args: func(*args),
        ):
            getattr(obj, "_BootcDefaultTimezone__generate_timezone_list_widgets")()

        self.assertEqual(getattr(obj, "_BootcDefaultTimezone__expanders"), [expander])
        self.assertEqual(len(getattr(obj, "_BootcDefaultTimezone__tz_entries")), 2)
        obj.all_timezones_group.add.assert_called_once_with(expander)
        expander.add_row.assert_any_call(first_row)
        expander.add_row.assert_any_call(second_row)
        first_row.select_button.set_group.assert_called_once_with(first_row.select_button)
        second_row.select_button.set_group.assert_called_once_with(first_row.select_button)


if __name__ == "__main__":
    unittest.main()

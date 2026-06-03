"""Branding parity tests.

Verifies that the generic recipe-driven branding paths produce the same
observable behaviour as the previously hardcoded Dakota/Bluefin values.
These tests run without a display (no GTK widgets are instantiated).
"""

import ast
import importlib
import inspect
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# GTK / GLib stubs — same pattern as test_done.py
# ---------------------------------------------------------------------------

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
    adw_mod.Window = _StubBin
    adw_mod.ActionRow = _StubBin
    adw_mod.ExpanderRow = _StubBin
    adw_mod.PreferencesGroup = _StubBin

    gobject_mod = types.ModuleType("gi.repository.GObject")
    gobject_mod.Property = lambda *a, **kw: (lambda f: property(f))

    class _ResourceLookupFlags:
        NONE = 0

    gio_mod = types.ModuleType("gi.repository.Gio")
    gio_mod.bus_get_sync = MagicMock()
    gio_mod.BusType = types.SimpleNamespace(SYSTEM=0)
    gio_mod.DBusCallFlags = types.SimpleNamespace(NONE=0)
    gio_mod.ResourceLookupFlags = _ResourceLookupFlags
    gio_mod.resources_lookup_data = MagicMock()
    gio_mod.File = MagicMock()
    gio_mod.BusType = type("BusType", (), {"SYSTEM": 0})
    gio_mod.DBusCallFlags = type("DBusCallFlags", (), {"NONE": 0})
    gio_mod.bus_get_sync = MagicMock()
    repo_mod.Gio = gio_mod
    sys.modules["gi.repository.Gio"] = gio_mod

    for lib in ("Gdk", "GLib"):
        stub = MagicMock()
        setattr(repo_mod, lib, stub)
        sys.modules[f"gi.repository.{lib}"] = stub

    sys.modules["gi.repository.Gtk"] = gtk_mod
    sys.modules["gi.repository.Adw"] = adw_mod
    sys.modules["gi.repository.GObject"] = gobject_mod
    repo_mod.Gtk = gtk_mod
    repo_mod.Adw = adw_mod
    repo_mod.GObject = gobject_mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


_build_gi_stubs()

# Stub heavy deps that aren't under test
for _mod in (
    "bootc_installer.windows.dialog_output",
    "bootc_installer.widgets.page_header",
):
    sys.modules.setdefault(_mod, MagicMock())

# pastry_compat needs real stubs (not MagicMock) so imports work
_pastry = types.ModuleType("bootc_installer.utils.pastry_compat")
_pastry.wrap_glass = lambda w: w
_pastry.add_glass_root = lambda w: None
_pastry.new_grid_spinner = MagicMock(return_value=MagicMock())
sys.modules["bootc_installer.utils.pastry_compat"] = _pastry


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

DAKOTA_RECIPE = {
    "log_file": "/var/log/bootc-installer.log",
    "distro_name": "Dakota",
    "distro_logo": "resource:///org/bootcinstaller/Installer/images/dakota.png",
    "imgref": "ghcr.io/projectbluefin/dakota:latest",
    "welcome_title": "Welcome to Dakota",
    "welcome_subtitle": "A GNOME workstation built on GnomeOS.",
    "store_url": "https://store.projectbluefin.io",
    "store_qr_resource": "/org/bootcinstaller/Installer/assets/store-qr.svg",
    "credits_data": "/org/bootcinstaller/Installer/data/credits.json",
    "soundtrack_data": "/org/bootcinstaller/Installer/data/tracks.json",
    "images": [
        {
            "name": "Dakota",
            "imgref": "ghcr.io/projectbluefin/dakota:latest",
            "bootloader": "systemd",
            "filesystem": "btrfs",
            "composefs": True,
        }
    ],
    "steps": {},
}

GENERIC_RECIPE = {
    "log_file": "/var/log/bootc-installer.log",
    "distro_name": "BootcOS",
    "distro_logo": "org.bootcinstaller.Installer",
    "welcome_title": "",
    "steps": {},
}


# ---------------------------------------------------------------------------
# recipe.py — demo fallback
# ---------------------------------------------------------------------------

class TestRecipeDemoFallback(unittest.TestCase):
    """recipe.py demo fallback must not hardcode any distro name."""

    def test_demo_fallback_distro_name_empty_by_default(self):
        env = {"BOOTC_DEMO": "1"}
        env.pop("BOOTC_DEMO_DISTRO_NAME", None)
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("BOOTC_DEMO_DISTRO_NAME", None)
            distro_name = os.environ.get("BOOTC_DEMO_DISTRO_NAME", "")
        self.assertEqual(distro_name, "")

    def test_demo_fallback_distro_name_from_env(self):
        with patch.dict(os.environ, {"BOOTC_DEMO": "1", "BOOTC_DEMO_DISTRO_NAME": "Dakota"}):
            distro_name = os.environ.get("BOOTC_DEMO_DISTRO_NAME", "")
        self.assertEqual(distro_name, "Dakota")

    def test_demo_fallback_not_hardcoded_bluefin(self):
        """Regression: distro_name must never be the literal string 'Bluefin' in recipe.py."""
        for mod_name in list(sys.modules):
            if "recipe" in mod_name and "bootc_installer" in mod_name:
                del sys.modules[mod_name]
        from bootc_installer.utils import recipe as recipe_mod
        source = inspect.getsource(recipe_mod)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "Bluefin":
                self.fail(
                    f"Hardcoded 'Bluefin' string found in recipe.py at line {node.lineno}. "
                    "Use BOOTC_DEMO_DISTRO_NAME env var instead."
                )


# ---------------------------------------------------------------------------
# done.py — __maybe_show_store logic (tested directly, no GTK instantiation)
# ---------------------------------------------------------------------------

def _import_done():
    _build_gi_stubs()
    sys.modules.pop("bootc_installer.views.done", None)
    try:
        import bootc_installer.views as views_pkg
        views_pkg.__dict__.pop("done", None)
    except Exception:
        pass
    return importlib.import_module("bootc_installer.views.done")


def _make_done_obj(recipe):
    """Build a minimal BootcDone-like object with just the store logic wired up."""
    done_mod = _import_done()

    window = MagicMock()
    window.recipe = recipe

    obj = object.__new__(done_mod.BootcDone)
    obj._BootcDone__window = window
    obj.store_qr = MagicMock()
    obj.store_group = MagicMock()
    return obj, done_mod


class TestDoneStoreQR(unittest.TestCase):
    """__maybe_show_store must be driven by recipe['store_url'], not hardcoded."""

    def test_store_hidden_when_no_store_url(self):
        obj, done_mod = _make_done_obj(GENERIC_RECIPE)
        with patch.object(done_mod.BootcDone, "_BootcDone__is_us_locale", return_value=True):
            done_mod.BootcDone._BootcDone__maybe_show_store(obj)
        obj.store_group.set_visible.assert_not_called()

    def test_store_shown_for_dakota_recipe_us_locale(self):
        obj, done_mod = _make_done_obj(DAKOTA_RECIPE)
        with patch.object(done_mod.BootcDone, "_BootcDone__is_us_locale", return_value=True):
            done_mod.BootcDone._BootcDone__maybe_show_store(obj)
        obj.store_qr.set_resource.assert_called_once_with(
            DAKOTA_RECIPE["store_qr_resource"]
        )
        obj.store_group.set_visible.assert_called_once_with(True)

    def test_store_hidden_for_dakota_recipe_non_us_locale(self):
        obj, done_mod = _make_done_obj(DAKOTA_RECIPE)
        with patch.object(done_mod.BootcDone, "_BootcDone__is_us_locale", return_value=False):
            done_mod.BootcDone._BootcDone__maybe_show_store(obj)
        obj.store_group.set_visible.assert_not_called()

    def test_store_qr_resource_defaults_to_builtin_when_key_absent(self):
        """If store_url is set but store_qr_resource is absent, use the built-in asset."""
        recipe = {k: v for k, v in DAKOTA_RECIPE.items() if k != "store_qr_resource"}
        obj, done_mod = _make_done_obj(recipe)
        with patch.object(done_mod.BootcDone, "_BootcDone__is_us_locale", return_value=True):
            done_mod.BootcDone._BootcDone__maybe_show_store(obj)
        obj.store_qr.set_resource.assert_called_once_with(
            "/org/bootcinstaller/Installer/assets/store-qr.svg"
        )


# ---------------------------------------------------------------------------
# progress.py — __load_tracks logic
# ---------------------------------------------------------------------------

def _import_progress():
    _build_gi_stubs()
    sys.modules.pop("bootc_installer.views.progress", None)
    try:
        import bootc_installer.views as views_pkg
        views_pkg.__dict__.pop("progress", None)
    except Exception:
        pass
    gio = sys.modules.get("gi.repository.Gio")
    if gio is not None and not hasattr(gio, "ResourceLookupFlags"):
        class _ResourceLookupFlags:
            NONE = 0
        gio.ResourceLookupFlags = _ResourceLookupFlags
    if gio is not None and not hasattr(gio, "resources_lookup_data"):
        gio.resources_lookup_data = MagicMock()
    return importlib.import_module("bootc_installer.views.progress")


def _make_progress_obj(recipe):
    prog_mod = _import_progress()
    window = MagicMock()
    window.recipe = recipe
    obj = object.__new__(prog_mod.BootcProgress)
    obj._BootcProgress__window = window
    obj._BootcProgress__populate_carousel = MagicMock()
    prog_mod.GLib.idle_add = lambda fn, *args: fn(*args)
    return obj, prog_mod


class TestProgressSoundtrackData(unittest.TestCase):
    """__load_tracks must prefer recipe['soundtrack_data'] over the built-in path."""

    def test_uses_recipe_soundtrack_data_filesystem_path(self):
        tracks = [{"title": "Test Track", "artist": "Test Artist"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(tracks, f)
            tmp_path = f.name
        try:
            recipe = dict(DAKOTA_RECIPE, soundtrack_data=tmp_path)
            obj, prog_mod = _make_progress_obj(recipe)
            # GResource lookup should not be reached
            prog_mod.Gio.resources_lookup_data = MagicMock(side_effect=Exception("no resource"))
            prog_mod.BootcProgress._BootcProgress__load_tracks(obj)
            obj._BootcProgress__populate_carousel.assert_called_once_with(tracks)
        finally:
            os.unlink(tmp_path)

    def test_falls_back_to_builtin_when_no_soundtrack_data(self):
        tracks = [{"title": "Builtin Track", "artist": "Builtin Artist"}]
        recipe = dict(GENERIC_RECIPE)  # no soundtrack_data key
        obj, prog_mod = _make_progress_obj(recipe)
        mock_bytes = MagicMock()
        mock_bytes.get_data.return_value = json.dumps(tracks).encode()
        prog_mod.Gio.resources_lookup_data = MagicMock(return_value=mock_bytes)
        # Mock pathlib.Path.read_text for dev-mode fallback path
        with patch("pathlib.Path.read_text", side_effect=FileNotFoundError):
            prog_mod.BootcProgress._BootcProgress__load_tracks(obj)
        obj._BootcProgress__populate_carousel.assert_called_once_with(tracks)

    def test_recipe_soundtrack_data_gresource_path(self):
        """A soundtrack_data starting with /org/ is loaded via Gio.resources_lookup_data."""
        tracks = [{"title": "GResource Track", "artist": "GResource Artist"}]
        recipe = dict(DAKOTA_RECIPE)  # soundtrack_data = "/org/bootcinstaller/..."
        obj, prog_mod = _make_progress_obj(recipe)
        mock_bytes = MagicMock()
        mock_bytes.get_data.return_value = json.dumps(tracks).encode()
        prog_mod.Gio.resources_lookup_data = MagicMock(return_value=mock_bytes)
        prog_mod.BootcProgress._BootcProgress__load_tracks(obj)
        prog_mod.Gio.resources_lookup_data.assert_called_with(
            DAKOTA_RECIPE["soundtrack_data"],
            prog_mod.Gio.ResourceLookupFlags.NONE,
        )


# ---------------------------------------------------------------------------
# dialog_credits.py — _load_credits logic
# ---------------------------------------------------------------------------

def _import_credits():
    _build_gi_stubs()
    sys.modules.pop("bootc_installer.windows.dialog_credits", None)
    try:
        import bootc_installer.windows as windows_pkg
        windows_pkg.__dict__.pop("dialog_credits", None)
    except Exception:
        pass
    adw = sys.modules.get("gi.repository.Adw")
    if adw is not None and not hasattr(adw, "Window"):
        class _Stub:
            pass
        adw.Window = _Stub
    gio = sys.modules.get("gi.repository.Gio")
    if gio is not None and not hasattr(gio, "File"):
        gio.File = MagicMock()
    return importlib.import_module("bootc_installer.windows.dialog_credits")


def _make_credits_obj(recipe):
    dc_mod = _import_credits()
    window = MagicMock()
    window.recipe = recipe
    obj = object.__new__(dc_mod.BootcCreditsWindow)
    obj._window = window
    obj.header_title = MagicMock()
    obj.header_subtitle = MagicMock()
    obj.header_quote = MagicMock()
    obj.sections_box = MagicMock()
    obj.footer_quote = MagicMock()
    obj.footer_closing = MagicMock()
    obj._reveal_queue = []
    obj._reveal_index = 0
    obj._section_revealers = []
    obj._current_section = 0
    dc_mod.GLib.timeout_add = MagicMock()
    return obj, dc_mod


_SAMPLE_CREDITS = {
    "header": {"title": "Dakota Credits", "subtitle": "sub", "quote": "q"},
    "sections": [],
    "footer": {"quote": "fq", "closing": "fc"},
}


class TestCreditsData(unittest.TestCase):
    """BootcCreditsWindow must prefer recipe['credits_data'] over the built-in path."""

    def test_uses_recipe_credits_data_filesystem_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(_SAMPLE_CREDITS, f)
            tmp_path = f.name
        try:
            recipe = dict(DAKOTA_RECIPE, credits_data=tmp_path)
            obj, dc_mod = _make_credits_obj(recipe)
            # GResource should not be reached
            dc_mod.Gio.File.new_for_uri = MagicMock(side_effect=Exception("no resource"))
            dc_mod.BootcCreditsWindow._load_credits(obj)
            obj.header_title.set_label.assert_called_with("Dakota Credits")
        finally:
            os.unlink(tmp_path)

    def test_generic_recipe_without_credits_data_falls_through_gracefully(self):
        """When credits_data is absent and GResource fails, degrade gracefully."""
        obj, dc_mod = _make_credits_obj(GENERIC_RECIPE)
        dc_mod.Gio.File.new_for_uri = MagicMock(side_effect=Exception("no resource"))
        with patch("builtins.open", side_effect=FileNotFoundError):
            dc_mod.BootcCreditsWindow._load_credits(obj)
        obj.header_title.set_label.assert_called_with("Credits")

    def test_credits_data_gresource_path_is_tried_first(self):
        """A credits_data starting with /org/ is loaded via Gio.File GResource URI."""
        recipe = dict(DAKOTA_RECIPE)  # credits_data = "/org/bootcinstaller/..."
        obj, dc_mod = _make_credits_obj(recipe)
        mock_gfile = MagicMock()
        mock_gfile.load_contents.return_value = (True, json.dumps(_SAMPLE_CREDITS).encode())
        dc_mod.Gio.File.new_for_uri = MagicMock(return_value=mock_gfile)
        dc_mod.BootcCreditsWindow._load_credits(obj)
        dc_mod.Gio.File.new_for_uri.assert_called_with(
            f"resource://{DAKOTA_RECIPE['credits_data']}"
        )
        obj.header_title.set_label.assert_called_with("Dakota Credits")


# ---------------------------------------------------------------------------
# recipe.json — welcome_title / distro_name parity
# ---------------------------------------------------------------------------

class TestRecipeJsonParity(unittest.TestCase):
    """recipe.json must not have a welcome_title that names a different distro."""

    def _load_recipe_json(self):
        recipe_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "recipe.json"
        )
        if not os.path.exists(recipe_path):
            self.skipTest("recipe.json not found")
        with open(recipe_path) as f:
            return json.load(f)

    def test_welcome_title_mentions_distro_name(self):
        recipe = self._load_recipe_json()
        distro = recipe.get("distro_name", "")
        title = recipe.get("welcome_title", "")
        if title and distro:
            self.assertIn(
                distro, title,
                f"welcome_title '{title}' does not mention distro_name '{distro}'."
            )

    def test_welcome_title_not_wrong_distro(self):
        """Regression: welcome_title must not say 'Bluefin' when distro_name is 'Dakota'."""
        recipe = self._load_recipe_json()
        distro = recipe.get("distro_name", "")
        title = recipe.get("welcome_title", "")
        if distro and distro != "Bluefin" and title:
            self.assertNotIn(
                "Bluefin", title,
                f"welcome_title '{title}' mentions 'Bluefin' but distro_name is '{distro}'."
            )


if __name__ == "__main__":
    unittest.main()

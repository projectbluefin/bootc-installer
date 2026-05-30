"""Unit tests for the pure-Python logic in defaults/slurp.py.

slurp.py has a GTK module-level import chain. We stub out all gi.repository
modules before importing so these tests run without a display or GResource.
"""

import sys
import types
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# ── Stub out gi.repository before importing anything from the package ──────────

def _build_gi_stubs():
    """Inject lightweight gi stubs so slurp.py can be imported headlessly.

    Other unit test files (e.g. test_image_helpers.py) install MagicMock gi
    modules before this file is collected. MagicMock returns truthy for any
    attribute, so a simple hasattr("_stubbed") check is not enough. We always
    force-install our stubs and then reload slurp.py so its class definitions
    are evaluated with our stubs rather than MagicMocks.
    """
    gi_mod = types.ModuleType("gi")
    gi_mod._stubbed = True
    repo_mod = types.ModuleType("gi.repository")

    # A Template decorator that accepts @Gtk.Template(resource_path=...) and
    # returns the class unchanged. Also provides Template.Child() as a
    # class-level descriptor.
    class _Template:
        def __call__(self, *args, **kwargs):
            # @Gtk.Template(resource_path="...") → returns decorator
            return lambda cls: cls

        def Child(self, *args, **kwargs):
            return None

    _template_instance = _Template()

    # Minimal stub class that satisfies Gtk.Template, Adw.Bin, etc.
    class _Stub:
        pass

    from unittest.mock import MagicMock as _MagicMock
    stubs = {}
    for lib in ("Gtk", "Adw", "GLib", "Gio", "Gdk", "NM"):
        stub = types.ModuleType(f"gi.repository.{lib}")
        stub.Template = _template_instance
        stub.Bin = _Stub
        stub.Box = _Stub
        stub.PreferencesGroup = _Stub
        stub.SwitchRow = _Stub
        stub.Label = _Stub
        stub.Picture = _Stub
        stub.Spinner = _Stub
        stub.Orientation = type("Orientation", (), {"HORIZONTAL": 0, "VERTICAL": 1})
        stub.Align = type("Align", (), {"CENTER": 0, "FILL": 1, "START": 2})
        stub.Client = type("Client", (), {"new": staticmethod(lambda: None)})
        setattr(repo_mod, lib, stub)
        sys.modules[f"gi.repository.{lib}"] = stub
        stubs[lib] = stub

    # Adw needs Window for dialog_credits.BootcCreditsWindow(Adw.Window)
    stubs["Adw"].Window = _Stub
    stubs["Adw"].ActionRow = _Stub
    stubs["Adw"].ExpanderRow = _Stub

    # Gio needs these for progress.py GResource lookups and dbus calls
    class _ResourceLookupFlags:
        NONE = 0
    stubs["Gio"].ResourceLookupFlags = _ResourceLookupFlags
    stubs["Gio"].resources_lookup_data = _MagicMock()
    stubs["Gio"].bus_get_sync = _MagicMock()
    stubs["Gio"].BusType = types.SimpleNamespace(SYSTEM=0)
    stubs["Gio"].DBusCallFlags = types.SimpleNamespace(NONE=0)
    stubs["Gio"].File = _MagicMock()
    stubs["GObject"] = types.ModuleType("gi.repository.GObject")
    stubs["GObject"].Property = lambda *a, **kw: (lambda f: property(f))
    repo_mod.GObject = stubs["GObject"]
    sys.modules["gi.repository.GObject"] = stubs["GObject"]

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod

    # Force-reload slurp and its dependencies so class bodies are evaluated
    # with our stubs (not MagicMocks from earlier test files).
    for mod_name in list(sys.modules):
        if "bootc_installer" in mod_name and (
            "slurp" in mod_name or "progress" in mod_name
        ):
            del sys.modules[mod_name]


_build_gi_stubs()

# Now import the helpers we want to test.
from bootc_installer.defaults.slurp import (  # noqa: E402
    _fmt_bytes,
    BootcDefaultSlurp,
)


# ── _fmt_bytes ─────────────────────────────────────────────────────────────────

class TestFmtBytes:
    @pytest.mark.parametrize("size,expected", [
        (0, "0.0 B"),
        (512, "512.0 B"),
        (1023, "1023.0 B"),
        (1024, "1.0 KB"),
        (2048, "2.0 KB"),
        (5 * 1024 ** 2, "5.0 MB"),
        (3 * 1024 ** 3, "3.0 GB"),
        (2 * 1024 ** 4, "2.0 TB"),
    ])
    def test_fmt_bytes(self, size, expected):
        assert _fmt_bytes(size) == expected


# ── BootcDefaultSlurp.should_show ───────────────────────────────────────────

class TestSlurpShouldShow:
    def _step(self):
        from types import SimpleNamespace
        return SimpleNamespace()

    def test_always_true(self):
        assert BootcDefaultSlurp.should_show(self._step(), {}) is True

    def test_true_with_populated_context(self):
        ctx = {"finals": [{"disk": "/dev/sda"}], "leaf_count": 2}
        assert BootcDefaultSlurp.should_show(self._step(), ctx) is True


# ── BootcDefaultSlurp.__get_disk ────────────────────────────────────────────

class TestSlurpGetDisk:
    def _get_disk(self, context):
        from types import SimpleNamespace
        step = SimpleNamespace()
        return BootcDefaultSlurp._BootcDefaultSlurp__get_disk(step, context)

    def test_auto_nested_dict(self):
        ctx = {"finals": [{"disk": {"auto": {"disk": "/dev/sda"}, "filesystem": "xfs"}}]}
        assert self._get_disk(ctx) == "/dev/sda"

    def test_plain_string(self):
        assert self._get_disk({"finals": [{"disk": "/dev/nvme0n1"}]}) == "/dev/nvme0n1"

    def test_empty_string_returns_none(self):
        assert self._get_disk({"finals": [{"disk": ""}]}) is None

    def test_no_finals_returns_none(self):
        assert self._get_disk({}) is None
        assert self._get_disk({"finals": []}) is None
        assert self._get_disk({"finals": [{}]}) is None

    def test_non_dict_finals_entry_skipped(self):
        ctx = {"finals": ["not-a-dict", {"disk": "/dev/sdb"}]}
        assert self._get_disk(ctx) == "/dev/sdb"

    def test_disk_dict_with_disk_key(self):
        ctx = {"finals": [{"disk": {"disk": "/dev/sdc"}}]}
        assert self._get_disk(ctx) == "/dev/sdc"


# ── BootcDefaultSlurp.get_finals ────────────────────────────────────────────

class TestSlurpGetFinals:
    def _get_finals(self, selection):
        from types import SimpleNamespace
        step = SimpleNamespace()
        step._BootcDefaultSlurp__selection = selection
        return BootcDefaultSlurp.get_finals(step)

    def test_empty_selection(self):
        assert self._get_finals({}) == {"slurp": None}

    def test_all_deselected(self):
        sel = {
            ("/dev/sda3", "Alice", "Documents"): False,
            ("/dev/sda3", "Alice", "Pictures"): False,
        }
        assert self._get_finals(sel) == {"slurp": None}

    def test_single_category_selected(self):
        sel = {
            ("/dev/sda3", "Alice", "Documents"): True,
            ("/dev/sda3", "Alice", "Pictures"): False,
        }
        result = self._get_finals(sel)
        assert result["slurp"] is not None
        assert result["slurp"]["sourcePartition"] == "/dev/sda3"
        assert result["slurp"]["users"][0]["name"] == "Alice"
        assert result["slurp"]["users"][0]["categories"] == ["Documents"]

    def test_multiple_categories_same_user(self):
        sel = {
            ("/dev/sda3", "Bob", "Documents"): True,
            ("/dev/sda3", "Bob", "Pictures"): True,
            ("/dev/sda3", "Bob", "Music"): False,
        }
        result = self._get_finals(sel)
        cats = sorted(result["slurp"]["users"][0]["categories"])
        assert cats == ["Documents", "Pictures"]

    def test_multiple_users_same_partition(self):
        sel = {
            ("/dev/sda3", "Alice", "Documents"): True,
            ("/dev/sda3", "Bob", "Pictures"): True,
        }
        result = self._get_finals(sel)
        assert result["slurp"] is not None
        names = {u["name"] for u in result["slurp"]["users"]}
        assert names == {"Alice", "Bob"}

    def test_source_partition_is_first_key(self):
        sel = {("/dev/nvme0n1p3", "Charlie", "Desktop"): True}
        result = self._get_finals(sel)
        assert result["slurp"]["sourcePartition"] == "/dev/nvme0n1p3"

    def test_users_with_no_selected_categories_omitted(self):
        sel = {
            ("/dev/sda3", "Alice", "Documents"): True,
            ("/dev/sda3", "Bob", "Pictures"): False,
        }
        result = self._get_finals(sel)
        names = [u["name"] for u in result["slurp"]["users"]]
        assert "Bob" not in names
        assert "Alice" in names

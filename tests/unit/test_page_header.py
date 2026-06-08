"""Unit tests for widgets/page_header.py.

GObject.Property descriptors are stubbed as plain Python properties so all
getter/setter logic is exercised without a display or GLib main loop.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock


def _build_gi_stubs():
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")

    class _Template:
        def __call__(self, *args, **kwargs):
            return lambda cls: cls

        def Child(self, *args, **kwargs):
            return MagicMock()

    class _StubBase:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    gtk_mod.Template = _Template()
    gtk_mod.Box = _StubBase

    gobject_mod = types.ModuleType("gi.repository.GObject")
    # Stub GObject.Property as a plain Python property decorator so the
    # getter/setter chain works without GLib's type system.
    gobject_mod.Property = lambda *a, **kw: (lambda f: property(f))
    gobject_mod.SignalFlags = types.SimpleNamespace(RUN_FIRST=0)

    for name, mod in [("Gtk", gtk_mod), ("GObject", gobject_mod)]:
        setattr(repo_mod, name, mod)
        sys.modules[f"gi.repository.{name}"] = mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


_build_gi_stubs()


def _import_page_header_fresh():
    """Import page_header under our GObject.Property stubs.

    Uses the canonical reimport pattern (pop + delattr parent) so the module
    is always loaded with the correct stubs regardless of what
    test_branding_parity.py or test_main_args.py have installed.
    """
    import importlib

    sys.modules.pop("bootc_installer.widgets.page_header", None)
    try:
        import bootc_installer.widgets as widgets_pkg
        widgets_pkg.__dict__.pop("page_header", None)
    except Exception:
        pass

    _build_gi_stubs()

    mod = importlib.import_module("bootc_installer.widgets.page_header")
    return mod.BootcPageHeader


class TestPageHeaderProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.BootcPageHeader = _import_page_header_fresh()

    def _make_obj(self):
        obj = self.BootcPageHeader.__new__(self.BootcPageHeader)
        obj._icon = MagicMock()
        obj._title_label = MagicMock()
        obj._subtitle_label = MagicMock()
        return obj

    # --- title ---

    def test_title_setter_calls_set_label(self):
        obj = self._make_obj()
        obj.title = "My Title"
        obj._title_label.set_label.assert_called_with("My Title")

    def test_title_getter_returns_label_text(self):
        obj = self._make_obj()
        obj._title_label.get_label.return_value = "Hello"
        self.assertEqual(obj.title, "Hello")

    def test_title_setter_accepts_empty_string(self):
        obj = self._make_obj()
        obj.title = ""
        obj._title_label.set_label.assert_called_with("")

    # --- icon_name ---

    def test_icon_name_setter_calls_set_from_icon_name(self):
        obj = self._make_obj()
        obj.icon_name = "star-symbolic"
        obj._icon.set_from_icon_name.assert_called_with("star-symbolic")

    def test_icon_name_getter_returns_icon_name(self):
        obj = self._make_obj()
        obj._icon.get_icon_name.return_value = "star-symbolic"
        self.assertEqual(obj.icon_name, "star-symbolic")

    def test_icon_name_getter_returns_empty_string_when_none(self):
        obj = self._make_obj()
        obj._icon.get_icon_name.return_value = None
        self.assertEqual(obj.icon_name, "")

    # --- subtitle ---

    def test_subtitle_setter_calls_set_label(self):
        obj = self._make_obj()
        obj.subtitle = "A subtitle"
        obj._subtitle_label.set_label.assert_called_with("A subtitle")

    def test_subtitle_setter_shows_label_when_non_empty(self):
        obj = self._make_obj()
        obj.subtitle = "Some text"
        obj._subtitle_label.set_visible.assert_called_with(True)

    def test_subtitle_setter_hides_label_when_empty(self):
        obj = self._make_obj()
        obj.subtitle = ""
        obj._subtitle_label.set_visible.assert_called_with(False)

    def test_subtitle_getter_returns_label_text(self):
        obj = self._make_obj()
        obj._subtitle_label.get_label.return_value = "Sub"
        self.assertEqual(obj.subtitle, "Sub")

    # --- helper methods ---

    def test_set_paintable_delegates_to_icon(self):
        obj = self._make_obj()
        paintable = MagicMock()
        obj.set_paintable(paintable)
        obj._icon.set_paintable.assert_called_with(paintable)

    def test_set_from_resource_delegates_to_icon(self):
        obj = self._make_obj()
        obj.set_from_resource("/some/resource/path")
        obj._icon.set_from_resource.assert_called_with("/some/resource/path")


if __name__ == "__main__":
    unittest.main()

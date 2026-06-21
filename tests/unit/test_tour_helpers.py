"""Unit tests for views/tour.py pure asset-routing logic.

__build_ui() resolves different asset URI formats to either set_resource() or
set_filename() on the picture widget.  gi.repository is stubbed at import
time; the BootcTour class is instantiated via __new__ + attribute injection so
no display is required.
"""

import importlib
import os
import sys
import tempfile
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
            return None

    class _Stub:
        pass

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    gtk_mod.Template = _Template()

    adw_mod = types.ModuleType("gi.repository.Adw")
    adw_mod.Bin = _Stub

    for name, mod in [("Gtk", gtk_mod), ("Adw", adw_mod)]:
        setattr(repo_mod, name, mod)
        sys.modules[f"gi.repository.{name}"] = mod

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *a, **kw: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


def _import_tour_fresh():
    _build_gi_stubs()
    sys.modules.pop("bootc_installer.views.tour", None)
    try:
        import bootc_installer.views as vp
        vp.__dict__.pop("tour", None)
    except Exception:
        pass
    return importlib.import_module("bootc_installer.views.tour")


_tour_mod = _import_tour_fresh()


def _make_tour_obj(tour_dict):
    """Build a BootcTour-like object with injected private attrs + mock children."""
    obj = object.__new__(_tour_mod.BootcTour)
    obj._BootcTour__window = MagicMock()
    obj._BootcTour__tour = tour_dict
    obj.page_header = MagicMock()
    obj.assets_svg = MagicMock()
    return obj


class TestTourBuildUiHeaderFields(unittest.TestCase):
    """page_header title/subtitle are set from tour dict."""

    def test_title_set_from_tour(self):
        obj = _make_tour_obj({"title": "Welcome!", "description": "Intro"})
        obj._BootcTour__build_ui()
        self.assertEqual(obj.page_header.title, "Welcome!")

    def test_subtitle_set_from_description(self):
        obj = _make_tour_obj({"title": "T", "description": "Some description"})
        obj._BootcTour__build_ui()
        self.assertEqual(obj.page_header.subtitle, "Some description")

    def test_missing_keys_default_to_empty_string(self):
        obj = _make_tour_obj({})
        obj._BootcTour__build_ui()
        self.assertEqual(obj.page_header.title, "")
        self.assertEqual(obj.page_header.subtitle, "")


class TestTourBuildUiAssetRouting(unittest.TestCase):
    """__build_ui() routes asset URIs to the correct Picture method."""

    def test_resource_triple_slash_calls_set_resource(self):
        """resource:///org/... strips 'resource://' prefix before set_resource()."""
        obj = _make_tour_obj({"resource": "resource:///org/bootcos/tour.svg"})
        obj._BootcTour__build_ui()
        obj.assets_svg.set_resource.assert_called_once_with("/org/bootcos/tour.svg")
        obj.assets_svg.set_filename.assert_not_called()

    def test_resource_double_slash_calls_set_resource(self):
        """resource://org/... strips 'resource://' prefix (no leading slash)."""
        obj = _make_tour_obj({"resource": "resource://org/bootcos/tour.svg"})
        obj._BootcTour__build_ui()
        obj.assets_svg.set_resource.assert_called_once_with("org/bootcos/tour.svg")

    def test_existing_absolute_path_calls_set_filename(self):
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            tmp_path = f.name
        try:
            obj = _make_tour_obj({"image": tmp_path})
            obj._BootcTour__build_ui()
            obj.assets_svg.set_filename.assert_called_once_with(tmp_path)
            obj.assets_svg.set_resource.assert_not_called()
        finally:
            os.unlink(tmp_path)

    def test_absolute_path_not_on_disk_treated_as_gresource(self):
        """/org/... path that does not exist on FS is passed to set_resource()."""
        obj = _make_tour_obj({"image": "/org/bootcos/Installer/images/tour.svg"})
        obj._BootcTour__build_ui()
        obj.assets_svg.set_resource.assert_called_once_with(
            "/org/bootcos/Installer/images/tour.svg"
        )
        obj.assets_svg.set_filename.assert_not_called()

    def test_empty_asset_no_method_called(self):
        obj = _make_tour_obj({"title": "T"})  # no "resource" or "image" key
        obj._BootcTour__build_ui()
        obj.assets_svg.set_resource.assert_not_called()
        obj.assets_svg.set_filename.assert_not_called()

    def test_resource_key_preferred_over_image(self):
        """'resource' key takes precedence when both are present."""
        obj = _make_tour_obj(
            {"resource": "resource:///org/r.svg", "image": "/some/image.svg"}
        )
        obj._BootcTour__build_ui()
        obj.assets_svg.set_resource.assert_called_once_with("/org/r.svg")

    def test_image_used_when_resource_absent(self):
        obj = _make_tour_obj({"image": "resource:///org/i.svg"})
        obj._BootcTour__build_ui()
        obj.assets_svg.set_resource.assert_called_once_with("/org/i.svg")


if __name__ == "__main__":
    unittest.main()

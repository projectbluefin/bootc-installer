"""Unit tests for image.py helpers — no GTK required."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Stub out gi.repository so image.py can be imported without a display.
for _mod in ("gi", "gi.repository", "gi.repository.Adw", "gi.repository.Gdk",
             "gi.repository.Gio", "gi.repository.GLib", "gi.repository.Gtk"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Patch Gio.resources_lookup_data so _load_manifest() uses our fixture manifest.
_FIXTURE_MANIFEST = {
    "fallback_flatpaks": ["org.mozilla.firefox"],
    "default_image": "",
    "images": [
        {
            "name": "Aurora",
            "icon": "resource:///org/bootcinstaller/Installer/images/aurora.svg",
            "children": [
                {
                    "name": "Stable",
                    "imgref": "ghcr.io/ublue-os/aurora:stable",
                    "desc": "Stable build",
                },
                {
                    "name": "Aurora DX",
                    "children": [
                        {
                            "name": "Stable",
                            "imgref": "ghcr.io/ublue-os/aurora-dx:stable",
                            "desc": "DX stable",
                        },
                    ],
                },
            ],
        },
        {
            "name": "Bluefin",
            "icon": "resource:///org/bootcinstaller/Installer/images/bluefin.png",
            "children": [
                {
                    "name": "Latest",
                    "imgref": "ghcr.io/ublue-os/bluefin:latest",
                    "icon": "resource:///org/bootcinstaller/Installer/images/bluefin-lts.png",
                },
            ],
        },
        {
            "name": "NoIcon",
            "children": [
                {
                    "name": "Leaf",
                    "imgref": "ghcr.io/example/noicon:latest",
                },
            ],
        },
    ],
}

import json as _json

_mock_gio_data = MagicMock()
_mock_gio_data.get_data.return_value = _json.dumps(_FIXTURE_MANIFEST).encode()
sys.modules["gi.repository"].Gio.resources_lookup_data.return_value = _mock_gio_data
sys.modules["gi.repository"].Gio.ResourceLookupFlags.NONE = 0

from bootc_installer.defaults.image import _find_icon_for_imgref  # noqa: E402


class TestFindIconForImgref(unittest.TestCase):

    def test_direct_child_inherits_parent_icon(self):
        icon = _find_icon_for_imgref("ghcr.io/ublue-os/aurora:stable")
        self.assertEqual(icon, "resource:///org/bootcinstaller/Installer/images/aurora.svg")

    def test_nested_child_inherits_grandparent_icon(self):
        icon = _find_icon_for_imgref("ghcr.io/ublue-os/aurora-dx:stable")
        self.assertEqual(icon, "resource:///org/bootcinstaller/Installer/images/aurora.svg")

    def test_leaf_with_own_icon_overrides_parent(self):
        # Bluefin:latest has its own icon (bluefin-lts.png) which overrides parent's
        icon = _find_icon_for_imgref("ghcr.io/ublue-os/bluefin:latest")
        self.assertEqual(icon, "resource:///org/bootcinstaller/Installer/images/bluefin-lts.png")

    def test_missing_imgref_returns_none(self):
        icon = _find_icon_for_imgref("ghcr.io/does/not/exist:latest")
        self.assertIsNone(icon)

    def test_empty_imgref_returns_none(self):
        icon = _find_icon_for_imgref("")
        self.assertIsNone(icon)

    def test_node_with_no_icon_returns_none(self):
        icon = _find_icon_for_imgref("ghcr.io/example/noicon:latest")
        self.assertIsNone(icon)


class TestDistroInfoDefaultImageIcon(unittest.TestCase):
    """Verify the distro_info pattern used by builder.py."""

    def test_no_default_image_gives_none_icon(self):
        icon = _find_icon_for_imgref("")
        self.assertIsNone(icon)

    def test_default_image_with_icon_resolves(self):
        icon = _find_icon_for_imgref("ghcr.io/ublue-os/aurora:stable")
        self.assertIsNotNone(icon)
        self.assertTrue(icon.startswith("resource://"))


if __name__ == "__main__":
    unittest.main()


class TestImagesCatalogIntegrity(unittest.TestCase):
    """Regression tests for fisherman/data/images.json content."""

    _CATALOG_PATH = os.path.join(
        os.path.dirname(__file__), "..", "..", "fisherman", "data", "images.json"
    )

    def _all_names_and_descs(self, node):
        """Yield every name/desc string in the tree recursively."""
        if isinstance(node, dict):
            if "name" in node:
                yield node["name"]
            if "desc" in node:
                yield node["desc"]
            if "subtitle" in node:
                yield node["subtitle"]
            if "title" in node:
                yield node["title"]
            for child in node.get("children", []):
                yield from self._all_names_and_descs(child)
        elif isinstance(node, list):
            for item in node:
                yield from self._all_names_and_descs(item)

    def _load_catalog(self):
        with open(self._CATALOG_PATH) as f:
            return _json.load(f)

    def test_no_bare_ampersand_in_names(self):
        """Names must not contain bare & — it breaks Pango markup rendering."""
        catalog = self._load_catalog()
        bad = [s for s in self._all_names_and_descs(catalog) if "&" in s and "&amp;" not in s]
        self.assertEqual(bad, [], f"Bare & found in catalog strings: {bad}")

    def test_no_gaming_label_in_names(self):
        """GDX images are Nvidia+CUDA, not 'Gaming'."""
        catalog = self._load_catalog()
        bad = [s for s in self._all_names_and_descs(catalog) if "Gaming" in s]
        self.assertEqual(bad, [], f"'Gaming' label found (use Nvidia+CUDA): {bad}")

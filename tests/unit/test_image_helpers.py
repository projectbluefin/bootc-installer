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

from bootc_installer.defaults.image import _find_icon_for_imgref, _resolve_aliases  # noqa: E402


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


class TestResolveAliases(unittest.TestCase):
    """Unit tests for the @alias resolution helper."""

    def test_string_value_replaced(self):
        aliases = {"brew_url": "https://example.com/flatpaks.Brewfile"}
        manifest = {"images": [{"name": "Foo", "flatpaks": "@brew_url"}]}
        _resolve_aliases(manifest, aliases)
        self.assertEqual(manifest["images"][0]["flatpaks"], "https://example.com/flatpaks.Brewfile")

    def test_list_value_replaced(self):
        aliases = {"foo": "bar"}
        obj = ["@foo", "baz", "@foo"]
        _resolve_aliases(obj, aliases)
        self.assertEqual(obj, ["bar", "baz", "bar"])

    def test_non_alias_string_left_unchanged(self):
        aliases = {"foo": "bar"}
        manifest = {"name": "NoAlias", "flatpaks": "https://example.com/file"}
        _resolve_aliases(manifest, aliases)
        self.assertEqual(manifest["flatpaks"], "https://example.com/file")

    def test_unknown_alias_left_as_is(self):
        aliases = {"known": "value"}
        manifest = {"key": "@unknown"}
        _resolve_aliases(manifest, aliases)
        self.assertEqual(manifest["key"], "@unknown")

    def test_nested_dict_resolved(self):
        aliases = {"url": "https://host/path"}
        manifest = {"a": {"b": {"flatpaks": "@url"}}}
        _resolve_aliases(manifest, aliases)
        self.assertEqual(manifest["a"]["b"]["flatpaks"], "https://host/path")

    def test_empty_aliases_no_change(self):
        aliases = {}
        manifest = {"key": "@something"}
        _resolve_aliases(manifest, aliases)
        self.assertEqual(manifest["key"], "@something")


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

    def _all_imgrefs(self, nodes, registry_ctx=""):
        """Yield every effective imgref in the tree, resolving registry+tag nodes."""
        for n in nodes:
            registry = n.get("registry", registry_ctx)
            if "imgref" in n:
                yield n["imgref"]
            elif "tag" in n and registry:
                yield f"{registry}:{n['tag']}"
            yield from self._all_imgrefs(n.get("children", []), registry)

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

    def test_default_image_present_and_valid(self):
        """If default_image is set it must exist as a leaf in the tree.

        An absent or empty default_image is valid — the tree starts fully
        collapsed with nothing pre-selected (btn_next disabled until the
        user picks an image).  Distros can override via their own images.json.
        """
        catalog = self._load_catalog()
        default = catalog.get("default_image", "")
        if not default:
            return  # fully-collapsed mode — no default required

        found = list(self._all_imgrefs(catalog.get("images", [])))
        self.assertIn(default, found,
                      f"default_image {default!r} is not a leaf imgref in the tree")

    def test_aliases_resolve_without_unknown_refs(self):
        """Every @alias_name in the catalog must have a corresponding alias definition."""
        catalog = self._load_catalog()
        aliases = catalog.get("aliases", {})

        def _collect_alias_refs(obj):
            if isinstance(obj, dict):
                for key, val in obj.items():
                    if key == "aliases":
                        continue  # skip the definitions dict itself
                    yield from _collect_alias_refs(val)
            elif isinstance(obj, list):
                for item in obj:
                    yield from _collect_alias_refs(item)
            elif isinstance(obj, str) and obj.startswith("@"):
                yield obj[1:]

        unknown = [name for name in _collect_alias_refs(catalog) if name not in aliases]
        self.assertEqual(unknown, [], f"Unknown alias references in images.json: {unknown}")

    def test_registry_tag_nodes_produce_valid_imgrefs(self):
        """Every ``tag`` node must have a ``registry`` in scope (itself or ancestor)."""
        catalog = self._load_catalog()

        def _check(nodes, registry_ctx=""):
            for n in nodes:
                registry = n.get("registry", registry_ctx)
                if "tag" in n and not "imgref" in n:
                    self.assertTrue(
                        registry,
                        f"Node '{n.get('name')}' has 'tag' but no registry in scope"
                    )
                    imgref = f"{registry}:{n['tag']}"
                    self.assertIn(":", imgref,
                                  f"Composed imgref '{imgref}' missing colon")
                _check(n.get("children", []), registry)

        _check(catalog.get("images", []))


if __name__ == "__main__":
    unittest.main()


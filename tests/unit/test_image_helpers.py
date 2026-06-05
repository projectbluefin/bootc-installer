"""Unit tests for image.py helpers — no GTK required."""
import importlib
import json
import os
import sys
import types
import unittest
import urllib.error
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


_mock_gio_data = MagicMock()
_mock_gio_data.get_data.return_value = json.dumps(_FIXTURE_MANIFEST).encode()
sys.modules["gi.repository"].Gio.resources_lookup_data.return_value = _mock_gio_data
sys.modules["gi.repository"].Gio.ResourceLookupFlags.NONE = 0


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

    template = _Template()
    stubs = {}
    for lib in ("Gtk", "Adw", "Gio"):
        stub = types.ModuleType(f"gi.repository.{lib}")
        stub.Template = template
        stub.Bin = _Stub
        setattr(repo_mod, lib, stub)
        sys.modules[f"gi.repository.{lib}"] = stub
        stubs[lib] = stub

    stubs["Gtk"].Image = _Stub
    stubs["Gtk"].CheckButton = _Stub
    stubs["Gtk"].SelectionMode = type("SelectionMode", (), {"NONE": 0})
    stubs["Adw"].ActionRow = _Stub
    stubs["Adw"].ExpanderRow = _Stub

    class _ResourceLookupFlags:
        NONE = 0

    data = MagicMock()
    data.get_data.return_value = json.dumps(_FIXTURE_MANIFEST).encode()
    stubs["Gio"].ResourceLookupFlags = _ResourceLookupFlags
    stubs["Gio"].resources_lookup_data = MagicMock(return_value=data)

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *args, **kwargs: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod



def _import_image_fresh():
    _build_gi_stubs()
    sys.modules.pop("bootc_installer.defaults.image", None)
    try:
        import bootc_installer.defaults as defaults_pkg

        defaults_pkg.__dict__.pop("image", None)
    except Exception:
        pass
    return importlib.import_module("bootc_installer.defaults.image")


import bootc_installer.defaults.image as image_mod  # noqa: E402
from bootc_installer.defaults.image import (  # noqa: E402
    _count_leaves,
    _fetch_remote_flatpak_list,
    _find_icon_for_imgref,
    _imgref_to_pretty_name,
    _load_manifest,
    _make_icon,
    _resolve_aliases,
)


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


class TestPrettyNameHelpers(unittest.TestCase):

    def test_imgref_to_pretty_name_hyphenated_slug(self):
        self.assertEqual(
            _imgref_to_pretty_name("ghcr.io/ublue-os/bluefin-dx:latest"),
            "Bluefin DX",
        )

    def test_imgref_to_pretty_name_single_word(self):
        self.assertEqual(
            _imgref_to_pretty_name("ghcr.io/ublue-os/aurora:stable"),
            "Aurora",
        )

    def test_imgref_to_pretty_name_underscores_become_hyphens(self):
        self.assertEqual(
            _imgref_to_pretty_name("ghcr.io/example/bluefin_dx:latest"),
            "Bluefin DX",
        )

    def test_imgref_to_pretty_name_empty_string(self):
        self.assertEqual(_imgref_to_pretty_name(""), "")

    def test_imgref_to_pretty_name_invalid_imgref_returns_as_is(self):
        self.assertEqual(_imgref_to_pretty_name("bluefin"), "bluefin")


class TestCountLeaves(unittest.TestCase):

    def test_empty_list_has_no_leaves(self):
        self.assertEqual(_count_leaves([]), 0)

    def test_flat_list_counts_all_leaves(self):
        nodes = [
            {"name": "A", "imgref": "ghcr.io/example/a:latest"},
            {"name": "B", "imgref": "ghcr.io/example/b:latest"},
            {"name": "C", "imgref": "ghcr.io/example/c:latest"},
        ]
        self.assertEqual(_count_leaves(nodes), 3)

    def test_nested_groups_count_recursively(self):
        nodes = [
            {
                "name": "Group",
                "children": [
                    {"name": "A", "imgref": "ghcr.io/example/a:latest"},
                    {
                        "name": "Nested",
                        "children": [
                            {"name": "B", "imgref": "ghcr.io/example/b:latest"},
                            {"name": "C", "imgref": "ghcr.io/example/c:latest"},
                        ],
                    },
                ],
            },
        ]
        self.assertEqual(_count_leaves(nodes), 3)

    def test_mixed_groups_and_leaves(self):
        nodes = [
            {"name": "Top", "imgref": "ghcr.io/example/top:latest"},
            {
                "name": "Group",
                "children": [
                    {"name": "Child", "imgref": "ghcr.io/example/child:latest"},
                ],
            },
            {"name": "EmptyGroup", "children": []},
        ]
        self.assertEqual(_count_leaves(nodes), 2)


class TestFetchRemoteFlatpakList(unittest.TestCase):

    @staticmethod
    def _mock_urlopen(text):
        response = MagicMock()
        response.read.return_value = text.encode("utf-8")
        context = MagicMock()
        context.__enter__.return_value = response
        context.__exit__.return_value = False
        return context

    def test_fetch_remote_flatpak_list_parses_brewfile_format(self):
        text = '\n# comment\nflatpak "com.example.App"\n\nflatpak "org.mozilla.Firefox"\n'
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen(text)):
            self.assertEqual(
                _fetch_remote_flatpak_list("https://example.test/Brewfile"),
                ["com.example.App", "org.mozilla.Firefox"],
            )

    def test_fetch_remote_flatpak_list_parses_plain_ref_format(self):
        text = "app/com.example.App/x86_64/stable\napp/org.mozilla.Firefox/x86_64/stable\n"
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen(text)):
            self.assertEqual(
                _fetch_remote_flatpak_list("https://example.test/refs.txt"),
                ["com.example.App", "org.mozilla.Firefox"],
            )

    def test_fetch_remote_flatpak_list_parses_plain_app_ids(self):
        text = "com.example.App\norg.mozilla.Firefox\n"
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen(text)):
            self.assertEqual(
                _fetch_remote_flatpak_list("https://example.test/appids.txt"),
                ["com.example.App", "org.mozilla.Firefox"],
            )

    def test_fetch_remote_flatpak_list_handles_mixed_content(self):
        text = (
            "# comment\n"
            "flatpak \"com.example.BrewfileApp\"\n"
            "app/com.example.RefApp/x86_64/stable\n"
            "runtime/org.freedesktop.Platform/x86_64/24.08\n"
            "org.mozilla.Firefox\n"
            "\n"
        )
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen(text)):
            self.assertEqual(
                _fetch_remote_flatpak_list("https://example.test/mixed.txt"),
                ["com.example.BrewfileApp", "com.example.RefApp", "org.mozilla.Firefox"],
            )

    def test_fetch_remote_flatpak_list_returns_none_on_network_error(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("boom"),
        ):
            self.assertIsNone(_fetch_remote_flatpak_list("https://example.test/down.txt"))

    def test_fetch_remote_flatpak_list_returns_none_when_no_apps_found(self):
        text = "# comment\n\nruntime/org.freedesktop.Platform/x86_64/24.08\n"
        with patch("urllib.request.urlopen", return_value=self._mock_urlopen(text)):
            self.assertIsNone(_fetch_remote_flatpak_list("https://example.test/empty.txt"))


class TestLoadManifestOverrides(unittest.TestCase):

    def test_load_manifest_prefers_user_override(self):
        user_override = "/custom/config/bootc-installer/images.json"
        manifest = {"fallback_flatpaks": [], "images": [{"imgref": "user"}]}

        def exists_side_effect(path):
            return str(path) == user_override

        with (
            patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/config"}, clear=False),
            patch("pathlib.Path.exists", new=lambda path: exists_side_effect(path)),
            patch("pathlib.Path.read_text", new=lambda path, *args, **kwargs: json.dumps(manifest)),
            patch("bootc_installer.defaults.image.Gio.resources_lookup_data") as lookup,
        ):
            self.assertEqual(_load_manifest(), manifest)
            lookup.assert_not_called()

    def test_load_manifest_uses_system_override_when_user_missing(self):
        system_override = "/etc/bootc-installer/images.json"
        manifest = {"fallback_flatpaks": ["org.mozilla.firefox"], "images": []}

        def exists_side_effect(path):
            return str(path) == system_override

        with (
            patch.dict(os.environ, {}, clear=False),
            patch("pathlib.Path.exists", new=lambda path: exists_side_effect(path)),
            patch("pathlib.Path.read_text", new=lambda path, *args, **kwargs: json.dumps(manifest)),
            patch("bootc_installer.defaults.image.Gio.resources_lookup_data") as lookup,
        ):
            self.assertEqual(_load_manifest(), manifest)
            lookup.assert_not_called()

    def test_load_manifest_falls_back_to_system_when_user_override_is_invalid(self):
        user_override = "/custom/config/bootc-installer/images.json"
        system_override = "/etc/bootc-installer/images.json"
        system_manifest = {"fallback_flatpaks": [], "images": [{"imgref": "system"}]}

        def exists_side_effect(path):
            return str(path) in {user_override, system_override}

        def read_text_side_effect(path, *args, **kwargs):
            if str(path) == user_override:
                return "{not-json}"
            if str(path) == system_override:
                return json.dumps(system_manifest)
            raise AssertionError(f"unexpected path: {path}")

        with (
            patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/config"}, clear=False),
            patch("pathlib.Path.exists", new=lambda path: exists_side_effect(path)),
            patch("pathlib.Path.read_text", new=lambda path, *args, **kwargs: read_text_side_effect(path, *args, **kwargs)),
            patch("bootc_installer.defaults.image.Gio.resources_lookup_data") as lookup,
        ):
            self.assertEqual(_load_manifest(), system_manifest)
            lookup.assert_not_called()

    def test_load_manifest_system_override_invalid_json_falls_through(self):
        """When system override exists but has invalid JSON, fall through to GResource."""
        fresh_mod = _import_image_fresh()
        system_override = "/etc/bootc-installer/images.json"
        gresource_manifest = {"fallback_flatpaks": [], "images": [{"imgref": "gresource"}]}

        def exists_side_effect(path):
            return str(path) == system_override

        def read_text_side_effect(path, *a, **kw):
            return "{not-valid-json}"

        gresource_data = MagicMock()
        gresource_data.get_data.return_value = json.dumps(gresource_manifest).encode()
        fresh_mod.Gio.resources_lookup_data = MagicMock(return_value=gresource_data)

        with (
            patch.dict(os.environ, {}, clear=False),
            patch("pathlib.Path.exists", new=lambda path: exists_side_effect(path)),
            patch("pathlib.Path.read_text", new=lambda path, *a, **kw: read_text_side_effect(path)),
        ):
            result = fresh_mod._load_manifest()
        self.assertEqual(result, gresource_manifest)

    def test_load_manifest_uses_gresource_when_no_overrides(self):
        """When no override files exist, load from GResource."""
        fresh_mod = _import_image_fresh()
        gresource_manifest = {"fallback_flatpaks": [], "images": [{"imgref": "bundled"}]}
        gresource_data = MagicMock()
        gresource_data.get_data.return_value = json.dumps(gresource_manifest).encode()
        fresh_mod.Gio.resources_lookup_data = MagicMock(return_value=gresource_data)

        with patch("pathlib.Path.exists", return_value=False):
            result = fresh_mod._load_manifest()
        self.assertEqual(result, gresource_manifest)

    def test_load_manifest_installed_path_fallback(self):
        """When GResource fails, load from installed data path."""
        fresh_mod = _import_image_fresh()
        installed_manifest = {"fallback_flatpaks": [], "images": [{"imgref": "installed"}]}
        fresh_mod.Gio.resources_lookup_data = MagicMock(side_effect=Exception("gresource missing"))

        def read_text_side_effect(path, *a, **kw):
            if str(path).startswith("/app/share") or str(path).startswith("/usr/share"):
                return json.dumps(installed_manifest)
            raise FileNotFoundError(path)

        with patch("pathlib.Path.read_text",
                   new=lambda path, *a, **kw: read_text_side_effect(path)):
            result = fresh_mod._load_manifest()
        self.assertEqual(result, installed_manifest)

    def test_load_manifest_dev_path_fallback(self):
        """When GResource and installed paths fail, fall back to the dev repo path."""
        fresh_mod = _import_image_fresh()
        dev_manifest = {"fallback_flatpaks": [], "images": [{"imgref": "dev"}]}
        fresh_mod.Gio.resources_lookup_data = MagicMock(side_effect=Exception("gresource missing"))

        def read_text_side_effect(path, *a, **kw):
            if "fisherman/data/images.json" in str(path):
                return json.dumps(dev_manifest)
            raise FileNotFoundError(path)

        with patch("pathlib.Path.read_text",
                   new=lambda path, *a, **kw: read_text_side_effect(path)):
            result = fresh_mod._load_manifest()
        self.assertEqual(result, dev_manifest)

    def test_load_manifest_returns_empty_fallback_when_all_fail(self):
        """When all manifest sources fail, return the hardcoded empty fallback."""
        fresh_mod = _import_image_fresh()
        fresh_mod.Gio.resources_lookup_data = MagicMock(side_effect=Exception("gresource missing"))

        with patch("pathlib.Path.read_text", side_effect=FileNotFoundError("not found")):
            result = fresh_mod._load_manifest()
        self.assertEqual(result, {"fallback_flatpaks": [], "images": []})


class TestMakeIcon(unittest.TestCase):

    def test_make_icon_returns_none_for_blank_spec(self):
        with patch.object(image_mod.Gtk, "Image", create=True) as image_cls:
            self.assertIsNone(_make_icon(""))
            image_cls.assert_not_called()

    def test_make_icon_loads_resource_icons(self):
        image = MagicMock()
        with patch.object(image_mod.Gtk, "Image", return_value=image, create=True):
            result = _make_icon("resource:///org/bootcinstaller/Installer/images/foo.svg", size=24)
        self.assertIs(result, image)
        image.set_pixel_size.assert_called_once_with(24)
        image.set_from_resource.assert_called_once_with("/org/bootcinstaller/Installer/images/foo.svg")

    def test_make_icon_loads_filesystem_icons(self):
        image = MagicMock()
        with patch.object(image_mod.Gtk, "Image", return_value=image, create=True):
            result = _make_icon("/usr/share/icons/foo.svg")
        self.assertIs(result, image)
        image.set_from_file.assert_called_once_with("/usr/share/icons/foo.svg")

    def test_make_icon_loads_icon_theme_names(self):
        image = MagicMock()
        with patch.object(image_mod.Gtk, "Image", return_value=image, create=True):
            result = _make_icon("computer-symbolic")
        self.assertIs(result, image)
        image.set_from_icon_name.assert_called_once_with("computer-symbolic")

    def test_make_icon_returns_none_when_loading_fails(self):
        image = MagicMock()
        image.set_from_resource.side_effect = RuntimeError("bad icon")
        with patch.object(image_mod.Gtk, "Image", return_value=image, create=True):
            self.assertIsNone(_make_icon("resource:///bad.svg"))


class TestBootcDefaultImagePureLogic(unittest.TestCase):

    def setUp(self):
        self.mod = _import_image_fresh()
        self.cls = self.mod.BootcDefaultImage

    def _make_widget(self):
        widget = object.__new__(self.cls)
        widget.row_custom = MagicMock()
        widget.image_url_entry = MagicMock()
        widget.btn_next = MagicMock()
        widget._BootcDefaultImage__update_btn_next = MagicMock()
        widget._BootcDefaultImage__radio_anchor = MagicMock()
        widget._BootcDefaultImage__selected_imgref = "ghcr.io/example/default:latest"
        widget._BootcDefaultImage__selected_flatpaks = ["org.default.App"]
        widget._BootcDefaultImage__selected_flatpak_var_path = "/var/lib/flatpak"
        widget._BootcDefaultImage__selected_carousel = ["slide1"]
        widget._BootcDefaultImage__selected_needs_user_creation = True
        widget._BootcDefaultImage__selected_composefs_backend = True
        widget._BootcDefaultImage__selected_image_type = "ostree"
        widget._BootcDefaultImage__selected_bootloader = "grub2"
        widget._BootcDefaultImage__selected_image_filesystem = "xfs"
        widget._BootcDefaultImage__selected_icon = "computer-symbolic"
        widget._BootcDefaultImage__selected_pretty_name = "Example"
        widget._BootcDefaultImage__selected_default_hostname = "example-host"
        widget._BootcDefaultImage__selected_filesystems = ["xfs", "btrfs"]
        return widget

    def test_on_check_toggled_updates_selected_state_for_remote_flatpaks(self):
        widget = self._make_widget()
        check = MagicMock()
        check.get_active.return_value = True
        widget.row_custom.get_expanded.return_value = True

        with patch.object(
            self.mod,
            "_fetch_remote_flatpak_list",
            return_value=["org.remote.App"],
        ) as fetch_remote:
            self.cls._BootcDefaultImage__on_check_toggled(
                widget,
                check,
                "ghcr.io/example/new:latest",
                "https://example.test/flatpaks.txt",
                "computer-symbolic",
                ["slide2"],
                False,
                False,
                "bootc",
                "systemd",
                "btrfs",
                "/var/lib/custom-flatpak",
                "new-host",
                ["btrfs"],
            )

        fetch_remote.assert_called_once_with("https://example.test/flatpaks.txt")
        self.assertEqual(widget._BootcDefaultImage__selected_imgref, "ghcr.io/example/new:latest")
        self.assertEqual(widget._BootcDefaultImage__selected_flatpaks, ["org.remote.App"])
        self.assertEqual(widget._BootcDefaultImage__selected_pretty_name, "New")
        self.assertEqual(widget._BootcDefaultImage__selected_default_hostname, "new-host")
        self.assertEqual(widget._BootcDefaultImage__selected_filesystems, ["btrfs"])
        widget.row_custom.set_expanded.assert_called_once_with(False)
        widget._BootcDefaultImage__update_btn_next.assert_called_once_with()

    def test_on_custom_toggled_resets_selection_for_custom_image(self):
        widget = self._make_widget()
        expander = MagicMock()
        expander.get_expanded.return_value = True

        self.cls._BootcDefaultImage__on_custom_toggled(widget, expander, None)

        widget._BootcDefaultImage__radio_anchor.set_active.assert_called_once_with(True)
        self.assertIsNone(widget._BootcDefaultImage__selected_imgref)
        self.assertIsNone(widget._BootcDefaultImage__selected_icon)
        self.assertIsNone(widget._BootcDefaultImage__selected_carousel)
        self.assertFalse(widget._BootcDefaultImage__selected_needs_user_creation)
        self.assertFalse(widget._BootcDefaultImage__selected_composefs_backend)
        self.assertEqual(widget._BootcDefaultImage__selected_image_type, "bootc")
        self.assertEqual(widget._BootcDefaultImage__selected_bootloader, "")
        self.assertEqual(widget._BootcDefaultImage__selected_image_filesystem, "")
        self.assertIsNone(widget._BootcDefaultImage__selected_pretty_name)
        self.assertEqual(widget._BootcDefaultImage__selected_default_hostname, "")
        self.assertEqual(widget._BootcDefaultImage__selected_filesystems, [])
        widget._BootcDefaultImage__update_btn_next.assert_called_once_with()

    def test_update_btn_next_uses_custom_url_validation(self):
        widget = self._make_widget()
        widget.row_custom.get_expanded.return_value = True
        widget.image_url_entry.get_text.return_value = "ghcr.io/example/custom:latest"

        self.cls._BootcDefaultImage__update_btn_next(widget)

        widget.btn_next.set_sensitive.assert_called_once_with(True)

    def test_on_url_changed_marks_invalid_custom_url(self):
        widget = self._make_widget()
        entry = MagicMock()
        entry.get_text.return_value = "not-a-valid-image"
        widget._BootcDefaultImage__update_btn_next = MagicMock()

        self.cls._BootcDefaultImage__on_url_changed(widget, entry)

        entry.add_css_class.assert_called_once_with("error")
        entry.remove_css_class.assert_not_called()
        widget._BootcDefaultImage__update_btn_next.assert_called_once_with()

    def test_should_show_skip_screen_and_leaf_count_helpers(self):
        widget = self._make_widget()
        self.assertFalse(self.cls.should_show(widget, {"leaf_count": 1}))
        self.assertTrue(self.cls.should_show(widget, {"leaf_count": 2}))
        self.assertEqual(self.cls.leaf_count.fget(widget), 4)
        self.assertFalse(self.cls.skip_screen.fget(widget))

    def test_get_finals_for_selected_catalog_image(self):
        widget = self._make_widget()
        widget.row_custom.get_expanded.return_value = False

        finals = self.cls.get_finals(widget)

        self.assertEqual(finals["selected_image"], "ghcr.io/example/default:latest")
        self.assertEqual(finals["pretty_name"], "Example")
        self.assertEqual(finals["flatpaks"], ["org.default.App"])
        self.assertEqual(finals["flatpak_var_path"], "/var/lib/flatpak")
        self.assertEqual(finals["carousel"], ["slide1"])
        self.assertTrue(finals["needs_user_creation"])
        self.assertTrue(finals["composefs_backend"])
        self.assertEqual(finals["image_type"], "ostree")
        self.assertEqual(finals["bootloader"], "grub2")
        self.assertEqual(finals["image_filesystem"], "xfs")
        self.assertEqual(finals["icon"], "computer-symbolic")
        self.assertEqual(finals["default_hostname"], "example-host")
        self.assertEqual(finals["supported_filesystems"], ["xfs", "btrfs"])

    def test_get_finals_for_custom_image_uses_fallbacks(self):
        widget = self._make_widget()
        widget.row_custom.get_expanded.return_value = True
        widget.image_url_entry.get_text.return_value = "ghcr.io/example/custom-dx:stable"

        finals = self.cls.get_finals(widget)

        self.assertEqual(finals["custom_image"], "ghcr.io/example/custom-dx:stable")
        self.assertEqual(finals["pretty_name"], "Custom DX")
        self.assertEqual(finals["flatpaks"], ["org.mozilla.firefox"])
        self.assertIsNone(finals["carousel"])
        self.assertFalse(finals["needs_user_creation"])
        self.assertFalse(finals["composefs_backend"])
        self.assertEqual(finals["image_type"], "bootc")
        self.assertEqual(finals["bootloader"], "")
        self.assertEqual(finals["image_filesystem"], "")
        self.assertIsNone(finals["icon"])


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
            return json.load(f)

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
                if "tag" in n and "imgref" not in n:
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


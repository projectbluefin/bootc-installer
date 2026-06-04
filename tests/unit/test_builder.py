"""Unit tests for bootc_installer.utils.builder."""

import importlib
import subprocess
import sys
import types
import unittest
from unittest.mock import MagicMock, mock_open, patch


_STUBBED_MODULES = (
    "bootc_installer.defaults.conn_check",
    "bootc_installer.defaults.disk",
    "bootc_installer.defaults.encryption",
    "bootc_installer.defaults.image",
    "bootc_installer.defaults.slurp",
    "bootc_installer.defaults.user",
    "bootc_installer.defaults.welcome",
    "bootc_installer.defaults.qr_companion",
    "bootc_installer.layouts.yes_no",
    "bootc_installer.utils.builder",
)


class _BaseWidget:
    def __init__(self, window, distro_info, key, step):
        self.window = window
        self.distro_info = distro_info
        self.key = key
        self.step = step

    def get_finals(self):
        return {self.key: self.step["template"]}


class _ImageWidget(_BaseWidget):
    leaf_count = 7


class _DiskWidget(_BaseWidget):
    installable_disk_count = 4


class _UserWidget(_BaseWidget):
    pass


class _FakeRecipeLoader:
    def __init__(self, raw):
        self.raw = raw


def _stub_module(module_name, **attrs):
    module = types.ModuleType(module_name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[module_name] = module
    return module


def _import_builder_fresh(default_image="ghcr.io/projectbluefin/bluefin:latest"):
    _stub_module(
        "bootc_installer.defaults.conn_check",
        BootcDefaultConnCheck=type("BootcDefaultConnCheck", (), {}),
    )
    _stub_module(
        "bootc_installer.defaults.disk",
        BootcDefaultDisk=type("BootcDefaultDisk", (), {}),
    )
    _stub_module(
        "bootc_installer.defaults.encryption",
        BootcDefaultEncryption=type("BootcDefaultEncryption", (), {}),
    )
    find_icon = MagicMock(return_value="default-icon")
    _stub_module(
        "bootc_installer.defaults.image",
        BootcDefaultImage=type("BootcDefaultImage", (), {}),
        _DEFAULT_IMAGE=default_image,
        _find_icon_for_imgref=find_icon,
    )
    _stub_module(
        "bootc_installer.defaults.slurp",
        BootcDefaultSlurp=type("BootcDefaultSlurp", (), {}),
    )
    _stub_module(
        "bootc_installer.defaults.user",
        BootcDefaultUsers=type("BootcDefaultUsers", (), {}),
    )
    _stub_module(
        "bootc_installer.defaults.welcome",
        BootcDefaultWelcome=type("BootcDefaultWelcome", (), {}),
    )
    _stub_module(
        "bootc_installer.defaults.qr_companion",
        BootcDefaultQrCompanion=type("BootcDefaultQrCompanion", (), {}),
    )
    _stub_module(
        "bootc_installer.layouts.yes_no",
        BootcLayoutYesNo=type("BootcLayoutYesNo", (), {}),
    )
    sys.modules.pop("bootc_installer.utils.builder", None)
    try:
        import bootc_installer.utils as utils_pkg

        utils_pkg.__dict__.pop("builder", None)
    except Exception:
        pass

    return importlib.import_module("bootc_installer.utils.builder"), find_icon


class TestBuilder(unittest.TestCase):
    def tearDown(self):
        for module_name in _STUBBED_MODULES:
            sys.modules.pop(module_name, None)

        try:
            import bootc_installer.defaults as defaults_pkg

            for attr in (
                "conn_check",
                "disk",
                "encryption",
                "image",
                "slurp",
                "user",
                "welcome",
                "qr_companion",
            ):
                defaults_pkg.__dict__.pop(attr, None)
        except Exception:
            pass

        try:
            import bootc_installer.layouts as layouts_pkg

            layouts_pkg.__dict__.pop("yes_no", None)
        except Exception:
            pass

        try:
            import bootc_installer.utils as utils_pkg

            utils_pkg.__dict__.pop("builder", None)
        except Exception:
            pass

    def test_init_exits_when_recipe_has_no_log_file(self):
        builder_mod, _ = _import_builder_fresh()
        builder_mod.RecipeLoader = lambda: _FakeRecipeLoader(
            {"distro_name": "Bluefin", "distro_logo": "logo.svg", "steps": {}}
        )

        with self.assertRaises(SystemExit):
            builder_mod.Builder(types.SimpleNamespace())

    def test_load_registers_widgets_and_step_metadata(self):
        builder_mod, find_icon = _import_builder_fresh()
        builder_mod.templates = {
            "image": _ImageWidget,
            "disk": _DiskWidget,
            "user": _UserWidget,
        }
        recipe = {
            "log_file": "builder.log",
            "distro_name": "Bluefin",
            "distro_logo": "logo.svg",
            "welcome_title": "Welcome to Bluefin",
            "steps": {
                "image": {"template": "image"},
                "disk": {"template": "disk"},
                "user": {"template": "user"},
                "custom": {"template": "unknown"},
            },
        }
        window = types.SimpleNamespace()
        builder_mod.RecipeLoader = lambda: _FakeRecipeLoader(recipe)

        with patch.object(builder_mod.os.path, "exists", return_value=True):
            builder = builder_mod.Builder(window)

        self.assertIs(window.recipe, recipe)
        self.assertEqual([widget.key for widget in builder.widgets], ["image", "disk", "user"])
        self.assertEqual([widget._bootc_template for widget in builder.widgets], ["image", "disk", "user"])
        self.assertEqual(recipe["steps"]["image"]["num"], 0)
        self.assertEqual(recipe["steps"]["disk"]["num"], 1)
        self.assertEqual(recipe["steps"]["user"]["num"], 2)
        self.assertEqual(len(builder.property_list), 4)
        self.assertIs(window.image_step, builder.widgets[0])
        self.assertEqual(window._image_leaf_count, 7)
        self.assertEqual(window._installable_disk_count, 4)
        self.assertEqual(
            builder.distro_info,
            {
                "name": "Bluefin",
                "logo": "logo.svg",
                "default_image_icon": "default-icon",
                "welcome_title": "Welcome to Bluefin",
            },
        )
        find_icon.assert_called_with("ghcr.io/projectbluefin/bluefin:latest")
        self.assertGreaterEqual(find_icon.call_count, 1)

    def test_missing_log_file_is_created_when_absent(self):
        builder_mod, _ = _import_builder_fresh()
        builder_mod.templates = {}
        recipe = {
            "log_file": "builder.log",
            "distro_name": "Bluefin",
            "distro_logo": "logo.svg",
            "steps": {},
        }
        builder_mod.RecipeLoader = lambda: _FakeRecipeLoader(recipe)

        opener = mock_open()
        with patch.object(builder_mod.os.path, "exists", return_value=False), patch(
            "builtins.open", opener
        ):
            builder_mod.Builder(types.SimpleNamespace())

        opener.assert_called_once_with("builder.log", "a")

    def test_log_creation_failure_is_nonfatal(self):
        builder_mod, _ = _import_builder_fresh()
        builder_mod.templates = {}
        recipe = {
            "log_file": "builder.log",
            "distro_name": "Bluefin",
            "distro_logo": "logo.svg",
            "steps": {},
        }
        builder_mod.RecipeLoader = lambda: _FakeRecipeLoader(recipe)

        with patch.object(builder_mod.os.path, "exists", return_value=False), patch(
            "builtins.open", side_effect=OSError("permission denied")
        ), patch.object(builder_mod.logger, "warning") as warn_logger, patch.object(
            builder_mod.logging, "warning"
        ) as root_warn:
            builder_mod.Builder(types.SimpleNamespace())

        warn_logger.assert_called_once()
        root_warn.assert_called_once()

    def test_display_condition_with_empty_output_skips_step(self):
        builder_mod, _ = _import_builder_fresh()
        builder_mod.templates = {"image": _ImageWidget}
        recipe = {
            "log_file": "builder.log",
            "distro_name": "Bluefin",
            "distro_logo": "logo.svg",
            "steps": {"image": {"template": "image", "display-conditions": ["check-image"]}},
        }
        builder_mod.RecipeLoader = lambda: _FakeRecipeLoader(recipe)

        with patch.object(builder_mod.os.path, "exists", return_value=True), patch.object(
            builder_mod.subprocess, "check_output", return_value=b""
        ):
            builder = builder_mod.Builder(types.SimpleNamespace())

        self.assertEqual(builder.widgets, [])
        self.assertEqual(builder.property_list, [])

    def test_display_condition_called_process_error_skips_step(self):
        builder_mod, _ = _import_builder_fresh()
        builder_mod.templates = {"image": _ImageWidget}
        recipe = {
            "log_file": "builder.log",
            "distro_name": "Bluefin",
            "distro_logo": "logo.svg",
            "steps": {"image": {"template": "image", "display-conditions": ["check-image"]}},
        }
        builder_mod.RecipeLoader = lambda: _FakeRecipeLoader(recipe)

        with patch.object(builder_mod.os.path, "exists", return_value=True), patch.object(
            builder_mod.subprocess,
            "check_output",
            side_effect=subprocess.CalledProcessError(1, "check-image"),
        ):
            builder = builder_mod.Builder(types.SimpleNamespace())

        self.assertEqual(builder.widgets, [])
        self.assertEqual(builder.property_list, [])

    def test_display_condition_nonempty_output_allows_step(self):
        builder_mod, _ = _import_builder_fresh()
        builder_mod.templates = {"image": _ImageWidget}
        recipe = {
            "log_file": "builder.log",
            "distro_name": "Bluefin",
            "distro_logo": "logo.svg",
            "steps": {"image": {"template": "image", "display-conditions": ["check-image"]}},
        }
        builder_mod.RecipeLoader = lambda: _FakeRecipeLoader(recipe)

        with patch.object(builder_mod.os.path, "exists", return_value=True), patch.object(
            builder_mod.subprocess, "check_output", return_value=b"yes"
        ):
            builder = builder_mod.Builder(types.SimpleNamespace())

        self.assertEqual(len(builder.widgets), 1)
        self.assertEqual(builder.widgets[0].key, "image")
        self.assertEqual(len(builder.property_list), 1)

    def test_get_finals_collects_widget_outputs_without_accumulating(self):
        builder_mod, _ = _import_builder_fresh()
        builder_mod.templates = {
            "image": _ImageWidget,
            "user": _UserWidget,
        }
        recipe = {
            "log_file": "builder.log",
            "distro_name": "Bluefin",
            "distro_logo": "logo.svg",
            "steps": {
                "image": {"template": "image"},
                "user": {"template": "user"},
            },
        }
        builder_mod.RecipeLoader = lambda: _FakeRecipeLoader(recipe)

        with patch.object(builder_mod.os.path, "exists", return_value=True):
            builder = builder_mod.Builder(types.SimpleNamespace())

        expected = [{"image": "image"}, {"user": "user"}]
        self.assertEqual(builder.get_finals(), expected)
        self.assertEqual(builder.get_finals(), expected)

    def test_distro_info_omits_default_image_icon_when_default_image_missing(self):
        builder_mod, find_icon = _import_builder_fresh(default_image=None)
        builder_mod.templates = {}
        recipe = {
            "log_file": "builder.log",
            "distro_name": "Bluefin",
            "distro_logo": "logo.svg",
            "steps": {},
        }
        builder_mod.RecipeLoader = lambda: _FakeRecipeLoader(recipe)

        with patch.object(builder_mod.os.path, "exists", return_value=True):
            builder = builder_mod.Builder(types.SimpleNamespace())

        self.assertEqual(
            builder.distro_info,
            {
                "name": "Bluefin",
                "logo": "logo.svg",
                "default_image_icon": None,
                "welcome_title": "",
            },
        )
        find_icon.assert_not_called()

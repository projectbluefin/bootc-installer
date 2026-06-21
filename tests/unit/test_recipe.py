"""Unit tests for utils/recipe.py — RecipeLoader.

All filesystem I/O and subprocess calls are mocked so tests run
without a live system or any recipe files on disk.
"""

import json
import os
import sys
import unittest
from unittest.mock import mock_open, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bootc_installer.utils.recipe import RecipeLoader

# ---------------------------------------------------------------------------
# Minimal valid recipe fixture
# ---------------------------------------------------------------------------

_VALID_RECIPE = {
    "log_file": "/tmp/test.log",
    "distro_name": "TestOS",
    "distro_logo": "/usr/share/logo.svg",
    "steps": {"welcome": {"label": "Welcome"}},
}

_VALID_JSON = json.dumps(_VALID_RECIPE)


def _mock_open_valid():
    return mock_open(read_data=_VALID_JSON)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_with_custom_recipe(recipe_dict, extra_env=None, exist_override=None):
    """Instantiate RecipeLoader with BOOTC_CUSTOM_RECIPE pointing at a fake file."""
    env = {"BOOTC_CUSTOM_RECIPE": "/fake/recipe.json"}
    if extra_env:
        env.update(extra_env)

    def _exists(path):
        if exist_override is not None:
            return exist_override(path)
        return path == "/fake/recipe.json"

    with patch.dict(os.environ, env, clear=False), \
         patch("bootc_installer.utils.recipe.os.path.exists", side_effect=_exists), \
         patch("builtins.open", mock_open(read_data=json.dumps(recipe_dict))):
        return RecipeLoader()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestRecipeValidation(unittest.TestCase):
    def test_valid_recipe_loads(self):
        loader = _load_with_custom_recipe(_VALID_RECIPE)
        self.assertEqual(loader.raw["distro_name"], "TestOS")

    def test_missing_log_file_fails(self):
        bad = {k: v for k, v in _VALID_RECIPE.items() if k != "log_file"}
        with self.assertRaises(SystemExit):
            _load_with_custom_recipe(bad, exist_override=lambda p: p == "/fake/recipe.json")

    def test_missing_distro_name_fails(self):
        bad = {k: v for k, v in _VALID_RECIPE.items() if k != "distro_name"}
        with self.assertRaises(SystemExit):
            _load_with_custom_recipe(bad, exist_override=lambda p: p == "/fake/recipe.json")

    def test_missing_steps_fails(self):
        bad = {k: v for k, v in _VALID_RECIPE.items() if k != "steps"}
        with self.assertRaises(SystemExit):
            _load_with_custom_recipe(bad, exist_override=lambda p: p == "/fake/recipe.json")

    def test_steps_not_dict_fails(self):
        bad = {**_VALID_RECIPE, "steps": ["welcome"]}
        with self.assertRaises(SystemExit):
            _load_with_custom_recipe(bad, exist_override=lambda p: p == "/fake/recipe.json")

    def test_step_value_not_dict_fails(self):
        bad = {**_VALID_RECIPE, "steps": {"welcome": "not-a-dict"}}
        with self.assertRaises(SystemExit):
            _load_with_custom_recipe(bad, exist_override=lambda p: p == "/fake/recipe.json")

    def test_recipe_not_dict_fails(self):
        # Patch json.load to return a list (not a dict) without touching builtins.open,
        # which would otherwise intercept gettext's .mo file reads on Python 3.14.
        _real_open = open

        def _fake_open(path, *args, **kwargs):
            if "/fake/recipe.json" in str(path):
                return mock_open(read_data="[]")()
            return _real_open(path, *args, **kwargs)

        with patch.dict(os.environ, {"BOOTC_CUSTOM_RECIPE": "/fake/recipe.json"}, clear=False), \
             patch("bootc_installer.utils.recipe.os.path.exists", return_value=True), \
             patch("builtins.open", side_effect=_fake_open), \
             patch("bootc_installer.utils.recipe.json.load", return_value=[]):
            with self.assertRaises(SystemExit):
                RecipeLoader()

    def test_empty_steps_is_valid(self):
        recipe = {**_VALID_RECIPE, "steps": {}}
        loader = _load_with_custom_recipe(recipe)
        self.assertEqual(loader.raw["steps"], {})


# ---------------------------------------------------------------------------
# BOOTC_CUSTOM_RECIPE env var
# ---------------------------------------------------------------------------

class TestCustomRecipeEnv(unittest.TestCase):
    def test_custom_recipe_sets_recipe_path(self):
        loader = _load_with_custom_recipe(_VALID_RECIPE)
        self.assertEqual(loader.recipe_path, "/fake/recipe.json")

    def test_custom_recipe_overrides_default_paths(self):
        # Even if default paths "exist", the env var path is used exclusively
        def _exists(path):
            # Both the custom path and a default path "exist"
            return path in ("/fake/recipe.json", "/etc/bootc-installer/recipe.json")

        env = {"BOOTC_CUSTOM_RECIPE": "/fake/recipe.json"}
        with patch.dict(os.environ, env, clear=False), \
             patch("bootc_installer.utils.recipe.os.path.exists", side_effect=_exists), \
             patch("builtins.open", mock_open(read_data=_VALID_JSON)):
            loader = RecipeLoader()
        self.assertEqual(loader.recipe_path, "/fake/recipe.json")


# ---------------------------------------------------------------------------
# No-recipe fallback: demo / preview mode
# ---------------------------------------------------------------------------

class TestNoRecipeFallback(unittest.TestCase):
    def test_demo_mode_continues_without_recipe(self):
        with patch.dict(os.environ, {"BOOTC_DEMO": "1"}, clear=False), \
             patch("bootc_installer.utils.recipe.os.path.exists", return_value=False), \
             patch("bootc_installer.utils.recipe.os.environ.get",
                   side_effect=lambda k, d=None: "1" if k in ("BOOTC_DEMO", "BOOTC_PREVIEW_SCREEN") else d):
            loader = RecipeLoader()
        self.assertIn("log_file", loader.raw)
        self.assertEqual(loader.raw["log_file"], "/tmp/bootc-installer-demo.log")

    def test_preview_mode_continues_without_recipe(self):
        with patch.dict(os.environ, {"BOOTC_PREVIEW_SCREEN": "1"}, clear=False), \
             patch("bootc_installer.utils.recipe.os.path.exists", return_value=False), \
             patch("bootc_installer.utils.recipe.os.environ.get",
                   side_effect=lambda k, d=None: "1" if k in ("BOOTC_DEMO", "BOOTC_PREVIEW_SCREEN") else d):
            loader = RecipeLoader()
        self.assertEqual(loader.raw["distro_name"], "")

    def test_no_recipe_exits_in_normal_mode(self):
        with patch.dict(os.environ, {}, clear=False), \
             patch("bootc_installer.utils.recipe.os.path.exists", return_value=False), \
             patch("bootc_installer.utils.recipe.os.environ.get", return_value=None):
            with self.assertRaises(SystemExit):
                RecipeLoader()


# ---------------------------------------------------------------------------
# Live ISO mode: __enrich() removes image step
# ---------------------------------------------------------------------------

class TestLiveISOEnrich(unittest.TestCase):
    def _load_live(self, recipe, extra_exists=None):
        """Load RecipeLoader with live ISO signals active."""
        recipe_with_image = {**recipe, "steps": {**recipe.get("steps", {}), "image": {"label": "Image"}}}

        def _exists(path):
            # Simulate /run/ostree-booted and recipe file present, no flatpak
            if extra_exists and path in extra_exists:
                return extra_exists[path]
            return path in ("/fake/recipe.json", "/run/ostree-booted")

        env = {"BOOTC_CUSTOM_RECIPE": "/fake/recipe.json"}
        with patch.dict(os.environ, env, clear=False), \
             patch("bootc_installer.utils.recipe.os.path.exists", side_effect=_exists), \
             patch("builtins.open", mock_open(read_data=json.dumps(recipe_with_image))), \
             patch("bootc_installer.utils.recipe.RecipeLoader._in_flatpak", False):
            return RecipeLoader()

    def test_live_iso_removes_image_step(self):
        loader = self._load_live(_VALID_RECIPE)
        self.assertNotIn("image", loader.raw.get("steps", {}))

    def test_live_iso_mode_uses_imgref_from_recipe(self):
        recipe = {**_VALID_RECIPE, "imgref": "ghcr.io/testorg/testimage:latest"}
        loader = self._load_live(recipe)
        self.assertEqual(loader.raw.get("imgref"), "ghcr.io/testorg/testimage:latest")

    def test_live_iso_local_imgref_override_keeps_imgref(self):
        recipe = {
            **_VALID_RECIPE,
            "imgref": "ghcr.io/testorg/testimage:latest",
            "local_imgref": "containers-storage:ghcr.io/testorg/testimage:latest",
        }
        loader = self._load_live(recipe)
        # imgref stays as the remote tracking ref when local_imgref is set
        self.assertEqual(loader.raw.get("imgref"), "ghcr.io/testorg/testimage:latest")

    def test_non_live_image_step_preserved(self):
        recipe = {**_VALID_RECIPE, "steps": {"welcome": {}, "image": {"label": "Image"}}}
        env = {"BOOTC_CUSTOM_RECIPE": "/fake/recipe.json"}

        def _exists(path):
            # No live ISO signals
            return path == "/fake/recipe.json"

        with patch.dict(os.environ, env, clear=False), \
             patch("bootc_installer.utils.recipe.os.path.exists", side_effect=_exists), \
             patch("builtins.open", mock_open(read_data=json.dumps(recipe))), \
             patch("bootc_installer.utils.recipe.RecipeLoader._in_flatpak", False):
            loader = RecipeLoader()
        self.assertIn("image", loader.raw.get("steps", {}))


# ---------------------------------------------------------------------------
# recipe_paths property
# ---------------------------------------------------------------------------

class TestRecipePaths(unittest.TestCase):
    def test_recipe_paths_contains_expected_locations(self):
        # Instantiate in demo mode to avoid SystemExit
        with patch.dict(os.environ, {"BOOTC_DEMO": "1"}, clear=False), \
             patch("bootc_installer.utils.recipe.os.path.exists", return_value=False), \
             patch("bootc_installer.utils.recipe.os.environ.get",
                   side_effect=lambda k, d=None: "1" if k in ("BOOTC_DEMO", "BOOTC_PREVIEW_SCREEN") else d):
            loader = RecipeLoader()
        paths = loader.recipe_paths
        self.assertTrue(any("bootc-installer" in p for p in paths))
        self.assertTrue(any("recipe.json" in p for p in paths))


if __name__ == "__main__":
    unittest.main()

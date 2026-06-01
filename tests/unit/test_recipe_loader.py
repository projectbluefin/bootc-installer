"""Unit tests for RecipeLoader (utils/recipe.py)."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, mock_open, MagicMock

# Add bootc_installer to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bootc_installer.utils.recipe import RecipeLoader


class TestRecipeLoaderInit(unittest.TestCase):
    """Tests for RecipeLoader.__init__ and recipe_paths property."""

    def test_recipe_paths_default(self):
        """recipe_paths should return the standard search paths."""
        loader = object.__new__(RecipeLoader)  # skip __init__
        loader._in_flatpak = False
        loader._etc = "/etc"
        paths = loader.recipe_paths
        self.assertEqual(len(paths), 4)
        self.assertIn("/etc/bootc-installer/recipe.json", paths)
        self.assertIn("/etc/bootcos-installer/recipe.json", paths)
        self.assertIn("/app/share/bootc-installer/recipe.json", paths)

    def test_recipe_paths_flatpak(self):
        """In Flatpak mode, /etc paths are prefixed with /run/host."""
        loader = object.__new__(RecipeLoader)
        loader._in_flatpak = True
        loader._etc = "/run/host/etc"
        paths = loader.recipe_paths
        self.assertTrue(all(p.startswith("/run/host/etc") or p == "/app/share/bootc-installer/recipe.json" for p in paths))


class TestRecipeLoaderValidate(unittest.TestCase):
    """Tests for RecipeLoader.__validate method."""

    def setUp(self):
        self.loader = object.__new__(RecipeLoader)
        self.loader._in_flatpak = False
        self.loader._etc = "/etc"
        self.loader.recipe_path = None

    def set_recipe(self, data):
        self.loader._RecipeLoader__recipe = data

    def test_valid_recipe(self):
        """A complete recipe with all essential keys should validate."""
        self.set_recipe({
            "log_file": "/tmp/test.log",
            "distro_name": "Test OS",
            "distro_logo": "logo.png",
            "steps": {"partition": {"type": "auto"}}
        })
        self.assertTrue(self.loader._RecipeLoader__validate())

    def test_missing_log_file(self):
        """A recipe missing 'log_file' should fail validation."""
        self.set_recipe({
            "distro_name": "Test OS",
            "distro_logo": "logo.png",
            "steps": {}
        })
        self.assertFalse(self.loader._RecipeLoader__validate())

    def test_missing_distro_name(self):
        """A recipe missing 'distro_name' should fail validation."""
        self.set_recipe({
            "log_file": "/tmp/test.log",
            "distro_logo": "logo.png",
            "steps": {}
        })
        self.assertFalse(self.loader._RecipeLoader__validate())

    def test_missing_distro_logo(self):
        """A recipe missing 'distro_logo' should fail validation."""
        self.set_recipe({
            "log_file": "/tmp/test.log",
            "distro_name": "Test OS",
            "steps": {}
        })
        self.assertFalse(self.loader._RecipeLoader__validate())

    def test_missing_steps(self):
        """A recipe missing 'steps' should fail validation."""
        self.set_recipe({
            "log_file": "/tmp/test.log",
            "distro_name": "Test OS",
            "distro_logo": "logo.png"
        })
        self.assertFalse(self.loader._RecipeLoader__validate())

    def test_not_a_dict(self):
        """A non-dict recipe should fail validation."""
        self.set_recipe(["list", "not", "dict"])
        self.assertFalse(self.loader._RecipeLoader__validate())

    def test_steps_not_a_dict(self):
        """Steps that are not a dict should fail validation."""
        self.set_recipe({
            "log_file": "/tmp/test.log",
            "distro_name": "Test OS",
            "distro_logo": "logo.png",
            "steps": "not a dict"
        })
        self.assertFalse(self.loader._RecipeLoader__validate())

    def test_step_value_not_dict(self):
        """A step whose value is not a dict should fail validation."""
        self.set_recipe({
            "log_file": "/tmp/test.log",
            "distro_name": "Test OS",
            "distro_logo": "logo.png",
            "steps": {"bad_step": "not a dict"}
        })
        self.assertFalse(self.loader._RecipeLoader__validate())


class TestRecipeLoaderEnrich(unittest.TestCase):
    """Tests for RecipeLoader.__enrich (live ISO detection)."""

    def setUp(self):
        self.loader = object.__new__(RecipeLoader)
        self.loader._in_flatpak = False
        self.loader._etc = "/etc"
        self.loader.recipe_path = None
        self.set_recipe({
            "log_file": "/tmp/test.log",
            "distro_name": "Test OS",
            "distro_logo": "logo.png",
            "steps": {"image": {"type": "select"}, "partition": {"type": "auto"}}
        })

    def set_recipe(self, data):
        self.loader._RecipeLoader__recipe = data

    @patch("os.path.exists")
    def test_normal_mode_keeps_image_step(self, mock_exists):
        """In normal mode, image selection step should be retained."""
        mock_exists.return_value = False  # not live ISO, no flatpak
        self.loader._in_flatpak = False
        self.loader._RecipeLoader__enrich()
        self.assertIn("image", self.loader._RecipeLoader__recipe["steps"])

    @patch("os.path.exists")
    def test_live_iso_removes_image_step(self, mock_exists):
        """In live ISO mode, image selection step should be removed."""
        mock_exists.return_value = True  # simulate live ISO
        self.set_recipe({
            "log_file": "/tmp/test.log",
            "distro_name": "Test OS",
            "distro_logo": "logo.png",
            "steps": {"image": {"type": "select"}, "partition": {"type": "auto"}},
            "imgref": "ghcr.io/test/image:latest"
        })
        self.loader._RecipeLoader__enrich()
        self.assertNotIn("image", self.loader._RecipeLoader__recipe["steps"])

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_live_iso_detects_bootc_image(self, mock_run, mock_exists):
        """In live ISO mode without imgref, should detect via bootc status."""
        mock_exists.side_effect = lambda path: True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"status": {"booted": {"image": {"image": {"image": "containers-storage:ghcr.io/test:latest"}}}}}),
            stderr=""
        )
        self.loader._RecipeLoader__enrich()
        self.assertEqual(
            self.loader._RecipeLoader__recipe["imgref"],
            "containers-storage:ghcr.io/test:latest"
        )

    @patch("os.path.exists")
    def test_local_imgref_preserves_imgref(self, mock_exists):
        """When local_imgref is set, imgref should stay as the remote tracking ref."""
        mock_exists.return_value = True
        self.set_recipe({
            "log_file": "/tmp/test.log",
            "distro_name": "Test OS",
            "distro_logo": "logo.png",
            "steps": {"partition": {"type": "auto"}},
            "local_imgref": "containers-storage:ghcr.io/test:local",
            "imgref": "ghcr.io/test/remote:latest"
        })
        self.loader._RecipeLoader__enrich()
        self.assertEqual(
            self.loader._RecipeLoader__recipe["imgref"],
            "ghcr.io/test/remote:latest"
        )


class TestRecipeLoaderDetectBootcImage(unittest.TestCase):
    """Tests for RecipeLoader.__detect_local_bootc_image."""

    def setUp(self):
        self.loader = object.__new__(RecipeLoader)
        self.loader._in_flatpak = False
        self.loader._etc = "/etc"
        self.loader.recipe_path = None

    @patch("subprocess.run")
    def test_detects_valid_image(self, mock_run):
        """Should parse bootc status JSON and return the image ref."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "status": {
                    "booted": {
                        "image": {"image": {"image": "ghcr.io/org/image:latest"}}
                    }
                }
            }),
            stderr=""
        )
        result = self.loader._RecipeLoader__detect_local_bootc_image()
        self.assertEqual(result, "ghcr.io/org/image:latest")

    @patch("subprocess.run")
    def test_bootc_status_failure_returns_empty(self, mock_run):
        """Should return empty string when bootc status fails."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = self.loader._RecipeLoader__detect_local_bootc_image()
        self.assertEqual(result, "")

    @patch("subprocess.run")
    def test_bootc_status_exception_returns_empty(self, mock_run):
        """Should return empty string on exception."""
        mock_run.side_effect = FileNotFoundError("bootc not found")
        result = self.loader._RecipeLoader__detect_local_bootc_image()
        self.assertEqual(result, "")


class TestRecipeLoaderCustomRecipe(unittest.TestCase):
    """Tests for BOOTC_CUSTOM_RECIPE environment variable support."""

    def setUp(self):
        # Create a temp recipe file
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({
            "log_file": "/tmp/custom.log",
            "distro_name": "Custom OS",
            "distro_logo": "custom.png",
            "steps": {"custom_step": {"type": "shell", "command": "echo hi"}}
        }, self.tmp)
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    @patch.dict(os.environ, {}, clear=True)
    @patch("os.path.exists")
    def test_custom_recipe_env_overrides_paths(self, mock_exists):
        """BOOTC_CUSTOM_RECIPE env var should override default recipe paths."""
        # Only the custom path should exist (or be checked)
        mock_exists.return_value = False  # all default paths don't exist
        os.environ["BOOTC_CUSTOM_RECIPE"] = self.tmp.name

        # We need the custom file to exist
        mock_exists.side_effect = lambda p: p == self.tmp.name

        loader = RecipeLoader()
        self.assertEqual(loader.recipe_path, self.tmp.name)
        self.assertEqual(loader.raw["distro_name"], "Custom OS")


if __name__ == "__main__":
    unittest.main()

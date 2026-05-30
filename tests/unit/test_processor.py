"""Unit tests for utils/processor.py — pure Python, no GTK required."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bootc_installer.utils.processor import Processor

# A minimal system recipe (the bootc recipe.json, NOT the fisherman recipe).
_SYS_RECIPE = {}


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ── Auto-disk helpers ──────────────────────────────────────────────────────────

def _auto_finals(disk="/dev/vda", fs="xfs", image="ghcr.io/tuna-os/yellowfin:gnome",
                 hostname="testhost", encryption=None, user=None, flatpaks=None,
                 composefs=False, image_type="bootc", bootloader="", image_filesystem="",
                 flatpak_var_path=""):
    d = {
        "disk": {
            "auto": {"disk": disk, "pretty_size": "100 GB", "size": 100_000_000_000},
            "filesystem": fs,
            "btrfsSubvolumes": fs == "btrfs",
        },
        "selected_image": image,
        "hostname": hostname,
        "flatpaks": flatpaks or [],
        "composefs_backend": composefs,
        "image_type": image_type,
        "bootloader": bootloader,
        "image_filesystem": image_filesystem,
        "flatpak_var_path": flatpak_var_path,
    }
    if encryption:
        d["encryption"] = encryption
    else:
        d["encryption"] = {"use_encryption": False}
    if user:
        d["user"] = user
    return [d]


# ── Auto-disk tests ────────────────────────────────────────────────────────────

class TestAutoDisk:
    def test_basic_xfs(self, tmp_path):
        path = Processor.gen_install_recipe("log", _auto_finals(), _SYS_RECIPE)
        r = _load(path)
        assert r["disk"] == "/dev/vda"
        assert r["filesystem"] == "xfs"
        assert "customMounts" not in r or r.get("customMounts") == []

    def test_selects_disk(self, tmp_path):
        path = Processor.gen_install_recipe("log", _auto_finals(disk="/dev/nvme0n1"), _SYS_RECIPE)
        r = _load(path)
        assert r["disk"] == "/dev/nvme0n1"

    def test_image_propagated(self):
        img = "ghcr.io/ublue-os/bluefin:stable"
        path = Processor.gen_install_recipe("log", _auto_finals(image=img), _SYS_RECIPE)
        r = _load(path)
        assert r["image"] == img

    def test_target_imgref_no_docker_prefix(self):
        # Regression: targetImgref must be a bare reference, not docker://ghcr.io/...
        # If docker:// is prepended here, bootc stores it verbatim and subsequent
        # `bootc update` calls prepend it again → double prefix → broken updates.
        img = "ghcr.io/projectbluefin/dakota:latest"
        path = Processor.gen_install_recipe("log", _auto_finals(image=img), _SYS_RECIPE)
        r = _load(path)
        assert r["targetImgref"] == img
        assert not r["targetImgref"].startswith("docker://")

    def test_hostname_propagated(self):
        path = Processor.gen_install_recipe("log", _auto_finals(hostname="mybox"), _SYS_RECIPE)
        r = _load(path)
        assert r["hostname"] == "mybox"

    def test_flatpaks_propagated(self):
        flatpaks = ["org.mozilla.firefox", "org.gnome.Fractal"]
        path = Processor.gen_install_recipe("log", _auto_finals(flatpaks=flatpaks), _SYS_RECIPE)
        r = _load(path)
        assert r["flatpaks"] == flatpaks

    def test_fallback_hostname_from_sys_recipe(self):
        finals = [{"disk": {"auto": {"disk": "/dev/vda"}}, "selected_image": "ghcr.io/x:y",
                   "encryption": {"use_encryption": False}}]
        path = Processor.gen_install_recipe("log", finals, {"hostname": "fallback-host"})
        r = _load(path)
        assert r["hostname"] == "fallback-host"

    def test_fallback_hostname_default(self):
        """When no hostname is specified, a hardware-derived hostname is generated."""
        finals = [{"disk": {"auto": {"disk": "/dev/vda"}}, "selected_image": "ghcr.io/x:y",
                   "encryption": {"use_encryption": False}}]
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        # Hardware-derived hostname: lowercase, contains hyphens, ends with 4-char hex suffix
        assert r["hostname"]  # non-empty
        assert r["hostname"] != "dakota"  # not the old hardcoded default
        import re
        assert re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", r["hostname"])


# ── Encryption tests ───────────────────────────────────────────────────────────

class TestEncryption:
    def test_no_encryption(self):
        path = Processor.gen_install_recipe(
            "log", _auto_finals(encryption={"use_encryption": False}), _SYS_RECIPE)
        r = _load(path)
        assert r["encryption"]["type"] == "none"
        assert r["encryption"]["passphrase"] == ""

    def test_luks_passphrase(self):
        enc = {"use_encryption": True, "type": "luks-passphrase", "encryption_key": "s3cr3t"}
        path = Processor.gen_install_recipe("log", _auto_finals(encryption=enc), _SYS_RECIPE)
        r = _load(path)
        assert r["encryption"]["type"] == "luks-passphrase"
        assert r["encryption"]["passphrase"] == "s3cr3t"

    def test_tpm2_luks(self):
        enc = {"use_encryption": True, "type": "tpm2-luks"}
        path = Processor.gen_install_recipe("log", _auto_finals(encryption=enc), _SYS_RECIPE)
        r = _load(path)
        assert r["encryption"]["type"] == "tpm2-luks"

    def test_tpm2_luks_passphrase(self):
        enc = {"use_encryption": True, "type": "tpm2-luks-passphrase", "encryption_key": "pw"}
        path = Processor.gen_install_recipe("log", _auto_finals(encryption=enc), _SYS_RECIPE)
        r = _load(path)
        assert r["encryption"]["type"] == "tpm2-luks-passphrase"
        assert r["encryption"]["passphrase"] == "pw"

    def test_key_without_explicit_type_defaults_to_luks_passphrase(self):
        enc = {"use_encryption": True, "encryption_key": "mykey"}
        path = Processor.gen_install_recipe("log", _auto_finals(encryption=enc), _SYS_RECIPE)
        r = _load(path)
        assert r["encryption"]["type"] == "luks-passphrase"
        assert r["encryption"]["passphrase"] == "mykey"

    def test_no_key_and_no_type_defaults_to_tpm2(self):
        enc = {"use_encryption": True}
        path = Processor.gen_install_recipe("log", _auto_finals(encryption=enc), _SYS_RECIPE)
        r = _load(path)
        assert r["encryption"]["type"] == "tpm2-luks"


# ── Manual partitioning tests ──────────────────────────────────────────────────

class TestManualDisk:
    def _manual_finals(self, partitions: dict):
        return [{
            "disk": partitions,
            "selected_image": "ghcr.io/x:y",
            "hostname": "manualhost",
            "flatpaks": [],
            "encryption": {"use_encryption": False},
        }]

    def test_basic_manual_layout(self):
        partitions = {
            "/dev/sda1": {"fs": "fat32", "mp": "/boot/efi"},
            "/dev/sda2": {"fs": "ext4",  "mp": "/boot"},
            "/dev/sda3": {"fs": "xfs",   "mp": "/"},
        }
        path = Processor.gen_install_recipe("log", self._manual_finals(partitions), _SYS_RECIPE)
        r = _load(path)
        assert "customMounts" in r
        mounts = {m["target"]: m for m in r["customMounts"]}
        assert mounts["/"]["partition"] == "/dev/sda3"
        assert mounts["/"]["fstype"] == "xfs"
        assert mounts["/boot/efi"]["partition"] == "/dev/sda1"
        assert mounts["/boot/efi"]["fstype"] == "fat32"
        assert mounts["/boot"]["partition"] == "/dev/sda2"
        assert mounts["/boot"]["fstype"] == "ext4"

    def test_manual_does_not_set_disk_field(self):
        partitions = {
            "/dev/sda1": {"fs": "fat32", "mp": "/boot/efi"},
            "/dev/sda2": {"fs": "xfs",   "mp": "/"},
        }
        path = Processor.gen_install_recipe("log", self._manual_finals(partitions), _SYS_RECIPE)
        r = _load(path)
        assert r.get("disk", "") == ""

    def test_unformatted_partition(self):
        partitions = {
            "/dev/sda1": {"fs": "unformatted", "mp": "/boot/efi"},
            "/dev/sda2": {"fs": "xfs",         "mp": "/"},
        }
        path = Processor.gen_install_recipe("log", self._manual_finals(partitions), _SYS_RECIPE)
        r = _load(path)
        mounts = {m["target"]: m for m in r["customMounts"]}
        assert mounts["/boot/efi"]["fstype"] == "unformatted"

    def test_swap_partition_included(self):
        partitions = {
            "/dev/sda1": {"fs": "fat32", "mp": "/boot/efi"},
            "/dev/sda2": {"fs": "xfs",   "mp": "/"},
            "/dev/sda3": {"fs": "swap",  "mp": "swap"},
        }
        path = Processor.gen_install_recipe("log", self._manual_finals(partitions), _SYS_RECIPE)
        r = _load(path)
        mounts = {m["target"]: m for m in r["customMounts"]}
        assert "swap" in mounts
        assert mounts["swap"]["partition"] == "/dev/sda3"

    def test_auto_takes_precedence_over_manual_check(self):
        """auto key means auto-partition, not manual."""
        finals = [{"disk": {"auto": {"disk": "/dev/sda"}}, "selected_image": "ghcr.io/x:y",
                   "hostname": "h", "encryption": {"use_encryption": False}}]
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert "customMounts" not in r or not r.get("customMounts")
        assert r["disk"] == "/dev/sda"


# ── User spec tests ────────────────────────────────────────────────────────────

class TestSlurpSpec:
    def test_slurp_omitted_when_not_selected(self):
        path = Processor.gen_install_recipe("log", _auto_finals(), _SYS_RECIPE)
        r = _load(path)
        assert "slurp" not in r

    def test_slurp_propagated(self):
        finals = _auto_finals()
        finals[0]["slurp"] = {
            "sourcePartition": "/dev/nvme0n1p3",
            "users": [
                {
                    "name": "JohnDoe",
                    "categories": ["Documents", "Pictures"],
                }
            ],
        }
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert r["slurp"] == finals[0]["slurp"]


class TestUserSpec:
    def test_user_propagated(self):
        user = {"username": "alice", "fullname": "Alice Smith", "password": "pass1",
                "groups": ["wheel"]}
        path = Processor.gen_install_recipe("log", _auto_finals(user=user), _SYS_RECIPE)
        r = _load(path)
        assert r["user"]["username"] == "alice"
        assert r["user"]["fullname"] == "Alice Smith"
        assert r["user"]["password"] == "pass1"
        assert r["user"]["groups"] == ["wheel"]

    def test_empty_user_when_not_provided(self):
        path = Processor.gen_install_recipe("log", _auto_finals(), _SYS_RECIPE)
        r = _load(path)
        assert r["user"]["username"] == ""

    def test_user_groups_default_empty(self):
        user = {"username": "bob", "password": "p"}
        path = Processor.gen_install_recipe("log", _auto_finals(user=user), _SYS_RECIPE)
        r = _load(path)
        assert r["user"]["groups"] == []


# ── unified storage tests ─────────────────────────────────────────────────────

class TestUnifiedStorage:
    def test_unified_storage_true_by_default(self):
        path = Processor.gen_install_recipe("log", _auto_finals(), _SYS_RECIPE)
        r = _load(path)
        assert r.get("unifiedStorage") is True

    def test_sys_recipe_can_disable_unified_storage(self):
        sys = {**_SYS_RECIPE, "unifiedStorage": False}
        path = Processor.gen_install_recipe("log", _auto_finals(), sys)
        r = _load(path)
        assert r.get("unifiedStorage") is False


# ── composefs + image_type tests ──────────────────────────────────────────────

class TestComposefs:
    def test_composefs_false_by_default(self):
        path = Processor.gen_install_recipe("log", _auto_finals(), _SYS_RECIPE)
        r = _load(path)
        assert r.get("composeFsBackend", False) is False

    def test_composefs_true_when_set(self):
        path = Processor.gen_install_recipe("log", _auto_finals(composefs=True), _SYS_RECIPE)
        r = _load(path)
        assert r["composeFsBackend"] is True

    def test_image_type_bootc_default(self):
        path = Processor.gen_install_recipe("log", _auto_finals(), _SYS_RECIPE)
        r = _load(path)
        # bootc is the default — field may be omitted or set to "bootc"
        assert r.get("imageType", "bootc") == "bootc"

    def test_image_type_ostree(self):
        path = Processor.gen_install_recipe(
            "log", _auto_finals(image_type="ostree"), _SYS_RECIPE)
        r = _load(path)
        assert r.get("imageType") == "ostree"

    def test_bootloader_default_empty(self):
        path = Processor.gen_install_recipe("log", _auto_finals(), _SYS_RECIPE)
        r = _load(path)
        assert r.get("bootloader", "") == ""

    def test_bootloader_systemd_propagates(self):
        path = Processor.gen_install_recipe(
            "log", _auto_finals(bootloader="systemd"), _SYS_RECIPE)
        r = _load(path)
        assert r["bootloader"] == "systemd"

    def test_image_filesystem_overrides_disk_filesystem(self):
        # Even if disk step says xfs, if the image requires btrfs it wins.
        path = Processor.gen_install_recipe(
            "log", _auto_finals(fs="xfs", image_filesystem="btrfs"), _SYS_RECIPE)
        r = _load(path)
        assert r["filesystem"] == "btrfs"

    def test_image_filesystem_empty_does_not_override(self):
        path = Processor.gen_install_recipe(
            "log", _auto_finals(fs="xfs", image_filesystem=""), _SYS_RECIPE)
        r = _load(path)
        assert r["filesystem"] == "xfs"

    def test_disk_step_btrfs_selection(self):
        # When the disk step picks btrfs (user chose it from filesystem dropdown),
        # the recipe must reflect btrfs + subvolumes=True.
        path = Processor.gen_install_recipe(
            "log", _auto_finals(fs="btrfs"), _SYS_RECIPE)
        r = _load(path)
        assert r["filesystem"] == "btrfs"
        assert r["btrfsSubvolumes"] is True

    def test_disk_step_xfs_no_subvolumes(self):
        # XFS selection must never set btrfsSubvolumes=True.
        path = Processor.gen_install_recipe(
            "log", _auto_finals(fs="xfs"), _SYS_RECIPE)
        r = _load(path)
        assert r["filesystem"] == "xfs"
        assert r.get("btrfsSubvolumes", False) is False

    def test_dakota_recipe_fields(self):
        """Simulate a Dakota image selection producing the full expected recipe."""
        path = Processor.gen_install_recipe("log", _auto_finals(
            image="ghcr.io/projectbluefin/dakota:latest",
            composefs=True,
            bootloader="systemd",
            image_filesystem="btrfs",
            flatpak_var_path="state/os/default/var",
        ), _SYS_RECIPE)
        r = _load(path)
        assert r["composeFsBackend"] is True
        assert r["bootloader"] == "systemd"
        assert r["filesystem"] == "btrfs"
        assert r["flatpakVarPath"] == "state/os/default/var"

    def test_flatpak_var_path_absent_when_empty(self):
        """flatpakVarPath should be omitted from the recipe when not set."""
        path = Processor.gen_install_recipe("log", _auto_finals(
            flatpak_var_path="",
        ), _SYS_RECIPE)
        r = _load(path)
        assert "flatpakVarPath" not in r

    def test_flatpak_var_path_propagated(self):
        """flatpak_var_path from image metadata must appear in the recipe."""
        path = Processor.gen_install_recipe("log", _auto_finals(
            flatpak_var_path="state/os/default/var",
        ), _SYS_RECIPE)
        r = _load(path)
        assert r["flatpakVarPath"] == "state/os/default/var"


# ── Misc / edge cases ──────────────────────────────────────────────────────────

class TestMisc:
    def test_returns_path_to_existing_file(self):
        path = Processor.gen_install_recipe("log", _auto_finals(), _SYS_RECIPE)
        assert os.path.exists(path)
        assert path.endswith(".json")

    def test_recipe_is_valid_json(self):
        path = Processor.gen_install_recipe("log", _auto_finals(), _SYS_RECIPE)
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_multiple_finals_dicts_merged(self):
        finals = [
            {"selected_image": "ghcr.io/x:y"},
            {"hostname": "mergedhost"},
            {"disk": {"auto": {"disk": "/dev/vda"}}},
            {"encryption": {"use_encryption": False}},
        ]
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert r["image"] == "ghcr.io/x:y"
        assert r["hostname"] == "mergedhost"
        assert r["disk"] == "/dev/vda"

    def test_custom_image_url_overrides_selected(self):
        finals = [{
            "custom_image": "ghcr.io/custom/image:tag",
            "selected_image": "ghcr.io/x:y",
            "disk": {"auto": {"disk": "/dev/vda"}},
            "hostname": "h",
            "encryption": {"use_encryption": False},
        }]
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert r["image"] == "ghcr.io/custom/image:tag"

    def test_sys_recipe_fallback_image(self):
        finals = [{"disk": {"auto": {"disk": "/dev/vda"}}, "hostname": "h",
                   "encryption": {"use_encryption": False}}]
        sys_recipe = {"imgref": "ghcr.io/sys/image:tag"}
        path = Processor.gen_install_recipe("log", finals, sys_recipe)
        r = _load(path)
        assert r["image"] == "ghcr.io/sys/image:tag"


class TestApplyIcon:
    """Regression tests for done.py apply_icon — no GTK required (uses mocks)."""

    @staticmethod
    def _get_apply_icon():
        """Import apply_icon with all gi dependencies stubbed out."""
        import sys
        import types
        from unittest.mock import MagicMock

        gi_stub = types.ModuleType("gi")
        repo_stub = types.ModuleType("gi.repository")
        gi_stub.repository = repo_stub
        gi_stub.require_version = lambda *a, **kw: None
        for name in ("Adw", "Gio", "GLib", "Gtk", "GObject"):
            setattr(repo_stub, name, MagicMock())

        mods_to_patch = {
            "gi": gi_stub,
            "gi.repository": repo_stub,
            "bootc_installer.widgets.page_header": MagicMock(),
        }
        with pytest.MonkeyPatch().context() as mp:
            for mod, stub in mods_to_patch.items():
                mp.setitem(sys.modules, mod, stub)
            # Remove cached module so we get a fresh import with stubs
            sys.modules.pop("bootc_installer.views.done", None)
            from bootc_installer.views.done import apply_icon
            # Keep module around so patching log works
            import bootc_installer.views.done as done_mod
        return apply_icon, done_mod

    def test_resource_uri_calls_set_from_resource(self):
        from unittest.mock import MagicMock
        apply_icon, _ = self._get_apply_icon()
        header = MagicMock()
        apply_icon(header, "resource:///org/bootcinstaller/Installer/images/dakota.png")
        header.set_from_resource.assert_called_once_with(
            "/org/bootcinstaller/Installer/images/dakota.png"
        )

    def test_icon_name_sets_icon_name(self):
        from unittest.mock import MagicMock
        apply_icon, _ = self._get_apply_icon()
        header = MagicMock()
        apply_icon(header, "object-select-symbolic")
        header.set_from_resource.assert_not_called()
        assert header.icon_name == "object-select-symbolic"

    def test_exception_is_logged_not_silenced(self):
        """apply_icon must log failures — not silently swallow them."""
        from unittest.mock import MagicMock, patch
        apply_icon, done_mod = self._get_apply_icon()
        header = MagicMock()
        header.set_from_resource.side_effect = Exception("resource not found")
        with patch.object(done_mod, "log") as mock_log:
            apply_icon(header, "resource:///org/bootcinstaller/Installer/images/missing.png")
            mock_log.warning.assert_called_once()


class TestVarDisk:
    """Tests for optional /var disk passthrough to recipe JSON."""

    def test_var_disk_absent_by_default(self):
        path = Processor.gen_install_recipe("log", _auto_finals(), _SYS_RECIPE)
        r = _load(path)
        assert "varDisk" not in r

    def test_var_disk_format_fresh(self):
        finals = _auto_finals()
        finals[0]["var_disk"] = {"disk": "/dev/sdb", "keep_existing": False}
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert r["varDisk"] == {"disk": "/dev/sdb", "keepExisting": False}

    def test_var_disk_keep_existing(self):
        finals = _auto_finals()
        finals[0]["var_disk"] = {"disk": "/dev/sdb", "keep_existing": True}
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert r["varDisk"] == {"disk": "/dev/sdb", "keepExisting": True}

    def test_var_disk_empty_disk_omitted(self):
        finals = _auto_finals()
        finals[0]["var_disk"] = {"disk": "", "keep_existing": False}
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert "varDisk" not in r


# ── NVIDIA auto-detection tests ───────────────────────────────────────────────

class TestNvidiaAutoDetect:
    def test_nvidia_gpu_detected_uses_nvidia_image(self, monkeypatch):
        """When NVIDIA GPU is present, both image and targetImgref use nvidia."""
        monkeypatch.setattr(
            "bootc_installer.core.system.Systeminfo.has_nvidia_gpu",
            staticmethod(lambda: True),
        )
        finals = _auto_finals(image="ghcr.io/projectbluefin/dakota:latest")
        finals[0]["nvidia_imgref"] = "ghcr.io/projectbluefin/dakota-nvidia:latest"
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert r["image"] == "ghcr.io/projectbluefin/dakota-nvidia:latest"
        assert r["targetImgref"] == "ghcr.io/projectbluefin/dakota-nvidia:latest"

    def test_no_nvidia_gpu_installs_nvidia_tracks_base(self, monkeypatch):
        """Without NVIDIA GPU, install nvidia (on ISO) but track base for updates."""
        monkeypatch.setattr(
            "bootc_installer.core.system.Systeminfo.has_nvidia_gpu",
            staticmethod(lambda: False),
        )
        finals = _auto_finals(image="ghcr.io/projectbluefin/dakota:latest")
        finals[0]["nvidia_imgref"] = "ghcr.io/projectbluefin/dakota-nvidia:latest"
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert r["image"] == "ghcr.io/projectbluefin/dakota-nvidia:latest"
        assert r["targetImgref"] == "ghcr.io/projectbluefin/dakota:latest"

    def test_no_nvidia_imgref_skips_detection(self):
        """When nvidia_imgref is empty, no NVIDIA logic runs."""
        finals = _auto_finals(image="ghcr.io/tuna-os/yellowfin:gnome")
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert r["image"] == "ghcr.io/tuna-os/yellowfin:gnome"
        assert r["targetImgref"] == "ghcr.io/tuna-os/yellowfin:gnome"


# ── Hostname generation tests ─────────────────────────────────────────────────

class TestHardwareHostname:
    def test_explicit_hostname_used(self):
        """User-provided hostname takes priority over hardware-derived."""
        finals = _auto_finals(hostname="my-workstation")
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert r["hostname"] == "my-workstation"

    def test_sys_recipe_hostname_used(self):
        """sys_recipe hostname used when no user hostname provided."""
        finals = _auto_finals(hostname="")
        path = Processor.gen_install_recipe("log", finals, {"hostname": "sys-host"})
        r = _load(path)
        assert r["hostname"] == "sys-host"

    def test_hardware_hostname_generated(self, monkeypatch):
        """When no hostname from user or sys_recipe, hardware hostname is used."""
        monkeypatch.setattr(
            "bootc_installer.core.system.Systeminfo.generate_hostname",
            staticmethod(lambda: "framework-13-a7c3"),
        )
        finals = _auto_finals(hostname="")
        path = Processor.gen_install_recipe("log", finals, _SYS_RECIPE)
        r = _load(path)
        assert r["hostname"] == "framework-13-a7c3"



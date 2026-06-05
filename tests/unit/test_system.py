"""Unit tests for core/system.py — GPU detection, TPM2, hostname generation."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bootc_installer.core.system import (
    Systeminfo,
    _detect_display_devices,
    _sanitize_hostname_part,
)

# ── GPU detection tests ───────────────────────────────────────────────────────

class TestGpuDetection:
    """Test GPU detection via mocked sysfs."""

    def setup_method(self):
        # Reset cached state between tests
        Systeminfo._nvidia = None
        Systeminfo._gpus = None

    def _make_pci_device(self, tmp_path, addr, vendor_id, class_code):
        """Create a fake PCI sysfs device directory."""
        dev_dir = tmp_path / "sys" / "bus" / "pci" / "devices" / addr
        dev_dir.mkdir(parents=True)
        (dev_dir / "vendor").write_text(vendor_id + "\n")
        (dev_dir / "class").write_text(class_code + "\n")
        return dev_dir

    def test_nvidia_vga_detected(self, tmp_path, monkeypatch):
        self._make_pci_device(tmp_path, "0000:01:00.0", "0x10de", "0x030000")
        monkeypatch.setattr(
            "bootc_installer.core.system.glob.glob",
            lambda pattern: [str(tmp_path / "sys/bus/pci/devices/0000:01:00.0/class")],
        )
        result = _detect_display_devices()
        assert len(result) == 1
        assert result[0]["vendor"] == "nvidia"

    def test_intel_vga_detected(self, tmp_path, monkeypatch):
        self._make_pci_device(tmp_path, "0000:00:02.0", "0x8086", "0x030000")
        monkeypatch.setattr(
            "bootc_installer.core.system.glob.glob",
            lambda pattern: [str(tmp_path / "sys/bus/pci/devices/0000:00:02.0/class")],
        )
        result = _detect_display_devices()
        assert len(result) == 1
        assert result[0]["vendor"] == "intel"

    def test_amd_vga_detected(self, tmp_path, monkeypatch):
        self._make_pci_device(tmp_path, "0000:06:00.0", "0x1002", "0x030000")
        monkeypatch.setattr(
            "bootc_installer.core.system.glob.glob",
            lambda pattern: [str(tmp_path / "sys/bus/pci/devices/0000:06:00.0/class")],
        )
        result = _detect_display_devices()
        assert len(result) == 1
        assert result[0]["vendor"] == "amd"

    def test_hybrid_intel_nvidia(self, tmp_path, monkeypatch):
        """Laptop with Intel iGPU + NVIDIA dGPU — both detected."""
        self._make_pci_device(tmp_path, "0000:00:02.0", "0x8086", "0x030000")
        self._make_pci_device(tmp_path, "0000:01:00.0", "0x10de", "0x030200")
        monkeypatch.setattr(
            "bootc_installer.core.system.glob.glob",
            lambda pattern: [
                str(tmp_path / "sys/bus/pci/devices/0000:00:02.0/class"),
                str(tmp_path / "sys/bus/pci/devices/0000:01:00.0/class"),
            ],
        )
        result = _detect_display_devices()
        vendors = {r["vendor"] for r in result}
        assert vendors == {"intel", "nvidia"}

    def test_intel_non_gpu_ignored(self, tmp_path, monkeypatch):
        """Intel PCI device that is NOT a GPU (e.g. USB controller) is excluded."""
        self._make_pci_device(tmp_path, "0000:00:14.0", "0x8086", "0x0c0330")
        monkeypatch.setattr(
            "bootc_installer.core.system.glob.glob",
            lambda pattern: [str(tmp_path / "sys/bus/pci/devices/0000:00:14.0/class")],
        )
        result = _detect_display_devices()
        assert result == []

    def test_nvidia_audio_function_ignored(self, tmp_path, monkeypatch):
        """NVIDIA HDMI audio function (class 0x040300) is not a GPU."""
        self._make_pci_device(tmp_path, "0000:01:00.1", "0x10de", "0x040300")
        monkeypatch.setattr(
            "bootc_installer.core.system.glob.glob",
            lambda pattern: [str(tmp_path / "sys/bus/pci/devices/0000:01:00.1/class")],
        )
        result = _detect_display_devices()
        assert result == []

    def test_no_pci_devices(self, monkeypatch):
        monkeypatch.setattr(
            "bootc_installer.core.system.glob.glob",
            lambda pattern: [],
        )
        result = _detect_display_devices()
        assert result == []

    def test_invalid_or_unreadable_sysfs_entries_are_ignored(self, tmp_path, monkeypatch):
        broken_dir = tmp_path / "sys" / "bus" / "pci" / "devices" / "0000:02:00.0"
        broken_dir.mkdir(parents=True)
        (broken_dir / "class").write_text("not-hex\n")

        monkeypatch.setattr(
            "bootc_installer.core.system.glob.glob",
            lambda pattern: [str(broken_dir / "class")],
        )

        assert _detect_display_devices() == []


class TestGpuDisplayString:
    def setup_method(self):
        Systeminfo._gpus = None
        Systeminfo._nvidia = None

    def test_nvidia_only(self, monkeypatch):
        monkeypatch.setattr(
            "bootc_installer.core.system._detect_display_devices",
            lambda: [{"vendor": "nvidia", "pci_addr": "0000:01:00.0"}],
        )
        assert Systeminfo.gpu_display_string() == "NVIDIA"

    def test_intel_plus_nvidia(self, monkeypatch):
        monkeypatch.setattr(
            "bootc_installer.core.system._detect_display_devices",
            lambda: [
                {"vendor": "intel", "pci_addr": "0000:00:02.0"},
                {"vendor": "nvidia", "pci_addr": "0000:01:00.0"},
            ],
        )
        # NVIDIA comes first (higher priority)
        assert Systeminfo.gpu_display_string() == "NVIDIA + Intel"

    def test_amd_only(self, monkeypatch):
        monkeypatch.setattr(
            "bootc_installer.core.system._detect_display_devices",
            lambda: [{"vendor": "amd", "pci_addr": "0000:06:00.0"}],
        )
        assert Systeminfo.gpu_display_string() == "AMD"

    def test_no_gpus_empty(self, monkeypatch):
        monkeypatch.setattr(
            "bootc_installer.core.system._detect_display_devices",
            lambda: [],
        )
        assert Systeminfo.gpu_display_string() == ""


class TestGpuIconName:
    def setup_method(self):
        Systeminfo._gpus = None
        Systeminfo._nvidia = None

    def test_nvidia_icon(self, monkeypatch):
        monkeypatch.setattr(
            "bootc_installer.core.system._detect_display_devices",
            lambda: [{"vendor": "nvidia", "pci_addr": "0000:01:00.0"}],
        )
        assert Systeminfo.gpu_icon_name() == "gpu-nvidia-symbolic"

    def test_intel_icon(self, monkeypatch):
        monkeypatch.setattr(
            "bootc_installer.core.system._detect_display_devices",
            lambda: [{"vendor": "intel", "pci_addr": "0000:00:02.0"}],
        )
        assert Systeminfo.gpu_icon_name() == "gpu-intel-symbolic"

    def test_hybrid_uses_nvidia_icon(self, monkeypatch):
        """For hybrid systems, icon uses the discrete GPU (highest priority)."""
        monkeypatch.setattr(
            "bootc_installer.core.system._detect_display_devices",
            lambda: [
                {"vendor": "intel", "pci_addr": "0000:00:02.0"},
                {"vendor": "nvidia", "pci_addr": "0000:01:00.0"},
            ],
        )
        assert Systeminfo.gpu_icon_name() == "gpu-nvidia-symbolic"

    def test_no_gpus_fallback_icon(self, monkeypatch):
        monkeypatch.setattr(
            "bootc_installer.core.system._detect_display_devices",
            lambda: [],
        )
        assert Systeminfo.gpu_icon_name() == "video-display-symbolic"


# ── Hostname sanitization tests ───────────────────────────────────────────────

class TestHostnameSanitize:
    def test_basic_sanitize(self):
        assert _sanitize_hostname_part("Framework Laptop 13") == "framework-laptop-13"

    def test_removes_corp_suffixes(self):
        assert _sanitize_hostname_part("Dell Inc. XPS 15") == "dell-xps-15"

    def test_collapses_hyphens(self):
        assert _sanitize_hostname_part("HP --- Pavilion") == "hp-pavilion"

    def test_strips_leading_trailing(self):
        assert _sanitize_hostname_part("  -ThinkPad X1-  ") == "thinkpad-x1"


class TestSysteminfoBasicChecks:
    def setup_method(self):
        Systeminfo.uefi = None
        Systeminfo.ram = None
        Systeminfo.cpu = None
        Systeminfo._nvidia = None
        Systeminfo._tpm2 = None
        Systeminfo._gpus = None

    def test_is_uefi_true_inside_flatpak(self, monkeypatch):
        monkeypatch.setattr("bootc_installer.core.system.os.path.exists", lambda path: path == "/.flatpak-info")
        monkeypatch.setattr("bootc_installer.core.system.os.path.isdir", lambda path: False)

        assert Systeminfo.is_uefi() is True

    def test_is_uefi_uses_sysfs_when_not_in_flatpak(self, monkeypatch):
        monkeypatch.setattr("bootc_installer.core.system.os.path.exists", lambda path: False)
        monkeypatch.setattr("bootc_installer.core.system.os.path.isdir", lambda path: path == "/sys/firmware/efi")

        assert Systeminfo.is_uefi() is True

    def test_is_uefi_returns_cached_value(self, monkeypatch):
        Systeminfo.uefi = True
        monkeypatch.setattr(
            "bootc_installer.core.system.os.path.exists",
            lambda path: (_ for _ in ()).throw(AssertionError("cache should be used")),
        )

        assert Systeminfo.is_uefi() is True

    def test_is_ram_enough_true_at_threshold(self, monkeypatch):
        fake_proc = SimpleNamespace(stdout=SimpleNamespace(read=lambda: b"3800000000\n"))
        monkeypatch.setattr("bootc_installer.core.system.subprocess.Popen", lambda *args, **kwargs: fake_proc)

        assert Systeminfo.is_ram_enough() is True

    def test_is_ram_enough_false_below_threshold(self, monkeypatch):
        fake_proc = SimpleNamespace(stdout=SimpleNamespace(read=lambda: b"3799999999\n"))
        monkeypatch.setattr("bootc_installer.core.system.subprocess.Popen", lambda *args, **kwargs: fake_proc)

        assert Systeminfo.is_ram_enough() is False

    def test_is_cpu_enough_true_with_two_cores_total(self, monkeypatch):
        procs = iter(
            [
                SimpleNamespace(stdout=SimpleNamespace(read=lambda: b"1\n")),
                SimpleNamespace(stdout=SimpleNamespace(read=lambda: b"2\n")),
            ]
        )
        monkeypatch.setattr("bootc_installer.core.system.subprocess.Popen", lambda *args, **kwargs: next(procs))

        assert Systeminfo.is_cpu_enough() is True

    def test_is_cpu_enough_false_with_single_core_total(self, monkeypatch):
        procs = iter(
            [
                SimpleNamespace(stdout=SimpleNamespace(read=lambda: b"1\n")),
                SimpleNamespace(stdout=SimpleNamespace(read=lambda: b"1\n")),
            ]
        )
        monkeypatch.setattr("bootc_installer.core.system.subprocess.Popen", lambda *args, **kwargs: next(procs))

        assert Systeminfo.is_cpu_enough() is False


class TestSysteminfoGpuAndTpmCaching:
    def setup_method(self):
        Systeminfo._nvidia = None
        Systeminfo._tpm2 = None
        Systeminfo._gpus = None

    def test_detect_gpus_returns_cached_value(self, monkeypatch):
        calls = []

        def fake_detect():
            calls.append(True)
            return [{"vendor": "amd", "pci_addr": "0000:06:00.0"}]

        monkeypatch.setattr("bootc_installer.core.system._detect_display_devices", fake_detect)

        first = Systeminfo.detect_gpus()
        second = Systeminfo.detect_gpus()

        assert first == second == [{"vendor": "amd", "pci_addr": "0000:06:00.0"}]
        assert calls == [True]

    def test_has_nvidia_gpu_true_and_cached(self, monkeypatch):
        calls = []

        def fake_detect():
            calls.append(True)
            return [{"vendor": "nvidia", "pci_addr": "0000:01:00.0"}]

        monkeypatch.setattr(Systeminfo, "detect_gpus", staticmethod(fake_detect))

        assert Systeminfo.has_nvidia_gpu() is True
        assert Systeminfo.has_nvidia_gpu() is True
        assert calls == [True]

    def test_has_nvidia_gpu_false_when_nvidia_missing(self, monkeypatch):
        monkeypatch.setattr(
            Systeminfo,
            "detect_gpus",
            staticmethod(lambda: [{"vendor": "intel", "pci_addr": "0000:00:02.0"}]),
        )

        assert Systeminfo.has_nvidia_gpu() is False

    def test_has_tpm2_false_when_sysfs_missing(self, monkeypatch):
        calls = []

        def fake_exists(path):
            calls.append(path)
            return False

        monkeypatch.setattr("bootc_installer.core.system.os.path.exists", fake_exists)

        assert Systeminfo.has_tpm2() is False
        assert Systeminfo.has_tpm2() is False
        assert calls == ["/sys/class/tpm/tpm0"]

    def test_has_tpm2_true_when_sysfs_exists(self, monkeypatch):
        monkeypatch.setattr("bootc_installer.core.system.os.path.exists", lambda path: True)

        assert Systeminfo.has_tpm2() is True


class TestGenerateHostname:
    def test_generate_hostname_prefers_lenovo_thinkpad_product_name(self):
        dmi = {
            "product_name": "ThinkPad X1 Carbon Gen 12",
            "sys_vendor": "Lenovo",
            "product_serial": "SERIAL123",
            "board_serial": "BOARD456",
        }
        with patch("bootc_installer.core.system._read_dmi", side_effect=lambda field: dmi.get(field, "")):
            hostname = Systeminfo.generate_hostname()

        assert hostname == "thinkpad-x1-carbon-g-a4c1"

    def test_generate_hostname_truncates_long_model_part(self):
        dmi = {
            "product_name": "Laptop 16 Ultra Edition Extra",
            "sys_vendor": "Framework",
            "product_serial": "FRAMEWORK123",
            "board_serial": "",
        }
        with patch("bootc_installer.core.system._read_dmi", side_effect=lambda field: dmi.get(field, "")):
            hostname = Systeminfo.generate_hostname()

        assert hostname == "framework-laptop-16-8336"
        assert len(hostname.rsplit("-", 1)[0]) <= 20

    def test_generate_hostname_uses_product_when_vendor_unknown(self):
        dmi = {
            "product_name": "Galago Pro",
            "sys_vendor": "Unknown Vendor",
            "product_serial": "SER123",
            "board_serial": "",
        }
        with patch("bootc_installer.core.system._read_dmi", side_effect=lambda field: dmi.get(field, "")):
            hostname = Systeminfo.generate_hostname()

        assert hostname == "galago-pro-3e10"

    def test_generate_hostname_uses_vendor_when_product_missing(self):
        dmi = {
            "product_name": "",
            "sys_vendor": "Framework",
            "product_serial": "SER123",
            "board_serial": "",
        }
        with patch("bootc_installer.core.system._read_dmi", side_effect=lambda field: dmi.get(field, "")):
            hostname = Systeminfo.generate_hostname()

        assert hostname == "framework-3e10"

    def test_generate_hostname_falls_back_to_dakota_when_dmi_missing(self):
        dmi = {
            "product_name": "",
            "sys_vendor": "",
            "product_serial": "",
            "board_serial": "BOARD123",
        }
        with patch("bootc_installer.core.system._read_dmi", side_effect=lambda field: dmi.get(field, "")):
            hostname = Systeminfo.generate_hostname()

        assert hostname == "dakota-27a3"

    def test_generate_hostname_uses_random_suffix_when_serials_missing(self):
        with patch("bootc_installer.core.system._read_dmi", return_value=""), patch(
            "bootc_installer.core.system.os.urandom", return_value=b"\x01\x02\x03\x04"
        ):
            hostname = Systeminfo.generate_hostname()

        assert hostname == "dakota-34b8"

    def test_generate_hostname_falls_back_when_sanitized_model_is_invalid(self):
        dmi = {
            "product_name": "---",
            "sys_vendor": "Unknown Vendor",
            "product_serial": "SER123",
            "board_serial": "",
        }
        with patch("bootc_installer.core.system._read_dmi", side_effect=lambda field: dmi.get(field, "")):
            hostname = Systeminfo.generate_hostname()

        assert hostname == "dakota-3e10"

    def test_generate_hostname_uses_regex_fallback_when_validation_fails(self):
        dmi = {
            "product_name": "Framework 13",
            "sys_vendor": "Framework",
            "product_serial": "SER123",
            "board_serial": "",
        }
        with patch("bootc_installer.core.system._read_dmi", side_effect=lambda field: dmi.get(field, "")), patch(
            "bootc_installer.core.system.re.match", return_value=None
        ):
            hostname = Systeminfo.generate_hostname()

        assert hostname == "dakota-3e10"

"""Unit tests for core/system.py — GPU detection, TPM2, hostname generation."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bootc_installer.core.system import (
    Systeminfo,
    _detect_display_devices,
    _sanitize_hostname_part,
    _GPU_VENDOR_DISPLAY,
)

_HAS_DISPLAY = bool(__import__("os").environ.get("DISPLAY") or __import__("os").environ.get("WAYLAND_DISPLAY"))


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


@__import__("pytest").mark.skipif(not _HAS_DISPLAY, reason="GPU tests require a display for Gtk icon lookup")
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


@__import__("pytest").mark.skipif(not _HAS_DISPLAY, reason="GPU tests require a display for Gtk icon lookup")
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

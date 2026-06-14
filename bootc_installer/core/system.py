import glob
import hashlib
import os
import re
import subprocess


# Vendor name normalization: raw DMI vendor → clean short name.
_VENDOR_MAP = {
    "dell inc.": "dell",
    "dell": "dell",
    "lenovo": "lenovo",
    "asus": "asus",
    "asustek computer inc.": "asus",
    "hewlett-packard": "hp",
    "hp inc.": "hp",
    "hp": "hp",
    "acer": "acer",
    "acer, inc.": "acer",
    "microsoft corporation": "surface",
    "apple inc.": "mac",
    "framework": "framework",
    "system76": "system76",
    "google": "chromebook",
    "samsung electronics co., ltd.": "samsung",
    "msi": "msi",
    "micro-star international co., ltd.": "msi",
    "razer": "razer",
    "razer inc": "razer",
    "tuxedo": "tuxedo",
    "star labs": "starlabs",
}


def _read_dmi(field: str) -> str:
    """Read a DMI field from sysfs, returning empty string on failure."""
    try:
        with open(f"/sys/devices/virtual/dmi/id/{field}") as f:
            return f.read().strip()
    except OSError:
        return ""


def _sanitize_hostname_part(s: str) -> str:
    """Sanitize a string for use in a hostname: lowercase, hyphens, no junk."""
    s = s.lower()
    # Remove common corporate suffixes
    for suffix in ("inc.", "inc", "corp.", "corp", "co., ltd.", "ltd.", "ltd",
                   "co.", "corporation", "electronics", "computer"):
        s = s.replace(suffix, "")
    # Replace non-alphanumeric with hyphens
    s = re.sub(r"[^a-z0-9]+", "-", s)
    # Collapse repeated hyphens and strip leading/trailing
    s = re.sub(r"-+", "-", s).strip("-")
    return s


# PCI vendor IDs for GPU manufacturers.
_GPU_VENDORS = {
    "0x10de": "nvidia",
    "0x8086": "intel",
    "0x1002": "amd",
}

# Human-readable display names for GPU vendors.
_GPU_VENDOR_DISPLAY = {
    "nvidia": "NVIDIA",
    "intel": "Intel",
    "amd": "AMD",
}


def _detect_display_devices() -> list[dict]:
    """Scan PCI sysfs for display-class devices (VGA, 3D, display controllers).

    Returns a list of dicts: {"vendor": "nvidia"|"intel"|"amd", "pci_addr": "0000:01:00.0"}
    Only includes devices with PCI class 0x03xxxx (display subsystem).
    """
    results = []
    seen_vendors = set()
    for class_file in glob.glob("/sys/bus/pci/devices/*/class"):
        dev_dir = os.path.dirname(class_file)
        try:
            with open(class_file) as f:
                class_code = int(f.read().strip(), 16)
            # Display class: top byte == 0x03 (VGA, 3D controller, display controller)
            if (class_code >> 16) != 0x03:
                continue
            with open(os.path.join(dev_dir, "vendor")) as f:
                vendor_id = f.read().strip()
        except (OSError, ValueError):
            continue

        vendor_name = _GPU_VENDORS.get(vendor_id)
        if vendor_name and vendor_name not in seen_vendors:
            seen_vendors.add(vendor_name)
            pci_addr = os.path.basename(dev_dir)
            results.append({"vendor": vendor_name, "pci_addr": pci_addr})
    return results


class Systeminfo:
    uefi = None
    ram = None
    cpu = None
    _nvidia = None
    _tpm2 = None
    _gpus = None

    @staticmethod
    def is_uefi() -> bool:
        if not Systeminfo.uefi:
            # Skip UEFI check inside Flatpak — assume UEFI
            if os.path.exists("/.flatpak-info"):
                Systeminfo.uefi = True
            else:
                Systeminfo.uefi = os.path.isdir("/sys/firmware/efi")

        return Systeminfo.uefi

    @staticmethod
    def is_ram_enough() -> bool:
        if not Systeminfo.ram:
            proc = subprocess.Popen(
                "free -b | grep Mem | awk '{print $2}'",
                shell=True,
                stdout=subprocess.PIPE
            ).stdout.read().decode()
            Systeminfo.ram = int(proc) >= 3800000000

        return Systeminfo.ram

    @staticmethod
    def is_cpu_enough() -> bool:
        if not Systeminfo.cpu:
            proc1 = subprocess.Popen(
                "lscpu | grep -E 'Core\\(s\\)' | awk '{print $4}'",
                shell=True,
                stdout=subprocess.PIPE
            ).stdout.read().decode()
            proc2 = subprocess.Popen(
                "lscpu | grep -E 'Socket\\(s\\)' | awk '{print $2}'",
                shell=True,
                stdout=subprocess.PIPE
            ).stdout .read().decode()
            Systeminfo.cpu = (int(proc1) * int(proc2)) >= 2

        return Systeminfo.cpu

    @staticmethod
    def has_nvidia_gpu() -> bool:
        """Detect NVIDIA GPU by checking PCI display-class devices."""
        if Systeminfo._nvidia is not None:
            return Systeminfo._nvidia
        gpus = Systeminfo.detect_gpus()
        Systeminfo._nvidia = any(g["vendor"] == "nvidia" for g in gpus)
        return Systeminfo._nvidia

    @staticmethod
    def detect_gpus() -> list[dict]:
        """Detect all GPU vendors present in the system.

        Returns cached list of {"vendor": "nvidia"|"intel"|"amd", "pci_addr": "..."}.
        Only includes PCI display-class devices (0x03xxxx).
        """
        if Systeminfo._gpus is not None:
            return Systeminfo._gpus
        Systeminfo._gpus = _detect_display_devices()
        return Systeminfo._gpus

    @staticmethod
    def gpu_display_string() -> str:
        """Human-readable GPU summary for UI display.

        Examples: "NVIDIA", "Intel + NVIDIA", "AMD", "Intel"
        """
        gpus = Systeminfo.detect_gpus()
        if not gpus:
            return ""
        # Priority order: nvidia > amd > intel (show discrete first)
        priority = {"nvidia": 0, "amd": 1, "intel": 2}
        vendors = sorted(set(g["vendor"] for g in gpus), key=lambda v: priority.get(v, 99))
        return " + ".join(_GPU_VENDOR_DISPLAY.get(v, v) for v in vendors)

    @staticmethod
    def gpu_icon_name() -> str:
        """Return the appropriate icon name for the primary GPU vendor.

        Uses the highest-priority discrete GPU for the icon.
        Falls back to generic 'video-display-symbolic' if unknown.
        """
        gpus = Systeminfo.detect_gpus()
        if not gpus:
            return "video-display-symbolic"
        priority = {"nvidia": 0, "amd": 1, "intel": 2}
        vendors = sorted(set(g["vendor"] for g in gpus), key=lambda v: priority.get(v, 99))
        primary = vendors[0]
        return f"gpu-{primary}-symbolic"

    @staticmethod
    def has_tpm2() -> bool:
        """Detect TPM2 chip via sysfs."""
        if Systeminfo._tpm2 is not None:
            return Systeminfo._tpm2
        Systeminfo._tpm2 = os.path.exists("/sys/class/tpm/tpm0")
        return Systeminfo._tpm2

    @staticmethod
    def generate_hostname() -> str:
        """Generate a hardware-derived hostname like 'framework-13-a7c3'.

        Format: {vendor/model}-{4-char hex suffix}
        The suffix is derived from the machine serial for uniqueness.
        Falls back to 'bluefin-XXXX' if DMI data is unavailable.
        """
        product = _read_dmi("product_name")
        vendor_raw = _read_dmi("sys_vendor")

        # Build the model portion
        vendor = _VENDOR_MAP.get(vendor_raw.lower().strip(), "")
        model_part = ""

        if vendor and product:
            # For Lenovo, check if product already contains "ThinkPad"
            if vendor == "lenovo" and "thinkpad" in product.lower():
                model_part = _sanitize_hostname_part(product)
            else:
                model_part = _sanitize_hostname_part(f"{vendor} {product}")
        elif product:
            model_part = _sanitize_hostname_part(product)
        elif vendor:
            model_part = vendor

        # Truncate model to 20 chars
        if len(model_part) > 20:
            model_part = model_part[:20].rstrip("-")

        if not model_part:
            model_part = "bluefin"

        # Generate 4-char hex suffix from hardware serial
        serial = (_read_dmi("product_serial")
                  or _read_dmi("board_serial")
                  or os.urandom(4).hex())
        suffix = hashlib.sha256(serial.encode()).hexdigest()[:4]

        hostname = f"{model_part}-{suffix}"

        # Final RFC 1123 validation
        if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", hostname):
            hostname = f"bluefin-{suffix}"

        return hostname

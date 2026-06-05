# main_qt.py
#
# Qt/Kirigami entry point for bootc-installer KDE variant

import logging
import sys
import os

_debug = os.environ.get("BOOTC_INSTALLER_DEBUG", "").lower() in ("1", "true", "yes")
_log_level = logging.DEBUG if _debug else logging.INFO

_cache_dir = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "bootc-installer",
)
os.makedirs(_cache_dir, exist_ok=True)
_log_file = os.path.join(_cache_dir, "installer-debug.log")

logging.basicConfig(
    level=_log_level,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(_log_file, mode="w"),
    ],
)
logger_boot = logging.getLogger("Installer::Boot")
logger_boot.info(f"Logging to {_log_file}")

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import QUrl
    from PyQt6.QtQml import QQmlApplicationEngine
    logger_boot.info("PyQt6 imported successfully")
except ImportError as e:
    logger_boot.error(f"Failed to import PyQt6: {e}")
    logger_boot.info("Falling back to GTK4 variant")
    from bootc_installer.main import main
    def main_qt(version):
        return main(version)
    sys.exit(0)

from bootc_installer.core.system import Systeminfo  # noqa: E402

try:
    from bootc_installer._version import VERSION as APP_VERSION
except ImportError:
    APP_VERSION = "unknown"

logger = logging.getLogger("Installer::Main")


def _show_fatal_error(title: str, message: str) -> None:
    """Display a Qt critical-error dialog and log the message."""
    logger.error("%s: %s", title, message)
    try:
        dialog = QMessageBox()
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()
    except Exception as e:
        logger.debug("Could not show Qt error dialog: %s", e)


class KDEBootcInstaller(QApplication):
    """KDE Plasma variant of the bootc installer using Qt/Kirigami."""

    def __init__(self):
        logger.info("KDEBootcInstaller.__init__")
        super().__init__(sys.argv)
        self.setApplicationName("bootc Installer")
        self.setApplicationVersion(APP_VERSION)
        self.setOrganizationName("org.kdeinstaller")

    def run(self):
        logger.info("Initializing QML engine")
        engine = QQmlApplicationEngine()

        # Load main QML file
        qml_path = os.path.join(os.path.dirname(__file__), "kde", "main.qml")
        logger.info(f"Loading QML from {qml_path}")

        if os.path.exists(qml_path):
            engine.load(QUrl.fromLocalFile(qml_path))
        else:
            logger.error(f"QML file not found: {qml_path}")
            logger.warning("Using fallback GTK4 interface")
            from bootc_installer.main import main
            return main(APP_VERSION)

        if not engine.rootObjects():
            logger.error("Failed to load QML engine")
            return 1

        logger.info("QML engine loaded successfully")
        return self.exec()


def main(version):
    """The application's entry point for KDE variant."""
    logger.info(f"KDE bootc Installer version: {version}")
    try:
        logger.info("Checking system requirements")
        if not Systeminfo.is_uefi():
            _show_fatal_error(
                "System Requirements Not Met",
                "This installer requires a UEFI system. Legacy BIOS boot is not supported.",
            )
            return 1

        if not Systeminfo.is_ram_enough():
            _show_fatal_error(
                "Insufficient RAM",
                "This system does not have enough RAM to run the installer. At least 4 GB is required.",
            )
            return 1

        if not Systeminfo.is_cpu_enough():
            _show_fatal_error(
                "Insufficient CPU",
                "This system does not have enough CPU cores to run the installer.",
            )
            return 1

        logger.info("System requirements met, starting KDE installer")
        app = KDEBootcInstaller()
        return app.run()
    except Exception:
        logger.exception("Fatal error in KDE installer")
        return 1

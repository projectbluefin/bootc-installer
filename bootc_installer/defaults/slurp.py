import json
import logging
import os
import subprocess
import threading
from collections import defaultdict
from gettext import gettext as _

from gi.repository import Adw, GLib, Gtk

from bootc_installer.core.disks import Diskutils
from bootc_installer.views.progress import (
    _FISHERMAN_HOST_PATH,
    _IN_FLATPAK,
    _LIVE_ISO,
    _stage_fisherman_on_host,
)

logger = logging.getLogger("Installer::Slurp")

_WARN_RESERVE_BYTES = 2 * 1024**3
_WARN_THRESHOLD_GB = 6
_DEFAULT_CATEGORIES = {"Documents", "Desktop", "Pictures", "Wallpapers"}


def _fmt_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


@Gtk.Template(resource_path="/org/bootcinstaller/Installer/gtk/default-slurp.ui")
class VanillaDefaultSlurp(Adw.Bin):
    __gtype_name__ = "VanillaDefaultSlurp"

    btn_next = Gtk.Template.Child()
    btn_skip = Gtk.Template.Child()
    page_header = Gtk.Template.Child()
    slurp_status_label = Gtk.Template.Child()
    slurp_warning_label = Gtk.Template.Child()
    slurp_content_box = Gtk.Template.Child()
    slurp_spinner = Gtk.Template.Child()

    def __init__(self, window, distro_info, key, step, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__distro_info = distro_info
        self.__key = key
        self.__step = step
        self.__scan_result = None
        self.__selection = {}
        self.__category_sizes = {}
        self.__rows = {}
        self.__row_handlers = {}
        self.__scan_disk = None
        self.__scan_inflight = False

        self.btn_next.connect("clicked", self.__window.next)
        self.btn_skip.connect("clicked", self.__on_skip)
        self.btn_next.set_sensitive(False)

    def should_show(self, context: dict) -> bool:
        return True

    def on_shown(self, context: dict):
        if os.environ.get("BOOTC_DEMO"):
            self.__show_message(
                _("Windows data scanning is unavailable in demo mode."),
                show_content=False,
                can_continue=True,
            )
            return

        disk = self.__get_disk(context)
        if not disk:
            self.__show_message(
                _("No install target is selected yet. Nothing to migrate."),
                show_content=False,
                can_continue=True,
            )
            return

        if self.__scan_inflight and disk == self.__scan_disk:
            return

        if self.__scan_result is not None and disk == self.__scan_disk:
            self.__render_scan_result()
            return

        self.__start_scan(disk)

    def get_finals(self):
        selected_by_partition = defaultdict(lambda: defaultdict(list))
        for (partition, user, category), selected in self.__selection.items():
            if selected:
                selected_by_partition[partition][user].append(category)

        if not selected_by_partition:
            return {"slurp": None}

        source_partition, users_for_partition = next(iter(selected_by_partition.items()))
        users = [
            {"name": user, "categories": categories}
            for user, categories in users_for_partition.items()
            if categories
        ]
        if not users:
            return {"slurp": None}

        return {
            "slurp": {
                "sourcePartition": source_partition,
                "users": users,
            }
        }

    def test_auto_advance(self):
        self.btn_next.emit("clicked")

    def __get_disk(self, context: dict) -> str | None:
        for step_finals in context.get("finals", []):
            if not isinstance(step_finals, dict):
                continue

            disk_info = step_finals.get("disk")
            if isinstance(disk_info, dict):
                if "auto" in disk_info and isinstance(disk_info["auto"], dict):
                    disk = disk_info["auto"].get("disk")
                    if disk:
                        return disk
                if "disk" in disk_info and isinstance(disk_info["disk"], str):
                    return disk_info["disk"]
                partition_keys = [key for key in disk_info if isinstance(key, str) and key.startswith("/dev/")]
                if partition_keys:
                    try:
                        disk, _partn = Diskutils.separate_device_and_partn(partition_keys[0])
                        return disk
                    except Exception as exc:
                        logger.warning("Failed to derive parent disk from %s: %s", partition_keys[0], exc)
            elif isinstance(disk_info, str) and disk_info:
                return disk_info
        return None

    def __start_scan(self, disk: str):
        self.__scan_disk = disk
        self.__scan_inflight = True
        self.__scan_result = None
        self.__selection = {}
        self.__category_sizes = {}
        self.__rows = {}
        self.__row_handlers = {}
        self.__clear_content()
        self.slurp_warning_label.set_visible(False)
        self.slurp_spinner.set_spinning(True)
        self.slurp_status_label.set_label(_("Scanning for Windows data…"))
        self.slurp_content_box.set_visible(False)
        self.btn_next.set_sensitive(False)

        fisherman_path = self.__resolve_fisherman_path()
        if not fisherman_path:
            self.__scan_inflight = False
            self.__show_message(
                _("Windows data scanning is unavailable right now. You can continue without migrating files."),
                show_content=False,
                can_continue=True,
            )
            return

        threading.Thread(
            target=self.__run_scan,
            args=(fisherman_path, disk),
            daemon=True,
        ).start()

    def __resolve_fisherman_path(self) -> str | None:
        env_path = os.environ.get("TUNA_FISHERMAN_PATH", "")

        if _IN_FLATPAK:
            if os.path.exists(_FISHERMAN_HOST_PATH):
                return _FISHERMAN_HOST_PATH
            if _stage_fisherman_on_host() and os.path.exists(_FISHERMAN_HOST_PATH):
                return _FISHERMAN_HOST_PATH
            if env_path and os.path.exists(env_path) and not env_path.startswith("/app/"):
                return env_path
            return None

        for candidate in (env_path, "/usr/local/bin/fisherman", "/usr/bin/fisherman"):
            if candidate and os.path.exists(candidate):
                return candidate

        if _LIVE_ISO and os.path.exists("/usr/local/bin/fisherman"):
            return "/usr/local/bin/fisherman"
        return None

    def __run_scan(self, fisherman_path: str, disk: str):
        if _IN_FLATPAK:
            cmd = ["flatpak-spawn", "--host", "pkexec", fisherman_path, "scan", disk]
        else:
            cmd = ["pkexec", fisherman_path, "scan", disk]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            if result.returncode != 0:
                logger.warning("fisherman scan failed (%s): %s", result.returncode, result.stderr.strip())
                scan = {"disk": disk, "partitions": []}
            else:
                try:
                    scan = json.loads(result.stdout or "{}")
                except json.JSONDecodeError as exc:
                    logger.warning("Invalid fisherman scan output: %s", exc)
                    scan = {"disk": disk, "partitions": []}
        except Exception as exc:
            logger.warning("fisherman scan failed: %s", exc)
            scan = {"disk": disk, "partitions": []}

        GLib.idle_add(self.__on_scan_complete, disk, scan)

    def __on_scan_complete(self, disk: str, scan: dict):
        if disk != self.__scan_disk:
            return False  # stale callback — newer scan is still running
        self.__scan_inflight = False
        self.__scan_result = scan
        self.__render_scan_result()
        return False

    def __render_scan_result(self):
        self.slurp_spinner.set_spinning(False)
        partitions = [part for part in (self.__scan_result or {}).get("partitions", []) if part.get("users")]

        if not partitions:
            self.__show_message(
                _("No Windows data found on this disk. Nothing to migrate."),
                show_content=False,
                can_continue=True,
            )
            return

        self.slurp_status_label.set_label(
            _("Windows data found! Select what to bring with you.")
        )
        self.__populate_checkboxes(partitions)
        self.slurp_content_box.set_visible(True)
        self.btn_next.set_sensitive(True)
        self.__update_budget_warning()

    def __show_message(self, text: str, *, show_content: bool, can_continue: bool):
        self.__clear_content()
        self.slurp_spinner.set_spinning(False)
        self.slurp_status_label.set_label(text)
        self.slurp_warning_label.set_visible(False)
        self.slurp_content_box.set_visible(show_content)
        self.btn_next.set_sensitive(can_continue)

    def __clear_content(self):
        child = self.slurp_content_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.slurp_content_box.remove(child)
            child = next_child

    def __populate_checkboxes(self, partitions: list[dict]):
        self.__clear_content()
        self.__selection = {}
        self.__category_sizes = {}
        self.__rows = {}
        self.__row_handlers = {}
        primary_partition = partitions[0].get("partition", "") if partitions else ""

        for part in partitions:
            partition_name = part.get("partition", "")
            for user in part.get("users", []):
                user_name = user.get("name", _("Unknown user"))
                group = Adw.PreferencesGroup()
                group.set_title(f"{user_name} — {partition_name}")

                for category in user.get("categories", []):
                    category_name = category.get("name", _("Unknown category"))
                    category_bytes = int(category.get("bytes", 0) or 0)
                    category_count = int(category.get("count", 0) or 0)
                    key = (partition_name, user_name, category_name)

                    row = Adw.SwitchRow()
                    row.set_title(category_name)
                    row.set_subtitle(_("%s · %d files") % (_fmt_bytes(category_bytes), category_count))

                    default_on = partition_name == primary_partition and category_name in _DEFAULT_CATEGORIES
                    row.set_active(default_on)
                    self.__selection[key] = default_on
                    self.__category_sizes[key] = category_bytes
                    self.__rows[key] = row
                    self.__row_handlers[key] = row.connect("notify::active", self.__on_row_toggled, key)
                    group.add(row)

                self.slurp_content_box.append(group)

    def __on_row_toggled(self, row, _param, key):
        active = row.get_active()
        partition, _user, _category = key
        self.__selection[key] = active

        if active:
            self.__clear_other_partitions(partition)

        self.__update_budget_warning()

    def __clear_other_partitions(self, active_partition: str):
        for key, row in self.__rows.items():
            partition, _user, _category = key
            if partition == active_partition or not self.__selection.get(key):
                continue
            handler_id = self.__row_handlers.get(key)
            if handler_id is not None:
                row.handler_block(handler_id)
            row.set_active(False)
            self.__selection[key] = False
            if handler_id is not None:
                row.handler_unblock(handler_id)

    def __selected_total_bytes(self) -> int:
        return sum(
            self.__category_sizes.get(key, 0)
            for key, selected in self.__selection.items()
            if selected
        )

    def __budget_limit_bytes(self) -> int:
        try:
            total_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
            return max(0, total_bytes - _WARN_RESERVE_BYTES)
        except (AttributeError, OSError, ValueError):
            return _WARN_THRESHOLD_GB * 1024**3

    def __update_budget_warning(self):
        selected_bytes = self.__selected_total_bytes()
        budget_limit = self.__budget_limit_bytes()
        if selected_bytes > budget_limit > 0:
            self.slurp_warning_label.set_label(
                _("Selected data (%s) may be too large for the live environment to migrate safely.")
                % _fmt_bytes(selected_bytes)
            )
            self.slurp_warning_label.set_visible(True)
        else:
            self.slurp_warning_label.set_visible(False)

    def __on_skip(self, _btn):
        for key, row in self.__rows.items():
            handler_id = self.__row_handlers.get(key)
            if handler_id is not None:
                row.handler_block(handler_id)
            row.set_active(False)
            self.__selection[key] = False
            if handler_id is not None:
                row.handler_unblock(handler_id)
        self.slurp_warning_label.set_visible(False)
        self.__window.next(None)

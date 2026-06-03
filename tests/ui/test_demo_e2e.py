"""GTK integration coverage for demo-mode end-to-end flows."""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from bootc_installer.windows.main_window import BootcWindow

_RECIPE_PATH = Path(__file__).resolve().parents[2] / "recipe.json"


def _pump():
    ctx = GLib.MainContext.default()
    while ctx.pending():
        ctx.iteration(False)


class _ImmediateThread:
    def __init__(self, target=None, args=(), kwargs=None, **_kwargs):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


class _TimeoutQueue:
    def __init__(self):
        self.pending = []

    def add(self, *args):
        callback = None
        callback_args = ()
        for index, value in enumerate(args):
            if callable(value):
                callback = value
                callback_args = args[index + 1:]
                break
        if callback is None:
            raise AssertionError(f"could not identify callback in GLib timeout args: {args!r}")
        self.pending.append((callback, callback_args))
        return len(self.pending)

    def add_seconds(self, _delay, _callback, *_args):
        return 1

    def drain(self, limit=64):
        for _ in range(limit):
            _pump()
            if not self.pending:
                return
            callback, args = self.pending.pop(0)
            callback(*args)
        raise AssertionError("timed out waiting for queued GTK callbacks")


class _FakeDisksManager:
    def __init__(self):
        self._disks = [
            SimpleNamespace(
                display_name="Demo Disk",
                disk="/dev/vda",
                pretty_size="128 GB",
                size=128 * 1024**3,
                is_removable=False,
            )
        ]

    def all_disks(self, include_removable=False):
        if include_removable:
            return list(self._disks)
        return [disk for disk in self._disks if not disk.is_removable]


def _make_window(extra_env):
    scheduler = _TimeoutQueue()
    app = Adw.Application(
        application_id="org.bootcinstaller.InstallerTest",
        flags=Gio.ApplicationFlags.NON_UNIQUE,
    )

    env = {
        "BOOTC_CUSTOM_RECIPE": str(_RECIPE_PATH),
        **extra_env,
    }

    patchers = [
        patch.dict(os.environ, env, clear=False),
        patch("bootc_installer.defaults.disk.DisksManager", return_value=_FakeDisksManager()),
        patch("bootc_installer.views.progress.threading.Thread", _ImmediateThread),
        patch("bootc_installer.windows.main_window.GLib.idle_add", side_effect=scheduler.add),
        patch("bootc_installer.windows.main_window.GLib.timeout_add", side_effect=scheduler.add),
        patch("bootc_installer.views.progress.GLib.timeout_add", side_effect=scheduler.add),
        patch.object(GLib, "timeout_add_seconds", side_effect=scheduler.add_seconds),
        # Prevent CompanionServer from starting a real HTTPS server (openssl subprocess + port bind)
        patch("bootc_installer.defaults.qr_companion.CompanionServer"),
        # Prevent get_local_ip() from making a real network socket call
        patch("bootc_installer.defaults.qr_companion.get_local_ip", return_value="127.0.0.1"),
    ]

    for patcher in patchers:
        patcher.start()

    try:
        window = BootcWindow(application=app)
        window.present()
        _pump()
    except Exception:
        for patcher in reversed(patchers):
            patcher.stop()
        raise

    return window, scheduler, patchers


def _view(window, name):
    return getattr(window, f"_BootcWindow__view_{name}")


class TestDemoEndToEnd:
    def test_bootc_demo_and_bootc_test_reach_done_screen(self):
        window, scheduler, patchers = _make_window({"BOOTC_DEMO": "1", "BOOTC_TEST": "1"})

        try:
            builder = getattr(window, "_BootcWindow__builder")
            for step in builder.widgets:
                step.test_auto_advance()
                _pump()
                scheduler.drain()

            window.update_finals()
            _view(window, "confirm").test_auto_advance()
            scheduler.drain()

            done = _view(window, "done")
            assert done.page_header.title == "Dakota is installed"
            assert (
                done.page_header.subtitle
                == "Restart now to complete the installation."
            )
        finally:
            window.destroy()
            _pump()
            for patcher in reversed(patchers):
                patcher.stop()

    def test_preview_screen_can_jump_to_confirm(self):
        window, scheduler, patchers = _make_window({"BOOTC_PREVIEW_SCREEN": "confirm"})

        try:
            window._BootcWindow__apply_preview_screen()
            _pump()
            scheduler.drain()
            titles = {
                row.get_title()
                for row in _view(window, "confirm").active_widgets
            }
            assert "Disk" in titles
            assert "Encryption" in titles
        finally:
            window.destroy()
            _pump()
            for patcher in reversed(patchers):
                patcher.stop()

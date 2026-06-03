"""Unit tests for defaults/conn_check.py without a GTK display."""

import importlib
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class _Template:
    def __call__(self, *args, **kwargs):
        return lambda cls: cls

    def Child(self, *args, **kwargs):
        return None

    def Callback(self, *args, **kwargs):
        return lambda func: func


class _StubBin:
    pass


def _build_gi_stubs():
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")

    gtk_mod = types.ModuleType("gi.repository.Gtk")
    gtk_mod.Template = _Template()
    gtk_mod.Box = _StubBin

    adw_mod = types.ModuleType("gi.repository.Adw")
    adw_mod.Bin = _StubBin

    glib_mod = types.ModuleType("gi.repository.GLib")
    glib_mod.idle_add = MagicMock(return_value=1)

    for name, module in {
        "Gtk": gtk_mod,
        "Adw": adw_mod,
        "GLib": glib_mod,
    }.items():
        setattr(repo_mod, name, module)
        sys.modules[f"gi.repository.{name}"] = module

    gi_mod.repository = repo_mod
    gi_mod.require_version = lambda *args, **kwargs: None
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


def _import_conn_check_fresh():
    _build_gi_stubs()
    sys.modules.pop("bootc_installer.defaults.conn_check", None)
    try:
        import bootc_installer.defaults as defaults_pkg

        defaults_pkg.__dict__.pop("conn_check", None)
    except Exception:
        pass
    return importlib.import_module("bootc_installer.defaults.conn_check")


class _SyncRunAsync:
    def __init__(self, task_func, callback=None, *args, **kwargs):
        result = task_func(*args, **kwargs)
        if callback is not None:
            callback(result, None)


class TestConnCheckShouldShow(unittest.TestCase):
    def test_should_show_returns_false_for_offline_install(self):
        mod = _import_conn_check_fresh()
        self.assertFalse(
            mod.BootcDefaultConnCheck.should_show(object(), {"offline_install": True})
        )

    def test_should_show_returns_true_for_normal_install(self):
        mod = _import_conn_check_fresh()
        self.assertTrue(mod.BootcDefaultConnCheck.should_show(object(), {}))


class TestConnCheckAsyncLogic(unittest.TestCase):
    def _step(self):
        return SimpleNamespace(
            _BootcDefaultConnCheck__window=SimpleNamespace(next=MagicMock()),
            _BootcDefaultConnCheck__step_num=2,
            _BootcDefaultConnCheck__ignore_callback=False,
            page_header=SimpleNamespace(icon_name=None, title=None, subtitle=None),
            btn_recheck=MagicMock(),
        )

    def test_conn_check_ignores_other_carousel_pages(self):
        mod = _import_conn_check_fresh()
        step = self._step()

        with patch.object(mod, "RunAsync") as run_async:
            mod.BootcDefaultConnCheck._BootcDefaultConnCheck__conn_check(step, None, 99)

        run_async.assert_not_called()
        step._BootcDefaultConnCheck__window.next.assert_not_called()

    def test_conn_check_success_advances_to_next_page(self):
        mod = _import_conn_check_fresh()
        step = self._step()

        with patch.object(mod, "RunAsync", _SyncRunAsync), patch.object(
            mod.urllib.request, "urlopen", return_value=object()
        ) as urlopen:
            mod.BootcDefaultConnCheck._BootcDefaultConnCheck__conn_check(step, None, 2)

        step._BootcDefaultConnCheck__window.next.assert_called_once_with()
        urlopen.assert_called_once()
        step.btn_recheck.set_visible.assert_not_called()

    def test_conn_check_failure_updates_header_and_reveals_retry(self):
        mod = _import_conn_check_fresh()
        step = self._step()

        with patch.object(mod, "RunAsync", _SyncRunAsync), patch.object(
            mod.urllib.request, "urlopen", side_effect=OSError("offline")
        ):
            mod.BootcDefaultConnCheck._BootcDefaultConnCheck__conn_check(step, None, 2)

        step._BootcDefaultConnCheck__window.next.assert_not_called()
        self.assertEqual(
            step.page_header.icon_name, "network-wired-disconnected-symbolic"
        )
        self.assertEqual(step.page_header.title, "No Internet Connection!")
        self.assertEqual(
            step.page_header.subtitle,
            "Installer requires an active internet connection",
        )
        step.btn_recheck.set_visible.assert_called_once_with(True)

    def test_conn_check_skip_env_bypasses_network_request(self):
        mod = _import_conn_check_fresh()
        step = self._step()

        with patch.object(mod, "RunAsync", _SyncRunAsync), patch.dict(
            mod.os.environ, {"VANILLA_SKIP_CONN_CHECK": "1"}, clear=False
        ), patch.object(mod.urllib.request, "urlopen") as urlopen:
            mod.BootcDefaultConnCheck._BootcDefaultConnCheck__conn_check(step, None, 2)

        step._BootcDefaultConnCheck__window.next.assert_called_once_with()
        urlopen.assert_not_called()

    def test_ignore_callback_suppresses_navigation_after_back_click(self):
        mod = _import_conn_check_fresh()
        step = self._step()

        mod.BootcDefaultConnCheck._BootcDefaultConnCheck__on_btn_back_clicked(step, None, 1)

        with patch.object(mod, "RunAsync", _SyncRunAsync), patch.object(
            mod.urllib.request, "urlopen", return_value=object()
        ):
            mod.BootcDefaultConnCheck._BootcDefaultConnCheck__conn_check(step, None, 2)

        self.assertFalse(step._BootcDefaultConnCheck__ignore_callback)
        step._BootcDefaultConnCheck__window.next.assert_not_called()
        step.btn_recheck.set_visible.assert_not_called()


if __name__ == "__main__":
    unittest.main()

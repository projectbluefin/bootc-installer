"""
Unit tests for utils/run_async.py — happy path, exception path,
default callback, and daemon flag. GLib.idle_add is mocked so no
GTK display or GLib main loop is needed.
"""
import os
import sys
import threading
import time
import importlib
import types
import unittest
from unittest.mock import MagicMock, patch


def _import_run_async_fresh():
    """Re-import run_async with a clean GLib mock each time."""
    glib_mock = MagicMock()
    glib_mock.idle_add.return_value = 1
    gi_mock = MagicMock()
    gi_mock.repository = MagicMock()
    gi_mock.repository.GLib = glib_mock
    sys.modules["gi"] = gi_mock
    sys.modules["gi.repository"] = gi_mock.repository
    sys.modules["gi.repository.GLib"] = glib_mock

    sys.modules.pop("bootc_installer.utils.run_async", None)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    return importlib.import_module("bootc_installer.utils.run_async")


# One-time import for the module; tests use patch() to override GLib per-test.
_run_async_mod = _import_run_async_fresh()
RunAsync = _run_async_mod.RunAsync


def _join(t, timeout=2.0):
    t.join(timeout)
    if t.is_alive():
        raise RuntimeError("Thread did not finish within timeout")


class TestRunAsyncHappyPath(unittest.TestCase):
    """Result is propagated to callback when task_func returns normally."""

    def test_result_passed_to_callback(self):
        received = {}

        def task():
            return 42

        def callback(result, error):
            received["result"] = result
            received["error"] = error

        with patch("bootc_installer.utils.run_async.GLib") as mock_glib:
            mock_glib.idle_add.side_effect = lambda fn, *a: fn(*a) or 1
            t = RunAsync(task, callback)
            _join(t)

        self.assertEqual(received["result"], 42)
        self.assertIsNone(received["error"])

    def test_none_result_propagated(self):
        received = {}

        def task():
            return None

        def callback(result, error):
            received["result"] = result
            received["error"] = error

        with patch("bootc_installer.utils.run_async.GLib") as mock_glib:
            mock_glib.idle_add.side_effect = lambda fn, *a: fn(*a) or 1
            t = RunAsync(task, callback)
            _join(t)

        self.assertIsNone(received["result"])
        self.assertIsNone(received["error"])

    def test_task_args_forwarded(self):
        received = {}

        def task(x, y):
            return x + y

        def callback(result, error):
            received["result"] = result

        with patch("bootc_installer.utils.run_async.GLib") as mock_glib:
            mock_glib.idle_add.side_effect = lambda fn, *a: fn(*a) or 1
            t = RunAsync(task, callback, 10, 32)
            _join(t)

        self.assertEqual(received["result"], 42)


class TestRunAsyncExceptionPath(unittest.TestCase):
    """Exception in task_func is caught and forwarded to callback as error."""

    def test_exception_passed_to_callback(self):
        received = {}
        err = ValueError("boom")

        def task():
            raise err

        def callback(result, error):
            received["result"] = result
            received["error"] = error

        with patch("bootc_installer.utils.run_async.GLib") as mock_glib:
            mock_glib.idle_add.side_effect = lambda fn, *a: fn(*a) or 1
            t = RunAsync(task, callback)
            _join(t)

        self.assertIsNone(received["result"])
        self.assertIsInstance(received["error"], ValueError)
        self.assertIs(received["error"], err)

    def test_exception_result_is_none(self):
        received = {}

        def task():
            raise RuntimeError("unexpected")

        def callback(result, error):
            received["result"] = result

        with patch("bootc_installer.utils.run_async.GLib") as mock_glib:
            mock_glib.idle_add.side_effect = lambda fn, *a: fn(*a) or 1
            t = RunAsync(task, callback)
            _join(t)

        self.assertIsNone(received["result"])

    def test_callback_called_exactly_once_on_exception(self):
        call_count = {"n": 0}

        def task():
            raise TypeError("count me")

        def callback(result, error):
            call_count["n"] += 1

        with patch("bootc_installer.utils.run_async.GLib") as mock_glib:
            mock_glib.idle_add.side_effect = lambda fn, *a: fn(*a) or 1
            t = RunAsync(task, callback)
            _join(t)

        self.assertEqual(call_count["n"], 1)


class TestRunAsyncDefaultCallback(unittest.TestCase):
    """callback=None installs a no-op lambda; thread completes without crash."""

    def test_no_callback_success_does_not_crash(self):
        def task():
            return "ok"

        with patch("bootc_installer.utils.run_async.GLib") as mock_glib:
            mock_glib.idle_add.side_effect = lambda fn, *a: fn(*a) or 1
            t = RunAsync(task)
            _join(t)

        self.assertFalse(t.is_alive())

    def test_no_callback_exception_does_not_crash(self):
        def task():
            raise TypeError("no callback crash test")

        with patch("bootc_installer.utils.run_async.GLib") as mock_glib:
            mock_glib.idle_add.side_effect = lambda fn, *a: fn(*a) or 1
            t = RunAsync(task)
            _join(t)

        self.assertFalse(t.is_alive())


class TestRunAsyncDaemon(unittest.TestCase):
    """Thread is a daemon thread by default."""

    def test_is_daemon_by_default(self):
        event = threading.Event()

        def task():
            event.wait(timeout=0.5)
            return None

        with patch("bootc_installer.utils.run_async.GLib") as mock_glib:
            mock_glib.idle_add.return_value = 1
            t = RunAsync(task)
            self.assertTrue(t.daemon)
            event.set()
            _join(t)


if __name__ == "__main__":
    unittest.main()

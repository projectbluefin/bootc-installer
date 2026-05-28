from __future__ import annotations

import gi

from gi.repository import Gtk

HAS_PASTRY = False
Pastry = None

try:
    gi.require_version("Pastry", "0.1")
    from gi.repository import Pastry as _Pastry

    Pastry = _Pastry
    HAS_PASTRY = True
except (ImportError, ValueError):
    Pastry = None


def wrap_glass(widget: Gtk.Widget) -> Gtk.Widget:
    if not HAS_PASTRY:
        return widget

    frame = Pastry.GlassFrame()
    frame.set_child(widget)
    return frame


def wrap_focus(widget: Gtk.Widget) -> Gtk.Widget:
    if not HAS_PASTRY:
        return widget

    overlay = Pastry.FocusOverlay()
    overlay.set_child(widget)
    return overlay


def add_glass_root(window) -> None:
    if not HAS_PASTRY or not hasattr(window, "get_content") or not hasattr(window, "set_content"):
        return

    try:
        content = window.get_content()
    except Exception:
        return

    if content is None or isinstance(content, Pastry.GlassRoot):
        return

    root = Pastry.GlassRoot()
    root.set_child(content)
    window.set_content(root)


def new_grid_spinner() -> Gtk.Widget | None:
    if not HAS_PASTRY:
        return None

    spinner = Pastry.GridSpinner()
    spinner.set_halign(Gtk.Align.CENTER)
    spinner.set_valign(Gtk.Align.CENTER)
    spinner.set_visible(False)
    return spinner

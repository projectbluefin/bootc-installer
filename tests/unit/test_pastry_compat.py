import importlib
import sys
import types


def _clear_pastry_module():
    sys.modules.pop("bootc_installer.utils.pastry_compat", None)


def _install_gi_stubs(with_pastry: bool):
    gi_mod = types.ModuleType("gi")
    repo_mod = types.ModuleType("gi.repository")

    gtk_mod = types.ModuleType("gi.repository.Gtk")

    class _Align:
        CENTER = "center"

    class _Widget:
        def __init__(self):
            self.halign = None
            self.valign = None
            self.visible = True

        def set_halign(self, value):
            self.halign = value

        def set_valign(self, value):
            self.valign = value

        def set_visible(self, value):
            self.visible = value

    gtk_mod.Align = _Align
    gtk_mod.Widget = _Widget
    repo_mod.Gtk = gtk_mod
    sys.modules["gi.repository.Gtk"] = gtk_mod

    if with_pastry:
        pastry_mod = types.ModuleType("gi.repository.Pastry")

        class _GlassFrame(_Widget):
            def __init__(self):
                super().__init__()
                self.child = None

            def set_child(self, child):
                self.child = child

        class _FocusOverlay(_GlassFrame):
            pass

        class _GlassRoot(_GlassFrame):
            pass

        class _GridSpinner(_Widget):
            pass

        pastry_mod.GlassFrame = _GlassFrame
        pastry_mod.FocusOverlay = _FocusOverlay
        pastry_mod.GlassRoot = _GlassRoot
        pastry_mod.GridSpinner = _GridSpinner
        repo_mod.Pastry = pastry_mod
        sys.modules["gi.repository.Pastry"] = pastry_mod

    def _require_version(namespace, _version):
        if namespace == "Pastry" and not with_pastry:
            raise ValueError("Pastry unavailable")

    gi_mod.require_version = _require_version
    gi_mod.repository = repo_mod
    sys.modules["gi"] = gi_mod
    sys.modules["gi.repository"] = repo_mod


def _import_pastry_compat(with_pastry: bool):
    _clear_pastry_module()
    _install_gi_stubs(with_pastry)
    return importlib.import_module("bootc_installer.utils.pastry_compat")


class DummyWindow:
    def __init__(self, content):
        self._content = content

    def get_content(self):
        return self._content

    def set_content(self, content):
        self._content = content


def test_pastry_compat_falls_back_cleanly_without_pastry():
    mod = _import_pastry_compat(with_pastry=False)
    widget = mod.Gtk.Widget()

    assert mod.HAS_PASTRY is False
    assert mod.wrap_glass(widget) is widget
    assert mod.wrap_focus(widget) is widget
    assert mod.new_grid_spinner() is None


def test_pastry_compat_wraps_widgets_when_pastry_available():
    mod = _import_pastry_compat(with_pastry=True)
    widget = mod.Gtk.Widget()

    glass = mod.wrap_glass(widget)
    focus = mod.wrap_focus(widget)
    spinner = mod.new_grid_spinner()

    assert mod.HAS_PASTRY is True
    assert glass.child is widget
    assert focus.child is widget
    assert spinner.halign == mod.Gtk.Align.CENTER
    assert spinner.valign == mod.Gtk.Align.CENTER
    assert spinner.visible is False


def test_pastry_compat_adds_glass_root_once():
    mod = _import_pastry_compat(with_pastry=True)
    content = mod.Gtk.Widget()
    window = DummyWindow(content)

    mod.add_glass_root(window)
    wrapped = window.get_content()

    assert wrapped.child is content

    mod.add_glass_root(window)
    assert window.get_content() is wrapped

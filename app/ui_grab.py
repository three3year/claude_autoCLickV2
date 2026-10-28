import tkinter as tk

import applog
import ui_theme
from window_coord import ROOT, WindowCoordinator

coord = WindowCoordinator()


def wname(w):
    try:
        return w.title() or str(w)
    except Exception:
        return str(w)


def top_window():
    t = coord.grab_target()
    if t is None or t is ROOT:
        return None
    return t


def register_modal(dlg):
    coord.modal_opened(dlg)
    applog.log("modal.open", win=wname(dlg), depth=coord.stack_depth())

    def on_destroy(e):
        if e.widget is dlg:
            coord.modal_closed(dlg)
            applog.log("modal.close", win=wname(dlg), depth=coord.stack_depth())
            apply_grab("modal-close")

    dlg.bind("<Destroy>", on_destroy, add=True)
    dlg.bind("<Map>",
             lambda e: apply_grab("map") if e.widget is dlg else None,
             add=True)
    apply_grab("modal-open")


def apply_grab(reason=""):
    target = coord.grab_target()
    if target is None or target is ROOT:
        return
    try:
        if not target.winfo_exists():
            coord.modal_closed(target)
            apply_grab(reason)
            return
        if not target.winfo_viewable():
            return
        if ui_theme.safe_grab_current(target) is not target:
            target.grab_set()
            applog.log("grab.set", win=wname(target), reason=reason)
    except tk.TclError:
        pass

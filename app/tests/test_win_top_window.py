"""win.top_window_at 用真的視窗驗: 給視窗中心點, 拿回它自己的頂層 handle (會開視窗, 在隱藏桌面跑)."""
import ctypes
import tkinter as tk
from ctypes import wintypes

from automation import win


def test_給實際開著的視窗中心點_拿回它的頂層handle(tkroot):
    top = tk.Toplevel(tkroot)
    try:
        top.geometry("320x240+200+150")
        top.attributes("-topmost", True)
        tk.Frame(top, bg="#3a6").pack(fill="both", expand=True)
        top.update()
        hwnd = win.user32.GetAncestor(top.winfo_id(), win.GA_ROOT)
        r = wintypes.RECT()
        assert win.user32.GetWindowRect(hwnd, ctypes.byref(r))
        cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
        assert win.top_window_at(cx, cy) == hwnd
    finally:
        top.destroy()

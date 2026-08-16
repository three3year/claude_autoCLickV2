"""子程序探針 (票 06): 建 App 到視窗完成首次映射, 印出已載入的重量級模組.

由 test_import_slim.py 以子程序執行——importlib 狀態乾淨, 量到的就是
真實開窗關鍵路徑。引擎工廠換成假件, 背景載入不碰 torch/cv2。
"""
import os
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk  # noqa: E402

import applog  # noqa: E402
import app as app_mod  # noqa: E402
import enginehub  # noqa: E402

applog.set_path(os.path.join(tempfile.gettempdir(), "slim_probe.log"))
enginehub._default_engine_factory = lambda: SimpleNamespace(
    coarse_only=False,
    register=lambda profile, name: None,
    query=lambda profile, name, screen: None,
)

from automation import win  # noqa: E402

win.set_dpi_aware()
root = tk.Tk()
a = app_mod.App(root)
root.update()  # 主視窗完成首次映射
heavy = [m for m in ("cv2", "mss", "torch", "numpy") if m in sys.modules]
print("HEAVY=" + (",".join(heavy) or "none"), flush=True)
deadline = time.monotonic() + 5
while a.hub.state == "loading" and time.monotonic() < deadline:
    root.update()
    time.sleep(0.02)
root.destroy()

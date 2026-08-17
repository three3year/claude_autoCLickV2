"""存圖後重新探索延後 (票 05): 先回畫面、後重探索, 查詢前補跑.

App 的重量級 __init__ 以子類跳過 (沿用 test_confirm_next_ui 的模式),
reload_profile 以計數 stub 取代——只驗「何時重探索」的排程語意。
圖落在工作區 (ADR 0006), 所以子類要備一個真的 Workspace。
"""
import tkinter as tk
from types import SimpleNamespace

import numpy as np

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import app as app_mod
import flowfile


class _RegApp(app_mod.App):
    """只建 save_captured / ensure_registered 需要的欄位."""

    def __init__(self, root, profile_dir):
        self.root = root
        self.profile_dir = str(profile_dir)
        self.ws = flowfile.Workspace(self.profile_dir)
        self.profile = SimpleNamespace(templates={})
        self._pending_templates = set()
        self._rereg_after = None
        self.reloads = 0
        self.logged = []

    def reload_profile(self):
        self.reloads += 1

    def refresh_templates(self):
        pass

    def log_ui(self, msg, level="info"):
        self.logged.append(msg)


def _shot():
    return {"img": np.zeros((8, 8, 3), np.uint8),
            "screenX": 10, "screenY": 20, "w": 8, "h": 8}


def _pump(root, ms=200):
    """跑事件迴圈一小段, 讓 after 佇列消化."""
    done = tk.IntVar(master=root, value=0)
    root.after(ms, lambda: done.set(1))
    root.wait_variable(done)


def test_存圖當下不重登錄_稍後自動補跑(tkroot, tmp_path):
    a = _RegApp(tkroot, tmp_path)
    name = a.save_captured(_shot())
    assert a.reloads == 0                       # 存圖當下不卡
    assert name in a.list_template_names()      # 但 UI 語意不變: 名字查得到
    assert a.template_image(name) is not None   # 預覽讀磁碟備援
    _pump(tkroot)
    assert a.reloads == 1                       # 排程的重登錄補跑了
    assert not a._pending_templates


def test_連續快速存多張_只重登錄一次(tkroot, tmp_path):
    a = _RegApp(tkroot, tmp_path)
    n1 = a.save_captured(_shot())
    n2 = a.save_captured(_shot())
    assert n1 != n2                             # 未重載也不撞名
    _pump(tkroot)
    assert a.reloads == 1                       # 合併成一次, 不重複不遺漏


def test_查詢前ensure_registered立即補跑(tkroot, tmp_path):
    a = _RegApp(tkroot, tmp_path)
    a.save_captured(_shot())
    a.ensure_registered()                       # 比對測試/執行前的同步補跑
    assert a.reloads == 1
    assert not a._pending_templates
    _pump(tkroot)
    assert a.reloads == 1                       # 排程的那次已取消, 不重複


def test_沒有待登錄時ensure是空操作(tkroot, tmp_path):
    a = _RegApp(tkroot, tmp_path)
    a.ensure_registered()
    assert a.reloads == 0

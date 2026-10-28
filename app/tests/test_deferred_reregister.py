import os
import tkinter as tk
from types import SimpleNamespace

import numpy as np

import harness

import app as app_mod
import flowfile


class _RegApp(app_mod.App):
    def __init__(self, root, base_dir):
        self.root = root
        self.store = flowfile.FlowTemplates.new(os.path.join(str(base_dir), "unsaved"))
        self.library = SimpleNamespace(templates={})
        self._pending_templates = set()
        self._rereg_after = None
        self.reloads = 0
        self.logged = []

    def rebind_templates(self, changed=None):
        self.reloads += 1

    def refresh_templates(self):
        pass

    def log_ui(self, msg, level="info"):
        self.logged.append(msg)


def _shot():
    return {"img": np.zeros((8, 8, 3), np.uint8),
            "screenX": 10, "screenY": 20, "w": 8, "h": 8}


def _pump(root, ms=200):
    done = tk.IntVar(master=root, value=0)
    root.after(ms, lambda: done.set(1))
    root.wait_variable(done)


def test_存圖當下不重登錄_稍後自動補跑(tkroot, tmp_path):
    a = _RegApp(tkroot, tmp_path)
    name = a.save_captured(_shot())
    assert a.reloads == 0
    assert name in a.list_template_names()
    assert a.template_image(name) is not None
    _pump(tkroot)
    assert a.reloads == 1
    assert not a._pending_templates


def test_連續快速存多張_只重登錄一次(tkroot, tmp_path):
    a = _RegApp(tkroot, tmp_path)
    n1 = a.save_captured(_shot())
    n2 = a.save_captured(_shot())
    assert n1 != n2
    _pump(tkroot)
    assert a.reloads == 1


def test_查詢前ensure_registered立即補跑(tkroot, tmp_path):
    a = _RegApp(tkroot, tmp_path)
    a.save_captured(_shot())
    a.ensure_registered()
    assert a.reloads == 1
    assert not a._pending_templates
    _pump(tkroot)
    assert a.reloads == 1


def test_沒有待登錄時ensure是空操作(tkroot, tmp_path):
    a = _RegApp(tkroot, tmp_path)
    a.ensure_registered()
    assert a.reloads == 0

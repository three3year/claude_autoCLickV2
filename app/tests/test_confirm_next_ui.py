import tkinter as tk

import harness
from harness import click, find

import app as app_mod


def test_步驟摘要顯示點到下一步的圖出現():
    assert "點到下一步的圖出現" in app_mod.step_desc(find("a", confirm="next"))


def test_步驟摘要_其他確認模式不受影響():
    assert "點到消失" in app_mod.step_desc(find("a", confirm="gone"))
    assert "點到" not in app_mod.step_desc(find("a"))


class _MiniApp(app_mod.App):
    def __init__(self, root, steps):
        self.root = root
        self.steps = steps
        self._collapsed = set()
        self._view = []
        self._drag_idxs = None
        self.step_list = app_mod.SegListbox(root)
        self._step_icons = type("_Icons", (), {"refresh": lambda self: None})()
        self._mark_dirty = lambda: None


def test_不相連的步驟列顯示警告標記(tkroot):
    root = tkroot
    root.withdraw()
    try:
        a = _MiniApp(root, [
            find("a", confirm="next"),
            click(1, 2),
            find("b", confirm="next"),
            find("c"),
            find("d", confirm="next"),
        ])
        a.render_steps()
        lines = a.step_list.get("1.0", "end").splitlines()
        assert "⚠" in lines[0]
        assert "⚠" not in lines[1]
        assert "⚠" not in lines[2]
        assert "⚠" not in lines[3]
        assert "⚠" in lines[4]
        for n, line in enumerate(lines):
            assert line.startswith(f" ☰ {n + 1:>2}.\t")
        a.steps[1] = find("x")
        a.render_steps()
        lines = a.step_list.get("1.0", "end").splitlines()
        assert "⚠" not in lines[0]
    finally:
        a.step_list.destroy()

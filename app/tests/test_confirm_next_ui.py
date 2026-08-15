"""confirm: "next" 的 UI 層輕量驗證: 步驟摘要文字與清單 ⚠ 警告標記.

清單渲染測試沿用「monkeypatch 自動存檔」的既有模式 (以 stub 取代
`_autosave`, 不寫使用者的 flows/_autosave.json); App 的重量級 __init__
(引擎/profile/整套 UI) 以子類跳過, 只建 render_steps 需要的欄位。
"""
import tkinter as tk

import harness  # noqa: F401  # 先把 app/ 加進 sys.path
from harness import click, find

import app as app_mod


def test_步驟摘要顯示點到下一步的圖出現():
    assert "點到下一步的圖出現" in app_mod.step_desc(find("a", confirm="next"))


def test_步驟摘要_其他確認模式不受影響():
    assert "點到消失" in app_mod.step_desc(find("a", confirm="gone"))
    assert "點到" not in app_mod.step_desc(find("a"))


class _MiniApp(app_mod.App):
    """只建 render_steps 用到的欄位, 跳過 App.__init__ 的引擎與整套 UI."""

    def __init__(self, root, steps):
        self.root = root
        self.steps = steps
        self._collapsed = set()
        self._view = []
        self._drag_idxs = None
        self.step_list = app_mod.SegListbox(root)
        self._step_icons = type("_Icons", (), {"refresh": lambda self: None})()
        self._autosave = lambda: None  # 不寫使用者的自動存檔


def test_不相連的步驟列顯示警告標記():
    root = tk.Tk()
    root.withdraw()
    try:
        a = _MiniApp(root, [
            find("a", confirm="next"),   # 下一步是座標點擊 → 不相連
            click(1, 2),
            find("b", confirm="next"),   # 下一步是找圖 → 相連
            find("c"),                   # 未用此選項
            find("d", confirm="next"),   # 最後一步 → 不相連
        ])
        a.render_steps()
        lines = a.step_list.get("1.0", "end").splitlines()
        assert "⚠" in lines[0]
        assert "⚠" not in lines[1]
        assert "⚠" not in lines[2]
        assert "⚠" not in lines[3]
        assert "⚠" in lines[4]
        # ⚠ 段不影響號碼欄 tab 對齊: 每列仍以「 ☰ 序號.\t」開頭
        for n, line in enumerate(lines):
            assert line.startswith(f" ☰ {n + 1:>2}.\t")
        # 改掉下一步後重繪, 標記即時消失 (清單重繪時以純函式重算)
        a.steps[1] = find("x")
        a.render_steps()
        lines = a.step_list.get("1.0", "end").splitlines()
        assert "⚠" not in lines[0]
    finally:
        root.destroy()

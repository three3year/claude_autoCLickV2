"""範本面板＝本流程的範本清單 (票 06): 選取/預覽/重新命名/刪除.

只拍靜態畫面驗證不了「互動才會執行到」的路徑, 所以選取、重新命名、刪除都用
`event_generate` 真的走一遍, 再斷言對外行為: 清單內容、預覽文字、工作區的
檔案狀態、步驟引用。App 的重量級 __init__ 以子類跳過 (沿用既有模式)。
"""
import os
import tkinter as tk

import numpy as np

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import app as app_mod
import flowfile
import ui_dialogs
from automation import imgio
from ui_theme import C, FONT_MONO


class _PanelApp(app_mod.App):
    """只建範本面板需要的欄位."""

    def __init__(self, root, profile_dir, steps=None):
        self.root = root
        self.profile_dir = str(profile_dir)
        self.ws = flowfile.Workspace(self.profile_dir)
        self.ws.ensure()
        self.profile = None          # 引擎尚未就緒: 面板照樣要能用
        self.steps = steps or []
        self._pending_templates = set()
        self._rereg_after = None
        self._collapsed = set()
        self._view = []
        self._drag_idxs = None
        self.reloads = 0
        self.logged = []
        self.rendered = 0

        # 虛擬事件 (<<ListboxSelect>>) 在未映射的視窗上不會派送 → 面板要真的
        # 顯示出來, 互動路徑才走得到
        root.deiconify()
        root.geometry("+40+40")
        root.update()          # 先真的映射, 之後 event_generate 才派送得到
        self.panel = tk.Frame(root)
        self.tmpl_list = tk.Listbox(self.panel, font=FONT_MONO,
                                    selectbackground=C["sel"], width=24,
                                    exportselection=False)
        self.tmpl_list.pack(side="left", fill="both", expand=True)
        self.tmpl_list.bind("<<ListboxSelect>>", self._on_tmpl_select)
        self._tmpl_rows = []
        self._tmpl_icons = type("_Icons", (), {"refresh": lambda self: None})()
        self.thumb_lbl = tk.Label(self.panel)
        self.thumb_lbl.pack(side="left")
        self.thumb_info = tk.Label(self.panel, text="")
        self.thumb_info.pack(side="left")
        self.panel.pack()

    def reload_profile(self):
        self.reloads += 1

    def render_steps(self, keep=None):
        self.rendered += 1

    def log_ui(self, msg, level="info"):
        self.logged.append(msg)

    def destroy(self):
        self.panel.destroy()
        self.root.withdraw()   # session 共用的 root, 還原成其他測試預期的狀態


def _img(w=12, h=8, fill=200):
    a = np.zeros((h, w, 3), np.uint8)
    a[:] = fill
    return a


def _add(app, name, w=12, h=8, fill=200):
    """把一張真圖放進工作區 (面板讀的就是這些檔案)."""
    imgio.imwrite(app.ws.path_of(name), _img(w, h, fill))
    return name


def _select(app, name):
    """真的走一遍互動: 點選清單中的某一列.

    先 update 讓元件真的映射——虛擬事件在未映射的視窗上不會派送, 少了這步
    就變成「只驗靜態畫面」, 互動才會執行到的 callback 根本沒跑到。
    """
    app.root.update()
    assert app.tmpl_list.winfo_viewable(), "清單要真的畫出來, 事件才派送得到"
    i = app._tmpl_rows.index(name)
    app.tmpl_list.selection_clear(0, "end")
    app.tmpl_list.selection_set(i)
    app.tmpl_list.event_generate("<<ListboxSelect>>")
    app.root.update()


def _panel(tkroot, tmp_path, names=("a", "b"), steps=None):
    app = _PanelApp(tkroot, tmp_path, steps=steps)
    for n in names:
        _add(app, n)
    app.refresh_templates()
    app.root.update()
    return app


def test_面板只列出本流程的範本(tkroot, tmp_path):
    app = _panel(tkroot, tmp_path, names=("btn", "icon"))
    try:
        rows = app.tmpl_list.get(0, "end")
        assert [r.strip() for r in rows] == ["🖼 btn", "🖼 icon"]
        assert app._tmpl_rows == ["btn", "icon"]
    finally:
        app.destroy()


def test_面板沒有資料夾層級(tkroot, tmp_path):
    """一份流程幾十張圖不需要命名空間: 名稱平面、清單沒有可展開的列."""
    app = _panel(tkroot, tmp_path, names=("a", "b"))
    try:
        assert not hasattr(app, "template_folders")
        assert not hasattr(app, "current_folder")
        assert not hasattr(app, "new_template_folder")
        for row in app.tmpl_list.get(0, "end"):
            assert "📁" not in row
    finally:
        app.destroy()


def test_切換流程時面板跟著換(tkroot, tmp_path):
    app = _panel(tkroot, tmp_path, names=("old",))
    try:
        other = os.path.join(str(tmp_path), "other" + flowfile.EXT)
        flowfile.write(other, {"steps": [{"type": "find_click",
                                          "template": "new"}],
                               "coordSpace": "region"}, {"new": b"N"})
        app.ws.load_flow(other)
        app.refresh_templates()
        app.root.update()
        assert app._tmpl_rows == ["new"], "上一份流程的範本不留在面板上"
    finally:
        app.destroy()


def test_選取範本時預覽顯示圖與尺寸(tkroot, tmp_path):
    app = _PanelApp(tkroot, tmp_path)
    try:
        _add(app, "btn", w=40, h=24)
        app.refresh_templates()
        _select(app, "btn")
        assert "btn" in app.thumb_info.cget("text")
        assert "40×24px" in app.thumb_info.cget("text")
        assert app.thumb_lbl.cget("image"), "預覽圖有畫出來"
    finally:
        app.destroy()


def test_重新命名同步改寫所有引用_含確認圖(tkroot, tmp_path, monkeypatch):
    steps = [{"type": "find_click", "template": "a"},
             {"type": "find_click", "template": "b", "confirm": "appear",
              "confirmTemplate": "a"}]
    app = _panel(tkroot, tmp_path, names=("a", "b"), steps=steps)
    try:
        monkeypatch.setattr(ui_dialogs, "ask_string",
                            lambda *a, **kw: "按鈕")
        _select(app, "a")
        app.rename_template()
        app.root.update()

        assert app._tmpl_rows == ["b", "按鈕"]
        assert not os.path.exists(app.ws.path_of("a"))
        assert os.path.exists(app.ws.path_of("按鈕"))
        assert steps[0]["template"] == "按鈕"
        assert steps[1]["confirmTemplate"] == "按鈕"
        assert any("2 個步驟" in m for m in app.logged)
    finally:
        app.destroy()


def test_重新命名撞名自動加序號(tkroot, tmp_path, monkeypatch):
    app = _panel(tkroot, tmp_path, names=("a", "b"))
    try:
        monkeypatch.setattr(ui_dialogs, "ask_string", lambda *a, **kw: "b")
        _select(app, "a")
        app.rename_template()
        app.root.update()
        assert app._tmpl_rows == ["b", "b_2"], "原有的 b 絕對不會被蓋掉"
    finally:
        app.destroy()


def test_重新命名輸入資料夾分隔被清成平面名稱(tkroot, tmp_path, monkeypatch):
    app = _panel(tkroot, tmp_path, names=("a",))
    try:
        monkeypatch.setattr(ui_dialogs, "ask_string",
                            lambda *a, **kw: "zh/按鈕")
        _select(app, "a")
        app.rename_template()
        app.root.update()
        assert app._tmpl_rows == ["zh_按鈕"]
    finally:
        app.destroy()


def test_刪除範本從本流程移除_引用它的步驟以既有方式標示(tkroot, tmp_path,
                                                monkeypatch):
    steps = [{"type": "find_click", "template": "a"}]
    app = _panel(tkroot, tmp_path, names=("a", "b"), steps=steps)
    try:
        asked = []
        monkeypatch.setattr(app_mod.messagebox, "askyesno",
                            lambda title, msg, **kw: (asked.append(msg), True)[1])
        os.makedirs(os.path.join(app.ws.registered_dir, "a"), exist_ok=True)
        _select(app, "a")
        app.del_template()
        app.root.update()

        assert app._tmpl_rows == ["b"]
        assert not os.path.exists(app.ws.path_of("a"))
        assert not os.path.exists(os.path.join(app.ws.registered_dir, "a"))
        assert asked and "步驟 1" in asked[0], "有步驟在用它才提醒"
        # 引用仍指向已刪除的範本 → 沿用既有機制 (執行前擋下), 不動步驟
        assert steps[0]["template"] == "a"
    finally:
        app.destroy()


def test_刪除沒有步驟在用的範本不打擾(tkroot, tmp_path, monkeypatch):
    app = _panel(tkroot, tmp_path, names=("a",), steps=[])
    try:
        asked = []
        monkeypatch.setattr(app_mod.messagebox, "askyesno",
                            lambda *a, **kw: asked.append(1))
        _select(app, "a")
        app.del_template()
        app.root.update()
        assert app._tmpl_rows == []
        assert asked == []
    finally:
        app.destroy()


def test_複製範本撞名加序號並帶走pos(tkroot, tmp_path):
    app = _panel(tkroot, tmp_path, names=("a",))
    try:
        app.ws.set_pos("a", [11, 22])
        _select(app, "a")
        app.copy_template()
        app.root.update()
        assert app._tmpl_rows == ["a", "a_2"]
        assert app.ws.pos_of("a_2") == [11, 22]
    finally:
        app.destroy()


def test_比對測試走既有的就緒gating與清場(tkroot, tmp_path, monkeypatch):
    """單一範本可直接跑`比對測試`——這條路徑沒有消失, 也沒有繞過 gating."""
    app = _panel(tkroot, tmp_path, names=("a",))
    try:
        calls = []
        monkeypatch.setattr(ui_dialogs, "show_match_test",
                            lambda a, name, **kw: calls.append(name))
        _select(app, "a")
        app.test_template()
        assert calls == ["a"], "走的是既有的 show_match_test (內含 engine_gate)"
    finally:
        app.destroy()


def test_沒選範本時比對測試提示先選一個(tkroot, tmp_path, monkeypatch):
    app = _panel(tkroot, tmp_path, names=("a",))
    try:
        infos = []
        monkeypatch.setattr(app_mod.messagebox, "showinfo",
                            lambda title, msg, **kw: infos.append(msg))
        monkeypatch.setattr(ui_dialogs, "show_match_test",
                            lambda *a, **kw: (_ for _ in ()).throw(
                                AssertionError("不該走到")))
        app.tmpl_list.selection_clear(0, "end")
        app.test_template()
        assert infos and "選擇一個範本" in infos[0]
    finally:
        app.destroy()

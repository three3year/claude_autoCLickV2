"""選範本對話框 (票 07): 跨存檔瀏覽、從磁碟挑圖、現場截圖, **確定才複製**.

「確定才複製 / 取消不留痕」只有互動才會執行到, 所以每個案例都真的把對話框開
起來、用 `event_generate` 走一遍選取與按鈕, 再斷言**檔案系統的狀態** (工作區
裡有沒有那張圖) 與回傳值。modal 對話框會卡住呼叫端, 所以互動放在 `after()` 裡
(既有紀律)。
"""
import os
import tkinter as tk

import numpy as np
import pytest

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import app as app_mod
import enginehub
import flowfile
import ui_dialogs
from automation import imgio


class _PickApp(app_mod.App):
    """只建選範本對話框需要的欄位."""

    def __init__(self, root, profile_dir, state=enginehub.READY):
        self.root = root
        self.profile_dir = str(profile_dir)
        self.ws = flowfile.Workspace(self.profile_dir)
        self.ws.ensure()
        self.hub = enginehub.EngineHub()
        self.hub.state = state
        self.profile = None
        self.steps = []
        self._pending_templates = set()
        self._rereg_after = None
        self.logged = []
        self.reloads = 0
        self.shot = None      # `pick_region_raw` 要回傳的假截圖

    def reload_profile(self):
        self.reloads += 1

    def refresh_templates(self):
        pass

    def render_steps(self, keep=None):
        pass

    def log_ui(self, msg, level="info"):
        self.logged.append((level, msg))

    def pick_region_raw(self, hide=()):
        return self.shot

    def _schedule_reregister(self):
        pass       # 測試不跑事件迴圈的延後排程


def _img(fill=200, w=12, h=8):
    a = np.zeros((h, w, 3), np.uint8)
    a[:] = fill
    return a


def _png(fill=200, w=12, h=8):
    return imgio.encode_png(_img(fill, w, h))


# ---------- 對話框的互動驅動 ----------

def _find(widget, cls=None, text=None):
    """在 widget 樹裡找元件 (依類別名稱與顯示文字), 找不到回 None."""
    for child in widget.winfo_children():
        if cls is None or child.winfo_class() == cls:
            if text is None:
                return child
            try:
                if child.cget("text") == text:
                    return child
            except tk.TclError:
                pass
        got = _find(child, cls, text)
        if got is not None:
            return got
    return None


class _Driver:
    """在 modal 對話框開著的時候操作它 (透過 after 排進同一個事件迴圈)."""

    def __init__(self, root, title):
        self.root = root
        self.title = title
        self.dlg = None
        self.rows = None
        self.error = None

    def run(self, *actions):
        """actions: 收 driver 的 callable, 依序排進事件迴圈執行."""
        delay = 60
        self.root.after(delay, self._attach)
        for act in actions:
            delay += 60
            self.root.after(delay, self._wrap(act))

    def _wrap(self, act):
        def go():
            if self.error is not None:
                return
            try:
                act(self)
            except BaseException as e:       # 讓失敗浮出來, 不要卡在 modal
                self.error = e
                self.close()
        return go

    def _attach(self):
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel) and w.winfo_exists() \
                    and w.title() == self.title:
                self.dlg = w
                self.list = _find(w, "Listbox")
                return
        self.error = AssertionError(f"對話框沒開起來: {self.title}")

    def rows_text(self):
        return list(self.list.get(0, "end"))

    def select(self, needle, under=None):
        """點選含 needle 的列 (真的發 <<ListboxSelect>>).

        `under` 指定先找到哪一個來源列, 再從它之後往下找——不同來源可以有
        同名的範本, 不指定就會抓到第一個。
        """
        self.dlg.update()
        rows = self.rows_text()
        start = 0
        if under is not None:
            start = next(i for i, tx in enumerate(rows) if under in tx) + 1
        for i in range(start, len(rows)):
            if needle in rows[i]:
                self.list.selection_clear(0, "end")
                self.list.selection_set(i)
                self.list.event_generate("<<ListboxSelect>>")
                self.dlg.update()
                return
        raise AssertionError(f"清單裡沒有 {needle!r}（under={under!r}）: {rows}")

    def press(self, text):
        _btn(self.dlg, text).invoke()
        if self.dlg.winfo_exists():
            self.dlg.update()

    def info_text(self):
        for w in _all(self.dlg):
            if w.winfo_class() == "TLabel" and "名稱：" in str(w.cget("text")):
                return w.cget("text")
        return ""

    def close(self):
        if self.dlg is not None and self.dlg.winfo_exists():
            self.dlg.destroy()


def _all(widget):
    for child in widget.winfo_children():
        yield child
        yield from _all(child)


def _btn(dlg, text):
    for w in _all(dlg):
        if w.winfo_class() in ("TButton", "Button"):
            try:
                if w.cget("text") == text:
                    return w
            except tk.TclError:
                pass
    raise AssertionError(f"找不到按鈕「{text}」")


@pytest.fixture
def picker(tkroot, tmp_path):
    tkroot.deiconify()
    tkroot.geometry("+40+40")
    tkroot.update()
    app = _PickApp(tkroot, tmp_path)
    yield app
    tkroot.withdraw()


def _open(app, driver, *actions):
    driver.run(*actions)
    got = ui_dialogs.pick_template(app, driver.title)
    if driver.error is not None:
        raise driver.error
    return got


TITLE = "選擇範本"


# ---------- 樹狀來源 ----------

def test_左側列出本流程與其他流程存檔(picker):
    app = picker
    app.ws.add("mine", _png())
    other = os.path.join(app.profile_dir, "flows", "morning" + flowfile.EXT)
    os.makedirs(os.path.dirname(other), exist_ok=True)
    flowfile.write(other, {"steps": [{"type": "find_click", "template": "btn"}],
                           "coordSpace": "region"}, {"btn": _png(50)})
    d = _Driver(app.root, TITLE)

    seen = {}

    def look(dr):
        seen["rows"] = dr.rows_text()
        dr.press("取消")

    _open(app, d, look)
    rows = seen["rows"]
    assert any("本流程" in r for r in rows)
    assert any("mine" in r for r in rows), "本流程預設展開"
    assert any("morning" + flowfile.EXT in r for r in rows)
    assert not any("btn" in r for r in rows), "其他存檔預設收合"


def test_展開其他存檔看到它的範本(picker):
    app = picker
    other = os.path.join(app.profile_dir, "flows", "night" + flowfile.EXT)
    os.makedirs(os.path.dirname(other), exist_ok=True)
    flowfile.write(other, {"steps": [{"type": "find_click", "template": "gear"}],
                           "coordSpace": "region"}, {"gear": _png(90, 30, 20)})
    d = _Driver(app.root, TITLE)
    seen = {}

    def expand(dr):
        dr.select("night")
        seen["rows"] = dr.rows_text()

    def preview(dr):
        dr.select("gear")
        seen["info"] = dr.info_text()
        dr.press("取消")

    _open(app, d, expand, preview)
    assert any("gear" in r for r in seen["rows"])
    assert "名稱：gear" in seen["info"]
    assert "30×20px" in seen["info"], "右側預覽顯示尺寸"
    assert "night" in seen["info"], "右側預覽顯示來源"


# ---------- 確定才複製 / 取消不留痕 ----------

def test_按確定才把其他存檔的圖複製進本流程(picker):
    app = picker
    other = os.path.join(app.profile_dir, "flows", "src" + flowfile.EXT)
    os.makedirs(os.path.dirname(other), exist_ok=True)
    flowfile.write(other, {"steps": [{"type": "find_click", "template": "gear"}],
                           "coordSpace": "region"}, {"gear": _png(90)})
    d = _Driver(app.root, TITLE)

    def pick(dr):
        dr.select("src")
        dr.select("gear")
        dr.press("確定")

    got = _open(app, d, pick)
    assert got == "gear"
    assert app.ws.names() == ["gear"]
    assert open(app.ws.path_of("gear"), "rb").read() == _png(90)


def test_按取消時檔案系統完全沒有變化(picker):
    app = picker
    other = os.path.join(app.profile_dir, "flows", "src" + flowfile.EXT)
    os.makedirs(os.path.dirname(other), exist_ok=True)
    flowfile.write(other, {"steps": [{"type": "find_click", "template": "gear"}],
                           "coordSpace": "region"}, {"gear": _png(90)})
    before = _snapshot(app.ws)
    d = _Driver(app.root, TITLE)

    def pick_then_cancel(dr):
        dr.select("src")
        dr.select("gear")
        dr.press("取消")

    got = _open(app, d, pick_then_cancel)
    assert got is None
    assert _snapshot(app.ws) == before
    assert app.ws.names() == []


def _snapshot(ws):
    """工作區的完整內容快照 (檔名 → 內容); 用來斷言「什麼都沒發生」."""
    out = {}
    for base, _dirs, files in os.walk(ws.root):
        for fn in files:
            p = os.path.join(base, fn)
            out[os.path.relpath(p, ws.root)] = open(p, "rb").read()
    return out


def test_跨流程複製進來的是獨立副本(picker):
    app = picker
    other = os.path.join(app.profile_dir, "flows", "src" + flowfile.EXT)
    os.makedirs(os.path.dirname(other), exist_ok=True)
    flowfile.write(other, {"steps": [{"type": "find_click", "template": "gear"}],
                           "coordSpace": "region"}, {"gear": _png(90)})
    d = _Driver(app.root, TITLE)

    def pick(dr):
        dr.select("src")
        dr.select("gear")
        dr.press("確定")

    _open(app, d, pick)
    # 來源流程日後改圖
    flowfile.write(other, {"steps": [{"type": "find_click", "template": "gear"}],
                           "coordSpace": "region"}, {"gear": _png(10)})
    assert open(app.ws.path_of("gear"), "rb").read() == _png(90)


def test_撞名自動加序號並寫進執行紀錄(picker):
    app = picker
    app.ws.add("gear", _png(1))
    other = os.path.join(app.profile_dir, "flows", "src" + flowfile.EXT)
    os.makedirs(os.path.dirname(other), exist_ok=True)
    flowfile.write(other, {"steps": [{"type": "find_click", "template": "gear"}],
                           "coordSpace": "region"}, {"gear": _png(90)})
    d = _Driver(app.root, TITLE)

    def pick(dr):
        dr.select("src")                      # 展開來源存檔
        dr.select("gear", under="src")        # 明確選它裡面那一張
        dr.press("確定")

    got = _open(app, d, pick)
    assert got == "gear_2", "本流程原有的圖絕對不會被蓋掉"
    assert open(app.ws.path_of("gear"), "rb").read() == _png(1)
    assert open(app.ws.path_of("gear_2"), "rb").read() == _png(90)
    assert any("自動改名" in m for _lvl, m in app.logged)


def test_選本流程已有的範本不複製(picker):
    app = picker
    app.ws.add("btn", _png(1))
    d = _Driver(app.root, TITLE)

    def pick(dr):
        dr.select("btn")
        dr.press("確定")

    got = _open(app, d, pick)
    assert got == "btn"
    assert app.ws.names() == ["btn"], "沒有多出一份副本"


# ---------- 現場截圖 ----------

def test_現場截圖後按確定才落地(picker):
    app = picker
    app.shot = {"img": _img(77, 20, 10), "screenX": 100, "screenY": 200,
                "w": 20, "h": 10}
    d = _Driver(app.root, TITLE)

    def shoot_ok(dr):
        dr.press("截圖新增")
        dr.press("確定")

    got = _open(app, d, shoot_ok)
    assert got == "tmpl_001"
    assert app.ws.names() == ["tmpl_001"]
    assert app.ws.pos_of("tmpl_001") == [110, 205], "截圖有記 pos"


def test_現場截圖後按取消那張圖被丟棄(picker):
    app = picker
    app.shot = {"img": _img(77, 20, 10), "screenX": 100, "screenY": 200,
                "w": 20, "h": 10}
    d = _Driver(app.root, TITLE)
    seen = {}

    def shoot_cancel(dr):
        dr.press("截圖新增")
        seen["rows"] = dr.rows_text()
        dr.press("取消")

    got = _open(app, d, shoot_cancel)
    assert got is None
    assert any("tmpl_001" in r for r in seen["rows"]), "截完在對話框裡看得到"
    assert app.ws.names() == [], "取消就是取消, 不留下我沒要的範本"
    assert _snapshot(app.ws) == {}


def test_加入範本後提示建議跑比對測試(picker):
    app = picker
    app.shot = {"img": _img(77, 20, 10), "screenX": 0, "screenY": 0,
                "w": 20, "h": 10}
    d = _Driver(app.root, TITLE)

    def shoot_ok(dr):
        dr.press("截圖新增")
        dr.press("確定")

    _open(app, d, shoot_ok)
    assert any("比對測試" in m for _lvl, m in app.logged)


# ---------- 從磁碟挑 PNG ----------

def test_從磁碟挑png_確定後複製進本流程(picker, tmp_path, monkeypatch):
    app = picker
    src = tmp_path / "outside.png"
    imgio.imwrite(str(src), _img(33, 16, 9))
    monkeypatch.setattr(ui_dialogs.filedialog, "askopenfilenames",
                        lambda **kw: (str(src),))
    d = _Driver(app.root, TITLE)

    def disk_ok(dr):
        dr.press("從磁碟挑圖…")
        dr.press("確定")

    got = _open(app, d, disk_ok)
    assert got == "outside"
    assert app.ws.names() == ["outside"]
    assert app.ws.pos_of("outside") is None, "從磁碟上傳的沒有 pos"


def test_從磁碟挑png_取消不留痕(picker, tmp_path, monkeypatch):
    app = picker
    src = tmp_path / "outside.png"
    imgio.imwrite(str(src), _img(33, 16, 9))
    monkeypatch.setattr(ui_dialogs.filedialog, "askopenfilenames",
                        lambda **kw: (str(src),))
    d = _Driver(app.root, TITLE)

    def disk_cancel(dr):
        dr.press("從磁碟挑圖…")
        dr.press("取消")

    assert _open(app, d, disk_cancel) is None
    assert _snapshot(app.ws) == {}


# ---------- 就緒 gating ----------

def test_引擎未就緒時對話框照樣開得起來也挑得動(tkroot, tmp_path):
    """挑圖不需要辨識, 只有比對類動作才走既有的就緒 gating."""
    tkroot.deiconify()
    tkroot.geometry("+40+40")
    tkroot.update()
    try:
        app = _PickApp(tkroot, tmp_path, state=enginehub.LOADING)
        app.ws.add("btn", _png(1))
        d = _Driver(app.root, TITLE)

        def pick(dr):
            dr.select("btn")
            dr.press("確定")

        assert _open(app, d, pick) == "btn"
    finally:
        tkroot.withdraw()


def test_沒選任何一列就按確定會提示(picker, monkeypatch):
    app = picker
    warns = []
    monkeypatch.setattr(ui_dialogs.messagebox, "showwarning",
                        lambda title, msg, **kw: warns.append(msg))
    d = _Driver(app.root, TITLE)

    def ok_then_cancel(dr):
        dr.press("確定")
        dr.press("取消")

    assert _open(app, d, ok_then_cancel) is None
    assert warns and "選一張" in warns[0]

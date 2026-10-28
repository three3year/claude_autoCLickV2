import os
from types import SimpleNamespace
import tkinter as tk

import numpy as np
import pytest

import harness

import app as app_mod
import enginehub
import flowfile
import ui_dialogs
from automation import imgio


class _PickApp(app_mod.App):
    def __init__(self, root, base_dir, state=enginehub.READY):
        self.root = root
        self.store = flowfile.FlowTemplates.new(os.path.join(str(base_dir), "unsaved"))
        self.hub = enginehub.EngineHub()
        self.hub.state = state
        self.library = None
        self.steps = []
        self._pending_templates = set()
        self._rereg_after = None
        self.logged = []
        self.reloads = 0
        self.shot = None
        self.shot_anchor = None
        self.shot_k = 1.0

    def rebind_templates(self, changed=None):
        self.reloads += 1

    def refresh_templates(self):
        pass

    def render_steps(self, keep=None):
        pass

    def log_ui(self, msg, level="info"):
        self.logged.append((level, msg))

    def pick_region_measured(self, done, hide=(), parent=None):
        if self.shot:
            done(self.shot, SimpleNamespace(anchor=self.shot_anchor, k=self.shot_k,
                                            frame=self.shot.get("frame"), job=None))

    def _schedule_reregister(self):
        pass


def _img(fill=200, w=12, h=8):
    a = np.zeros((h, w, 3), np.uint8)
    a[:] = fill
    return a


def _png(fill=200, w=12, h=8):
    return imgio.encode_png(_img(fill, w, h))


def _other_flow(name, template, images):
    import apppaths
    folder = os.path.join(apppaths.flows_root(), name)
    flow = flowfile.new_flow()
    flow["steps"] = [{"type": "find_click", "target": {"template": template}}]
    flowfile.write_flow(folder, flow, images)
    return folder


def _first(widget, cls):
    for child in widget.winfo_children():
        if child.winfo_class() == cls:
            return child
        got = _first(child, cls)
        if got is not None:
            return got
    return None


class _Driver:
    STEP_MS = 60
    LEFT_OPEN_MS = 10000

    def __init__(self, root, title):
        self.root = root
        self.title = title
        self.dlg = None
        self.error = None
        self._todo = []

    def run(self, *actions):
        self._todo = list(actions)
        self.root.after(self.STEP_MS, self._start)

    def _start(self):
        self._attach()
        self._next()

    def _next(self):
        if self.error is not None:
            return
        if not self._todo:
            self.root.after(self.LEFT_OPEN_MS, self._left_open)
            return
        act = self._todo.pop(0)
        try:
            act(self)
        except BaseException as e:
            self.error = e
            self.close()
            return
        self.root.after(self.STEP_MS, self._next)

    def _left_open(self):
        if self.error is None and self.dlg is not None and self.dlg.winfo_exists():
            self.error = AssertionError(
                f"動作都做完了，對話框「{self.title}」還開著（例如確定沒通過）")
            self.close()

    def _attach(self):
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel) and w.winfo_exists()                     and w.title() == self.title:
                self.dlg = w
                self.tree = _first(w, "Treeview")
                return
        self.error = AssertionError(f"對話框沒開起來: {self.title}")

    def _nodes(self, parent=""):
        out = []
        for node in self.tree.get_children(parent):
            out.append((node, self.tree.item(node, "text")))
            if self.tree.item(node, "open"):
                out.extend(self._nodes(node))
        return out

    def rows_text(self):
        return [text for _node, text in self._nodes()]

    def _find_node(self, needle, under=None):
        parent = ""
        if under is not None:
            parent = next(n for n, tx in self._nodes() if under in tx)
        for node, text in self._nodes(parent):
            if needle in text:
                return node
        raise AssertionError(
            f"樹裡沒有 {needle!r}（under={under!r}）: {self.rows_text()}")

    def select(self, needle, under=None):
        self._update()
        node = self._find_node(needle, under)
        self.tree.focus(node)
        if self.tree.parent(node) == "":
            self.tree.item(node, open=True)
            self.tree.event_generate("<<TreeviewOpen>>")
        else:
            self.tree.selection_set(node)
            self.tree.event_generate("<<TreeviewSelect>>")
        self._update()

    def press(self, text):
        _btn(self.dlg, text).invoke()
        if self.dlg.winfo_exists():
            self._update()

    def _update(self):
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


def _slow_dialog(root, title, build_ms, busy_ms):
    import time
    dlg = tk.Toplevel(root)
    dlg.title(title)
    time.sleep(build_ms / 1000)
    left = [3]

    def burst():
        if dlg.winfo_exists() and left[0] > 0:
            left[0] -= 1
            time.sleep(busy_ms / 1000)
            dlg.after(1, burst)
    dlg.after(0, burst)
    root.wait_window(dlg)


@pytest.mark.parametrize("build_ms,busy_ms", [(150, 60), (220, 40), (250, 20)])
def test_驅動照順序做動作_對話框開得慢也不插隊(picker, build_ms, busy_ms):
    order = []

    def step(k):
        def act(dr):
            order.append(k)
            dr._update()
        return act
    d = _Driver(picker.root, "慢對話框")
    d.run(step(1), step(2), step(3), lambda dr: dr.close())
    _slow_dialog(picker.root, "慢對話框", build_ms, busy_ms)
    assert d.error is None
    assert order == [1, 2, 3]


def test_動作做完對話框還開著_算失敗並關掉_不卡住(picker, monkeypatch):
    monkeypatch.setattr(_Driver, "LEFT_OPEN_MS", 200)
    d = _Driver(picker.root, "關不掉")
    d.run(lambda dr: None)
    _slow_dialog(picker.root, "關不掉", build_ms=0, busy_ms=0)
    assert isinstance(d.error, AssertionError)
    assert "還開著" in str(d.error)


def test_左側列出本流程與其他流程存檔(picker):
    app = picker
    app.store.add("mine", _png())
    other = _other_flow("morning", "btn", {"btn": _png(50)})
    d = _Driver(app.root, TITLE)

    seen = {}

    def look(dr):
        seen["rows"] = dr.rows_text()
        dr.press("取消")

    _open(app, d, look)
    rows = seen["rows"]
    assert any("本流程" in r for r in rows)
    assert any("mine" in r for r in rows), "本流程預設展開"
    assert any("morning" in r for r in rows)
    assert not any("btn" in r for r in rows), "其他存檔預設收合"


def test_展開其他存檔看到它的範本(picker):
    app = picker
    other = _other_flow("night", "gear", {"gear": _png(90, 30, 20)})
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


def test_按確定才把其他存檔的圖複製進本流程(picker):
    app = picker
    other = _other_flow("src", "gear", {"gear": _png(90)})
    d = _Driver(app.root, TITLE)

    def pick(dr):
        dr.select("src")
        dr.select("gear")
        dr.press("確定")

    got = _open(app, d, pick)
    assert got == "gear"
    assert app.store.names() == ["gear"]
    assert open(app.store.path_of("gear"), "rb").read() == _png(90)


def test_按取消時檔案系統完全沒有變化(picker):
    app = picker
    other = _other_flow("src", "gear", {"gear": _png(90)})
    before = _snapshot(app.store)
    d = _Driver(app.root, TITLE)

    def pick_then_cancel(dr):
        dr.select("src")
        dr.select("gear")
        dr.press("取消")

    got = _open(app, d, pick_then_cancel)
    assert got is None
    assert _snapshot(app.store) == before
    assert app.store.names() == []


def _snapshot(store):
    out = {}
    for base, _dirs, files in os.walk(store.cache):
        for fn in files:
            p = os.path.join(base, fn)
            out[os.path.relpath(p, store.cache)] = open(p, "rb").read()
    return out


def test_跨流程複製進來的是獨立副本(picker):
    app = picker
    other = _other_flow("src", "gear", {"gear": _png(90)})
    d = _Driver(app.root, TITLE)

    def pick(dr):
        dr.select("src")
        dr.select("gear")
        dr.press("確定")

    _open(app, d, pick)
    _other_flow(os.path.basename(other), "gear", {"gear": _png(10)})
    assert open(app.store.path_of("gear"), "rb").read() == _png(90)


def test_撞名自動加序號並寫進執行紀錄(picker):
    app = picker
    app.store.add("gear", _png(1))
    other = _other_flow("src", "gear", {"gear": _png(90)})
    d = _Driver(app.root, TITLE)

    def pick(dr):
        dr.select("src")
        dr.select("gear", under="src")
        dr.press("確定")

    got = _open(app, d, pick)
    assert got == "gear_2", "本流程原有的圖絕對不會被蓋掉"
    assert open(app.store.path_of("gear"), "rb").read() == _png(1)
    assert open(app.store.path_of("gear_2"), "rb").read() == _png(90)
    assert any("自動改名" in m for _lvl, m in app.logged)


def test_選本流程已有的範本不複製(picker):
    app = picker
    app.store.add("btn", _png(1))
    d = _Driver(app.root, TITLE)

    def pick(dr):
        dr.select("btn")
        dr.press("確定")

    got = _open(app, d, pick)
    assert got == "btn"
    assert app.store.names() == ["btn"], "沒有多出一份副本"


def test_現場截圖後按確定才落地(picker):
    app = picker
    app.shot = {"img": _img(77, 20, 10), "screenX": 100, "screenY": 200,
                "w": 20, "h": 10}
    app.shot_anchor = (60, 180)
    d = _Driver(app.root, TITLE)

    def shoot_ok(dr):
        dr.press("截圖新增")
        dr.press("確定")

    got = _open(app, d, shoot_ok)
    assert got == "tmpl_001"
    assert app.store.names() == ["tmpl_001"]
    assert app.store.pos_of("tmpl_001") == [50, 25], "截圖有記拍攝位置 (相對基準點)"


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
    assert app.store.names() == [], "取消就是取消, 不留下我沒要的範本"
    assert _snapshot(app.store) == {}


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
    assert app.store.names() == ["outside"]
    assert app.store.pos_of("outside") is None, "從磁碟上傳的沒有 pos"


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
    assert _snapshot(app.store) == {}


def test_引擎未就緒時對話框照樣開得起來也挑得動(tkroot, tmp_path):
    tkroot.deiconify()
    tkroot.geometry("+40+40")
    tkroot.update()
    try:
        app = _PickApp(tkroot, tmp_path, state=enginehub.LOADING)
        app.store.add("btn", _png(1))
        d = _Driver(app.root, TITLE)

        def pick(dr):
            dr.select("btn")
            dr.press("確定")

        assert _open(app, d, pick) == "btn"
    finally:
        tkroot.withdraw()


def test_沒選任何一列就按確定_底列提示_不彈窗(picker, no_real_dialogs):
    app = picker
    d = _Driver(app.root, TITLE)
    seen = {}

    def ok_then_cancel(dr):
        dr.press("確定")
        seen["labels"] = [str(w.cget("text")) for w in _all(dr.dlg)
                          if w.winfo_class() == "TLabel"]
        dr.press("取消")

    assert _open(app, d, ok_then_cancel) is None
    assert "請先選一張範本" in seen["labels"]
    assert not any(no_real_dialogs.values())


def test_取消整個對話框時這次加的範本被丟棄(picker):
    app = picker
    app.store.add("kept", b"K")
    app.steps = [{"type": "find_click", "target": {"template": "kept"}}]

    ui_dialogs.discard_unused(app, ["shot_1", "shot_2"], None)

    assert app.store.names() == ["kept"], "這次加的都不留"
    assert any("丟棄" in m for _l, m in app.logged)


def test_按確定時只留這一步真的引用到的(picker):
    app = picker
    for n in ("a", "b", "c"):
        app.store.add(n, b"X")
    step = {"type": "find_click", "target": {"template": "a"},
            "confirm": "appear", "confirm_target": {"template": "c"}}

    ui_dialogs.discard_unused(app, ["a", "b", "c"], step)

    assert app.store.names() == ["a", "c"], "中途換掉的那張不留"


def test_已被其他步驟引用的絕不誤刪(picker):
    app = picker
    app.store.add("shared", b"S")
    app.steps = [{"type": "find_click", "target": {"template": "shared"}}]

    ui_dialogs.discard_unused(app, ["shared"], None)

    assert app.store.names() == ["shared"]


def test_校準對的範本絕不誤刪(picker):
    app = picker
    app.store.add("圖示", b"I")
    app.store.add("關閉", b"X")
    app.flow_cal = {"pair": ["圖示", "關閉"], "baseline": 1696.0}

    ui_dialogs.discard_unused(app, ["圖示", "關閉"], None)

    assert app.store.names() == sorted(["圖示", "關閉"])


def test_沒有新增範本時是空操作(picker):
    app = picker
    app.store.add("a", b"A")
    ui_dialogs.discard_unused(app, [], None)
    assert app.store.names() == ["a"]
    assert app.logged == []


def test_樹狀每一列都帶縮圖_展開時才讀(picker):
    app = picker
    app.store.add("mine", _png(200, 20, 12))
    other = _other_flow("src", "gear", {"gear": _png(90)})
    d = _Driver(app.root, TITLE)
    seen = {}

    def look(dr):
        node = dr._find_node("mine")
        seen["cur"] = dr.tree.item(node, "image")
        dr.select("src")
        node = dr._find_node("gear", under="src")
        seen["other"] = dr.tree.item(node, "image")
        dr.press("取消")

    _open(app, d, look)
    assert seen["cur"], "本流程的範本列有縮圖"
    assert seen["other"], "其他存檔的範本列也有縮圖"


def test_未展開的來源不去讀它的圖(picker, monkeypatch):
    app = picker
    _other_flow("src", "gear", {"gear": _png(90)})
    reads = []
    real = flowfile.folder_template_bytes
    monkeypatch.setattr(flowfile, "folder_template_bytes",
                        lambda p, n: (reads.append((p, n)), real(p, n))[1])
    d = _Driver(app.root, TITLE)

    def just_look(dr):
        dr.press("取消")

    _open(app, d, just_look)
    assert reads == [], "沒展開就不去讀那份存檔裡的圖"

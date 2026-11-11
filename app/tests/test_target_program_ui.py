import os
import tkinter as tk

import pytest

import app as app_mod
import flowfile
from automation import win
from test_main_window import _logs, _row_button, _row_texts, _settings
from test_template_picker import _Driver, _all

TC = r"C:\Program Files\GRYPHLINK\games\Arknights_TC\Arknights.exe"
CN = r"C:\Program Files\Arknights bilibili\games\Arknights Game\Arknights.exe"
PYEXE = r"C:\Python313\python.exe"
PICK = "選擇目標程式"
ROW = 3
UNSET = "未設定（串接時必須有）"


def W(hwnd, path, size=(1280, 720), title="明日方舟", pid=None, minimized=False):
    return win.Window(hwnd=hwnd, pid=1000 + hwnd if pid is None else pid, title=title,
                      size=size, path=path, minimized=minimized)


@pytest.fixture
def windows(monkeypatch):
    shown = []
    monkeypatch.setattr(win, "list_windows", lambda: list(shown))
    return shown


@pytest.fixture
def fronted(monkeypatch):
    got = []
    monkeypatch.setattr(win, "bring_to_front", lambda hwnd, **kw: got.append(hwnd) or True)
    return got


def _pick(a, *actions):
    d = _Driver(a.root, PICK)
    d.run(*actions)
    a.set_program()
    if d.error is not None:
        raise d.error


def _rows(dr):
    t = dr.tree
    return [(list(t.item(n, "values")), "off" in t.item(n, "tags"))
            for n in t.get_children()]


def _node(dr, title, path):
    for n in dr.tree.get_children():
        v = dr.tree.item(n, "values")
        if v[0] == title and v[3] == path:
            return n
    raise AssertionError((title, path, _rows(dr)))


def _choose(dr, node):
    dr.tree.selection_set(node)
    dr.tree.event_generate("<<TreeviewSelect>>")
    dr._update()


def _selected_paths(dr):
    return [dr.tree.item(n, "values")[3] for n in dr.tree.selection()]


def test_選程式清單_欄位_不列出自己這個程序_別的同路徑程序照列(main_app, windows):
    windows += [W(1, PYEXE, (800, 600), title="AutoClick", pid=os.getpid()),
                W(2, TC), W(3, CN, (1600, 900), minimized=True),
                W(5, PYEXE, (640, 480), title="別的 Python")]
    seen = {}

    def look(dr):
        t = dr.tree
        seen["heads"] = [t.heading(c, "text") for c in t["columns"]]
        seen["rows"] = _rows(dr)
        dr.press("取消")
    _pick(main_app, look)
    assert seen["heads"] == ["標題", "程式", "大小", "路徑"]
    assert seen["rows"] == [
        (["明日方舟", "Arknights.exe", "1280×720", TC], False),
        (["明日方舟", "Arknights.exe", "1600×900", CN], False),
        (["別的 Python", "python.exe", "640×480", PYEXE], False)]
    assert main_app.program is None and not main_app.dirty


def test_選一列按確定_記下完整路徑_標為未存檔(main_app, windows):
    a = main_app
    windows += [W(2, TC), W(3, CN, (1600, 900))]

    def choose(dr):
        _choose(dr, _node(dr, "明日方舟", CN))
        dr.press("確定")
    _pick(a, choose)
    assert a.program == CN
    assert a.dirty and a.root.title().startswith("*")
    assert any("目標程式" in m and CN in m for m in _logs(a))


def test_讀不到路徑的列反灰_不能選(main_app, windows):
    a = main_app
    windows += [W(2, TC), W(4, None, title="受保護的程式")]
    seen = {}

    def choose(dr):
        seen["row"] = _rows(dr)[1]
        _choose(dr, dr.tree.get_children()[1])
        seen["sel"] = list(dr.tree.selection())
        dr.press("確定")
        seen["open"] = dr.dlg.winfo_exists()
        dr.press("取消")
    _pick(a, choose)
    values, off = seen["row"]
    assert values[0] == "受保護的程式" and off
    assert seen["sel"] == [] and seen["open"], "選不到, 確定也不收"
    assert a.program is None


def test_有設定時預先選中路徑相同的列_同路徑多個取最大的(main_app, windows):
    a = main_app
    a.program = TC.lower().replace("\\", "/")
    windows += [W(2, TC, (400, 300), title="小"), W(3, CN), W(6, TC, (1280, 720), title="大")]
    seen = {}

    def look(dr):
        seen["sel"] = [dr.tree.item(n, "values")[0] for n in dr.tree.selection()]
        seen["first"] = _rows(dr)[0]
        dr.press("取消")
    _pick(a, look)
    assert seen["sel"] == ["大"]
    assert seen["first"] == (["小", "Arknights.exe", "400×300", TC], False), \
        "程式有開就不加「目前設定」那列"


def test_設定的程式沒開_最上面一列反灰的目前設定_不能選(main_app, windows):
    a = main_app
    a.program = TC
    windows += [W(3, CN)]
    seen = {}

    def look(dr):
        seen["rows"] = _rows(dr)
        _choose(dr, dr.tree.get_children()[0])
        seen["sel"] = list(dr.tree.selection())
        dr.press("取消")
    _pick(a, look)
    (first, off), second = seen["rows"]
    assert first[0].startswith("目前設定：") and first[0].endswith("（沒在執行）")
    assert first[3] == TC and off
    assert second == (["明日方舟", "Arknights.exe", "1280×720", CN], False)
    assert seen["sel"] == []
    assert a.program == TC and not a.dirty


def test_重新整理_剛開的程式出現(main_app, windows):
    a = main_app
    windows += [W(3, CN)]
    seen = {}

    def refresh(dr):
        seen["before"] = len(_rows(dr))
        windows.append(W(2, TC))
        dr.press("重新整理")
        _choose(dr, _node(dr, "明日方舟", TC))
        dr.press("確定")
    _pick(a, refresh)
    assert seen["before"] == 1
    assert a.program == TC


def _tip_texts(widget):
    widget.event_generate("<Enter>", x=2, y=2)
    widget.update()
    texts = [str(w.cget("text")) for w in _all(widget)
             if isinstance(w, tk.Label) and w.winfo_toplevel() is not widget.winfo_toplevel()]
    widget.event_generate("<Leave>")
    return texts


def _row_label(dlg):
    from test_main_window import _body
    [lbl] = _body(dlg).grid_slaves(row=ROW, column=1)
    return lbl


def test_設定列_沒設時的文字_有設時檔名與資料夾_太長中間省略_滑鼠移上去看完整路徑(main_app):
    a = main_app
    seen = {}
    _settings(a, lambda dr: seen.update(unset=_row_texts(dr.dlg, ROW)))
    assert seen["unset"] == [UNSET]

    a.program = CN

    def look(dr):
        [seen["text"]] = _row_texts(dr.dlg, ROW)
        seen["tip"] = _tip_texts(_row_label(dr.dlg))
    _settings(a, look)
    text = seen["text"]
    assert text.startswith("Arknights.exe（C:\\") and text.endswith("Arknights Game）")
    assert "…" in text and len(text) <= app_mod.PROGRAM_TEXT_MAX
    assert seen["tip"] == [CN]

    a.program = r"C:\Games\a.exe"
    _settings(a, lambda dr: seen.update(short=_row_texts(dr.dlg, ROW)))
    assert seen["short"] == ["a.exe（C:\\Games）"]


def test_設定列_設定後文字跟著換_清除後回到未設定_都標未存檔(main_app, windows):
    a = main_app
    windows += [W(2, TC)]
    seen = {}

    def set_then_clear(dr):
        d = _Driver(a.root, PICK)

        def choose(pdr):
            _choose(pdr, _node(pdr, "明日方舟", TC))
            pdr.press("確定")
        d.run(choose)
        _row_button(dr.dlg, ROW, "設定…").invoke()
        if d.error is not None:
            raise d.error
        dr._update()
        [seen["set"]] = _row_texts(dr.dlg, ROW)
        seen["dirty_after_set"] = a.dirty
        a._set_dirty(False)
        _row_button(dr.dlg, ROW, "清除").invoke()
        dr._update()
        [seen["cleared"]] = _row_texts(dr.dlg, ROW)
    _settings(a, set_then_clear)
    assert seen["set"].startswith("Arknights.exe（") and seen["dirty_after_set"]
    assert seen["cleared"] == UNSET
    assert a.program is None and a.dirty


def test_開流程讀進目標程式_存檔寫回(main_app, tmp_path):
    a = main_app
    folder = tmp_path / "早_繁中"
    f = flowfile.new_flow()
    f["program"] = TC
    flowfile.write_flow(folder, f, {})
    a.open_flow_folder(str(folder))
    assert a.program == TC
    a.program = CN
    a._mark_dirty()
    assert a.save_flow()
    assert flowfile.read_flow(folder)["program"] == CN
    a.new_flow()
    assert a.program is None


class _After:
    def __init__(self, a, monkeypatch):
        self.calls = []
        monkeypatch.setattr(a.root, "after", self.after, raising=False)

    def after(self, ms, fn=None, *args):
        self.calls.append((ms, fn, args))
        return f"after#{len(self.calls)}"

    def fire(self):
        calls, self.calls = self.calls, []
        for _ms, fn, args in calls:
            fn(*args)


def test_測試_移到最上層並寫紀錄_約2秒後把AutoClick移回前景(main_app, windows, fronted,
                                                     monkeypatch):
    a = main_app
    a.program = TC
    windows += [W(2, TC, (1280, 720), minimized=True), W(3, CN, (1600, 900))]
    clock = _After(a, monkeypatch)
    a.test_program()
    assert fronted == [2]
    assert any("目標程式已移到最上層：Arknights.exe（1280×720）" in m for m in _logs(a))
    assert [ms for ms, _fn, _a in clock.calls] == [2000]
    clock.fire()
    assert fronted == [2, win.root_hwnd(a.root.winfo_id())]


def test_測試_找不到就寫找不到_不移任何視窗(main_app, windows, fronted, monkeypatch):
    a = main_app
    a.program = TC
    windows += [W(3, CN), W(1, TC, pid=os.getpid())]
    clock = _After(a, monkeypatch)
    a.test_program()
    assert fronted == [] and clock.calls == []
    assert any(f"找不到：{TC}沒在執行" in m for m in _logs(a))


def test_測試_移不到最上層寫警告_照樣移回AutoClick(main_app, windows, monkeypatch):
    a = main_app
    a.program = TC
    windows += [W(2, TC)]
    got = []
    monkeypatch.setattr(win, "bring_to_front", lambda hwnd, **kw: got.append(hwnd) and False)
    clock = _After(a, monkeypatch)
    a.test_program()
    assert any("移不到最上層" in m for m in _logs(a))
    clock.fire()
    assert got == [2, win.root_hwnd(a.root.winfo_id())]


def test_測試_沒設目標程式只寫一行(main_app, fronted):
    main_app.test_program()
    assert fronted == []
    assert any("目標程式還沒設定" in m for m in _logs(main_app))

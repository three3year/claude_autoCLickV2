import os

import pytest
from tkinter import messagebox

import apppaths
import flowfile
import ui_chain
import ui_dialogs
from test_template_picker import _Driver, _all, _btn, _first

TC = r"C:\Program Files\GRYPHLINK\games\Arknights_TC\Arknights.exe"
TITLE = ui_chain.TITLE


def _root():
    return apppaths.flows_root()


def _flow(name, program=TC):
    f = flowfile.new_flow()
    f["program"] = program
    flowfile.write_flow(os.path.join(_root(), name), f)


def _broken(name):
    folder = os.path.join(_root(), name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, flowfile.FLOW_YAML), "w", encoding="utf-8") as f:
        f.write("format: 9\n")


def _chain(name, *flows):
    flowfile.write_chain(_root(), name, [{"flow": f, "run": r} for f, r in flows])


def _chain_text(name):
    with open(flowfile.chain_path(_root(), name), encoding="utf-8") as f:
        return f.read()


def _edit(a, *actions):
    d = _Driver(a.root, TITLE)

    def close(dr):
        if dr.dlg.winfo_exists():
            dr.press("關閉")
    d.run(*actions, close)
    _btn(a.root, "串接…").invoke()
    if d.error is not None:
        raise d.error


def _rows(dr):
    t = dr.tree
    return [[str(v) for v in t.item(n, "values")] for n in t.get_children()]


def _combo(dr):
    return _first(dr.dlg, "TCombobox")


def test_開啟時選第一個串接檔_每列流程名輪數與三種警告(main_app):
    _flow("早_繁中")
    _flow("早_簡中", program=None)
    _broken("壞的")
    _chain("晚班")
    _chain("早班", ("早_繁中", 1), ("早_簡中", 2), ("壞的", 1), ("不見了", 1))
    seen = {}

    def look(dr):
        seen["chains"] = list(_combo(dr).cget("values"))
        seen["chain"] = _combo(dr).get()
        seen["rows"] = _rows(dr)
    _edit(main_app, look)
    assert seen["chains"] == ["早班", "晚班"]
    assert seen["chain"] == "早班"
    assert seen["rows"] == [["早_繁中", "1", ""],
                            ["早_簡中", "2", "⚠ 未設目標程式"],
                            ["壞的", "1", "⚠ 讀不到流程"],
                            ["不見了", "1", "⚠ 流程不在存放區"]]


def _select(dr, index):
    node = dr.tree.get_children()[index]
    dr.tree.selection_set(node)
    dr.tree.event_generate("<<TreeviewSelect>>")
    dr._update()


def _add(dr, flow, look=None):
    d = _Driver(dr.root, ui_chain.ADD_TITLE)

    def choose(pdr):
        rows = _rows(pdr)
        if look is not None:
            look(rows)
        [i] = [n for n, r in enumerate(rows) if r[0] == flow]
        pdr.tree.selection_set(pdr.tree.get_children()[i])
        pdr._update()
        pdr.press("確定")
    d.run(choose)
    dr.press("加入…")
    if d.error is not None:
        raise d.error


def test_加入_清單是存放區的流程且標警告_插在選取列之後_同一份可加兩次_存檔內容(main_app):
    _flow("早_繁中")
    _flow("早_簡中", program=None)
    _broken("壞的")
    _chain("早班", ("早_繁中", 1))
    seen = {}

    def edit(dr):
        _add(dr, "早_簡中", look=lambda rows: seen.update(pick=rows))
        _select(dr, 0)
        _add(dr, "早_繁中")
        seen["rows"] = _rows(dr)
        dr.press("存檔")
    _edit(main_app, edit)
    assert seen["pick"] == [["壞的", "⚠ 讀不到流程"], ["早_簡中", "⚠ 未設目標程式"],
                            ["早_繁中", ""]]
    assert seen["rows"] == [["早_繁中", "1", ""], ["早_繁中", "1", ""],
                            ["早_簡中", "1", "⚠ 未設目標程式"]]
    assert _chain_text("早班") == ("format: 1\nflows:\n  - {flow: 早_繁中}\n"
                                   "  - {flow: 早_繁中}\n  - {flow: 早_簡中}\n")


def test_移除上移下移_存檔內容_流程本身不變(main_app):
    for n in ("A", "B", "C", "D"):
        _flow(n)
    before = {n: open(os.path.join(_root(), n, flowfile.FLOW_YAML), "rb").read()
              for n in "ABCD"}
    _chain("早班", ("A", 1), ("B", 2), ("C", 1), ("D", 1))
    seen = {}

    def edit(dr):
        _select(dr, 1)
        dr.press("移除")
        seen["after_remove"] = [r[0] for r in _rows(dr)]
        _select(dr, 2)
        dr.press("上移")
        seen["after_up"] = [r[0] for r in _rows(dr)]
        _select(dr, 0)
        dr.press("下移")
        seen["after_down"] = [r[0] for r in _rows(dr)]
        seen["selected"] = dr.tree.index(dr.tree.selection()[0])
        dr.press("存檔")
    _edit(main_app, edit)
    assert seen["after_remove"] == ["A", "C", "D"]
    assert seen["after_up"] == ["A", "D", "C"]
    assert seen["after_down"] == ["D", "A", "C"]
    assert seen["selected"] == 1, "選取跟著搬動的那列"
    assert _chain_text("早班") == ("format: 1\nflows:\n  - {flow: D}\n  - {flow: A}\n"
                                   "  - {flow: C}\n")
    after = {n: open(os.path.join(_root(), n, flowfile.FLOW_YAML), "rb").read()
             for n in "ABCD"}
    assert after == before


def _run_box(dr):
    return _first(dr.dlg, "TSpinbox")


def test_改選中列的輪數_不是正整數不收_存檔寫出非1的輪數(main_app):
    _flow("早_繁中")
    _flow("早_簡中")
    _chain("早班", ("早_繁中", 1), ("早_簡中", 2))
    seen = {}

    def edit(dr):
        _select(dr, 1)
        seen["shown"] = _run_box(dr).get()
        _select(dr, 0)
        _run_box(dr).set("3")
        dr._update()
        for bad in ("0", "abc", "-1", ""):
            _run_box(dr).set(bad)
            dr._update()
            seen.setdefault("bad", []).append(_rows(dr)[0][1])
        _run_box(dr).set("4")
        dr._update()
        _select(dr, 1)
        _run_box(dr).set("1")
        dr._update()
        seen["rows"] = _rows(dr)
        dr.press("存檔")
    _edit(main_app, edit)
    assert seen["shown"] == "2"
    assert seen["bad"] == ["3", "3", "3", "3"]
    assert seen["rows"] == [["早_繁中", "4", ""], ["早_簡中", "1", ""]]
    assert _chain_text("早班") == "format: 1\nflows:\n  - {flow: 早_繁中, run: 4}\n  - {flow: 早_簡中}\n"


@pytest.fixture
def names(monkeypatch):
    answers = []
    monkeypatch.setattr(ui_dialogs, "ask_string", lambda *a, **kw: answers.pop(0))
    return answers


@pytest.fixture
def answers(monkeypatch):
    got = {"asked": [], "yesnocancel": [], "yesno": []}

    def yesnocancel(title, msg, **kw):
        got["asked"].append(msg)
        return got["yesnocancel"].pop(0)

    def yesno(title, msg, **kw):
        got["asked"].append(msg)
        return got["yesno"].pop(0)
    monkeypatch.setattr(messagebox, "askyesnocancel", yesnocancel)
    monkeypatch.setattr(messagebox, "askyesno", yesno)
    return got


def test_新增串接檔_空的並選中_擋下同名與不能當檔名(main_app, names, no_real_dialogs):
    _flow("早_繁中")
    _chain("早班", ("早_繁中", 1))
    seen = {}

    def edit(dr):
        names.extend(["晚班", "早班", "a/b", None])
        dr.press("新增…")
        seen["chain"], seen["rows"] = _combo(dr).get(), _rows(dr)
        seen["chains"] = list(_combo(dr).cget("values"))
        dr.press("新增…")
        dr.press("新增…")
        dr.press("新增…")
        seen["still"] = _combo(dr).get()
    _edit(main_app, edit)
    assert (seen["chain"], seen["rows"]) == ("晚班", [])
    assert seen["chains"] == ["早班", "晚班"]
    assert flowfile.list_chains(_root()) == ["早班", "晚班"]
    assert _chain_text("晚班") == "format: 1\nflows: []\n"
    warned = no_real_dialogs["warning"]
    assert len(warned) == 2 and "已經有" in warned[0] and "不能有 /" in warned[1]
    assert seen["still"] == "晚班"


def test_改名串接檔_內容跟著走_擋下同名(main_app, names, no_real_dialogs):
    _flow("早_繁中")
    _chain("早班", ("早_繁中", 2))
    _chain("晚班")
    seen = {}

    def edit(dr):
        names.extend(["晚班", "白天"])
        dr.press("改名…")
        dr.press("改名…")
        seen["chain"], seen["rows"] = _combo(dr).get(), _rows(dr)
        seen["chains"] = list(_combo(dr).cget("values"))
    _edit(main_app, edit)
    assert "已經有" in no_real_dialogs["warning"][0]
    assert seen["chain"] == "白天" and seen["rows"] == [["早_繁中", "2", ""]]
    assert seen["chains"] == ["晚班", "白天"]
    assert flowfile.read_chain(_root(), "白天") == [{"flow": "早_繁中", "run": 2}]


def test_刪除串接檔_先問_刪完選下一個_流程還在(main_app, answers):
    _flow("早_繁中")
    _chain("早班", ("早_繁中", 1))
    _chain("晚班")
    seen = {}

    def edit(dr):
        answers["yesno"] += [False, True, True]
        dr.press("刪除")
        seen["kept"] = flowfile.list_chains(_root())
        dr.press("刪除")
        seen["chain"] = _combo(dr).get()
        dr.press("刪除")
        seen["empty"] = (_combo(dr).get(), _rows(dr), str(_btn(dr.dlg, "加入…").cget("state")))
    _edit(main_app, edit)
    assert seen["kept"] == ["早班", "晚班"]
    assert seen["chain"] == "晚班"
    assert seen["empty"] == ("", [], "disabled")
    assert flowfile.list_chains(_root()) == []
    assert os.path.isfile(os.path.join(_root(), "早_繁中", flowfile.FLOW_YAML))
    assert all("流程不受影響" in m for m in answers["asked"])


def test_關閉時有未存檔改動先問_取消留著_不存就關且檔案不變(main_app, answers):
    _flow("A")
    _flow("B")
    _chain("早班", ("A", 1), ("B", 1))
    seen = {}

    def edit(dr):
        _select(dr, 0)
        dr.press("下移")
        answers["yesnocancel"] += [None, False]
        dr.press("關閉")
        seen["open_after_cancel"] = dr.dlg.winfo_exists()
        dr.press("關閉")
        seen["open_after_discard"] = dr.dlg.winfo_exists()
    _edit(main_app, edit)
    assert seen == {"open_after_cancel": True, "open_after_discard": False}
    assert len(answers["asked"]) == 2 and "早班" in answers["asked"][0]
    assert flowfile.read_chain(_root(), "早班") == [{"flow": "A", "run": 1},
                                                   {"flow": "B", "run": 1}]


def test_關閉時選存檔_寫進檔案(main_app, answers):
    _flow("A")
    _chain("早班", ("A", 1))
    answers["yesnocancel"].append(True)

    def edit(dr):
        _select(dr, 0)
        _run_box(dr).set("2")
        dr._update()
        dr.press("關閉")
    _edit(main_app, edit)
    assert flowfile.read_chain(_root(), "早班") == [{"flow": "A", "run": 2}]


def test_沒改動關閉不問(main_app, answers):
    _flow("A")
    _chain("早班", ("A", 1))
    _edit(main_app, lambda dr: _select(dr, 0))
    assert answers["asked"] == []


def _choose_chain(dr, name):
    _combo(dr).set(name)
    _combo(dr).event_generate("<<ComboboxSelected>>")
    dr._update()


def test_切換串接檔時有未存檔改動先問_取消留在原本的(main_app, answers):
    _flow("A")
    _chain("早班", ("A", 1))
    _chain("晚班", ("A", 3))
    seen = {}

    def edit(dr):
        _select(dr, 0)
        dr.press("移除")
        answers["yesnocancel"] += [None, False]
        _choose_chain(dr, "晚班")
        seen["cancel"] = (_combo(dr).get(), _rows(dr))
        _choose_chain(dr, "晚班")
        seen["switched"] = (_combo(dr).get(), _rows(dr))
    _edit(main_app, edit)
    assert seen["cancel"] == ("早班", [])
    assert seen["switched"] == ("晚班", [["A", "3", ""]])
    assert len(answers["asked"]) == 2
    assert flowfile.read_chain(_root(), "早班") == [{"flow": "A", "run": 1}]

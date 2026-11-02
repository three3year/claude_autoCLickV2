"""編輯器支援外部步驟: 新增列、編輯窗 (工具名下拉、參數、備註)、步驟清單 (Tk, 隱藏桌面跑)."""
import flowfile
from test_external_app import _flow_folder
from test_main_window import _btn_in, step_head
from test_template_picker import _Driver, _all

TITLE_NEW = "新增：外部步驟"
TITLE_EDIT = "編輯：外部步驟"


def _widget(dlg, cls):
    [w] = [w for w in _all(dlg) if w.winfo_class() == cls]
    return w


def _fill(name=None, args=None, note=None):
    def act(dr):
        if name is not None:
            _widget(dr.dlg, "TCombobox").set(name)
        if args is not None:
            box = _widget(dr.dlg, "Text")
            box.delete("1.0", "end")
            box.insert("1.0", args)
        if note is not None:
            ent = _widget(dr.dlg, "TEntry")
            ent.delete(0, "end")
            ent.insert(0, note)
        dr._update()
    return act


def _drive(a, title, *actions):
    d = _Driver(a.root, title)
    d.run(*actions)
    return d


def _raise(d):
    if d.error is not None:
        raise d.error


def test_新增列有外部_加入後打開編輯窗(main_app):
    a = main_app
    d = _drive(a, TITLE_NEW, _fill(name="公開招募"), lambda dr: dr.press("確定"))
    _btn_in(step_head(a), "外部").invoke()
    _raise(d)
    assert a.steps == [{"type": "external", "external": "公開招募", "args": [], "note": ""}]
    assert a.dirty


def _values(dr, seen):
    seen["values"] = list(_widget(dr.dlg, "TCombobox").cget("values"))


def test_工具名下拉列出登錄裡的工具(main_app, tmp_path):
    a = main_app
    folder, _ = _flow_folder(tmp_path)
    assert a.open_flow_folder(str(folder))
    seen = {}
    d = _drive(a, TITLE_NEW, lambda dr: _values(dr, seen), lambda dr: dr.press("取消"))
    _btn_in(step_head(a), "外部").invoke()
    _raise(d)
    assert seen["values"] == ["公開招募"]


def test_開著流程補寫登錄_下拉跟著列出(main_app, tmp_path):
    a = main_app
    folder, d = _flow_folder(tmp_path)
    assert a.open_flow_folder(str(folder))
    (folder / flowfile.TOOLS_YAML).write_text(
        f"公開招募:\n  dir: {d}\n  exe: recruit-step.exe\n"
        f"基建:\n  dir: {d}\n  exe: recruit-step.exe\n", encoding="utf-8")
    seen = {}
    dr = _drive(a, TITLE_NEW, lambda dr: _values(dr, seen), lambda dr: dr.press("取消"))
    _btn_in(step_head(a), "外部").invoke()
    _raise(dr)
    assert seen["values"] == ["公開招募", "基建"]


def test_新流程沒有登錄_下拉是空的_照樣可以打字(main_app):
    a = main_app
    seen = {}
    d = _drive(a, TITLE_NEW, lambda dr: _values(dr, seen), _fill(name="還沒登錄的工具"),
               lambda dr: dr.press("確定"))
    _btn_in(step_head(a), "外部").invoke()
    _raise(d)
    assert seen["values"] == []
    assert a.steps[-1]["external"] == "還沒登錄的工具"


def test_沒填工具名稱_擋下不關窗(main_app):
    a = main_app
    seen = {}

    def look(dr):
        dr.press("確定")
        seen["open"] = dr.dlg.winfo_exists()
        seen["err"] = [str(w.cget("text")) for w in _all(dr.dlg)
                       if w.winfo_class() == "TLabel" and str(w.cget("text")).startswith("請填")]
        dr.press("取消")
    d = _drive(a, TITLE_NEW, _fill(name="  "), look)
    _btn_in(step_head(a), "外部").invoke()
    _raise(d)
    assert seen["open"] and seen["err"] == ["請填工具名稱"]
    assert a.steps == []


def test_參數一行一個_存回時去掉空行_備註照存(main_app):
    a = main_app
    d = _drive(a, TITLE_NEW, _fill(name="公開招募", args="--mode\n\n加急\n  \n--n\n",
                                   note="早班最後"), lambda dr: dr.press("確定"))
    _btn_in(step_head(a), "外部").invoke()
    _raise(d)
    assert a.steps == [{"type": "external", "external": "公開招募",
                        "args": ["--mode", "加急", "--n"], "note": "早班最後"}]


def test_參數框按Enter換行_不會按到確定(main_app):
    a = main_app
    seen = {}

    def enter(dr):
        box = _widget(dr.dlg, "Text")
        box.focus_force()
        box.mark_set("insert", "end-1c")
        box.event_generate("<Return>")
        dr._update()
        seen["open"] = dr.dlg.winfo_exists()
        seen["text"] = box.get("1.0", "end-1c")
        dr.press("取消")
    d = _drive(a, TITLE_NEW, _fill(name="公開招募", args="--a"), enter)
    _btn_in(step_head(a), "外部").invoke()
    _raise(d)
    assert seen == {"open": True, "text": "--a\n"}
    assert a.steps == []


def test_編輯既有外部步驟_欄位帶入原值(main_app, tmp_path):
    a = main_app
    folder, _ = _flow_folder(tmp_path)
    assert a.open_flow_folder(str(folder))
    seen = {}

    def look(dr):
        seen["name"] = _widget(dr.dlg, "TCombobox").get()
        seen["args"] = _widget(dr.dlg, "Text").get("1.0", "end-1c")
    d = _drive(a, TITLE_EDIT, look, _fill(note="改了備註"), lambda dr: dr.press("確定"))
    a.step_list.selection_set(0)
    a.edit_step()
    _raise(d)
    assert seen == {"name": "公開招募", "args": "--hwnd\n{hwnd}"}
    assert a.steps[0] == {"type": "external", "external": "公開招募",
                          "args": ["--hwnd", "{hwnd}"], "note": "改了備註"}


def test_存檔重開後步驟內容一樣_登錄檔不變(main_app, tmp_path):
    a = main_app
    folder, _ = _flow_folder(tmp_path)
    registry = (folder / flowfile.TOOLS_YAML).read_text(encoding="utf-8")
    assert a.open_flow_folder(str(folder))
    d = _drive(a, TITLE_NEW, _fill(name="公開招募", args="--mode\n加急", note="晚班"),
               lambda dr: dr.press("確定"))
    _btn_in(step_head(a), "外部").invoke()
    _raise(d)
    steps = [dict(s) for s in a.steps]
    assert a.save_flow()
    assert (folder / flowfile.TOOLS_YAML).read_text(encoding="utf-8") == registry
    assert a.open_flow_folder(str(folder))
    assert a.steps == steps
    assert steps[-1] == {"type": "external", "external": "公開招募",
                         "args": ["--mode", "加急"], "note": "晚班"}


def test_步驟清單標籤是外部步驟的顏色_描述含工具名與參數(main_app, tmp_path):
    a = main_app
    folder, _ = _flow_folder(tmp_path)
    assert a.open_flow_folder(str(folder))
    lb = a.step_list
    row = lb.get("1.0", "1.end")
    start = lb.search("［外部步驟］", "1.0", "1.end")
    [tag] = [t for t in lb.tag_names(start) if t.startswith("c")]
    assert str(lb.tag_cget(tag, "foreground")).upper() == "#F472B6"
    assert row.endswith("［外部步驟］公開招募 --hwnd {hwnd}"), row

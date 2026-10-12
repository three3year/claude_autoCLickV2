"""主視窗 (ui-slim): ⓘ 說明提示、視窗標題、版面 D 的元件.

真的 App (conftest `main_app`), 元件以文字找、互動用 event_generate 真的走一遍;
斷言看得到什麼 (按鈕文字、提示框、標題), 不看內部欄位。
"""
import tkinter as tk

import numpy as np

import app as app_mod
import calibration
import flowfile
import ui_dialogs
from automation import flowdefaults, imgio
from automation.flowcheck import STEP_LABELS
from test_template_picker import _Driver
from ui_theme import C


def all_widgets(w):
    for c in w.winfo_children():
        yield c
        yield from all_widgets(c)


def texts(w, classes=("TButton", "Button", "TLabel", "Label", "TMenubutton")):
    out = []
    for c in all_widgets(w):
        if c.winfo_class() in classes:
            try:
                out.append(str(c.cget("text")))
            except tk.TclError:
                pass
    return out


def tips(w):
    """所有 ⓘ 元件."""
    return [c for c in all_widgets(w) if c.winfo_class() == "Label"
            and str(c.cget("text")) == "ⓘ"]


def tip_windows(lbl):
    return [c for c in lbl.winfo_children() if isinstance(c, tk.Toplevel)]


def hover(lbl):
    lbl.event_generate("<Enter>", x=2, y=2)
    lbl.update()


def leave(lbl):
    lbl.event_generate("<Leave>")
    lbl.update()


# ---------- ⓘ (票 01) ----------

def _scan_tip(a):
    row = a.scan_lbl.master
    [lbl] = [t for t in tips(row)]
    return lbl


def test_搜尋範圍旁有說明圖示_常駐說明那行不見(main_app):
    a = main_app
    assert _scan_tip(a).winfo_viewable()
    assert not [t for t in texts(a.root) if "都只在此範圍內找圖" in t]


def test_說明圖示懸停才顯示提示_移開就消失(main_app):
    lbl = _scan_tip(main_app)
    assert tip_windows(lbl) == []
    hover(lbl)
    [t] = tip_windows(lbl)
    assert t.winfo_viewable()
    assert any("搜尋範圍" in s or "範圍" in s for s in texts(t))
    leave(lbl)
    assert tip_windows(lbl) == []


def test_說明圖示提示不搶焦點_所在視窗關閉時跟著消失(main_app):
    a = main_app
    a.scan_lbl.focus_force()
    a.root.update()
    before = a.root.focus_get()
    lbl = _scan_tip(a)
    hover(lbl)
    [t] = tip_windows(lbl)
    assert a.root.focus_get() is before
    a.root.destroy()
    assert not t.winfo_exists()


def test_說明圖示提示框夾在螢幕工作區內(main_app):
    from automation import win
    lbl = _scan_tip(main_app)
    lbl.event_generate("<Enter>", x=2, y=2)
    hover(lbl)
    [t] = tip_windows(lbl)
    x1, y1, x2, y2 = win.monitor_work_area(lbl.winfo_id())
    assert x1 <= t.winfo_rootx() and t.winfo_rootx() + t.winfo_width() <= x2
    assert y1 <= t.winfo_rooty() and t.winfo_rooty() + t.winfo_height() <= y2


# ---------- 版面 D (票 05): 元件數對照 05 Answer 的表格 ----------

REMOVED = ("設定校準對", "設定備用校準對", "校準", "忙碌指示…", "上傳圖片", "比對測試",
           "複製", "重新整理", "讀檔", "＋ 新增步驟", "框選範圍", "截圖框選")


def buttons(w):
    return sorted(texts(w, ("TButton", "Button", "TMenubutton")))


def toolbar_rows(a):
    """主視窗由上而下的第一、二列工具列."""
    return [w for w in a.root.winfo_children() if w.winfo_class() == "TFrame"][:2]


def step_head(a):
    return a.step_list.master.grid_slaves(row=0, column=0)[0]


def mapped_buttons(w):
    return sorted(str(c.cget("text")) for c in all_widgets(w)
                  if c.winfo_class() == "TButton" and c.winfo_ismapped())


def resize(a, width):
    a.root.minsize(400, 300)    # 主視窗最小寬 900 時剛好放得下, 測收合要更窄
    a.root.geometry(f"{width}x700")
    a.root.update()
    a.root.update()


def label_of(t):
    return STEP_LABELS[t]


def _btn_in(w, text):
    [b] = [c for c in all_widgets(w) if c.winfo_class() == "TButton"
           and c.cget("text") == text]
    return b


def _menu_of(a, button_text):
    btn = _btn_in(step_head(a), button_text)
    [menu] = [c for c in btn.winfo_children() if c.winfo_class() == "Menu"]
    items = {menu.entrycget(i, "label"): i for i in range(menu.index("end") + 1)
             if menu.type(i) == "command"}
    return menu, items


def test_第一列與第二列的按鈕對照版面D(main_app):
    row1, row2 = toolbar_rows(main_app)
    assert buttons(row1) == sorted(["新流程", "開檔", "存檔", "框選", "清除", "流程設定…"])
    assert buttons(row2) == sorted(["▶ 開始執行", "■ 停止"])
    assert "F12 = 急停" in texts(row2) and "待機" in texts(row2)
    assert main_app.settings_lbl.cget("text") == "校準對 ✗　忙碌指示 —"


def test_步驟標題列_寬時一排新增鈕_窄時收成一顆新增選單(main_app):
    a = main_app
    resize(a, 1400)
    assert mapped_buttons(step_head(a)) == sorted(
        ["測試選取", "找圖", "點擊", "拖曳", "等待", "區段 ▾"])
    resize(a, 760)
    assert mapped_buttons(step_head(a)) == sorted(["測試選取", "＋ 新增 ▾"])
    resize(a, 1400)
    assert "找圖" in mapped_buttons(step_head(a)), "寬度回來時換回一排鈕"


def test_收合的新增選單列出全部九項_點了新增對應種類(main_app, monkeypatch):
    a = main_app
    menu, items = _menu_of(a, "＋ 新增 ▾")
    assert list(items) == [label_of(t) for t in (
        "find_click", "click", "drag", "wait", "repeat_start", "repeat_end",
        "branch_start", "branch_or", "branch_end")]
    # 直接執行該項的命令: menu.invoke 在 Windows 會留下選單訊息, 下一個測試的選單
    # 用到同一個命令編號時被誤觸發 (開出步驟對話框卡住)
    menu.tk.call(menu.entrycget(items[label_of("branch_or")], "command"))
    assert [s["type"] for s in a.steps] == ["branch_or"]
    monkeypatch.setattr(ui_dialogs, "edit_step", lambda app, s: dict(s))
    _btn_in(step_head(a), "找圖").invoke()
    assert a.steps[-1]["type"] == "find_click", "「找圖」新增的是 find_click"
    _menu, sec = _menu_of(a, "區段 ▾")
    assert list(sec) == [label_of(t) for t in (
        "repeat_start", "repeat_end", "branch_start", "branch_or", "branch_end")]


def test_被拿掉的按鈕都不在了(main_app):
    left = set(texts(main_app.root))
    assert not left & set(REMOVED), left & set(REMOVED)


def test_範本面板與紀錄的按鈕(main_app):
    panel = main_app.tmpl_list.master
    assert buttons(panel) == sorted(["截圖新增", "重截", "重新命名", "刪除"])
    assert buttons(main_app.log_text.master) == ["清除"]


def test_選取步驟列只剩編輯與刪除兩個圖示(main_app):
    icons = [str(w.cget("text")) for w in main_app._step_icons.bar.winfo_children()]
    assert icons == ["✎", "✕"]


def test_存檔開檔快速鍵照舊(main_app):
    assert main_app.root.bind("<Control-s>") and main_app.root.bind("<Control-o>")


# ---------- 流程設定對話框 (票 04) ----------

SETTINGS = "流程設定"
CAL = {"pair": ["左", "右"], "baseline": 300.0}
CAL_FB = dict(CAL, fallback=calibration.make_fallback(["圖示", "關閉"], 500.0, (1, 2)))


def _body(dlg):
    return dlg.winfo_children()[0]


def _row_texts(dlg, row):
    return [str(w.cget("text")) for w in _body(dlg).grid_slaves(row=row, column=1)]


def _row_button(dlg, row, text):
    [b] = [w for w in _body(dlg).grid_slaves(row=row) if w.winfo_class() == "TButton"
           and w.cget("text") == text]
    return b


def _settings(a, *actions):
    d = _Driver(a.root, SETTINGS)
    d.run(*actions, lambda dr: dr.press("關閉"))
    a.open_flow_settings()
    if d.error is not None:
        raise d.error


def _logs(a):
    return a.log_text.get("1.0", "end").splitlines()


def test_流程設定三列_名稱說明圖示與現狀(main_app):
    a = main_app
    a.flow_cal = dict(CAL_FB)
    a.busy_target = {"template": "忙"}
    seen = {}

    def look(dr):
        seen["rows"] = [_row_texts(dr.dlg, r) for r in range(3)]
        seen["tips"] = len(tips(dr.dlg))
        seen["buttons"] = sorted(texts(dr.dlg, ("TButton",)))
    _settings(a, look)
    assert seen["rows"] == [["左 × 右（基準 300 px）"],
                            ["圖示 × 關閉（基準 500 px）"], ["忙"]]
    assert seen["tips"] == 3
    assert seen["buttons"] == sorted(["設定…", "清除", "測試"] * 3 + ["關閉"])


def test_流程設定沒設時的現狀文字(main_app):
    seen = {}
    _settings(main_app, lambda dr: seen.update(
        rows=[_row_texts(dr.dlg, r) for r in range(3)]))
    assert seen["rows"] == [["沒有（不能執行）"], ["沒有"], ["不設"]]


def test_清除主校準對_有備用時先確認_回答否不清(main_app, no_real_dialogs):
    a = main_app
    a.flow_cal = dict(CAL_FB)
    _settings(a, lambda dr: _row_button(dr.dlg, 0, "清除").invoke())
    assert a.flow_cal == CAL_FB and not a.dirty


def test_清除主校準對_確認後整份清空_摘要與現狀跟著變(main_app, monkeypatch):
    a = main_app
    a.flow_cal = dict(CAL_FB)
    a._settings_changed()
    asked = []
    monkeypatch.setattr(app_mod.messagebox, "askyesno",
                        lambda title, msg, **kw: asked.append(msg) or True)
    seen = {}

    def clear(dr):
        _row_button(dr.dlg, 0, "清除").invoke()
        seen["rows"] = [_row_texts(dr.dlg, r) for r in range(2)]
    _settings(a, clear)
    assert asked and "備用" in asked[0]
    assert a.flow_cal is None and a.dirty
    assert seen["rows"] == [["沒有（不能執行）"], ["沒有"]]
    assert a.settings_lbl.cget("text").startswith("校準對 ✗")
    assert a.root.title().startswith("*")
    assert any("已清除校準對與備用校準對" in m for m in _logs(a))


def test_清除校準對_有存下的座標時提醒不會跟著換算_回答否不清(main_app, monkeypatch):
    a = main_app
    a.flow_cal = dict(CAL)
    a.steps = [flowdefaults.complete({"type": "find_click",
                                      "target": {"template": "x", "within": [1, 2, 3, 4]}})]
    asked = []
    monkeypatch.setattr(app_mod.messagebox, "askyesno",
                        lambda title, msg, **kw: asked.append(msg) or False)
    a.clear_calibration()
    assert asked and "1 個座標" in asked[0] and "不會跟著換算" in asked[0]
    assert a.flow_cal == CAL


def test_清除備用只拿掉備用_清除忙碌指示_都不問(main_app, no_real_dialogs):
    a = main_app
    a.flow_cal = dict(CAL_FB)
    a.busy_target = {"template": "忙"}
    _settings(a, lambda dr: _row_button(dr.dlg, 1, "清除").invoke(),
              lambda dr: _row_button(dr.dlg, 2, "清除").invoke())
    assert a.flow_cal == CAL and a.busy_target is None and a.dirty
    assert a.settings_lbl.cget("text") == "校準對 ✓　忙碌指示 —"
    assert not any(no_real_dialogs.values())


def test_沒設的那列按測試_紀錄寫還沒設定_不彈窗(main_app, no_real_dialogs):
    a = main_app
    _settings(a, *(lambda dr, r=r: _row_button(dr.dlg, r, "測試").invoke()
                   for r in range(3)))
    assert sum("還沒設定" in m for m in _logs(a)) == 3
    assert not any(no_real_dialogs.values())


def test_忙碌指示的測試走比對測試(main_app, monkeypatch):
    a = main_app
    a.busy_target = {"template": "忙", "within": [1, 2, 3, 4]}
    calls = []
    monkeypatch.setattr(ui_dialogs, "show_match_test",
                        lambda app, tgt, **kw: calls.append(tgt))
    _settings(a, lambda dr: _row_button(dr.dlg, 2, "測試").invoke())
    assert calls == [a.busy_target]


def test_設定忙碌指示後現狀與摘要立刻跟著變(main_app, monkeypatch):
    a = main_app
    a.store.add("忙", b"B")
    monkeypatch.setattr(ui_dialogs, "pick_template",
                        lambda app, title, initial=None: "忙")
    monkeypatch.setattr(ui_dialogs, "edit_target_opts", lambda *x, **k: {
        "within": None, "pick": None, "color": False})
    seen = {}

    def set_busy(dr):
        _row_button(dr.dlg, 2, "設定…").invoke()
        seen["row"] = _row_texts(dr.dlg, 2)
    _settings(a, set_busy)
    assert a.busy_target == {"template": "忙"}
    assert seen["row"] == ["忙"]
    assert a.settings_lbl.cget("text") == "校準對 ✗　忙碌指示 ✓"


# ---------- 範本面板: 未引用標記與重截 (票 06) ----------

def _img(fill, w=12, h=8):
    x = np.zeros((h, w, 3), np.uint8)
    x[:] = fill
    return x


def _rows(a):
    return [(a.tmpl_list.get(i).strip(), a.tmpl_list.itemcget(i, "fg"))
            for i in range(a.tmpl_list.size())]


def _find(name):
    return flowdefaults.complete({"type": "find_click", "target": {"template": name}})


def test_沒被引用的範本灰字標未引用_步驟改動即時跟著變(main_app):
    a = main_app
    for n in ("a", "b"):
        a.store.add(n, imgio.encode_png(_img(100)))
    a.steps = [_find("a")]
    a.render_steps()
    assert _rows(a)[0][0] == "🖼 a"
    assert _rows(a)[1] == ("○ b　（未引用）", C["muted"])
    a.step_list.selection_set(0)
    a.del_step()                       # 刪掉最後一個引用 a 的步驟
    assert _rows(a)[0][0] == "○ a　（未引用）"
    a.steps.append(_find("b"))
    a.render_steps()
    assert _rows(a)[1][0] == "🖼 b", "加回引用就不標"


def test_流程設定引用的範本不算未引用(main_app):
    a = main_app
    a.store.add("忙", imgio.encode_png(_img(100)))
    a.busy_target = {"template": "忙"}
    a._settings_changed()
    assert _rows(a)[0][0] == "🖼 忙"
    a.clear_busy_indicator()
    assert _rows(a)[0][0] == "○ 忙　（未引用）"


def _opened(a, tmp_path):
    folder = tmp_path / "流程"
    flow = flowfile.new_flow()
    flow["steps"] = [_find("a")]
    flowfile.write_flow(folder, flow, {"a": imgio.encode_png(_img(100))})
    assert a.open_flow_folder(str(folder))
    return folder


def _select_tmpl(a, name):
    i = a._tmpl_names.index(name)
    a.tmpl_list.selection_clear(0, "end")
    a.tmpl_list.selection_set(i)
    a.tmpl_list.event_generate("<<ListboxSelect>>")
    a.root.update()


def test_重截_同名換圖_存檔前templates不動_存檔後換成新圖(main_app, tmp_path, monkeypatch):
    a = main_app
    folder = _opened(a, tmp_path)
    saved = (folder / "templates" / "a.png").read_bytes()
    _select_tmpl(a, "a")
    shot = {"img": _img(30, 20, 10), "screenX": 0, "screenY": 0, "w": 20, "h": 10,
            "frame": None}
    monkeypatch.setattr(a, "pick_region_measured", lambda **kw: (shot, None, 1.0))
    _btn_in(a.tmpl_list.master, "重截").invoke()
    assert a.list_template_names() == ["a"]
    assert a.steps[0]["target"]["template"] == "a", "引用它的步驟不用改"
    assert a.dirty and (folder / "templates" / "a.png").read_bytes() == saved
    assert imgio.imread(a.store.path_of("a")).shape[:2] == (10, 20)
    assert a.save_flow()
    got = imgio.imread(str(folder / "templates" / "a.png"))
    assert got.shape[:2] == (10, 20) and int(got[0, 0, 0]) == 30
    assert flowfile.read_flow(folder)["steps"][0]["target"]["template"] == "a"


def test_重截取消什麼都不變_沒選範本寫一行提示(main_app, tmp_path, monkeypatch):
    a = main_app
    folder = _opened(a, tmp_path)
    monkeypatch.setattr(a, "pick_region_measured", lambda **kw: None)
    a.tmpl_list.selection_clear(0, "end")
    a.recapture_template()
    assert any("先在範本清單選一個範本" in m for m in _logs(a))
    _select_tmpl(a, "a")
    a.recapture_template()
    assert not a.dirty
    assert a.store.path_of("a") == str(folder / "templates" / "a.png")

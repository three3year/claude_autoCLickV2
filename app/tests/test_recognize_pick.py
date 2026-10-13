"""拾取類入口: 覆蓋層先出現、辨識在背景 (recognize-off-clear 票 03–06).

清場只截一張整個虛擬桌面的圖, 覆蓋層直接顯示它; 校準與 ◎ 推算在背景同時做。覆蓋層以樁
取代 (記下被叫時待定結果好了沒、是不是在清場裡), 背景辨識扣住／放行 (`harness.Held`),
`ClearProbe` 斷言清場中查詢 0 次。對話框照常用 `_Driver` 真的按按鈕。
"""
import numpy as np

import harness  # noqa: F401  # 先把 app/ 加進 sys.path
from harness import CAL_PAIR, miss

import recognition
import ui_dialogs
import ui_overlay
from automation import findtarget, flowdefaults, imgio
from test_editor_scale import ANCHOR, _edit, _press, _shot, make_app  # noqa: F401
from test_fixed_rect_ui import FIXED_ZH, RECT, _choose
from test_main_window import _btn_in, _logs, _rows
from test_pickcheck_ui import _engine, _template
from test_recognition import PAIR, ClearProbe, flow_app, held  # noqa: F401
from test_template_picker import TITLE, _all, _btn, _Driver, _open


def _overlay(monkeypatch, result, probe=None):
    """覆蓋層樁: 記下 (模式, 待定結果的狀態, 是否在清場裡, kw), 回傳 result (可為 callable)."""
    calls = []

    def pick(root, mode, prompt, **kw):
        pending = kw.get("pending")
        calls.append({"mode": mode, "status": pending.status() if pending else None,
                      "clearing": probe.depth > 0 if probe else None, "kw": kw})
        return result(kw) if callable(result) else result
    monkeypatch.setattr(ui_overlay, "pick", pick)
    return calls


def _labels(dlg):
    return [str(w.cget("text")) for w in _all(dlg) if w.winfo_class() == "TLabel"]


def _entries(dlg):
    return [w.get() for w in _all(dlg) if w.winfo_class() == "TEntry"]


def _disabled(dlg, text):
    return _btn(dlg, text).instate(["disabled"])


def _new_templates(app):
    return [n for n in app.store.names() if n.startswith("tmpl_")]


# ---------- 票 03: 截圖新增 / 重截 / 選範本對話框截圖 / 固定矩形 ----------

def test_截圖新增_覆蓋層先出現_放行後才存範本並查縮放餘裕_清場中查詢0次(make_app, monkeypatch):
    app = make_app(2.0)
    _engine(app, monkeypatch)
    app.vision.plan("tmpl_001", [miss("match", 0.6), (300, 400)])
    probe = ClearProbe(monkeypatch, app)
    h = held(app)
    calls = _overlay(monkeypatch, _shot(40, 20, 210, 250), probe)
    app.capture_template()
    assert [(c["mode"], c["status"], c["clearing"]) for c in calls] == \
        [("region", "pending", True)], "覆蓋層出現時背景校準還沒放行"
    assert calls[0]["kw"]["shot"][1] == (0, 0), "覆蓋層顯示清場中截的整張圖"
    assert app.recognition.busy
    assert _new_templates(app) == [] and app.pick_warnings() == {}, "扣住時沒有新範本也沒有 ⚠"
    h.release()
    [name] = _new_templates(app)
    assert imgio.imread(app.store.path_of(name)).shape[:2] == (10, 20)
    assert app.store.pos_of(name) == [40, 15]
    assert name in app.pick_warnings(), "縮放餘裕在同一件辨識裡"
    assert probe.calls and probe.in_clear() == []
    assert not app.recognition.busy


def test_截圖新增_覆蓋層顯示中校準失敗_立刻中止_還原後警告_什麼都不存(make_app, monkeypatch,
                                                no_real_dialogs):
    app = make_app(1.0)
    app.vision.plan(CAL_PAIR[0], [None])
    h = held(app)

    def fail_while_shown(kw):
        h.release()                     # 背景在覆蓋層顯示中做完: 量不到
        assert kw["pending"].status() == "failed"
        return ui_overlay.ABORT          # 真的覆蓋層看到失敗就結束 (GUI 測試另驗)
    _overlay(monkeypatch, fail_while_shown)
    app.capture_template()
    assert _new_templates(app) == []
    assert any("搜尋範圍" in m and CAL_PAIR[0] in m for m in no_real_dialogs["warning"])
    assert not app.recognition.busy


def test_截圖新增_Esc取消_背景結果作廢(make_app, monkeypatch):
    app = make_app(1.0)
    h = held(app)
    _overlay(monkeypatch, None)
    app.capture_template()
    assert app.recognition.busy, "背景那段還在跑"
    h.release()
    assert _new_templates(app) == [] and not app.recognition.busy


def test_沒有校準對_截範本照常_倍率1不記位置(make_app, monkeypatch):
    app = make_app(pair=False)
    h = held(app)
    _overlay(monkeypatch, _shot(40, 20))
    app.capture_template()
    h.release()
    [name] = _new_templates(app)
    assert imgio.imread(app.store.path_of(name)).shape[:2] == (20, 40)
    assert app.store.pos_of(name) is None


def test_重截_清場中查詢0次_放行後才換圖(flow_app, monkeypatch):
    a = flow_app
    from automation import pickcheck
    monkeypatch.setattr(pickcheck, "resize_image", lambda img, s: img.resized(s))
    before = a.store.path_of("新左")
    i = a._tmpl_names.index("新左")
    a.tmpl_list.selection_set(i)
    probe = ClearProbe(monkeypatch, a)
    h = held(a)
    _overlay(monkeypatch, _shot(40, 20, 210, 250), probe)
    _btn_in(a.tmpl_list.master, "重截").invoke()
    assert a.store.path_of("新左") == before and not a.dirty
    assert _btn_in(a.tmpl_list.master, "重截").instate(["disabled"])
    h.release()
    assert imgio.imread(a.store.path_of("新左")).shape[:2] == (20, 40)
    assert a.dirty and probe.in_clear() == [] and probe.calls
    assert not _btn_in(a.tmpl_list.master, "重截").instate(["disabled"])


def test_截圖新增中關掉主視窗_不出錯_結果不套用(flow_app, monkeypatch):
    a = flow_app
    h = held(a)
    _overlay(monkeypatch, _shot(40, 20, 210, 250))
    a.capture_template()
    a.dirty = False
    a.on_close()
    h.release()
    assert _new_templates(a) == [] and not a.recognition.busy


def test_選範本對話框截圖_辨識中對話框關不掉_放行後才暫存(make_app, monkeypatch):
    app = make_app(1.0)
    probe = ClearProbe(monkeypatch, app)
    h = held(app)
    _overlay(monkeypatch, _shot(40, 20, 170, 240), probe)
    seen = {}

    def look(dr):
        seen["ok"] = _disabled(dr.dlg, "確定")
        seen["cancel"] = _disabled(dr.dlg, "取消")
        seen["shoot"] = _disabled(dr.dlg, "截圖新增")
        seen["busy"] = recognition.BUSY_TEXT in _labels(dr.dlg)
        dr.dlg.event_generate("<Escape>")
        dr._update()
        seen["alive"] = dr.dlg.winfo_exists()
        h.release()
        dr._update()
        seen["after"] = (_disabled(dr.dlg, "確定"), recognition.BUSY_TEXT in _labels(dr.dlg))
    d = _Driver(app.root, TITLE)
    got = _open(app, d, _press("截圖新增"), look, _press("確定"))
    assert seen == {"ok": True, "cancel": True, "shoot": True, "busy": True, "alive": True,
                    "after": (False, False)}
    assert got == "tmpl_001" and app.store.pos_of(got) == [40, 20]
    assert probe.in_clear() == [] and probe.calls


def _target_dialog(app, tgt, *actions, origin_fn=None):
    d = _Driver(app.root, "找圖設定")
    d.run(*actions)
    got = ui_dialogs.edit_target_opts(app, app.root, tgt, "找圖設定", origin_fn=origin_fn)
    if d.error is not None:
        raise d.error
    return got


BOX = {"screenX": 300, "screenY": 350, "w": 400, "h": 150}


def test_固定矩形_清場中查詢0次_扣住時確定反灰_放行後換算照舊(make_app, monkeypatch):
    app = make_app(1.0)
    probe = ClearProbe(monkeypatch, app)
    h = held(app)
    calls = _overlay(monkeypatch, dict(BOX), probe)
    seen = {}

    def look(dr):
        seen["ok"] = _disabled(dr.dlg, "確定")
        seen["rect"] = "（還沒框選）" in _labels(dr.dlg)
        h.release()
        dr._update()
        seen["ok_after"] = _disabled(dr.dlg, "確定")
    got = _target_dialog(app, {"template": "a"}, _choose(FIXED_ZH), _press("框選"), look,
                         _press("確定"))
    assert calls[0]["status"] == "pending" and calls[0]["clearing"]
    assert seen == {"ok": True, "rect": True, "ok_after": False}
    assert got["within"] == RECT
    assert probe.calls and probe.in_clear() == []


def test_固定矩形_校準失敗_矩形不變(make_app, monkeypatch, no_real_dialogs):
    app = make_app(1.0)
    app.vision.plan(CAL_PAIR[1], [None])
    old = [1, 2, 300, 300]
    _overlay(monkeypatch, dict(BOX))
    got = _target_dialog(app, {"template": "a", "within": list(old)}, _press("框選"),
                         _press("確定"))
    assert got["within"] == old
    assert any(CAL_PAIR[1] in m for m in no_real_dialogs["warning"])


# ---------- 票 04: 指定點 / 拾取座標 ── ◎ 晚到、可先點 ----------

def _find_step(name="a"):
    return flowdefaults.complete({"type": "find_click", "target": {"template": name}})


def _pointer_app(make_app, monkeypatch, scale=1.0):
    """前一步是找圖 a: ◎＝即時在拾取那張截圖上找到 a 的位置 (背景)."""
    app = make_app(scale)
    _engine(app, monkeypatch)
    _template(app, "a", 20, 20)
    app.vision.plan("a", [(400, 300)])
    app.steps = [_find_step()]
    return app


def test_拾取座標_扣住時以點一下模式叫出_先點_放行後才填_紀錄區寫原點(make_app, monkeypatch):
    app = _pointer_app(make_app, monkeypatch)
    probe = ClearProbe(monkeypatch, app)
    h = held(app)
    calls = _overlay(monkeypatch, {"endX": 450, "endY": 330, "early": True}, probe)
    seen = {}

    def look(dr):
        seen["fields"] = _entries(dr.dlg)
        seen["closers"] = (_disabled(dr.dlg, "確定"), _disabled(dr.dlg, "取消"))
        seen["busy"] = recognition.BUSY_TEXT in _labels(dr.dlg)
        h.release()
        dr._update()
        seen["after"] = _entries(dr.dlg)
    got = _edit(app, {"type": "click", "click": [0, 0], "_index": 1},
                _press("截圖拾取"), look, _press("確定"), title="新增：座標點擊")
    [c] = calls
    assert (c["mode"], c["status"], c["kw"].get("late"), c["kw"].get("base")) == \
        ("line", "pending", "base", None), "◎ 待定: line 的點一下模式, 還沒有原點"
    assert seen["fields"] == ["0", "0"] and seen["closers"] == (True, True) and seen["busy"]
    assert seen["after"] == ["50", "30"]
    assert got["click"] == [50, 30]
    assert any("原點 ◎ 在 (400, 300)" in m for _lvl, m in app.logged)
    assert probe.in_clear() == [] and ("a", False) in probe.calls, \
        "即時找上一步的圖在背景、用拾取那張截圖"


def test_拾取座標_先點之後推不出原點_警告_欄位不變(make_app, monkeypatch, no_real_dialogs):
    app = make_app(1.0)          # 沒有前一步: 推不出原點
    h = held(app)
    _overlay(monkeypatch, {"endX": 450, "endY": 330, "early": True})

    def release(dr):
        h.release()
        dr._update()
    got = _edit(app, {"type": "click", "click": [7, 8], "_index": 0},
                _press("截圖拾取"), release, _press("確定"), title="新增：座標點擊")
    assert got["click"] == [7, 8]
    assert any("推算不出原點，這次沒存" in m for m in no_real_dialogs["warning"])


def test_拾取座標_原點已算好_照現在一樣標出原點(make_app, monkeypatch):
    app = _pointer_app(make_app, monkeypatch, scale=2.0)
    calls = _overlay(monkeypatch, {"dx": 50, "dy": -30})
    got = _edit(app, {"type": "click", "click": [0, 0], "_index": 1},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert calls[0]["kw"]["base"] == (400, 300) and "pending" not in calls[0]["kw"]
    assert got["click"] == [25, -15]


def test_拖曳_清場中查詢0次_先拖_放行後換算(make_app, monkeypatch):
    app = _pointer_app(make_app, monkeypatch)
    probe = ClearProbe(monkeypatch, app)
    h = held(app)
    calls = _overlay(monkeypatch, {"startX": 410, "startY": 310, "endX": 460, "endY": 400,
                                   "dx": 50, "dy": 90, "early": True}, probe)

    def release(dr):
        h.release()
        dr._update()
    got = _edit(app, {"type": "drag", "drag": [0, 0], "to": [0, 0], "_index": 1},
                _press("截圖拾取"), release, _press("確定"), title="新增：滑鼠拖曳")
    assert [(c["mode"], c["kw"].get("late")) for c in calls] == [("line", "mark")]
    assert (got["drag"], got["to"]) == ([10, 10], [60, 100])
    assert probe.calls and probe.in_clear() == []


def test_指定點_先點_放行後才填_除以倍率(make_app, monkeypatch):
    app = make_app(2.0)
    probe = ClearProbe(monkeypatch, app)
    h = held(app)
    calls = _overlay(monkeypatch, {"screenX": 560, "screenY": 440, "early": True}, probe)
    seen = {}

    def look(dr):
        seen["ok"] = _disabled(dr.dlg, "確定")
        h.release()
        dr._update()
    got = _target_dialog(app, {"template": "a", "pick": {"near": [0, 0]}},
                         _press("點選"), look, _press("確定"),
                         origin_fn=lambda: lambda frame, anchor, k: (500, 500))
    assert calls[0]["kw"].get("late") == "mark" and calls[0]["status"] == "pending"
    assert seen["ok"] is True
    assert got["pick"] == {"near": [30, -30]}
    assert any("原點 ◎ 在 (500, 500)" in m for _lvl, m in app.logged)
    assert probe.in_clear() == []


def test_指定點_原點確定推不出且還沒點_先請你點原點(make_app, monkeypatch):
    app = make_app(1.0)
    modes = []

    def pick(root, mode, prompt, **kw):
        modes.append((mode, kw.get("mark")))
        return {"screenX": 100, "screenY": 100} if len(modes) == 1 else \
            {"screenX": 130, "screenY": 90}
    monkeypatch.setattr(ui_overlay, "pick", pick)
    got = _target_dialog(app, {"template": "a", "pick": {"near": [0, 0]}},
                         _press("點選"), _press("確定"),
                         origin_fn=lambda: lambda frame, anchor, k: None)
    assert modes == [("point", None), ("point", (100, 100))]
    assert got["pick"] == {"near": [30, -10]}


# ---------- 票 05: 比對測試 ----------

def test_比對測試_清場中查詢0次_扣住時結果視窗還沒開_發起的對話框關不掉(make_app, monkeypatch):
    app = _pointer_app(make_app, monkeypatch)
    monkeypatch.setattr(ui_dialogs, "_annotate_find",
                        lambda screen, org, f, origin=None, anchor=None:
                        np.zeros((60, 80, 3), np.uint8))
    probe = ClearProbe(monkeypatch, app)
    h = held(app)
    # ◎ 待定: 同一次清場叫「點一下原點」的覆蓋層 (算好會自己結束); 這裡模擬使用者先點了
    calls = _overlay(monkeypatch, {"screenX": 400, "screenY": 300}, probe)
    seen = {}

    def result_open():
        return any(w.winfo_exists() and getattr(w, "title", lambda: "")() == "比對測試結果"
                   for w in app.root.winfo_children())

    def look(dr):
        seen["before"] = (result_open(), _disabled(dr.dlg, "確定"))
        h.release()
        dr._update()
        seen["after"] = result_open()
        for w in app.root.winfo_children():
            if getattr(w, "title", lambda: "")() == "比對測試結果":
                w.destroy()
    step = flowdefaults.complete({"type": "find_click", "_index": 1,
                                  "target": {"template": "a", "pick": {"near": [0, 0]},
                                             "within": [0, 0, 600, 400]}})
    _edit(app, step, _press("立即比對測試"), look, _press("確定"), title="新增：找圖點擊")
    assert [(c["mode"], c["status"], c["clearing"], c["kw"].get("late")) for c in calls] == \
        [("point", "pending", True, "origin")]
    assert seen == {"before": (False, True), "after": True}
    assert probe.calls and probe.in_clear() == []


def test_比對測試_引擎沒就緒_不進清場也不進辨識中(make_app, monkeypatch, no_real_dialogs):
    app = make_app(1.0)
    app.hub.state = "loading"
    entered = []
    monkeypatch.setattr(ui_overlay, "screen_clear",
                        lambda root, extra=(): entered.append(1))
    ui_dialogs.show_match_test(app, {"template": "a"})
    assert entered == [] and not app.recognition.busy
    assert no_real_dialogs["warning"]


def test_比對測試_範本載入失敗_收尾時提示(make_app, monkeypatch, no_real_dialogs):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 20, 20)

    def ensure(name):
        if name == "a":
            raise OSError("壞檔")
    app.hub.ensure_template = ensure
    ui_dialogs.show_match_test(app, {"template": "a"})
    assert any("範本載入失敗" in m and "壞檔" in m for m in no_real_dialogs["error"])
    assert not app.recognition.busy


def test_比對測試_推不出原點_在剛截的圖上請你點原點_再背景找(make_app, monkeypatch):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 20, 20)
    monkeypatch.setattr(ui_dialogs, "_annotate_find",
                        lambda screen, org, f, origin=None, anchor=None:
                        np.zeros((60, 80, 3), np.uint8))
    probe = ClearProbe(monkeypatch, app)
    h = held(app)
    calls = _overlay(monkeypatch, {"screenX": 300, "screenY": 300}, probe)
    seen = []
    real_find = findtarget.find

    def find(tgt, *a, origin=None, **k):
        seen.append(origin)
        return real_find(tgt, *a, origin=origin, **k)
    monkeypatch.setattr(ui_dialogs.findtarget, "find", find)
    ui_dialogs.show_match_test(app, {"template": "a", "pick": {"near": [0, 0]}},
                               origin_fn=lambda: lambda frame, anchor, k: None)
    assert [(c["mode"], c["clearing"], c["kw"].get("late")) for c in calls] == \
        [("point", True, "origin")], "同一次清場, 在剛截的那張圖上點"
    h.release()
    assert calls[0]["kw"]["shot"] is not None, "點在剛截的那張圖上"
    assert seen and seen[0] == (300, 300)
    assert probe.in_clear() == []
    for w in app.root.winfo_children():
        if getattr(w, "title", lambda: "")() == "比對測試結果":
            w.destroy()


def test_比對測試_原點已經算好_不開覆蓋層(make_app, monkeypatch):
    app = _pointer_app(make_app, monkeypatch)
    monkeypatch.setattr(ui_dialogs, "_annotate_find",
                        lambda screen, org, f, origin=None, anchor=None:
                        np.zeros((60, 80, 3), np.uint8))
    calls = _overlay(monkeypatch, None)
    seen = []
    real_find = findtarget.find

    def find(tgt, *a, origin=None, **k):
        seen.append(origin)
        return real_find(tgt, *a, origin=origin, **k)
    monkeypatch.setattr(ui_dialogs.findtarget, "find", find)
    ui_dialogs.show_match_test(app, {"template": "a", "pick": {"near": [0, 0]}},
                               origin_fn=lambda: lambda frame, anchor, k: (400, 300))
    assert calls == [] and seen[0] == (400, 300)
    for w in app.root.winfo_children():
        if getattr(w, "title", lambda: "")() == "比對測試結果":
            w.destroy()


# ---------- 票 06: 按確定觸發的拾取檢查 ----------

def test_找圖設定按確定_對話框先關_主視窗辨識中_放行後才標警告(flow_app, monkeypatch):
    a = flow_app
    from automation import pickcheck
    monkeypatch.setattr(pickcheck, "resize_image", lambda img, s: img.resized(s))
    a.vision.plan("新左", [[(300, 400), (500, 400)]])
    probe = ClearProbe(monkeypatch, a)
    h = held(a)
    d = _Driver(a.root, "找圖設定")
    d.run(_press("確定"))
    got = ui_dialogs.edit_target_opts(a, a.root, {"template": "新左"}, "找圖設定")
    if d.error is not None:
        raise d.error
    assert got == {"within": None, "pick": None, "color": False}
    assert not any(w.winfo_exists() and w.title() == "找圖設定"
                   for w in a.root.winfo_children() if hasattr(w, "title"))
    assert a.recognition.holds(a.root)
    a.run_poll()
    assert a.status_lbl.cget("text") == recognition.BUSY_TEXT
    assert _btn_in(a.root, "存檔").instate(["disabled"])
    assert "新左" not in a.pick_warnings()
    h.release()
    assert "新左" in a.pick_warnings()
    assert any("拾取檢查「新左」" in m and "2 個匹配" in m for m in _logs(a))
    assert any("⚠ 新左" in r for r, _fg in _rows(a))
    assert probe.calls and probe.in_clear() == []
    a.run_poll()
    assert a.status_lbl.cget("text") != recognition.BUSY_TEXT
    assert not _btn_in(a.root, "存檔").instate(["disabled"])


def test_步驟編輯器按確定_步驟照存_檢查清場中查詢0次(make_app, monkeypatch):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 50, 50)
    app.vision.plan("a", [[(300, 400), (500, 400)]])
    probe = ClearProbe(monkeypatch, app)
    h = held(app)
    got = _edit(app, {"type": "find_click", "target": {"template": "a"}, "_index": 0},
                _press("確定"), title="新增：找圖點擊")
    assert findtarget.template(got) == "a", "對話框照關、步驟照存"
    assert app.recognition.holds(app.root)
    h.release()
    assert "a" in app.pick_warnings()
    assert probe.calls and probe.in_clear() == []


def test_按確定時引擎沒就緒_安靜略過_不進辨識中(make_app, monkeypatch, no_real_dialogs):
    app = make_app(1.0)
    _engine(app, monkeypatch)
    _template(app, "a", 50, 50)
    app.hub.state = "loading"
    got = _target_dialog(app, {"template": "a"}, _press("確定"))
    assert got is not None and not app.recognition.busy
    assert not any(no_real_dialogs.values()) and app.pick_warnings() == {}

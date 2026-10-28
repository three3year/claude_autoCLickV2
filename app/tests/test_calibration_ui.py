from types import SimpleNamespace

import os
import harness

import app as app_mod
import calibration
import enginehub
import flowfile
import ui_dialogs


class _FakeRunner:
    def __init__(self):
        self.started = []

    def status(self):
        return {"running": False, "round": 0, "totalRounds": 1,
                "step": 0, "stepTotal": 0, "loops": []}

    def start(self, steps, *a, **kw):
        self.started.append((list(steps), kw))


class _CalApp(app_mod.App):
    def __init__(self, root, base_dir, cal=None, names=None):
        self.root = root
        self.hub = enginehub.EngineHub()
        self.hub.state = enginehub.READY
        self.runner = _FakeRunner()
        self.steps = [{"type": "wait", "wait": 0.01}]
        self.scan_region = None
        self._pending_templates = set()
        self.run_mode = SimpleNamespace(get=lambda: "執行次數")
        self.flow_cal = cal
        self._names = (list(cal["pair"]) if cal else []) if names is None \
            else names

    def _run_count(self):
        return 1

    def list_template_names(self):
        return self._names

    def _show_mini(self):
        pass

    def log_ui(self, msg, level="info"):
        pass


def _warnings(monkeypatch):
    rec = []
    monkeypatch.setattr(app_mod.messagebox, "showwarning",
                        lambda title, msg, **kw: rec.append(msg))
    return rec


FLOW_CAL = {"pair": ["圖示", "關閉"], "baseline": 1696.0}


def test_沒有校準對的流程不能執行_並說明要先設定(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path)
    a.start_run()
    assert a.runner.started == []
    assert any("校準對" in m for m in rec)


def test_執行時把流程的校準資料交給執行器(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path, cal=FLOW_CAL)
    a.start_run()
    assert rec == []
    assert a.runner.started[0][1]["calibration"] == FLOW_CAL
    assert "scale" not in a.runner.started[0][1], "倍率由執行器開頭自己量"


def test_沒有搜尋範圍也能執行_基準點來自校準(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path, cal=FLOW_CAL)
    a.steps = _full({"type": "click", "click": [3, 4]})
    a.start_run()
    assert rec == [] and len(a.runner.started) == 1


def test_測試選取也把校準資料交給執行器(tkroot, monkeypatch, tmp_path):
    _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path, cal=FLOW_CAL)
    a.start_run(steps=list(a.steps), test=True)
    assert a.runner.started[0][1]["calibration"] == FLOW_CAL


def test_校準對的範本不在本流程_不執行(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path, cal=FLOW_CAL, names=["圖示"])
    a.start_run()
    assert a.runner.started == []
    assert any("關閉（校準對）" in m for m in rec)


def _full(*steps):
    from automation import flowdefaults
    return [flowdefaults.complete(s) for s in steps]


def test_拾取值反除倍率換回流程尺度():
    assert ui_dialogs._unscale(150, 1.5) == 100
    assert ui_dialogs._unscale(-75, 1.5) == -50
    assert ui_dialogs._unscale(33, 1.0) == 33, "倍率 1 與現狀等價"


def test_預設原點推算_相對偏移累積乘倍率():
    app = SimpleNamespace(
        steps=_full({"type": "find_click", "target": {"template": "a"}},
                    {"type": "click", "click": [30, 40]},
                    {"type": "click", "click": [10, 10]}),
        template_pos=lambda n: [0, 0])
    got = ui_dialogs._resolve_prev_origin(app, {"_index": 3}, None, 2.0, (100, 200))
    assert got == (100 + 60 + 20, 200 + 80 + 20)


def test_預設原點推算_倍率1沿用原值():
    app = SimpleNamespace(steps=_full({"type": "find_click", "target": {"template": "a"}},
                                      {"type": "click", "click": [30, 40]}),
                          template_pos=lambda n: [0, 0])
    got = ui_dialogs._resolve_prev_origin(app, {"_index": 2}, None, 1.0, (0, 0))
    assert got == (30, 40)


def test_範本拍攝位置相對基準點():
    shot = {"screenX": 100, "screenY": 200, "w": 20, "h": 10}
    assert ui_dialogs.template_pos_from_shot(shot, (60, 180), 1.0) == [50, 25]
    assert ui_dialogs.template_pos_from_shot(shot, (60, 180), 2.0) == [25, 13]
    assert ui_dialogs.template_pos_from_shot(shot, None, 1.0) is None


class _Btn:
    def __init__(self):
        self.text = ""

    def configure(self, **kw):
        self.text = kw.get("text", self.text)


class _EditorApp(app_mod.App):
    def __init__(self, root, base_dir, vision, cal=None):
        self.root = root
        self.store = flowfile.FlowTemplates.new(os.path.join(str(base_dir), "unsaved"))
        self.hub = vision
        self.detector = vision
        self.scan_region = None
        self.steps = []
        self.busy_target = None
        self._pending_templates = set()
        self._rereg_after = None
        self.logged = []
        self.autosaved = 0
        self.rendered = 0
        self.flow_cal = cal
        self.settings_lbl = _Btn()
        for n in (cal["pair"] if cal else ()):
            self.store.add(n, b"P")

    @property
    def library(self):
        return SimpleNamespace(templates={n: object() for n in self.store.names()})

    def ensure_registered(self):
        pass

    def _mark_dirty(self):
        self.autosaved += 1

    def render_steps(self, keep=None):
        self.rendered += 1

    def log_ui(self, msg, level="info"):
        self.logged.append(msg)


def _stub_capture(monkeypatch):
    import contextlib

    from harness import Screen
    monkeypatch.setattr(app_mod.ui_overlay, "screen_clear",
                        lambda root, extra=(): contextlib.nullcontext())
    monkeypatch.setattr(app_mod.capture, "grab",
                        lambda region=None: (Screen((0, 0)), (0, 0)))
    monkeypatch.setattr(app_mod.time, "sleep", lambda s: None)


def _editor(tkroot, monkeypatch, tmp_path, cal=None, pick=None):
    from harness import Vision
    _stub_capture(monkeypatch)
    if pick is not None:
        monkeypatch.setattr(ui_dialogs, "pick_cal_pair", lambda app: pick)
    vision = Vision()
    a = _EditorApp(tkroot, tmp_path, vision, cal)
    for n in (pick or ()):
        a.store.add(n, b"N")
    return a, vision


OLD = {"pair": ["舊圖示", "舊關閉"], "baseline": 1000.0}


def test_流程設定顯示校準對_主視窗摘要打勾(tkroot, monkeypatch, tmp_path):
    a, _ = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    a._settings_changed()
    assert a._cal_text() == "舊圖示 × 舊關閉（基準 1000 px）"
    assert a.settings_lbl.text.startswith("校準對 ✓")
    assert not hasattr(a, "editor_scale"), "沒有跨操作保存的編輯器倍率"


def test_新流程設定校準對_當下畫面就是流程尺度_第一張中心是基準點(
        tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, pick=("圖示", "關閉"))
    vision.plan("圖示", [(100, 100)])
    vision.plan("關閉", [(400, 100)])
    a.designate_pair()
    assert a.flow_cal == {"pair": ["圖示", "關閉"], "baseline": 300.0}
    assert a.autosaved == 1, "校準對跟著步驟草稿走"
    assert any("座標基準點 (100, 100)" in m for m in a.logged)


def _flow_with_coords(a):
    rect = [100, 50, 30, 20]
    a.steps = [{"type": "click", "click": [10, 20]},
               {"type": "drag", "drag": [1, 2], "to": [3, 4]},
               {"type": "find_click", "target": {"template": "a", "within": list(rect)},
                "confirm_target": {"template": "b", "within": list(rect)}}]
    a.busy_target = {"template": "z", "within": list(rect)}
    a.store.add("a", b"A", pos=[200, 100])


def test_更換校準對_先用舊對量倍率與舊基準點_所有座標改成相對新基準點(
        tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD),
                        pick=("圖示", "關閉"))
    _flow_with_coords(a)
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(1000, 50)])
    vision.plan("圖示", [(190, 95)])
    vision.plan("關閉", [(640, 95)])
    a.designate_pair()
    assert a.flow_cal == {"pair": ["圖示", "關閉"], "baseline": 500.0}
    s = a.steps
    assert s[0]["click"] == [10, 20], "相對原點的座標不動"
    assert (s[1]["drag"], s[1]["to"]) == ([1, 2], [3, 4])
    assert s[2]["target"]["within"] == [0, 0, 30, 20]
    assert s[2]["confirm_target"]["within"][0] == 0
    assert a.busy_target["within"][0] == 0
    assert a.store.pos_of("a") == [100, 50], "拍攝位置也平移"
    assert a.autosaved == 1 and a.rendered == 1
    assert any("換算" in m and "落點不變" in m for m in a.logged)
    from automation import flowfmt
    assert flowfmt.rect_to_screen([100, 50, 30, 20], (100, 50), 0.9) == \
        flowfmt.rect_to_screen(s[2]["target"]["within"], (190, 95), 0.9)


def test_更換校準對時舊對量不到_拒絕且資料不變(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD),
                        pick=("圖示", "關閉"))
    _flow_with_coords(a)
    vision.plan("舊圖示", [None])
    vision.plan("圖示", [(100, 100)])
    vision.plan("關閉", [(550, 100)])
    a.designate_pair()
    assert a.flow_cal == OLD
    assert a.steps[0]["click"] == [10, 20]
    assert a.store.pos_of("a") == [200, 100]
    assert any("舊圖示" in m for m in rec)
    assert a.autosaved == 0


def test_更換校準對時新對量不到_拒絕且資料不變(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD),
                        pick=("圖示", "關閉"))
    _flow_with_coords(a)
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(1000, 50)])
    vision.plan("圖示", [(100, 100)])
    vision.plan("關閉", [None])
    a.designate_pair()
    assert a.flow_cal == OLD
    assert a.steps[0]["click"] == [10, 20]
    assert any("關閉" in m for m in rec)


def test_兩張中心距離太近_拒絕(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _editor(tkroot, monkeypatch, tmp_path, pick=("圖示", "關閉"))
    vision.plan("圖示", [(100, 100)])
    vision.plan("關閉", [(100, 100)])
    a.designate_pair()
    assert a.flow_cal is None
    assert any("重疊" in m for m in rec)


def test_按校準只顯示倍率與基準點_步驟資料不變(tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    _flow_with_coords(a)
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(1300, 50)])
    a.test_calibration()
    assert any("×1.200" in m and "(100, 50)" in m for m in a.logged)
    assert a.flow_cal == OLD, "校準只量, 不動校準資料"
    assert a.steps[0]["click"] == [10, 20]
    assert a.store.pos_of("a") == [200, 100]
    assert a.autosaved == 0


def test_按校準失敗只寫紀錄(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    vision.plan("舊關閉", [None])
    a.test_calibration()
    assert any("舊關閉" in m for m in a.logged)
    assert rec == [], "結果寫紀錄, 不彈窗"
    assert a.flow_cal == OLD


def test_按校準主對找不到退備用對_備用對的範本也先載入(tkroot, monkeypatch, tmp_path):
    cal = dict(OLD)
    cal[calibration.FALLBACK_KEY] = calibration.make_fallback(
        ["標題左", "標題右"], 500.0, (0, 0))
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=cal)
    for n in ("標題左", "標題右"):
        a.store.add(n, b"F")
    vision.plan("舊圖示", [None])
    vision.plan("舊關閉", [(1300, 50)])
    vision.plan("標題左", [(100, 10)])
    vision.plan("標題右", [(700, 10)])
    a.test_calibration()
    assert set(vision.ensured) >= {"舊圖示", "舊關閉", "標題左", "標題右"}
    assert any("×1.200" in m and "備用" in m for m in a.logged)


def test_拾取檢查的安靜量測_備用對的範本也先確認載得起來(tkroot, monkeypatch):
    import contextlib

    import recognition
    monkeypatch.setattr(ui_dialogs.ui_overlay, "screen_clear",
                        lambda root, extra=(): contextlib.nullcontext())
    cal = dict(OLD)
    cal[calibration.FALLBACK_KEY] = calibration.make_fallback(
        ["標題左", "標題右"], 500.0, (0, 0))
    known, loaded = [], []
    measured = SimpleNamespace(ok=True, used="main", anchor=(1, 2), scale=1.0,
                               in_range=True)
    monkeypatch.setattr(ui_dialogs.calibration, "calibrate", lambda *a: measured)
    app = SimpleNamespace(
        root=tkroot, flow_cal=cal, hub=SimpleNamespace(ready=True),
        detector=SimpleNamespace(query=None),
        templates_known=lambda names: known.extend(names) or True,
        load_problem=lambda names: loaded.extend(names),
        calibration_ready=lambda *a, **k: (_ for _ in ()).throw(AssertionError("quiet 不該走這裡")),
        ensure_registered=lambda: None,
        grab_frame=lambda: ("frame", (0, 0)),
        log_ui=lambda msg, level="info": None)
    app.calibration_names = lambda: app_mod.App.calibration_names(app)
    app.recognition = recognition.Recognition(app)
    got = []
    ui_dialogs.measured_pick(app, tkroot, "拾取檢查", lambda r, m: got.append((m.anchor, m.k)),
                             quiet=True)
    assert got == [((1, 2), 1.0)]
    assert set(known) == set(loaded) == {"舊圖示", "舊關閉", "標題左", "標題右"}


def test_校準量測查詢不帶預期尺度(tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(1000, 50)])
    a.test_calibration()
    assert vision.expected_scales == [("舊圖示", None), ("舊關閉", None)]


def test_校準只在搜尋範圍內截圖(tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    a.scan_region = [50, 60, 700, 500]
    grabs = []
    from harness import Screen
    monkeypatch.setattr(app_mod.capture, "grab",
                        lambda region=None: (grabs.append(region),
                                             (Screen((region[0], region[1]),
                                                     (region[2], region[3])),
                                              (region[0], region[1])))[1])
    vision.plan("舊圖示", [(100, 100)])
    vision.plan("舊關閉", [(700, 100)])
    a.test_calibration()
    assert grabs == [[50, 60, 700, 500]]
    assert any("(100, 100)" in m for m in a.logged), "中心是螢幕座標"


def test_沒有校準對時按測試_紀錄寫還沒設定_不彈窗(tkroot, monkeypatch, tmp_path,
                                      no_real_dialogs):
    a, vision = _editor(tkroot, monkeypatch, tmp_path)
    a.test_calibration()
    assert any("還沒設定" in m for m in a.logged)
    assert not any(no_real_dialogs.values())
    assert vision.lookups == []


def test_開流程或切換流程時流程設定摘要跟著換(tkroot, monkeypatch, tmp_path):
    a, _ = _editor(tkroot, monkeypatch, tmp_path)
    assert a._settings_summary().startswith("校準對 ✗")
    for attr in ("run_mode", "run_count"):
        setattr(a, attr, SimpleNamespace(set=lambda v: None, get=lambda: 1))
    a.scan_lbl = _Btn()
    a._mode_ui = lambda: None
    a._update_region_preview = lambda: None
    a._apply_flow(dict(flowfile.new_flow(),
                       calibration={"pair": ["x", "y"], "baseline": 50.0}))
    assert a.flow_cal == {"pair": ["x", "y"], "baseline": 50.0}
    assert a.settings_lbl.text == "校準對 ✓　忙碌指示 —"


def test_按校準量到支援倍率範圍外_照常顯示倍率_另印一行警告(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    _flow_with_coords(a)
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(800, 50)])
    a.test_calibration()
    assert any("×0.700" in m and "(100, 50)" in m for m in a.logged)
    assert any("×0.700" in m and "×0.85–1.15" in m and "調大" in m
               for m in a.logged)
    assert rec == [], "只印紀錄, 不彈對話框"
    assert a.flow_cal == OLD
    assert a.steps[0]["click"] == [10, 20]


def test_按校準量到範圍內_沒有範圍外警告(tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(1100, 50)])
    a.test_calibration()
    assert not any("支援倍率範圍" in m for m in a.logged)

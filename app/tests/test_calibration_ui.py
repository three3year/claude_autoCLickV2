"""校準的 UI 薄殼接線 (ADR 0009、0012): 執行時交校準資料、編輯器的校準對與「校準」按鈕、
換校準對平移座標.

量測本身是 calibration 模組純函式 (test_calibration.py); 拾取當下的量測在
test_editor_scale.py。這裡只驗 UI 薄殼接對——沿用 test_engine_gating 的最小 App 子類手法。
"""
from types import SimpleNamespace

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import app as app_mod
import calibration
import enginehub
import flowfile
import ui_dialogs


class _FakeRunner:
    def __init__(self):
        self.started = []  # (steps, kwargs)

    def status(self):
        return {"running": False, "round": 0, "totalRounds": 1,
                "step": 0, "stepTotal": 0, "loops": []}

    def start(self, steps, *a, **kw):
        self.started.append((list(steps), kw))


class _CalApp(app_mod.App):
    """只建 start_run 需要的欄位 (引擎一律就緒)."""

    def __init__(self, root, profile_dir, cal=None, names=None):
        self.root = root
        self.hub = enginehub.EngineHub()
        self.hub.state = enginehub.READY
        self.runner = _FakeRunner()
        self.steps = [{"type": "wait", "ms": 10}]
        self.scan_region = None
        self.profile_dir = str(profile_dir)
        self._pending_templates = set()
        self.start_delay = SimpleNamespace(get=lambda: "無")
        self.run_mode = SimpleNamespace(get=lambda: "執行次數")
        self.avoid_hover = SimpleNamespace(get=lambda: False)
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


def test_絕對座標步驟沒有搜尋範圍也能執行_基準點來自校準(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path, cal=FLOW_CAL)
    a.steps = [{"type": "click", "x": 3, "y": 4}]
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


# ---------- 拾取換算的純邏輯 ----------

def test_拾取值反除倍率換回流程尺度():
    assert ui_dialogs._unscale(150, 1.5) == 100
    assert ui_dialogs._unscale(-75, 1.5) == -50
    assert ui_dialogs._unscale(33, 1.0) == 33, "倍率 1 與現狀等價"


def test_預設原點推算_相對偏移累積乘倍率_絕對點擊相對基準點():
    app = SimpleNamespace(
        steps=[{"type": "click", "x": 30, "y": 40},
               {"type": "click", "x": 10, "y": 10, "mode": "prev"}],
        template_pos=lambda n: None)
    got = ui_dialogs._resolve_prev_origin(app, {"_index": 2}, None, 2.0, (100, 200))
    assert got == (100 + 60 + 20, 200 + 80 + 20)


def test_預設原點推算_倍率1沿用原值():
    app = SimpleNamespace(steps=[{"type": "click", "x": 30, "y": 40}],
                          template_pos=lambda n: None)
    got = ui_dialogs._resolve_prev_origin(app, {"_index": 1}, None, 1.0, (0, 0))
    assert got == (30, 40)


def test_範本拍攝位置相對基準點():
    shot = {"screenX": 100, "screenY": 200, "w": 20, "h": 10}
    assert ui_dialogs.template_pos_from_shot(shot, (60, 180), 1.0) == [50, 25]
    assert ui_dialogs.template_pos_from_shot(shot, (60, 180), 2.0) == [25, 13]
    assert ui_dialogs.template_pos_from_shot(shot, None, 1.0) is None


# ---------- 編輯器: 校準對與「校準」按鈕 ----------

class _Btn:
    """記下 configure(text=...) 的按鈕/標籤樁."""

    def __init__(self):
        self.text = ""

    def configure(self, **kw):
        self.text = kw.get("text", self.text)


class _EditorApp(app_mod.App):
    """只建校準對/校準按鈕需要的欄位; 清場與擷取以樁取代."""

    def __init__(self, root, profile_dir, vision, cal=None):
        self.root = root
        self.profile_dir = str(profile_dir)
        self.ws = flowfile.Workspace(self.profile_dir)
        self.ws.ensure()
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
        self.cal_btn, self.cal_info = _Btn(), _Btn()
        for n in (cal["pair"] if cal else ()):
            self.ws.add(n, b"P")

    @property
    def profile(self):
        return SimpleNamespace(templates={n: object() for n in self.ws.names()})

    def ensure_registered(self):
        pass

    def _autosave(self):
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
        a.ws.add(n, b"N")
    return a, vision


OLD = {"pair": ["舊圖示", "舊關閉"], "baseline": 1000.0}


def test_介面顯示校準對_校準鈕只有名字(tkroot, monkeypatch, tmp_path):
    a, _ = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    a._update_cal_ui()
    assert a.cal_btn.text == "校準"
    assert "舊圖示" in a.cal_info.text and "1000" in a.cal_info.text
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
    rect = {"kind": "rect", "x": 100, "y": 50, "w": 30, "h": 20}
    a.steps = [{"type": "click", "x": 10, "y": 20},
               {"type": "click", "x": 10, "y": 20, "mode": "prev"},
               {"type": "drag", "x1": 1, "y1": 2, "x2": 3, "y2": 4},
               {"type": "find_click", "target": {"template": "a", "limit": dict(rect)},
                "confirmTarget": {"template": "b", "limit": dict(rect)}}]
    a.busy_target = {"template": "z", "limit": dict(rect)}
    a.ws.add("a", b"A", pos=[200, 100])


def test_更換校準對_先用舊對量倍率與舊基準點_所有座標改成相對新基準點(
        tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD),
                        pick=("圖示", "關閉"))
    _flow_with_coords(a)
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(1000, 50)])   # 900 ÷ 1000 → 倍率 0.9, 舊基準點 (100,50)
    vision.plan("圖示", [(190, 95)])      # 新基準點: 螢幕上差 (90,45) → 流程尺度 (100,50)
    vision.plan("關閉", [(640, 95)])      # 450 ÷ 0.9 = 500
    a.designate_pair()
    assert a.flow_cal == {"pair": ["圖示", "關閉"], "baseline": 500.0}
    s = a.steps
    assert (s[0]["x"], s[0]["y"]) == (-90, -30), "絕對座標減 (100,50)"
    assert (s[1]["x"], s[1]["y"]) == (10, 20), "相對座標不動"
    assert (s[2]["x1"], s[2]["y1"], s[2]["x2"], s[2]["y2"]) == (-99, -48, -97, -46)
    assert s[3]["target"]["limit"] == {"kind": "rect", "x": 0, "y": 0, "w": 30, "h": 20}
    assert s[3]["confirmTarget"]["limit"]["x"] == 0
    assert a.busy_target["limit"]["x"] == 0
    assert a.ws.pos_of("a") == [100, 50], "拍攝位置也平移"
    assert a.autosaved == 1 and a.rendered == 1
    assert any("換算" in m and "落點不變" in m for m in a.logged)
    # 落點不變: 舊 (100,50) + 10×0.9 = 109; 新 (190,95) + (−90)×0.9 = 109
    from automation import flowfmt
    assert flowfmt.to_screen((10, 20), (100, 50), 0.9) == \
        flowfmt.to_screen((s[0]["x"], s[0]["y"]), (190, 95), 0.9)


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
    assert (a.steps[0]["x"], a.steps[0]["y"]) == (10, 20)
    assert a.ws.pos_of("a") == [200, 100]
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
    assert (a.steps[0]["x"], a.steps[0]["y"]) == (10, 20)
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
    a.calibrate_now()
    assert "×1.20" in a.cal_btn.text
    assert any("×1.200" in m and "(100, 50)" in m for m in a.logged)
    assert a.flow_cal == OLD, "校準只量, 不動校準資料"
    assert (a.steps[0]["x"], a.steps[0]["y"]) == (10, 20)
    assert a.ws.pos_of("a") == [200, 100]
    assert a.autosaved == 0


def test_按校準失敗只提示(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    vision.plan("舊關閉", [None])
    a.calibrate_now()
    assert a.cal_btn.text == ""
    assert any("舊關閉" in m for m in rec)


def test_校準量測查詢不帶預期尺度(tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(1000, 50)])
    a.calibrate_now()
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
    vision.plan("舊關閉", [(700, 100)])    # 都在範圍 (50,60) 700×500 內
    a.calibrate_now()
    assert grabs == [[50, 60, 700, 500]]
    assert any("(100, 100)" in m for m in a.logged), "中心是螢幕座標"


def test_沒有校準對時按校準_提示先設定(tkroot, monkeypatch, tmp_path):
    rec = []
    monkeypatch.setattr(app_mod.messagebox, "showinfo",
                        lambda title, msg, **kw: rec.append(msg))
    a, vision = _editor(tkroot, monkeypatch, tmp_path)
    a.calibrate_now()
    assert any("設定校準對" in m for m in rec)
    assert vision.lookups == []


def test_開流程或切換流程時校準鈕回到只有名字(tkroot, monkeypatch, tmp_path):
    a, _ = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    a.cal_btn.text = "校準　×0.90"
    for attr in ("run_mode", "run_count", "avoid_hover"):
        setattr(a, attr, SimpleNamespace(set=lambda v: None, get=lambda: 1))
    a.scan_lbl = _Btn()
    a._mode_ui = lambda: None
    a._update_region_preview = lambda: None
    a._apply_flow({"steps": [], "coordSpace": "anchor",
                   "calibration": {"pair": ["x", "y"], "baseline": 50.0}})
    assert a.flow_cal == {"pair": ["x", "y"], "baseline": 50.0}
    assert a.cal_btn.text == "校準" and "x × y" in a.cal_info.text

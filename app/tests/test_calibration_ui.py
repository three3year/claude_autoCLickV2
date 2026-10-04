"""校準的 UI 薄殼接線: 執行警告與倍率 (票 03)、拾取守門/歸一與存檔重定 (票 04).

判斷本身是 calibration 模組純函式 (test_calibration.py); 這裡只驗 UI 薄殼
把警告、倍率、換算接對——沿用 test_engine_gating 的最小 App 子類手法。
"""
import json
import os
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


# ---------- 拾取守門與歸一 (票 04) ----------

def _dlg_warnings(monkeypatch):
    rec = []
    monkeypatch.setattr(ui_dialogs.messagebox, "showwarning",
                        lambda title, msg, **kw: rec.append(msg))
    return rec


def test_未校準時拾取被擋下並提示先校準(monkeypatch, tmp_path):
    calibration.save(str(tmp_path), {"pair": ["a", "b"], "baseline": 100.0,
                                     "scale": None, "fingerprint": None})
    rec = _dlg_warnings(monkeypatch)
    app = SimpleNamespace(profile_dir=str(tmp_path))
    ok, k = ui_dialogs._cal_state(app, None)
    assert not ok
    assert any("校準" in m for m in rec)


def test_已校準或無校準對時拾取放行(monkeypatch, tmp_path):
    rec = _dlg_warnings(monkeypatch)
    app = SimpleNamespace(profile_dir=str(tmp_path))
    assert ui_dialogs._cal_state(app, None) == (True, 1.0), "無校準對: 放行、倍率 1"
    calibration.save(str(tmp_path), {
        "pair": ["a", "b"], "baseline": 100.0, "scale": 1.25,
        "fingerprint": calibration.current_fingerprint()})
    assert ui_dialogs._cal_state(app, None) == (True, 1.25)
    assert rec == []


def test_拾取值反除倍率歸一到基準尺度():
    assert ui_dialogs._unscale(150, 1.5) == 100
    assert ui_dialogs._unscale(-75, 1.5) == -50
    assert ui_dialogs._unscale(33, 1.0) == 33, "倍率 1 與現狀等價"


def test_預設原點推算_絕對點擊_範圍原點加偏移乘倍率():
    app = SimpleNamespace(steps=[{"type": "click", "x": 30, "y": 40}],
                          scan_region=[100, 200, 800, 600],
                          template_pos=lambda n: None)
    got = ui_dialogs._resolve_prev_origin(app, {"_index": 1}, None, 1.5)
    assert got == (100 + 45, 200 + 60)


def test_預設原點推算_相對偏移累積乘倍率():
    app = SimpleNamespace(
        steps=[{"type": "click", "x": 30, "y": 40},
               {"type": "click", "x": 10, "y": 10, "mode": "prev"}],
        scan_region=[100, 200, 800, 600], template_pos=lambda n: None)
    got = ui_dialogs._resolve_prev_origin(app, {"_index": 2}, None, 2.0)
    assert got == (100 + 60 + 20, 200 + 80 + 20)


def test_預設原點推算_倍率1沿用原值(tmp_path):
    app = SimpleNamespace(steps=[{"type": "click", "x": 30, "y": 40}],
                          scan_region=[0, 0, 800, 600],
                          template_pos=lambda n: None)
    got = ui_dialogs._resolve_prev_origin(app, {"_index": 1}, None, 1.0)
    assert got == (30, 40)


# ---------- 存檔時重定基準 (票 04) ----------

class _RebaseApp(app_mod.App):
    """只建 _maybe_rebase 需要的欄位; 重繪/自動存檔以記錄樁取代."""

    def __init__(self, root, profile_dir, steps):
        self.root = root
        self.profile_dir = str(profile_dir)
        self.steps = steps
        self.rendered = 0
        self.cal_ui_updated = 0

    def render_steps(self, keep=None):
        self.rendered += 1

    def _update_cal_ui(self):
        self.cal_ui_updated += 1

    def log_ui(self, msg, level="info"):
        pass


OTHER_FLOW = "other" + flowfile.EXT


def _write_flow(profile_dir, name, steps):
    """一份流程＝一個自包自足的存檔 (ADR 0006)."""
    os.makedirs(os.path.join(str(profile_dir), "flows"), exist_ok=True)
    flowfile.write(os.path.join(str(profile_dir), "flows", name),
                   {"steps": steps, "coordSpace": "region"}, {})


def _read_steps(profile_dir, name):
    return flowfile.read(os.path.join(str(profile_dir), "flows",
                                      name))["data"]["steps"]


def test_倍率不為1時存檔自動重定並告知(tkroot, monkeypatch, tmp_path):
    infos = []
    monkeypatch.setattr(app_mod.messagebox, "showinfo",
                        lambda title, msg, **kw: infos.append(msg))
    calibration.save(str(tmp_path), {
        "pair": ["a", "b"], "baseline": 200.0, "scale": 1.25,
        "fingerprint": calibration.current_fingerprint()})
    _write_flow(tmp_path, OTHER_FLOW, [{"type": "click", "x": 100, "y": 40}])
    a = _RebaseApp(tkroot, tmp_path, [{"type": "click", "x": 8, "y": 8}])

    a._maybe_rebase()

    assert _read_steps(tmp_path, OTHER_FLOW)[0]["x"] == 125, \
        "profile 內其他流程檔一併改寫 (漏一份=混尺度)"
    assert (a.steps[0]["x"], a.steps[0]["y"]) == (10, 10), "記憶體同步跟上新基準"
    cal = calibration.load(str(tmp_path))
    assert cal["scale"] == 1.0 and cal["baseline"] == 250.0
    assert infos and "重定" in infos[0]
    assert a.rendered == 1 and a.cal_ui_updated == 1


def test_倍率為1時存檔不觸發重定(tkroot, monkeypatch, tmp_path):
    infos = []
    monkeypatch.setattr(app_mod.messagebox, "showinfo",
                        lambda title, msg, **kw: infos.append(msg))
    calibration.save(str(tmp_path), {
        "pair": ["a", "b"], "baseline": 200.0, "scale": 1.0,
        "fingerprint": calibration.current_fingerprint()})
    _write_flow(tmp_path, OTHER_FLOW, [{"type": "click", "x": 100, "y": 40}])
    a = _RebaseApp(tkroot, tmp_path, [{"type": "click", "x": 8, "y": 8}])

    a._maybe_rebase()

    assert _read_steps(tmp_path, OTHER_FLOW)[0]["x"] == 100, "不改寫任何流程檔"
    assert a.steps[0]["x"] == 8
    assert infos == [] and a.rendered == 0


def test_未校準時存檔不觸發重定(tkroot, monkeypatch, tmp_path):
    """倍率未知 (指紋不符) 時亂乘會毀掉座標, 必須完全不動."""
    infos = []
    monkeypatch.setattr(app_mod.messagebox, "showinfo",
                        lambda title, msg, **kw: infos.append(msg))
    calibration.save(str(tmp_path), {
        "pair": ["a", "b"], "baseline": 200.0, "scale": 1.25,
        "fingerprint": {"x": 0, "y": 0, "w": 1, "h": 1}})  # 別台機器量的
    _write_flow(tmp_path, OTHER_FLOW, [{"type": "click", "x": 100, "y": 40}])
    a = _RebaseApp(tkroot, tmp_path, [{"type": "click", "x": 8, "y": 8}])

    a._maybe_rebase()

    assert _read_steps(tmp_path, OTHER_FLOW)[0]["x"] == 100
    assert calibration.load(str(tmp_path))["scale"] == 1.25
    assert infos == []


# ---------- 來源基準標記的存檔守門 (票 06) ----------

MARKER = {"pair": ["srcA", "srcB"], "baseline": 60.0}


class _SaveApp(app_mod.App):
    """只建 _resolve_source_baseline 需要的欄位; 量測以樁取代."""

    def __init__(self, root, profile_dir, steps, marker, dist=None):
        self.root = root
        self.profile_dir = str(profile_dir)
        self.steps = steps
        self._source_baseline = marker
        self.hub = enginehub.EngineHub()
        self.hub.state = enginehub.READY
        self._dist = dist
        self.measured = []
        self.autosaved = 0

    def _measure_pair(self, pair, title):
        self.measured.append(list(pair))
        return self._dist

    def render_steps(self, keep=None):
        pass

    def _autosave(self):
        self.autosaved += 1

    def log_ui(self, msg, level="info"):
        pass


def test_無標記流程的存檔路徑不受影響(tkroot, tmp_path):
    a = _SaveApp(tkroot, tmp_path, [{"type": "click", "x": 30, "y": 40}], None)
    assert a._resolve_source_baseline() is True
    assert a.measured == []


def test_守門路徑一_量測成功依比值換算並移除標記(tkroot, monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod.messagebox, "askyesnocancel",
                        lambda *a, **kw: True)
    # 本機已校準 (倍率 1): 量得 120 ÷ 來源基準 60 → 比值 2
    calibration.save(str(tmp_path), {
        "pair": ["x", "y"], "baseline": 100.0, "scale": 1.0,
        "fingerprint": calibration.current_fingerprint()})
    a = _SaveApp(tkroot, tmp_path, [{"type": "click", "x": 30, "y": 40}],
                 dict(MARKER), dist=120.0)
    assert a._resolve_source_baseline() is True
    assert a.measured == [["srcA", "srcB"]], "量測對象是 pack 的校準對"
    assert (a.steps[0]["x"], a.steps[0]["y"]) == (60, 80)
    assert a._source_baseline is None


def test_守門路徑一_量測失敗中止存檔且標記保留(tkroot, monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod.messagebox, "askyesnocancel",
                        lambda *a, **kw: True)
    calibration.save(str(tmp_path), {
        "pair": ["x", "y"], "baseline": 100.0, "scale": 1.0,
        "fingerprint": calibration.current_fingerprint()})
    a = _SaveApp(tkroot, tmp_path, [{"type": "click", "x": 30, "y": 40}],
                 dict(MARKER), dist=None)  # 量測失敗 (缺圖)
    assert a._resolve_source_baseline() is False
    assert a._source_baseline == MARKER
    assert a.steps[0]["x"] == 30


def test_守門路徑一_本機未校準時擋下(tkroot, monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod.messagebox, "askyesnocancel",
                        lambda *a, **kw: True)
    rec = _warnings(monkeypatch)
    calibration.save(str(tmp_path), {"pair": ["x", "y"], "baseline": 100.0,
                                     "scale": None, "fingerprint": None})
    a = _SaveApp(tkroot, tmp_path, [{"type": "click", "x": 30, "y": 40}],
                 dict(MARKER), dist=120.0)
    assert a._resolve_source_baseline() is False
    assert any("校準" in m for m in rec)
    assert a._source_baseline == MARKER and a.measured == []


def test_守門路徑二_明確確認以匯入基準存檔(tkroot, monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod.messagebox, "askyesnocancel",
                        lambda *a, **kw: False)
    a = _SaveApp(tkroot, tmp_path, [{"type": "click", "x": 30, "y": 40}],
                 dict(MARKER))
    assert a._resolve_source_baseline() is True
    assert a._source_baseline is None, "確認後移除標記"
    assert a.steps[0]["x"] == 30, "座標不換算"
    assert a.autosaved == 1, "標記移除要落地"


def test_守門取消則不存檔(tkroot, monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod.messagebox, "askyesnocancel",
                        lambda *a, **kw: None)
    a = _SaveApp(tkroot, tmp_path, [{"type": "click", "x": 30, "y": 40}],
                 dict(MARKER))
    assert a._resolve_source_baseline() is False
    assert a._source_baseline == MARKER


# ---------- 校準圖由 profile 自存 (ADR 0006) ----------

# ---------- 編輯器: 校準對與「校準」按鈕 (flow-scale 票 03) ----------

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
        self._pending_templates = set()
        self._rereg_after = None
        self.logged = []
        self.autosaved = 0
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


def test_編輯器倍率預設1_介面顯示目前倍率(tkroot, monkeypatch, tmp_path):
    a, _ = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    assert a.editor_scale == 1.0
    a._update_cal_ui()
    assert "×1.00" in a.cal_btn.text
    assert "舊圖示" in a.cal_info.text and "1000" in a.cal_info.text


def test_新流程設定校準對_當下畫面就是流程尺度(tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, pick=("圖示", "關閉"))
    vision.plan("圖示", [(100, 100)])
    vision.plan("關閉", [(400, 100)])
    a.designate_pair()
    assert a.flow_cal == {"pair": ["圖示", "關閉"], "baseline": 300.0}
    assert a.editor_scale == 1.0
    assert a.autosaved == 1, "校準對跟著步驟草稿走"


def test_更換校準對_先用舊對量倍率_新基準距離換回流程尺度(tkroot, monkeypatch,
                                         tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD),
                        pick=("圖示", "關閉"))
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(1000, 50)])   # 900 ÷ 1000 → 倍率 0.9
    vision.plan("圖示", [(100, 100)])
    vision.plan("關閉", [(550, 100)])     # 450 ÷ 0.9 = 500
    a.designate_pair()
    assert a.flow_cal == {"pair": ["圖示", "關閉"], "baseline": 500.0}
    assert a.editor_scale == 0.9
    assert "×0.90" in a.cal_btn.text


def test_更換校準對時舊對量不到_拒絕且原資料不變(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD),
                        pick=("圖示", "關閉"))
    vision.plan("舊圖示", [None])
    vision.plan("圖示", [(100, 100)])
    vision.plan("關閉", [(550, 100)])
    a.designate_pair()
    assert a.flow_cal == OLD and a.editor_scale == 1.0
    assert any("舊圖示" in m for m in rec)
    assert a.autosaved == 0


def test_兩張中心距離太近_拒絕(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _editor(tkroot, monkeypatch, tmp_path, pick=("圖示", "關閉"))
    vision.plan("圖示", [(100, 100)])
    vision.plan("關閉", [(100, 100)])
    a.designate_pair()
    assert a.flow_cal is None
    assert any("重疊" in m for m in rec)


def test_按校準成功更新編輯器倍率(tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(1300, 50)])
    a.calibrate_now()
    assert a.editor_scale == 1.2
    assert "×1.20" in a.cal_btn.text
    assert a.flow_cal == OLD, "校準只量倍率, 不動校準資料"


def test_按校準失敗保留原倍率並說明(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    a.editor_scale = 0.8
    vision.plan("舊關閉", [None])
    a.calibrate_now()
    assert a.editor_scale == 0.8
    assert any("舊關閉" in m for m in rec)


def test_校準量測查詢不帶預期尺度(tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(1000, 50)])
    a.calibrate_now()
    assert vision.expected_scales == [("舊圖示", None), ("舊關閉", None)]


def test_沒有校準對時按校準_提示先設定(tkroot, monkeypatch, tmp_path):
    rec = []
    monkeypatch.setattr(app_mod.messagebox, "showinfo",
                        lambda title, msg, **kw: rec.append(msg))
    a, vision = _editor(tkroot, monkeypatch, tmp_path)
    a.calibrate_now()
    assert any("設定校準對" in m for m in rec)
    assert vision.lookups == []


def test_開流程或切換流程時編輯器倍率回到1(tkroot, monkeypatch, tmp_path):
    a, _ = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    a.editor_scale = 0.9
    a.steps = []
    for attr in ("run_mode", "run_count", "avoid_hover"):
        setattr(a, attr, SimpleNamespace(set=lambda v: None, get=lambda: 1))
    a.scan_lbl = _Btn()
    a._mode_ui = lambda: None
    a.render_steps = lambda keep=None: None
    a._update_region_preview = lambda: None
    a._source_baseline = None
    a._apply_flow({"steps": [], "coordSpace": "region",
                   "calibration": {"pair": ["x", "y"], "baseline": 50.0}})
    assert a.editor_scale == 1.0
    assert a.flow_cal == {"pair": ["x", "y"], "baseline": 50.0}
    assert "×1.00" in a.cal_btn.text and "x × y" in a.cal_info.text

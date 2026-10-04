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

class _MeasureApp(app_mod.App):
    """只建 _measure_pair / designate_pair 需要的欄位; 清場與擷取以樁取代."""

    def __init__(self, root, profile_dir, vision):
        self.root = root
        self.profile_dir = str(profile_dir)
        self.ws = flowfile.Workspace(self.profile_dir)
        self.hub = vision
        self.detector = vision
        self.profile = SimpleNamespace(templates={})
        self.scan_region = None
        self._pending_templates = set()
        self._rereg_after = None
        self.logged = []

    def ensure_registered(self):
        pass

    def reload_profile(self):
        """引擎看得到的＝本流程的範本 (工作區) ＋ profile 自存的校準圖."""
        templates = {n: object() for n in self.ws.names()}
        templates.update(flowfile.calibration_template_list(self.profile_dir))
        self.profile = SimpleNamespace(templates=templates)

    def _update_cal_ui(self):
        pass

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


def test_指定校準對把兩張圖複製進profile自存(tkroot, monkeypatch, tmp_path):
    from harness import Vision
    _stub_capture(monkeypatch)
    monkeypatch.setattr(ui_dialogs, "pick_cal_pair", lambda app: ("a", "b"))
    vision = Vision()
    vision.plan("a", [(100, 100)])     # 量的是本流程的範本 (量成功才複製)
    vision.plan("b", [(400, 100)])
    a = _MeasureApp(tkroot, tmp_path, vision)
    a.ws.add("a", b"AAA")
    a.ws.add("b", b"BBB")
    a.reload_profile()

    a.designate_pair()

    stored = flowfile.calibration_images(str(tmp_path))
    assert sorted(stored) == ["a", "b"], "兩張圖複製進 profile 自存"
    assert open(stored["a"], "rb").read() == b"AAA"
    cal = calibration.load(str(tmp_path))
    assert cal["pair"] == ["a", "b"]
    assert cal["baseline"] == 300.0 and cal["scale"] == 1.0


def test_量測取profile自存的校準圖_不是本流程的範本(tkroot, monkeypatch, tmp_path):
    """刪掉或搬走任何一份流程後校準仍可量測——工作區裡沒有那兩張圖也要行."""
    from harness import Vision
    _stub_capture(monkeypatch)
    flowfile.store_calibration_images(str(tmp_path), {"a": b"A", "b": b"B"})
    vision = Vision()
    vision.plan(flowfile.cal_template_name("a"), [(0, 0)])
    vision.plan(flowfile.cal_template_name("b"), [(0, 60)])
    a = _MeasureApp(tkroot, tmp_path, vision)
    a.reload_profile()
    assert a.ws.names() == [], "工作區是空的 (流程被刪掉了)"

    dist = a._measure_pair(["a", "b"], "校準")

    assert dist == 60.0
    assert vision.lookups == [flowfile.cal_template_name("a"),
                              flowfile.cal_template_name("b")], \
        "查的是 profile 自存的校準圖, 不是本流程的範本"


def test_profile缺校準圖時量測失敗並提示重新指定(tkroot, monkeypatch, tmp_path):
    from harness import Vision
    _stub_capture(monkeypatch)
    rec = _warnings(monkeypatch)
    a = _MeasureApp(tkroot, tmp_path, Vision())
    a.reload_profile()
    assert a._measure_pair(["a", "b"], "校準") is None
    assert any("校準圖" in m for m in rec)


def test_指定校準對量測失敗時舊校準圖不被砍掉(tkroot, monkeypatch, tmp_path):
    """先複製再量測的話,量測失敗就留下「calibration.json 指名一對圖、圖已被刪」
    的殘局——指定失敗必須完全不動舊校準."""
    from harness import Vision
    _stub_capture(monkeypatch)
    _warnings(monkeypatch)
    monkeypatch.setattr(ui_dialogs, "pick_cal_pair", lambda app: ("a", "b"))
    # 既有校準: 一對圖 + calibration.json
    calibration.save(str(tmp_path), {"pair": ["old1", "old2"],
                                     "baseline": 111.0, "scale": 1.0,
                                     "fingerprint": None})
    flowfile.store_calibration_images(str(tmp_path),
                                      {"old1": b"O1", "old2": b"O2"})
    vision = Vision()
    vision.plan("a", [(100, 100)])       # b 找不到 → 量測失敗
    vision.plan("b", [None])
    a = _MeasureApp(tkroot, tmp_path, vision)
    a.ws.add("a", b"AAA")
    a.ws.add("b", b"BBB")
    a.reload_profile()

    a.designate_pair()

    assert sorted(flowfile.calibration_images(str(tmp_path))) == \
        ["old1", "old2"], "舊校準圖原封不動"
    cal = calibration.load(str(tmp_path))
    assert cal["pair"] == ["old1", "old2"] and cal["baseline"] == 111.0


def test_指定校準對用本流程的範本量測(tkroot, monkeypatch, tmp_path):
    """量的是工作區裡那兩張 (量成功才複製進 profile), 不是 profile 自存的圖
    ——否則第一次指定時 profile 還沒有圖, 根本量不起來."""
    from harness import Vision
    _stub_capture(monkeypatch)
    monkeypatch.setattr(ui_dialogs, "pick_cal_pair", lambda app: ("a", "b"))
    vision = Vision()
    vision.plan("a", [(0, 0)])
    vision.plan("b", [(0, 50)])
    a = _MeasureApp(tkroot, tmp_path, vision)
    a.ws.add("a", b"AAA")
    a.ws.add("b", b"BBB")
    a.reload_profile()

    a.designate_pair()

    assert vision.lookups == ["a", "b"], "查的是本流程的範本名, 沒有 _cal/ 前綴"
    assert calibration.load(str(tmp_path))["baseline"] == 50.0
    assert sorted(flowfile.calibration_images(str(tmp_path))) == ["a", "b"]

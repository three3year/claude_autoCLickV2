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

    def __init__(self, root, profile_dir):
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

    def _run_count(self):
        return 1

    def list_template_names(self):
        return []

    def _show_mini(self):
        pass

    def log_ui(self, msg, level="info"):
        pass


def _warnings(monkeypatch):
    rec = []
    monkeypatch.setattr(app_mod.messagebox, "showwarning",
                        lambda title, msg, **kw: rec.append(msg))
    return rec


def test_沒有校準對_無警告_倍率1(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path)
    a.start_run()
    assert rec == []
    assert a.runner.started[0][1]["scale"] == 1.0


def test_未校準_警告後照跑_倍率1(tkroot, monkeypatch, tmp_path):
    calibration.save(str(tmp_path), {"pair": ["a", "b"], "baseline": 100.0,
                                     "scale": None, "fingerprint": None})
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path)
    a.start_run()
    assert any("尚未校準" in m for m in rec)
    assert len(a.runner.started) == 1, "警告後仍可執行"
    assert a.runner.started[0][1]["scale"] == 1.0


def test_已校準_無警告_倍率傳進runner(tkroot, monkeypatch, tmp_path):
    calibration.save(str(tmp_path), {
        "pair": ["a", "b"], "baseline": 100.0, "scale": 1.5,
        "fingerprint": calibration.current_fingerprint()})
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path)
    a.start_run()
    assert rec == []
    assert a.runner.started[0][1]["scale"] == 1.5


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


def _write_flow(profile_dir, name, steps):
    flows = os.path.join(str(profile_dir), "flows")
    os.makedirs(flows, exist_ok=True)
    with open(os.path.join(flows, name), "w", encoding="utf-8") as f:
        json.dump({"steps": steps, "coordSpace": "region"}, f)


def _read_steps(profile_dir, name):
    with open(os.path.join(str(profile_dir), "flows", name),
              encoding="utf-8") as f:
        return json.load(f)["steps"]


def test_倍率不為1時存檔自動重定並告知(tkroot, monkeypatch, tmp_path):
    infos = []
    monkeypatch.setattr(app_mod.messagebox, "showinfo",
                        lambda title, msg, **kw: infos.append(msg))
    calibration.save(str(tmp_path), {
        "pair": ["a", "b"], "baseline": 200.0, "scale": 1.25,
        "fingerprint": calibration.current_fingerprint()})
    _write_flow(tmp_path, "other.json", [{"type": "click", "x": 100, "y": 40}])
    a = _RebaseApp(tkroot, tmp_path, [{"type": "click", "x": 8, "y": 8}])

    a._maybe_rebase()

    assert _read_steps(tmp_path, "other.json")[0]["x"] == 125, \
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
    _write_flow(tmp_path, "other.json", [{"type": "click", "x": 100, "y": 40}])
    a = _RebaseApp(tkroot, tmp_path, [{"type": "click", "x": 8, "y": 8}])

    a._maybe_rebase()

    assert _read_steps(tmp_path, "other.json")[0]["x"] == 100, "不改寫任何流程檔"
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
    _write_flow(tmp_path, "other.json", [{"type": "click", "x": 100, "y": 40}])
    a = _RebaseApp(tkroot, tmp_path, [{"type": "click", "x": 8, "y": 8}])

    a._maybe_rebase()

    assert _read_steps(tmp_path, "other.json")[0]["x"] == 100
    assert calibration.load(str(tmp_path))["scale"] == 1.25
    assert infos == []

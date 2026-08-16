"""執行入口的校準接線 (票 03): 未校準警告一次後照跑、倍率傳進 runner.

判斷本身是 calibration 模組純函式 (test_calibration.py); 這裡只驗 UI 薄殼
把警告與倍率接對——沿用 test_engine_gating 的最小 App 子類手法。
"""
from types import SimpleNamespace

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import app as app_mod
import calibration
import enginehub


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

"""就緒 gating (startup-speed 票 03): `引擎就緒`前辨識類操作提示並拒絕.

App 的重量級 __init__ 以子類跳過 (沿用 test_deferred_reregister 模式),
hub 直接撥狀態、messagebox 以紀錄樁取代——驗「狀態×操作」的外部行為:
拒絕時跳提示且不啟動, 就緒時放行。
"""
from types import SimpleNamespace

import tkinter as tk

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import app as app_mod
import enginehub


class _FakeRunner:
    def __init__(self):
        self.started = []
        self.stopped = 0
        self.running = False

    def status(self):
        return {"running": self.running, "round": 0, "totalRounds": 1,
                "step": 0, "stepTotal": 0, "loops": []}

    def start(self, steps, *a, **kw):
        self.started.append(list(steps))

    def stop(self):
        self.stopped += 1


class _GateApp(app_mod.App):
    """只建 start_run / stop_all / F12 gating 需要的欄位."""

    def __init__(self, root, state):
        self.root = root
        self.hub = enginehub.EngineHub()
        self.hub.state = state
        self.runner = _FakeRunner()
        self.steps = [{"type": "wait", "wait": 0.01}]
        self.scan_region = None
        self.flow_cal = {"pair": ["a", "b"], "baseline": 100.0}  # 流程可執行
        self._pending_templates = set()
        self.run_mode = SimpleNamespace(get=lambda: "執行次數")

    def _run_count(self):
        return 1

    def list_template_names(self):
        return ["a", "b"]

    def _show_mini(self):
        pass

    def log_ui(self, msg, level="info"):
        pass


class _MsgRec:
    def __init__(self, monkeypatch):
        self.warnings = []
        self.infos = []
        monkeypatch.setattr(app_mod.messagebox, "showwarning",
                            lambda title, msg, **kw: self.warnings.append(msg))
        monkeypatch.setattr(app_mod.messagebox, "showinfo",
                            lambda title, msg, **kw: self.infos.append(msg))


def _pump(root, ms=120):
    done = tk.IntVar(master=root, value=0)
    root.after(ms, lambda: done.set(1))
    root.wait_variable(done)


def test_載入中按執行_提示並拒絕(tkroot, monkeypatch):
    rec = _MsgRec(monkeypatch)
    a = _GateApp(tkroot, enginehub.LOADING)
    a.start_run()
    assert a.runner.started == []
    assert any("載入中" in m for m in rec.warnings)


def test_載入失敗按執行_提示並拒絕(tkroot, monkeypatch):
    rec = _MsgRec(monkeypatch)
    a = _GateApp(tkroot, enginehub.FAILED)
    a.start_run()
    assert a.runner.started == []
    assert any("失敗" in m for m in rec.warnings)


def test_就緒按執行_放行啟動(tkroot, monkeypatch):
    rec = _MsgRec(monkeypatch)
    a = _GateApp(tkroot, enginehub.READY)
    a.start_run()
    assert a.runner.started == [a.steps]
    assert rec.warnings == []


def test_載入中按F12_提示並拒絕_不經急停(tkroot, monkeypatch):
    rec = _MsgRec(monkeypatch)
    a = _GateApp(tkroot, enginehub.LOADING)
    a._on_hotkey()
    _pump(tkroot)  # 提示是轉回 UI 執行緒跳的
    assert a.runner.stopped == 0
    assert any("載入中" in m for m in rec.warnings)


def test_執行中按F12_直接急停不提示(tkroot, monkeypatch):
    rec = _MsgRec(monkeypatch)
    a = _GateApp(tkroot, enginehub.LOADING)  # 理論上不會發生, 但急停必須永遠有效
    a.runner.running = True
    a._on_hotkey()
    assert a.runner.stopped == 1
    assert rec.warnings == []


def test_就緒按F12未執行_照舊空停止(tkroot, monkeypatch):
    rec = _MsgRec(monkeypatch)
    a = _GateApp(tkroot, enginehub.READY)
    a._on_hotkey()
    assert a.runner.stopped == 1
    assert rec.warnings == []

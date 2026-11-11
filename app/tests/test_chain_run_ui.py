import os

import numpy as np
import pytest

import app as app_mod
import apppaths
import enginehub
import flowfile
from automation import imgio, win
from harness import FileLog
from test_main_window import _logs, texts

TC = r"C:\Program Files\GRYPHLINK\games\Arknights_TC\Arknights.exe"
CN = r"C:\Program Files\Arknights bilibili\games\Arknights Game\Arknights.exe"
WINDOWS = {TC: 11, CN: 22}
CAL = {"pair": ["p", "q"], "baseline": 100.0}
RUNNER_END_LOG = {"done": "執行完成", "stopped": "已停止 (使用者中斷)", "error": "執行錯誤: x"}


def _png():
    return imgio.encode_png(np.full((20, 40, 3), 100, np.uint8))


def _flow(name, program, steps=None, run=1, images=True):
    f = flowfile.new_flow()
    f["program"] = program
    f["calibration"] = CAL
    f["run"] = run
    f["steps"] = flowfile.parse_steps(steps if steps is not None else [{"wait": 0.01}])
    flowfile.write_flow(os.path.join(apppaths.flows_root(), name), f,
                        {"p": _png(), "q": _png()} if images else None)


def _chain(name, *items):
    flowfile.write_chain(apppaths.flows_root(), name,
                         [{"flow": f, "run": r} for f, r in items])


class _Runner:
    def __init__(self, app):
        self.app = app
        self.started = []
        self.running = False
        self.ended = None
        self.error_reason = None
        self.count = 0
        self.logs = []

    def status(self):
        return {"running": self.running, "prerun": None, "round": 1 if self.running else 0,
                "totalRounds": self.count, "step": 0, "stepTotal": 0, "loops": []}

    def logs_since(self, seq):
        return [e for e in self.logs if e["seq"] > seq]

    def start(self, steps, run_mode="count", run_count=1, **kw):
        assert not self.running, "上一份還沒結束就開始下一份"
        self.started.append((self.app.flow_name(), run_mode, run_count))
        self.running, self.ended, self.error_reason = True, None, None
        self.count = run_count

    def stop(self):
        pass

    def finish(self, ended="done", reason=None):
        self.running, self.ended, self.error_reason = False, ended, reason
        self.logs.append({"seq": len(self.logs) + 1, "t": "00:00:00", "level": "ok",
                          "msg": RUNNER_END_LOG[ended]})


@pytest.fixture
def chain_app(main_app, monkeypatch):
    a = main_app
    a.runner = _Runner(a)
    a.hub.state = enginehub.READY
    monkeypatch.setattr(a, "start_preload", lambda: None)
    return a


@pytest.fixture
def windows(monkeypatch):
    shown = [win.Window(hwnd=h, pid=1000 + h, title="明日方舟", size=(1280, 720), path=p)
             for p, h in WINDOWS.items()]
    monkeypatch.setattr(win, "list_windows", lambda: list(shown))
    return shown


@pytest.fixture
def fronted(monkeypatch):
    got = []
    monkeypatch.setattr(win, "bring_to_front", lambda hwnd, **kw: got.append(hwnd) or True)
    return got


@pytest.fixture
def filelog(monkeypatch):
    rec = FileLog()
    monkeypatch.setattr(app_mod.applog, "log", rec)
    return rec


def _start(a, name):
    a.chain_pick.set(name)
    a.btn_chain.invoke()


def _finish(a, ended="done", reason=None):
    a.runner.finish(ended, reason)
    a.run_poll()


def test_依序切流程_每份用串接檔的輪數_不受主視窗輪數欄位影響(
        chain_app, windows, fronted, filelog):
    a = chain_app
    _flow("早_繁中", TC, run=5)
    _flow("早_簡中", CN)
    _chain("早班", ("早_繁中", 2), ("早_簡中", 1))
    a.run_count.set(9)
    _start(a, "早班")
    assert a.runner.started == [("早_繁中", "count", 2)]
    assert fronted == [WINDOWS[TC]]
    _finish(a)
    assert a.runner.started[1:] == [("早_簡中", "count", 1)]
    assert fronted == [WINDOWS[TC], WINDOWS[CN]]
    _finish(a)
    assert len(a.runner.started) == 2
    assert a.flow_name() == "早_簡中", "結束後停在最後一份"


def test_迷你視窗顯示串接進度_兩份之間不關_整條結束才關(chain_app, windows, fronted):
    a = chain_app
    _flow("早_繁中", TC)
    _flow("早_簡中", CN)
    _chain("早班", ("早_繁中", 1), ("早_簡中", 1))
    _start(a, "早班")
    mini = a._mini
    assert mini is not None and "串接 1/2：早_繁中" in texts(mini)
    _finish(a)
    assert a._mini is mini and mini.winfo_exists(), "兩份之間不關"
    assert "串接 2/2：早_簡中" in texts(mini)
    _finish(a)
    assert a._mini is None and not mini.winfo_exists()


def test_結束時執行紀錄印總結_檔案日誌記一筆chain(chain_app, windows, fronted, filelog):
    a = chain_app
    _flow("早_繁中", TC)
    _flow("早_簡中", CN)
    _chain("早班", ("早_繁中", 1), ("早_簡中", 1))
    _start(a, "早班")
    _finish(a)
    _finish(a)
    logs = _logs(a)
    i = next(k for k, m in enumerate(logs) if "串接「早班」結束" in m)
    assert [m.split(" ", 1)[1] for m in logs[i + 1:i + 3]] == [
        "　1. 早_繁中：完成", "　2. 早_簡中：完成"]
    assert filelog.of("chain") == [{"name": "早班",
                                    "summary": "1. 早_繁中：完成；2. 早_簡中：完成"}]


def test_準備檢查不過_一個警告列出全部問題_沒有開始(
        chain_app, windows, fronted, no_real_dialogs):
    a = chain_app
    windows[:] = [w for w in windows if w.path != CN]
    _flow("缺圖", TC, images=False)
    _flow("早_簡中", CN)
    _flow("沒設程式", None)
    _chain("早班", ("缺圖", 1), ("早_簡中", 1), ("沒設程式", 1))
    _start(a, "早班")
    assert a.runner.started == [] and fronted == [] and a._mini is None
    [msg] = no_real_dialogs["warning"]
    assert "「缺圖」" in msg and "p（校準對）" in msg
    assert f"「早_簡中」\n・目標程式沒在執行：{CN}" in msg
    assert "「沒設程式」\n・未設目標程式" in msg


def test_未存檔時先問存或丟_取消就不開始(chain_app, windows, fronted, monkeypatch):
    a = chain_app
    _flow("早_繁中", TC)
    _chain("早班", ("早_繁中", 1))
    a._mark_dirty()
    asked = []
    monkeypatch.setattr(app_mod.messagebox, "askyesnocancel",
                        lambda title, msg, **kw: asked.append(title))
    _start(a, "早班")
    assert asked == ["執行串接"] and a.runner.started == []
    monkeypatch.setattr(app_mod.messagebox, "askyesnocancel", lambda *x, **kw: False)
    _start(a, "早班")
    assert a.runner.started == [("早_繁中", "count", 1)]


def test_第一份失敗_同目標程式的第三份跳過_不同目標程式的第二份照跑(
        chain_app, windows, fronted, filelog):
    a = chain_app
    _flow("早_繁中", TC)
    _flow("早_簡中", CN)
    _flow("晚_繁中", TC)
    _chain("早班", ("早_繁中", 1), ("早_簡中", 1), ("晚_繁中", 1))
    _start(a, "早班")
    _finish(a, "error", "找不到圖：開始")
    assert [s[0] for s in a.runner.started] == ["早_繁中", "早_簡中"]
    _finish(a)
    assert [s[0] for s in a.runner.started] == ["早_繁中", "早_簡中"]
    assert fronted == [WINDOWS[TC], WINDOWS[CN]]
    assert filelog.of("chain") == [{"name": "早班", "summary": "；".join([
        "1. 早_繁中：失敗（找不到圖：開始）", "2. 早_簡中：完成",
        "3. 晚_繁中：跳過（因為第 1 份「早_繁中」失敗）"])}]
    assert a.flow_name() == "早_簡中", "停在最後實際跑過的那份, 不切到跳過的"
    assert a._mini is None


def test_移不到前景_這份記為失敗_同目標程式的跳過_其他照跑(
        chain_app, windows, monkeypatch, filelog):
    a = chain_app
    monkeypatch.setattr(win, "bring_to_front", lambda hwnd, **kw: hwnd != WINDOWS[CN])
    _flow("早_繁中", TC)
    _flow("早_簡中", CN)
    _flow("晚_簡中", CN)
    _flow("晚_繁中", TC)
    _chain("早班", ("早_繁中", 1), ("早_簡中", 1), ("晚_簡中", 1), ("晚_繁中", 1))
    _start(a, "早班")
    _finish(a)
    assert [s[0] for s in a.runner.started] == ["早_繁中", "晚_繁中"]
    _finish(a)
    [rec] = filelog.of("chain")
    lines = rec["summary"].split("；")
    assert lines[1].startswith("2. 早_簡中：失敗（移不到前景")
    assert lines[2:] == ["3. 晚_簡中：跳過（因為第 2 份「早_簡中」失敗）", "4. 晚_繁中：完成"]
    assert a.flow_name() == "晚_繁中"


def test_兩份之間按F12_下一份不會開始(chain_app, windows, monkeypatch, filelog):
    a = chain_app

    def front_then_f12(hwnd, **kw):
        if hwnd == WINDOWS[CN]:
            a._on_hotkey()
        return True

    monkeypatch.setattr(win, "bring_to_front", front_then_f12)
    _flow("早_繁中", TC)
    _flow("早_簡中", CN)
    _flow("晚_繁中", TC)
    _chain("早班", ("早_繁中", 1), ("早_簡中", 1), ("晚_繁中", 1))
    _start(a, "早班")
    _finish(a)
    a.run_poll()
    assert [s[0] for s in a.runner.started] == ["早_繁中"]
    assert filelog.of("chain") == [{"name": "早班", "summary": "；".join([
        "1. 早_繁中：完成", "2. 早_簡中：中斷（急停）", "3. 晚_繁中：未執行（急停）"])}]
    assert a._mini is None


def test_停止鈕_執行中按下_整條結束(chain_app, windows, fronted, filelog):
    a = chain_app
    _flow("早_繁中", TC)
    _flow("早_簡中", CN)
    _chain("早班", ("早_繁中", 1), ("早_簡中", 1))
    _start(a, "早班")
    a.run_poll()
    a.btn_stop.invoke()
    a.runner.finish("stopped")
    a.run_poll()
    assert [s[0] for s in a.runner.started] == ["早_繁中"]
    [rec] = filelog.of("chain")
    assert rec["summary"] == "1. 早_繁中：中斷（急停）；2. 早_簡中：未執行（急停）"


def test_最後一份讀不到_主視窗停在之前實際跑過的那份(chain_app, windows, fronted, filelog):
    a = chain_app
    _flow("早_繁中", TC)
    _flow("早_簡中", CN)
    _chain("早班", ("早_繁中", 1), ("早_簡中", 1))
    _start(a, "早班")
    with open(os.path.join(apppaths.flows_root(), "早_簡中", "flow.yaml"), "w",
              encoding="utf-8") as f:
        f.write("format: 999\n")
    _finish(a)
    assert [s[0] for s in a.runner.started] == ["早_繁中"]
    [rec] = filelog.of("chain")
    assert "2. 早_簡中：失敗（讀不到流程：" in rec["summary"]
    assert a.flow_name() == "早_繁中"


def test_執行器停止_整條結束_不跑下一份(chain_app, windows, fronted, filelog):
    a = chain_app
    _flow("早_繁中", TC)
    _flow("早_簡中", CN)
    _chain("早班", ("早_繁中", 1), ("早_簡中", 1))
    _start(a, "早班")
    _finish(a, "stopped")
    assert [s[0] for s in a.runner.started] == ["早_繁中"]
    [rec] = filelog.of("chain")
    assert rec["summary"] == "1. 早_繁中：中斷（急停）；2. 早_簡中：未執行（急停）"


def test_最後一份找不到視窗_主視窗切回之前實際跑過的那份(chain_app, windows, fronted, filelog):
    a = chain_app
    _flow("早_繁中", TC)
    _flow("早_簡中", CN)
    _chain("早班", ("早_繁中", 1), ("早_簡中", 1))
    _start(a, "早班")
    windows[:] = [w for w in windows if w.path != CN]
    _finish(a)
    [rec] = filelog.of("chain")
    assert rec["summary"] == f"1. 早_繁中：完成；2. 早_簡中：失敗（找不到視窗：{CN}沒在執行）"
    assert a.flow_name() == "早_繁中"
    assert a.steps and not a.dirty


@pytest.mark.parametrize("cn_window", [True, False], ids=["視窗還在", "視窗不見了"])
def test_切換流程時按F12_不再移動視窗_記中斷不記失敗(
        chain_app, windows, fronted, filelog, monkeypatch, cn_window):
    a = chain_app
    switch = a._switch_flow

    def switch_then_f12(folder, flow):
        switch(folder, flow)
        if os.path.basename(folder) == "早_簡中":
            a._on_hotkey()

    monkeypatch.setattr(a, "_switch_flow", switch_then_f12)
    _flow("早_繁中", TC)
    _flow("早_簡中", CN)
    _flow("晚_繁中", TC)
    _chain("早班", ("早_繁中", 1), ("早_簡中", 1), ("晚_繁中", 1))
    _start(a, "早班")
    if not cn_window:
        windows[:] = [w for w in windows if w.path != CN]
    _finish(a)
    assert fronted == [WINDOWS[TC]]
    assert [s[0] for s in a.runner.started] == ["早_繁中"]
    assert filelog.of("chain") == [{"name": "早班", "summary": "；".join([
        "1. 早_繁中：完成", "2. 早_簡中：中斷（急停）", "3. 晚_繁中：未執行（急停）"])}]
    assert not any("失敗" in m for m in _logs(a))
    assert a.flow_name() == "早_繁中"


def test_總結排在執行器的結束紀錄後面(chain_app, windows, fronted):
    a = chain_app
    _flow("早_繁中", TC)
    _chain("早班", ("早_繁中", 1))
    _start(a, "早班")
    _finish(a)
    logs = [m.split(" ", 1)[-1] for m in _logs(a)]
    assert logs.index("執行完成") < next(
        i for i, m in enumerate(logs) if m.startswith("串接「早班」結束"))

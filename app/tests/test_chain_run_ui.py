"""主視窗「執行串接」(會開視窗, 在隱藏桌面跑).

執行器換成替身 (記下每次 start、由測試決定何時結束); 列視窗與移到最上層換成假的。
流程與串接檔寫在 conftest 換好的暫存流程存放區。輪詢由測試手動推 (`run_poll`)。
"""
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
    """執行器替身: start 記下 (當時主視窗開的流程, 模式, 輪數), finish 讓它結束."""

    def __init__(self, app):
        self.app = app
        self.started = []
        self.running = False
        self.ended = None
        self.error_reason = None
        self.count = 0

    def status(self):
        return {"running": self.running, "prerun": None, "round": 1 if self.running else 0,
                "totalRounds": self.count, "step": 0, "stepTotal": 0, "loops": []}

    def logs_since(self, _seq):
        return []

    def start(self, steps, run_mode="count", run_count=1, **kw):
        assert not self.running, "上一份還沒結束就開始下一份"
        self.started.append((self.app.flow_name(), run_mode, run_count))
        self.running, self.ended, self.error_reason = True, None, None
        self.count = run_count

    def stop(self):
        pass

    def finish(self, ended="done", reason=None):
        self.running, self.ended, self.error_reason = False, ended, reason


@pytest.fixture
def chain_app(main_app, monkeypatch):
    a = main_app
    a.runner = _Runner(a)
    a.hub.state = enginehub.READY
    monkeypatch.setattr(a, "start_preload", lambda: None)
    return a


@pytest.fixture
def windows(monkeypatch):
    """假的「列出視窗」: 預設兩個客戶端都開著."""
    shown = [win.Window(hwnd=h, pid=1000 + h, title="明日方舟", size=(1280, 720), path=p)
             for p, h in WINDOWS.items()]
    monkeypatch.setattr(win, "list_windows", lambda: list(shown))
    return shown


@pytest.fixture
def fronted(monkeypatch):
    """假的「移到最上層」: 記下被移上去的視窗, 一律成功."""
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


def test_移不到前景_這份記為失敗_整條結束不跑下一份(chain_app, windows, monkeypatch, filelog):
    a = chain_app
    monkeypatch.setattr(win, "bring_to_front", lambda hwnd, **kw: hwnd != WINDOWS[CN])
    _flow("早_繁中", TC)
    _flow("早_簡中", CN)
    _flow("晚_繁中", TC)
    _chain("早班", ("早_繁中", 1), ("早_簡中", 1), ("晚_繁中", 1))
    _start(a, "早班")
    _finish(a)
    assert [s[0] for s in a.runner.started] == ["早_繁中"]
    [rec] = filelog.of("chain")
    assert "2. 早_簡中：失敗（移不到前景" in rec["summary"]
    assert a._mini is None


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

import contextlib
import threading
import time
import tkinter as tk

import pytest

import harness
from harness import FileLog, Held, Screen, Vision

import app as app_mod
import calibration
import enginehub
import recognition
import ui_overlay
from test_main_window import SETTINGS, _btn_in, _logs, _row_button
from test_template_picker import _all, _Driver


class ClearProbe:
    def __init__(self, monkeypatch, app):
        self.depth = 0
        self.calls = []

        @contextlib.contextmanager
        def screen_clear(root, extra=()):
            self.depth += 1
            try:
                yield
            finally:
                self.depth -= 1
        monkeypatch.setattr(ui_overlay, "screen_clear", screen_clear)
        query, ensure = app.detector.query, app.hub.ensure_template

        def probe_query(name, *a, **k):
            self.calls.append((name, self.depth > 0))
            return query(name, *a, **k)

        def probe_ensure(name):
            self.calls.append((name, self.depth > 0))
            return ensure(name)
        monkeypatch.setattr(app.detector, "query", probe_query)
        monkeypatch.setattr(app.hub, "ensure_template", probe_ensure)

    def in_clear(self):
        return [n for n, clearing in self.calls if clearing]


def held(app):
    h = app.recognition.executor = Held()
    return h


def _disabled(w):
    return w.instate(["disabled"])


class _Mini:
    def __init__(self, root):
        self.root = root
        self.logged = []

    def log_ui(self, msg, level="info"):
        self.logged.append((level, msg))


@pytest.fixture
def mini(tkroot):
    tkroot.deiconify()
    tkroot.update()
    app = _Mini(tkroot)
    app.recognition = recognition.Recognition(app, Held())
    frame = tk.Frame(tkroot)
    frame.pack()
    app.btns = {name: tk.Button(frame, text=name) for name in ("圖", "灰", "設定")}
    for b in app.btns.values():
        b.pack()
    app.btns["灰"].configure(state="disabled")
    yield app
    frame.destroy()
    tkroot.withdraw()


def test_辨識中登記的按鈕反灰_非圖片類照常_放行後恢復_原本反灰的維持(mini):
    rec, b = mini.recognition, mini.btns
    rec.register(b["圖"], b["灰"])
    got = []
    rec.start("測試", lambda: 42).then(got.append)
    assert rec.busy
    assert [str(b[n].cget("state")) for n in ("圖", "灰", "設定")] == \
        ["disabled", "disabled", "normal"]
    rec.executor.release()
    assert got == [42] and not rec.busy
    assert [str(b[n].cget("state")) for n in ("圖", "灰", "設定")] == \
        ["normal", "disabled", "normal"]


def test_辨識中改登記元件的可用與否_留到解除才套用(mini):
    rec, b = mini.recognition, mini.btns
    rec.register(b["圖"])
    rec.start("測試", lambda: None).then(lambda r: None)
    rec.want(b["圖"], False)
    assert str(b["圖"].cget("state")) == "disabled"
    rec.executor.release()
    assert str(b["圖"].cget("state")) == "disabled", "辨識中說要反灰的, 解除後照它"
    rec.want(b["圖"], True)
    assert str(b["圖"].cget("state")) == "normal"


def test_辨識中才開的對話框按鈕_登記時就反灰(mini):
    rec, b = mini.recognition, mini.btns
    rec.start("測試", lambda: None).then(lambda r: None)
    rec.register(b["設定"])
    assert str(b["設定"].cget("state")) == "disabled"
    rec.executor.release()
    assert str(b["設定"].cget("state")) == "normal"


def test_發起的對話框顯示辨識中_關閉類反灰_視窗X無效(mini):
    rec = mini.recognition
    dlg = tk.Toplevel(mini.root)
    status = tk.Label(dlg, text="")
    close = tk.Button(dlg, text="關閉", command=dlg.destroy)
    rec.register_window(dlg, status, (close,))
    dlg.update()
    rec.start("測試", lambda: None, origin=dlg).then(lambda r: None)
    assert status.cget("text") == recognition.BUSY_TEXT
    assert str(close.cget("state")) == "disabled"
    assert rec.holds(dlg)
    dlg.tk.call(dlg.protocol("WM_DELETE_WINDOW"))
    assert dlg.winfo_exists(), "做完前關不掉"
    rec.executor.release()
    assert status.cget("text") == "" and str(close.cget("state")) == "normal"
    assert not rec.holds(dlg)
    dlg.destroy()


def test_工作丟例外_辨識中解除_紀錄區說明(mini):
    rec, b = mini.recognition, mini.btns
    rec.register(b["圖"])

    def boom():
        raise ValueError("壞掉了")
    got = []
    rec.start("測試校準對", boom).then(got.append)
    rec.executor.release()
    assert got == [] and not rec.busy
    assert str(b["圖"].cget("state")) == "normal", "不卡在反灰"
    assert any(lvl == "error" and "測試校準對失敗" in m and "壞掉了" in m
               for lvl, m in mini.logged)


def test_多段辨識_收尾接下一段_最後一段做完才解除(mini):
    rec = mini.recognition
    seen = []

    def first(r):
        seen.append(r)
        job.chain(lambda: r + 1, seen.append)
    job = rec.start("截圖", lambda: 1)
    job.then(first)
    rec.executor.release()
    assert seen == [1, 2] and not rec.busy


def test_取消_結果作廢_做完才解除(mini):
    rec = mini.recognition
    got = []
    job = rec.start("截圖", lambda: 1)
    job.cancel()
    assert rec.busy, "背景那段還在跑: 辨識中不解除 (不會同時兩件)"
    job.then(got.append)
    rec.executor.release()
    assert got == [] and not rec.busy


def test_日誌每件一筆開始一筆結束_含耗時與結果(mini, monkeypatch):
    log = FileLog()
    monkeypatch.setattr(recognition.applog, "log", log)
    mini.recognition.start("測試校準對", lambda: 1).then(lambda r: None)
    mini.recognition.executor.release()
    [start] = log.of("recog.start")
    [end] = log.of("recog.end")
    assert start["title"] == "測試校準對"
    assert end["result"] == "ok" and float(end["seconds"]) >= 0


def test_真的開執行緒_背景跑工作_收尾回到介面執行緒(tkroot):
    app = _Mini(tkroot)
    rec = recognition.Recognition(app, recognition.Threaded())
    where = {}

    def work():
        where["work"] = threading.current_thread()
        time.sleep(0.05)
        return "ok"

    def done(r):
        where["done"] = threading.current_thread()
        where["result"] = r
    rec.start("測試", work).then(done)
    t0 = time.monotonic()
    while rec.busy and time.monotonic() - t0 < 5:
        tkroot.update()
        time.sleep(0.01)
    assert where["result"] == "ok"
    assert where["work"] is not threading.main_thread()
    assert where["done"] is threading.main_thread()


PAIR = ("圖示", "關閉鈕")
FB = ("標題左", "標題右")


@pytest.fixture
def flow_app(main_app, monkeypatch):
    a = main_app
    vision = Vision()
    a.hub.state = enginehub.READY
    a._engine_state_seen = enginehub.READY
    monkeypatch.setattr(a.hub, "ensure_template", vision.ensure_template)
    a.detector = vision
    for n in (*PAIR, *FB, "新左", "新右"):
        a.store.add(n, b"P")
    a.rebind_templates()
    a.refresh_templates()
    monkeypatch.setattr(app_mod.capture, "grab",
                        lambda region=None: (Screen((0, 0)), (0, 0)))
    monkeypatch.setattr(app_mod.time, "sleep", lambda s: None)
    a.flow_cal = calibration.make(list(PAIR), 1000.0)
    a.vision = vision
    vision.plan(PAIR[0], [(100, 50)])
    vision.plan(PAIR[1], [(1100, 50)])
    return a


def _in_settings(a, *actions):
    d = _Driver(a.root, SETTINGS)
    d.run(*actions, lambda dr: dr.press("關閉"))
    a.open_flow_settings()
    if d.error is not None:
        raise d.error


def test_測試校準對_清場中查詢0次_紀錄照舊(flow_app, monkeypatch):
    a = flow_app
    probe = ClearProbe(monkeypatch, a)
    a.test_calibration()
    assert probe.calls and probe.in_clear() == []
    assert any("測試校準對：目前畫面倍率 ×1.000" in m and "(100, 50)" in m for m in _logs(a))


def test_測試校準對_扣住時流程設定顯示辨識中_圖片類反灰_關閉無效_放行後解除(flow_app):
    a = flow_app
    h = held(a)
    seen = {}

    def press_test(dr):
        _row_button(dr.dlg, 0, "測試").invoke()
        dr._update()

    def look(dr):
        dlg = dr.dlg
        seen["status"] = [w.cget("text") for w in _all(dlg) if w.winfo_class() == "TLabel"]
        seen["image"] = [_disabled(_row_button(dlg, r, t))
                         for r, t in ((0, "設定…"), (0, "測試"), (1, "設定…"), (1, "測試"),
                                      (2, "測試"))]
        seen["other"] = [_disabled(_row_button(dlg, r, "清除")) for r in range(3)] + \
            [_disabled(_row_button(dlg, 2, "設定…"))]
        seen["close"] = _disabled(_btn_in(dlg, "關閉"))
        seen["main"] = [_disabled(_btn_in(a.root, t)) for t in ("存檔", "開檔", "新流程",
                                                               "截圖新增", "重截", "測試選取")]
        seen["run"] = _disabled(a.btn_run)
        seen["main_status"] = a.status_lbl.cget("text")
        dlg.event_generate("<Escape>")
        dlg.tk.call(dlg.protocol("WM_DELETE_WINDOW"))
        dr._update()
        seen["alive"] = dlg.winfo_exists()
        seen["logged_before"] = any("測試校準對：" in m for m in _logs(a))
        h.release()
        dr._update()
        seen["after"] = (_disabled(_btn_in(dlg, "關閉")), _disabled(_row_button(dlg, 0, "測試")),
                         _disabled(_btn_in(a.root, "存檔")))
    _in_settings(a, press_test, look)
    assert recognition.BUSY_TEXT in seen["status"]
    assert seen["image"] == [True] * 5
    assert seen["other"] == [False] * 4, "非圖片類照常可用"
    assert seen["close"] and seen["alive"]
    assert seen["main"] == [True] * 6 and seen["run"]
    assert seen["main_status"] != recognition.BUSY_TEXT, "辨識中…只在發起的視窗"
    assert not seen["logged_before"]
    assert seen["after"] == (False, False, False)
    assert any("測試校準對：目前畫面倍率" in m for m in _logs(a))


def test_測試校準對_量測丟例外_辨識中解除並寫紀錄(flow_app, monkeypatch):
    a = flow_app

    def boom(*a_, **k):
        raise RuntimeError("引擎炸了")
    monkeypatch.setattr(app_mod.calibration, "calibrate", boom)
    a.test_calibration()
    assert not a.recognition.busy
    assert not _disabled(_btn_in(a.root, "存檔"))
    assert any("測試校準對失敗" in m and "引擎炸了" in m for m in _logs(a))


def test_測試備用校準對_清場中查詢0次(flow_app, monkeypatch):
    a = flow_app
    a.flow_cal[calibration.FALLBACK_KEY] = calibration.make_fallback(list(FB), 500.0, (0, 0))
    a.vision.plan(FB[0], [(100, 10)])
    a.vision.plan(FB[1], [(600, 10)])
    probe = ClearProbe(monkeypatch, a)
    a.test_fallback_calibration()
    assert probe.calls and probe.in_clear() == []
    assert any("測試備用校準對：畫面倍率 ×1.000" in m for m in _logs(a))


def _pick_pair(monkeypatch, pair):
    monkeypatch.setattr(app_mod.ui_dialogs, "pick_cal_pair", lambda app, fallback=False: pair)


def test_設定校準對_清場中查詢0次_扣住時資料沒變_放行後才平移(flow_app, monkeypatch):
    a = flow_app
    a.store.set_pos(PAIR[0], [10, 20])
    _pick_pair(monkeypatch, ("新左", "新右"))
    a.vision.plan("新左", [(200, 100)])
    a.vision.plan("新右", [(700, 100)])
    probe = ClearProbe(monkeypatch, a)
    h = held(a)
    old = a.flow_cal
    a.designate_pair()
    assert a.recognition.busy
    assert a.flow_cal is old and a.store.pos_of(PAIR[0]) == [10, 20], "扣住時還沒變"
    h.release()
    assert probe.in_clear() == [] and probe.calls
    assert a.flow_cal["pair"] == ["新左", "新右"] and a.flow_cal["baseline"] == 500.0
    assert a.store.pos_of(PAIR[0]) == [-90, -30], "存下的座標跟著平移"
    assert not a.recognition.busy


def test_設定校準對_舊對量不到_拒絕_資料不動(flow_app, monkeypatch, no_real_dialogs):
    a = flow_app
    _pick_pair(monkeypatch, ("新左", "新右"))
    a.vision.plan(PAIR[1], [None])
    old = a.flow_cal
    a.designate_pair()
    assert a.flow_cal is old
    assert any(PAIR[1] in m for m in no_real_dialogs["warning"])


def test_設定備用校準對_清場中查詢0次_放行後才存(flow_app, monkeypatch):
    a = flow_app
    _pick_pair(monkeypatch, FB)
    a.vision.plan(FB[0], [(100, 10)])
    a.vision.plan(FB[1], [(600, 10)])
    probe = ClearProbe(monkeypatch, a)
    h = held(a)
    a.designate_fallback_pair()
    assert calibration.fallback_pair(a.flow_cal) is None
    h.release()
    assert probe.calls and probe.in_clear() == []
    fb = calibration.fallback_pair(a.flow_cal)
    assert fb["pair"] == list(FB) and fb["offset"] == [0, 40]


def test_校準圖載入失敗_收尾時提示_不進清場前擋(flow_app, monkeypatch, no_real_dialogs):
    a = flow_app
    a.vision.missing(PAIR[0])
    a.test_calibration()
    assert any("校準圖載入失敗" in m and PAIR[0] in m for m in no_real_dialogs["warning"])
    assert not a.recognition.busy


def test_引擎沒就緒_不進清場也不進辨識中(flow_app, monkeypatch, no_real_dialogs):
    a = flow_app
    a.hub.state = enginehub.LOADING
    probe = ClearProbe(monkeypatch, a)
    entered = []
    monkeypatch.setattr(ui_overlay, "screen_clear",
                        lambda root, extra=(): entered.append(1) or contextlib.nullcontext())
    a.test_calibration()
    assert entered == [] and probe.calls == []
    assert not a.recognition.busy
    assert no_real_dialogs["warning"], "照現在一樣 modal 提示"


def test_辨識中關掉主視窗_不出錯_結果不套用(flow_app, monkeypatch):
    a = flow_app
    _pick_pair(monkeypatch, ("新左", "新右"))
    a.vision.plan("新左", [(200, 100)])
    a.vision.plan("新右", [(700, 100)])
    h = held(a)
    old = a.flow_cal
    a.designate_pair()
    a.dirty = False
    a.on_close()
    assert not a.root.winfo_exists()
    h.release()
    assert not a.recognition.busy
    assert a.flow_cal is old, "結果不套用"


@pytest.mark.parametrize("row,text", [(0, "設定…"), (1, "設定…"), (1, "測試")])
def test_流程設定其他量測入口_扣住時也是辨識中_關閉無效(flow_app, monkeypatch, row, text):
    a = flow_app
    if row == 1 and text == "測試":
        a.flow_cal[calibration.FALLBACK_KEY] = calibration.make_fallback(list(FB), 500.0, (0, 0))
    _pick_pair(monkeypatch, ("新左", "新右") if row == 0 else FB)
    for n, xy in (("新左", (200, 100)), ("新右", (700, 100)),
                  (FB[0], (100, 10)), (FB[1], (600, 10))):
        a.vision.plan(n, [xy])
    h = held(a)
    seen = {}

    def press(dr):
        _row_button(dr.dlg, row, text).invoke()
        dr._update()

    def look(dr):
        seen["busy"] = recognition.BUSY_TEXT in [w.cget("text") for w in _all(dr.dlg)
                                                 if w.winfo_class() == "TLabel"]
        seen["close"] = _disabled(_btn_in(dr.dlg, "關閉"))
        seen["image"] = _disabled(_row_button(dr.dlg, 0, "測試"))
        dr.dlg.tk.call(dr.dlg.protocol("WM_DELETE_WINDOW"))
        dr._update()
        seen["alive"] = dr.dlg.winfo_exists()
        h.release()
        dr._update()
        seen["after"] = _disabled(_btn_in(dr.dlg, "關閉"))
    _in_settings(a, press, look)
    assert seen == {"busy": True, "close": True, "image": True, "alive": True, "after": False}

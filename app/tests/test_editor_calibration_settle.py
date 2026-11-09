"""編輯器 4 個校準鈕 (設定校準對、設定備用校準對、測試校準對、測試備用校準對) 等主畫面停穩再量."""
import threading

from harness import Screen

import app as app_mod
import calibration
import recognition
from test_calibration_ui import OLD, _editor
from test_fallback_calibration_ui import FB, _fb_editor

REGION = [50, 60, 1700, 500]
STOP = (REGION[0] - 2, REGION[1] + REGION[3] + 1)


def _record_grabs(monkeypatch, fake_cursor):
    """每次截圖前游標在哪 (截圖照搜尋範圍給)."""
    seen = []

    def grab(region=None):
        seen.append((tuple(region) if region else None, fake_cursor.cursor_pos()))
        org = (region[0], region[1]) if region else (0, 0)
        return Screen(org, (region[2], region[3]) if region else (1920, 1080)), org
    monkeypatch.setattr(app_mod.capture, "grab", grab)
    return seen


def _sleeps(monkeypatch, on_wait=None, ui_sleeps=None):
    """假時鐘: time.sleep 不真的睡, 推進 time.monotonic 並記下每次等多久;
    on_wait() 在每次 ≥0.5 秒的等待 (等停穩的每秒間隔) 時呼叫; ui_sleeps 收介面執行緒上的睡."""
    rec, now = [], [1000.0]

    def sleep(s):
        rec.append(s)
        if ui_sleeps is not None and threading.current_thread() is threading.main_thread():
            ui_sleeps.append(s)
        now[0] += s
        if on_wait is not None and s >= 0.5:
            on_wait()
    monkeypatch.setattr(app_mod.time, "sleep", sleep)
    monkeypatch.setattr(app_mod.time, "monotonic", lambda: now[0])
    return rec


def test_測試校準對_游標先移到停點_倉庫還在動時等停穩才報倍率(
        tkroot, monkeypatch, tmp_path, fake_cursor):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    a.scan_region = list(REGION)
    grabs = _record_grabs(monkeypatch, fake_cursor)
    sleeps = _sleeps(monkeypatch)
    vision.plan("舊圖示", [(100, 100)])
    vision.plan("舊關閉", [(1150, 100), (1250, 100), (1300, 100), (1300, 100)])
    a.test_calibration()
    assert any("×1.200" in m for m in a.logged), a.logged
    assert not any("×1.050" in m or "×1.150" in m for m in a.logged)
    assert len(grabs) == 4
    assert all(g == (tuple(REGION), STOP) for g in grabs), "每張都在搜尋範圍、游標在停點"
    assert sum(s for s in sleeps if s >= 1) == 3, "停穩前每 1 秒量一次"


def test_設定校準對_舊對已停穩新對還在動_等新對也停穩才定案(
        tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD),
                        pick=("圖示", "關閉"))
    vision.plan("舊圖示", [(100, 50)])
    vision.plan("舊關閉", [(1000, 50)])
    vision.plan("圖示", [(190, 95)])
    vision.plan("關閉", [(600, 95), (620, 95), (640, 95), (640, 95)])
    a.designate_pair()
    assert a.flow_cal == {"pair": ["圖示", "關閉"], "baseline": 500.0}, \
        "基準距離＝停穩後的 (640−190) ÷ 0.9"


def test_設定備用校準對_主對已停穩備用對還在動_等備用對也停穩才定案(
        tkroot, monkeypatch, tmp_path):
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    vision.plan("舊圖示", [(300, 200)])
    vision.plan("舊關閉", [(1200, 200)])
    vision.plan(FB[0], [(10, 20), (25, 20), (30, 20), (30, 20)])
    vision.plan(FB[1], [(1710, 20)])
    a.designate_fallback_pair()
    fb = calibration.fallback_pair(a.flow_cal)
    assert fb["offset"] == [300, 200], "(主基準點 − 停穩後的備用第一張中心) ÷ 0.9"
    assert abs(fb["baseline"] - 1680 / 0.9) < 0.1


def test_測試備用校準對_只量備用對_備用對停穩才報倍率(tkroot, monkeypatch, tmp_path):
    cal = dict(OLD)
    cal[calibration.FALLBACK_KEY] = calibration.make_fallback(list(FB), 500.0, (0, 0))
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=cal)
    vision.plan(FB[0], [(100, 10)])
    vision.plan(FB[1], [(500, 10), (550, 10), (600, 10), (600, 10)])
    a.test_fallback_calibration()
    assert any("×1.000" in m for m in a.logged), a.logged
    assert not any("×0.800" in m or "×0.900" in m for m in a.logged)
    assert not {"舊圖示", "舊關閉"} & set(vision.lookups), "主對不量, 也不看它停穩沒"


def test_等停穩的每秒等待不卡介面執行緒_介面事件照常處理(tkroot, monkeypatch, tmp_path):
    """背景每等 1 秒, 都要等到介面執行緒處理完一個排定的事件才放行; 介面被等待卡住就等不到."""
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=dict(OLD))
    a.recognition.executor = recognition.Threaded()
    vision.plan("舊圖示", [(100, 100)])
    vision.plan("舊關閉", [(1150, 100), (1200, 100), (1200, 100)])
    waited = []
    tick = threading.Event()
    timer = []

    def ui_event():
        tick.set()
        timer[:] = [tkroot.after(5, ui_event)]

    def per_second_wait():
        tick.clear()
        waited.append(tick.wait(2))
    ui_sleeps = []
    _sleeps(monkeypatch, per_second_wait, ui_sleeps)
    timer.append(tkroot.after(5, ui_event))
    try:
        a.test_calibration()
    finally:
        tkroot.after_cancel(timer[0])
    assert waited == [True, True], "每秒等待期間介面執行緒都處理了事件"
    assert ui_sleeps == [], "介面執行緒不睡 (清場生效的等待也在背景)"
    assert any("×1.100" in m for m in a.logged), a.logged
    assert not a.recognition.busy

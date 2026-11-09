"""measure_baseline.py 的離線自測: 假引擎、假截圖、假游標, 不碰真的螢幕和滑鼠.

用法: .venv/Scripts/python .scratch/calibration-settle/selftest_measure_baseline.py
"""
import math
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import measure_baseline as mb  # noqa: E402  (會把 app/、src/ 加進 sys.path)

import numpy as np  # noqa: E402

import calibration as calib  # noqa: E402
import enginehub  # noqa: E402
import flowfile  # noqa: E402
from automation import capture, win  # noqa: E402

MAIN = ["主畫面設定鈕", "主畫面倉庫"]
TITLE = ["標題列圖示", "標題列關閉鈕"]


def layout(warehouse_x, title_scale=1.0):
    """一張假畫面上四張圖的中心; warehouse_x 模擬視差緩動."""
    return {MAIN[0]: (100, 100), MAIN[1]: (warehouse_x, 1000),
            TITLE[0]: (60, 30), TITLE[1]: (60 + round(1868.0 * title_scale), 30)}


class Screens:
    """假截圖: 每張是小 numpy 陣列, 用物件身分查它的版面."""

    def __init__(self):
        self.layouts = []

    def make(self, lay):
        img = np.zeros((4, 4, 3), np.uint8)
        self.layouts.append((img, lay))
        return img

    def query(self, name, screen):
        lay = next(l for img, l in self.layouts if img is screen)
        if name in lay:
            x, y = lay[name]
            return types.SimpleNamespace(found=True, score=0.9, box=(x - 5, y - 5, 10, 10))
        return types.SimpleNamespace(found=False, score=0.12, box=None)


def flow_cal(name):
    return flowfile.read_flow(os.path.join(mb.ROOT, "flows", name))["calibration"]


def test_pick_pairs_real_flows():
    m, t = mb.pick_pairs(flow_cal("晚_繁中"))
    assert m["pair"] == MAIN and m["key"] == "calibration.baseline", m
    assert t["pair"] == TITLE and t["baseline"] == 1868.0, t
    m, t = mb.pick_pairs(flow_cal("早_繁中"))
    assert m["pair"] == MAIN and m["key"] == "calibration.fallback.baseline", m
    assert t["pair"] == TITLE, t
    for name in ("晚_簡中", "早_簡中"):
        m, t = mb.pick_pairs(flow_cal(name))
        assert mb.is_title_pair(t["pair"]) and not mb.is_title_pair(m["pair"])


def _run_no_move(lay):
    sc = Screens()
    blank = sc.make(lay)

    def grab():
        raise AssertionError("檢查沒過卻移動了游標")

    try:
        mb.run(flow_cal("晚_繁中"), sc.query, lambda: (blank, (0, 0)), grab,
               lambda s: None, say=lambda *a: None)
    except mb.Abort as e:
        return str(e)
    raise AssertionError("應該中止")


def test_no_game_aborts_before_cursor_moves():
    msg = _run_no_move({})
    assert "沒有移動游標" in msg, msg


def test_only_title_visible_aborts_before_cursor_moves():
    lay = layout(1800)
    del lay[MAIN[1]]
    msg = _run_no_move(lay)
    assert MAIN[1] in msg and "主畫面那一對" in msg, msg


def test_settles_and_computes_baseline():
    sc = Screens()
    pre = sc.make(layout(1850, 1.132))
    seq = [sc.make(layout(x, 1.132)) for x in (1860, 1840, 1832, 1832)]
    grabs, waits = [], []

    def grab():
        grabs.append(1)
        return seq[len(grabs) - 1], (0, 0)

    r, s = mb.run(flow_cal("晚_繁中"), sc.query, lambda: (pre, (0, 0)), grab,
                  waits.append, say=lambda *a: None)
    assert r["settle"] == "stable" and r["reads"] == 4 and len(waits) == 3, r
    assert s.screen is seq[3]
    k = round(1868.0 * 1.132) / 1868.0
    assert r["title_pair"]["scale"] == round(k, 4), r
    assert r["main_screen_pair"]["settled_distance"] == round(math.hypot(1732, 900), 2), r
    assert r["new_baseline"] == round(math.hypot(1732, 900) / k, 1), r
    assert r["main_screen_pair"]["flow_key"] == "calibration.baseline"


def test_timeout_flagged():
    sc = Screens()
    pre = sc.make(layout(1800))
    n = [0]

    def grab():
        n[0] += 1
        return sc.make(layout(1800 + 5 * n[0])), (0, 0)

    r, _ = mb.run(flow_cal("早_繁中"), sc.query, lambda: (pre, (0, 0)), grab,
                  lambda s: None, say=lambda *a: None)
    assert r["settle"] == "timeout" and r["reads"] == calib.SETTLE_READS, r
    assert r["main_screen_pair"]["flow_key"] == "calibration.fallback.baseline"


class FakeHub:
    def __init__(self, query):
        self.query = query
        self.ready, self.coarse_only, self.error = True, False, None

    def load(self):
        pass

    def bind(self, *a):
        pass

    def preload(self, names):
        pass


def _patched_main(sc, grabs, argv):
    """用假引擎、假截圖、假游標跑 main(); 回傳 (SystemExit 訊息或 None, park 呼叫)."""
    parks = []
    saved = (enginehub.EngineHub, capture.grab, win.park, win.cursor_pos, win.set_dpi_aware)
    enginehub.EngineHub = lambda: FakeHub(sc.query)
    capture.grab = lambda region=None: (grabs.pop(0), (0, 0))
    win.park = lambda x, y: parks.append((x, y))
    win.cursor_pos = lambda: parks[-1] if parks else (777, 333)
    win.set_dpi_aware = lambda: None
    try:
        mb.main(argv)
        return None, parks
    except SystemExit as e:
        return str(e.code), parks
    finally:
        (enginehub.EngineHub, capture.grab, win.park, win.cursor_pos,
         win.set_dpi_aware) = saved


def test_main_no_game_never_parks():
    sc = Screens()
    msg, parks = _patched_main(sc, [sc.make({})], ["晚_繁中", "--delay", "0"])
    assert msg and "中止" in msg and "沒有移動游標" in msg, msg
    assert parks == [], parks


def test_main_success_parks_like_runner_and_restores():
    sc = Screens()
    grabs = [sc.make(layout(x)) for x in (1850, 1845, 1843, 1843)]
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "r.json")
        msg, parks = _patched_main(sc, grabs, ["早_繁中", "--delay", "0", "--out", out])
        assert msg is None, msg
        assert os.path.isfile(out)
    region = [-8, 0, 1928, 1034]
    x1, y1, x2, y2 = win.monitor_rect_at(region[0] + region[2] / 2, region[1] + region[3] / 2)
    stop = (min(max(region[0] - 2, x1), x2 - 1), min(max(region[1] + region[3] + 1, y1), y2 - 1))
    assert parks[0] == stop and parks[-1] == (777, 333), parks


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"全部通過（{len(tests)}）")

"""`校準`模組純邏輯: 流程層級的校準資料、倍率貼齊、量測 (ADR 0009).

詞彙見 app/GLOSSARY.md「尺度與畫面倍率」; 量測照 harness 的假 query 直接餵。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calibration  # noqa: E402
from harness import Vision  # noqa: E402


# ---------- 流程層級的校準資料 ----------

def test_流程資料上的校準對():
    cal = {"pair": ["圖示", "關閉"], "baseline": 1696.0}
    assert calibration.flow_pair({"calibration": cal}) == cal
    assert calibration.flow_pair({}) is None
    assert calibration.flow_pair(None) is None


def test_不成形的校準資料視同沒有校準對():
    for bad in ({"pair": ["a"], "baseline": 100.0},
                {"pair": ["a", ""], "baseline": 100.0},
                {"pair": ["a", "b"], "baseline": 0},
                {"pair": ["a", "b"], "baseline": "x"},
                {"pair": "ab", "baseline": 100.0}, "garbage"):
        assert calibration.flow_pair({"calibration": bad}) is None, bad


def test_組一份校準資料():
    assert calibration.make(("a", "b"), 300) == {"pair": ["a", "b"],
                                                  "baseline": 300.0}


def test_倍率貼齊_量測抖動視同1():
    """在建立流程時的視窗大小下執行, 量到 0.997 也要是 1 (座標原樣、網格對準)."""
    assert calibration.snap_identity(0.997) == 1.0
    assert calibration.snap_identity(1.004) == 1.0
    assert calibration.snap_identity(1.25) == 1.25
    assert calibration.snap_identity(0.98) == 0.98


# ---------- 量測 (票 02) ----------

def _grab(vision, region=None):
    screen, _ = vision.grab(region)
    return screen


def test_量測回傳兩匹配框中心的直線距離():
    v = Vision()
    v.plan("a", [(100, 100)])
    v.plan("b", [(400, 500)])  # 距離 = hypot(300, 400) = 500
    m = calibration.measure(v.query, _grab(v), ("a", "b"))
    dist, missing = m.distance, m.missing
    assert missing == []
    assert dist == 500.0


def test_量測失敗指明哪一張沒找到():
    v = Vision()
    v.plan("a", [None])
    v.plan("b", [(400, 500)])
    m = calibration.measure(v.query, _grab(v), ("a", "b"))
    dist, missing = m.distance, m.missing
    assert dist is None
    assert missing == ["a"]


def test_量測兩張都沒找到全部列出():
    v = Vision()
    v.plan("a", [None])
    v.plan("b", [None])
    m = calibration.measure(v.query, _grab(v), ("a", "b"))
    dist, missing = m.distance, m.missing
    assert dist is None
    assert missing == ["a", "b"]


def test_量測在搜尋範圍內找時距離不受範圍原點影響():
    """兩張圖同一次擷取, 範圍原點在距離上互相抵銷."""
    v = Vision()
    v.plan("a", [(300, 300)])
    v.plan("b", [(600, 700)])
    dist = calibration.measure(v.query, _grab(v, [200, 250, 800, 600]),
                               ("a", "b")).distance
    assert dist == 500.0


def test_量測記下兩張圖的中心與分數_重疊時不能當比例尺():
    v = Vision()
    v.plan("a", [(100, 100)])
    v.plan("b", [(100, 100)])
    m = calibration.measure(v.query, _grab(v), ("a", "b"))
    assert m.centers == {"a": (100, 100), "b": (100, 100)}
    assert m.scores == {"a": 0.99, "b": 0.99}
    assert m.too_close


def test_量測得出的倍率貼齊1():
    v = Vision()
    v.plan("a", [(0, 0)])
    v.plan("b", [(999, 0)])
    m = calibration.measure(v.query, _grab(v), ("a", "b"))
    assert m.scale(1000.0) == 1.0
    v.plan("b", [(900, 0)])
    assert calibration.measure(v.query, _grab(v), ("a", "b")).scale(1000.0) == 0.9

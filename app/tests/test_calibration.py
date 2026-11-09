import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calibration  # noqa: E402
from harness import Vision  # noqa: E402


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
    assert calibration.snap_identity(0.997) == 1.0
    assert calibration.snap_identity(1.004) == 1.0
    assert calibration.snap_identity(1.25) == 1.25
    assert calibration.snap_identity(0.98) == 0.98


def _grab(vision, region=None):
    screen, _ = vision.grab(region)
    return screen


def test_量測回傳兩匹配框中心的直線距離():
    v = Vision()
    v.plan("a", [(100, 100)])
    v.plan("b", [(400, 500)])
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


class _SlowRecognition:
    """假時鐘＋每次辨識花 cost 秒 (辨識會推進時鐘); 預設每次量到的位置都不同＝一直沒停穩."""

    def __init__(self, cost, steady=False):
        self.t, self.cost, self.steady, self.grab_times = 0.0, cost, steady, []

    def now(self):
        return self.t

    def wait(self, s):
        self.t += max(0.0, s)

    def grab(self):
        self.grab_times.append(self.t)
        return None, (0, 0)

    def read(self, screen, origin):
        self.t += self.cost
        n = len(self.grab_times)
        return calibration.Reading(n, {"倉庫": (0 if self.steady else 100 * n, 0)})

    def settle(self):
        return calibration.settle(self.grab, self.read, self.wait, self.now)


def test_停穩照截止時間量_辨識花的時間不拉長每秒一次的節奏():
    fake = _SlowRecognition(0.4)
    s = fake.settle()
    assert s.timed_out and s.reads == 11
    assert fake.grab_times == pytest.approx([float(i) for i in range(11)])
    assert fake.t == pytest.approx(10.4), "上限＝10 秒＋最後一次辨識"
    assert s.elapsed == pytest.approx(10.0)


def test_辨識比間隔還慢_不補量追趕_超過第10秒就不再量():
    fake = _SlowRecognition(1.5)
    s = fake.settle()
    assert s.timed_out
    assert fake.grab_times == pytest.approx([0.0, 1.5, 3.0, 4.5, 6.0, 7.5, 9.0])
    assert s.reads == 7 and s.value == 7, "用最後一次"
    assert fake.t == pytest.approx(10.5), "最多約 10 秒＋最後一次辨識"


def test_兩次一致就定案_第1秒那次():
    fake = _SlowRecognition(0.3, steady=True)
    s = fake.settle()
    assert not s.timed_out and s.reads == 2 and s.value == 2
    assert fake.grab_times == pytest.approx([0.0, 1.0])

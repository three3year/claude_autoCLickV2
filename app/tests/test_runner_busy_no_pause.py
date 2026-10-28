import pytest

from harness import branch_end, branch_or, branch_start, click, find, here, tgt

AT = (500, 400)
BUSY_AT = (960, 1000)
BUSY = tgt("busy", within=[640, 720, 640, 360])


def span(harness):
    times = harness.vision.grab_times[1:]
    return times[-1] - times[0]


def records(harness, event="find.target"):
    return harness.filelog.of(event)


def busy_lookups(harness):
    return harness.lookups().count("busy")


def _branch(timeout=5):
    return [branch_start(),
            find("a", timeout=timeout, interval=0.5, on_fail="skip"),
            branch_or(),
            find("b", timeout=timeout, interval=0.5, on_fail="skip"),
            branch_end()]


def test_分岔_忙碌期間照原本時間逾時_不查忙碌指示(harness):
    harness.vision.plan("a", [None])
    harness.vision.plan("b", [None])
    harness.vision.plan("busy", [BUSY_AT])
    r = harness.run(_branch(), busy=BUSY)
    assert r.ended == "done" and harness.clicks() == []
    assert span(harness) == pytest.approx(5.0, abs=0.1)
    assert "busy" not in harness.lookups()
    recs = [x for x in records(harness) if x["role"] == "branch"]
    assert len(recs) == 2 and all("busy_pause" not in x for x in recs)


def test_分岔_忙碌結束後才出現的條件_已逾時就挑不到(harness):
    harness.vision.plan("a", [None])
    harness.vision.plan("b", [None] * 10 + [AT])
    harness.vision.plan("busy", [BUSY_AT])
    r = harness.run(_branch(timeout=3), busy=BUSY)
    assert r.ended == "done"
    assert harness.clicks() == [], "沒有忙碌暫停: 3s 就全逾時跳過"


def test_一般找圖_忙碌不延後逾時(harness):
    harness.vision.plan("a", [None] * 12 + [AT])
    harness.vision.plan("busy", [BUSY_AT])
    r = harness.run([find("a", timeout=2, interval=0.5, on_fail="stop")],
                    busy=BUSY)
    assert r.ended == "error" and harness.clicks() == []
    assert span(harness) == pytest.approx(2.0, abs=0.1)
    [rec] = records(harness)
    assert rec["result"] == "timeout" and "busy_pause" not in rec


def test_找圖等待完全不查忙碌指示(harness):
    harness.vision.plan("a", [None, None, AT])
    harness.vision.plan("busy", [BUSY_AT])
    harness.run([find("a", interval=0.5)], busy=BUSY)
    assert harness.lookups() == ["a", "a", "a"]


def test_沒設忙碌指示_時間點不變也不查(harness):
    harness.vision.plan("a", [None])
    harness.vision.plan("busy", [BUSY_AT])
    harness.run([find("a", timeout=2, interval=0.5, on_fail="skip")])
    assert span(harness) == pytest.approx(2.0, abs=0.1)
    assert "busy" not in harness.lookups()


def test_生效確認_忙碌不延後逾時_補做門照舊每輪查一次(harness):
    harness.vision.plan("a", [AT])
    harness.vision.plan("ok", [None] * 10 + [(300, 300)])
    harness.vision.plan("busy", [BUSY_AT])
    r = harness.run([find("a", confirm="appear", confirm_target=tgt("ok"),
                          timeout=1.5, interval=0.2, on_fail="skip"),
                     click(9, 9)], busy=BUSY)
    assert r.ended == "done"
    assert harness.clicks() == [AT, (509, 409)], "一直忙碌: 不補做; 1.5s 逾時跳過"
    [rec] = [x for x in records(harness) if x["role"] == "confirm_appear"]
    assert rec["result"] == "timeout" and "busy_pause" not in rec
    assert busy_lookups(harness) == rec["polls"] == 8
    [find_rec] = [x for x in records(harness) if x["role"] == "find"]
    assert "busy_pause" not in find_rec


def test_生效確認_補做門用同一張截圖查_沒忙碌就照間隔補做(harness):
    harness.vision.plan("a", [AT] * 6 + [None])
    harness.vision.plan("busy", [None])
    harness.run([find("a", confirm="gone", interval=0.2)], busy=BUSY)
    assert busy_lookups(harness) == 5, "沒達成的 5 輪各查一次"
    assert harness.clicks() == [AT, AT], "1.0s 補做一次 (門檻照舊)"


def test_座標點擊的生效確認_忙碌不延後逾時_日誌沒有暫停欄位(harness):
    harness.vision.plan("ok", [None])
    harness.vision.plan("busy", [BUSY_AT])
    r = harness.run([here(), click(9, 9, confirm="appear", confirm_target=tgt("ok"),
                           timeout=1.5, interval=0.2, on_fail="skip"),
                     click(1, 1)], busy=BUSY)
    assert r.ended == "done" and harness.clicks() == [(9, 9), (1, 1)]
    [rec] = records(harness, "input.confirm")
    assert rec["result"] == "timeout" and "busy_pause" not in rec
    assert "busy_delay" in rec, "補做被忙碌延後的秒數照舊記"


GONE = dict(type="wait_gone", interval=0.5, timeout=2, on_fail="stop")


def test_等待消失_忙碌不延後逾時(harness):
    harness.vision.plan("x", [AT] * 8 + [None])
    harness.vision.plan("busy", [BUSY_AT])
    r = harness.run([find("x", **GONE), click(9, 9)], busy=BUSY)
    assert r.ended == "error" and harness.clicks() == []
    [rec] = records(harness)
    assert rec["result"] == "not_gone" and "busy_pause" not in rec
    assert "busy" not in harness.lookups()


def test_等待消失的目標就是忙碌指示_只查步驟自己那一次(harness):
    harness.vision.plan("busy", [BUSY_AT] * 3 + [None])
    r = harness.run([find("busy", target={"within": BUSY["within"]}, **GONE),
                     click(9, 9)], busy=BUSY)
    assert r.ended == "done" and harness.clicks() == [(969, 1009)]
    [rec] = records(harness)
    assert rec["result"] == "gone"
    assert harness.lookups() == ["busy"] * 4, "每輪只有步驟自己那一次查詢"

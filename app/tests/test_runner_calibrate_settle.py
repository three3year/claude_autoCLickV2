"""執行開頭的`校準`等主畫面停穩: 避開游標後每 1 秒量一次, 連續兩次一致才採用."""
import pytest

from harness import cal, click, find

PAIR = ("標題列圖示", "倉庫")


def run(harness, steps, calibration=None, **kw):
    return harness.run(steps, calibration=calibration or cal(PAIR, 1000.0),
                       **kw)


def first_input_delay(harness):
    """從開頭校準第一次截圖到第一個輸入的虛擬時間."""
    [(_, t)] = harness.input_times()[:1]
    return t - harness.vision.grab_times[0]


def test_倉庫逐次收斂_用停穩那次的倍率_落點照那個倍率(harness):
    harness.vision.plan(PAIR[0], [(100, 40)])
    harness.vision.plan(PAIR[1], [(1010, 40), (1030, 40), (1050, 40),
                                  (1050, 40)])
    harness.vision.plan("a", [(500, 400)])
    r = run(harness, [find("a", type="find"), click(100, 0)])
    assert r.ended == "done"
    assert harness.clicks() == [(595, 400)]
    [rec] = harness.filelog.of("calibrate")
    assert rec["scale"] == "0.950"
    assert rec["settle"] == "stable" and rec["reads"] == 4


def test_前兩次就一致_只多等1秒(harness):
    harness.vision.plan(PAIR[0], [(100, 40)])
    harness.vision.plan(PAIR[1], [(1100, 40)])
    harness.vision.plan("a", [(500, 400)])
    r = run(harness, [find("a", confirm="none")])
    assert r.ended == "done"
    assert first_input_delay(harness) == pytest.approx(1.0, abs=0.1)
    [rec] = harness.filelog.of("calibrate")
    assert rec["settle"] == "stable" and rec["reads"] == 2


def test_一直不一致_第10秒後用最後一次_紀錄寫timeout_訊息有警告(harness):
    harness.vision.plan(PAIR[0], [(100, 40)])
    harness.vision.plan(PAIR[1], [(1100 + 5 * i, 40) for i in range(11)]
                        + [(2000, 40)])
    harness.vision.plan("a", [(500, 400)])
    r = run(harness, [find("a", type="find"), click(100, 0)])
    assert r.ended == "done"
    assert harness.clicks() == [(605, 400)], "倍率 ×1.050 (第 11 次的值)"
    assert first_input_delay(harness) == pytest.approx(10.0, abs=0.1)
    [rec] = harness.filelog.of("calibrate")
    assert rec["scale"] == "1.050"
    assert rec["settle"] == "timeout" and rec["reads"] == 11
    assert any("沒停穩" in m for m in harness.logs(r))


def test_等待停穩期間按停止_流程停下_沒有任何點擊(harness):
    harness.vision.plan(PAIR[0], [(100, 40)])
    harness.vision.plan(PAIR[1], [(1000 + 5 * i, 40) for i in range(11)])
    r = harness.make_runner()
    harness.runner = r
    harness.clock.on_sleep = lambda n: r.stop() if n == 5 else None
    harness.start(r, [click(1, 1)], calibration=cal(PAIR, 1000.0))
    r._thread.join(10)
    assert not r._thread.is_alive()
    assert r.ended == "stopped"
    assert harness.kinds() == []
    assert harness.clock.t - harness.vision.grab_times[0] < 1.0, "立刻停下"


FB = ("設定鈕", "倉庫")


def with_fallback():
    c = cal(PAIR, 1000.0)
    c["fallback"] = {"pair": list(FB), "baseline": 500.0, "offset": [0, 0]}
    return c


def test_第一次主對缺圖改用備用_第二次主對找到_不算一致_繼續量(harness):
    harness.vision.plan(PAIR[0], [None, (100, 40)])
    harness.vision.plan(PAIR[1], [(1100, 40)])
    harness.vision.plan(FB[0], [(600, 40)])
    r = run(harness, [click(1, 1)], calibration=with_fallback())
    assert r.ended == "done"
    [rec] = harness.filelog.of("calibrate")
    assert rec["reads"] == 3 and rec["settle"] == "stable"
    assert "used" not in rec, "定案用主對"
    assert "備用校準對" not in harness.log_text(r)


def test_兩次都缺同一張圖_不執行_說明原因(harness):
    harness.vision.plan(PAIR[0], [(100, 40)])
    harness.vision.plan(PAIR[1], [None])
    r = run(harness, [click(1, 1)])
    assert r.ended == "error" and harness.kinds() == []
    text = harness.log_text(r)
    assert "找不到校準圖" in text and PAIR[1] in text
    [rec] = harness.filelog.of("calibrate")
    assert rec["result"] == "missing" and rec["missing"] == PAIR[1]
    assert rec["settle"] == "stable" and rec["reads"] == 2


def test_標題列對第一次就穩定_總共量兩次(harness):
    title = ("標題列圖示", "關閉鈕")
    harness.vision.plan(title[0], [(100, 10)])
    harness.vision.plan(title[1], [(1100, 10)])
    run(harness, [click(1, 1)], calibration=cal(title, 1000.0))
    assert len(harness.vision.grabs) == 2
    [rec] = harness.filelog.of("calibrate")
    assert rec["reads"] == 2

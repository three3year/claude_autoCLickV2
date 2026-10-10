"""`備用校準對` (scale-range 票 07): 存檔、量測純函式、執行器.

主對找不到時改量備用對, 座標基準點＝備用第一張中心 + 偏移×倍率 (偏移是「備用第一張
中心 → 座標基準點」的流程尺度向量), 所以存下的座標一律仍相對同一個基準點;
主備都找不到才不執行並列出兩組各缺哪張。沒設備用對的行為與現在完全相同。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calibration  # noqa: E402
import flowfile  # noqa: E402
from automation import flowfmt  # noqa: E402
from harness import Vision, cal, click, find, tgt  # noqa: E402

MAIN = ("遊戲左上", "遊戲右下")
FB = ("標題列圖示", "關閉鈕")


def with_fallback(baseline=1000.0, fb_baseline=1868.0, offset=(100, 50)):
    """主對 + 備用對的校準資料."""
    c = cal(MAIN, baseline)
    c[calibration.FALLBACK_KEY] = calibration.make_fallback(FB, fb_baseline, offset)
    return c


# ---------- 存檔格式 ----------

def test_備用組的形狀():
    fb = calibration.make_fallback(FB, 1868, (100, 50))
    assert fb == {"pair": list(FB), "baseline": 1868.0, "offset": [100, 50]}
    assert calibration.fallback_pair(with_fallback()) == fb
    assert calibration.fallback_pair(cal()) is None
    assert calibration.fallback_pair(None) is None


def test_備用組不成形當沒有並說明():
    for bad in ({"pair": ["a"], "baseline": 1.0, "offset": [0, 0]},
                {"pair": ["a", "b"], "baseline": 0, "offset": [0, 0]},
                {"pair": ["a", "b"], "baseline": 1.0},
                {"pair": ["a", "b"], "baseline": 1.0, "offset": [1]},
                {"pair": ["a", "b"], "baseline": 1.0, "offset": ["x", 0]},
                "garbage"):
        c = cal()
        c[calibration.FALLBACK_KEY] = bad
        assert calibration.fallback_pair(c) is None, bad
        assert calibration.fallback_problem(c), bad
    assert calibration.fallback_problem(cal()) is None
    assert calibration.fallback_problem(with_fallback()) is None
    assert calibration.valid(with_fallback()), "主對照常成形"


def test_沒有備用組的存檔一字不差(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    data = {"steps": [find("a")], flowfmt.COORD_SPACE: flowfmt.ANCHOR,
            calibration.FLOW_KEY: cal(MAIN)}
    flowfile.write(path, data, {"a": b"A", MAIN[0]: b"1", MAIN[1]: b"2"})
    r = flowfile.read(path)
    assert r["data"][calibration.FLOW_KEY] == cal(MAIN)
    assert calibration.FALLBACK_KEY not in r["data"][calibration.FLOW_KEY]
    assert r["data"]["flowFormat"] == flowfile.FORMAT, "格式版本不升"


def test_備用組存檔往返_備用對的圖也進存檔(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    data = {"steps": [find("a")], flowfmt.COORD_SPACE: flowfmt.ANCHOR,
            calibration.FLOW_KEY: with_fallback()}
    images = {"a": b"A", MAIN[0]: b"1", MAIN[1]: b"2", FB[0]: b"3", FB[1]: b"4",
              "沒人用": b"U"}
    assert flowfile.write(path, data, images) == []
    assert flowfile.template_names(path) == sorted(["a", *MAIN, *FB])
    r = flowfile.read(path)
    assert calibration.fallback_pair(r["data"][calibration.FLOW_KEY]) == \
        calibration.make_fallback(FB, 1868.0, (100, 50))
    assert flowfile.flow_refs(data) == sorted(["a", *MAIN, *FB])


def test_改名跟著改備用對():
    data = {"steps": [], calibration.FLOW_KEY: with_fallback()}
    assert flowfile.rename_flow_refs(data, FB[1], "關閉鈕2") == 1
    assert calibration.fallback_pair(data[calibration.FLOW_KEY])["pair"] == \
        [FB[0], "關閉鈕2"]


# ---------- 量測純函式 ----------

def _grab(v, region=None):
    screen, org = v.grab(region)
    return screen, org


def _place(v, names, a, b):
    v.plan(names[0], [a])
    v.plan(names[1], [b])


def test_主對找得到_不碰備用對():
    v = Vision()
    _place(v, MAIN, (300, 200), (1100, 200))    # 800 ÷ 1000 = 0.8
    _place(v, FB, (20, 20), (1500, 20))
    c = calibration.calibrate(v.query, *_grab(v), with_fallback())
    assert c.ok and c.used == "main"
    assert (c.scale, c.anchor) == (0.8, (300, 200))
    assert c.pair == list(MAIN)
    assert not any(n in v.lookups for n in FB)


def test_主對缺一張_改量備用對_基準點換回同一點():
    v = Vision()
    _place(v, MAIN, None, (1100, 200))
    # 備用距離 1494.4 ÷ 1868 = 0.8; 基準點＝備用第一張 (20,20) + 偏移 (100,50)×0.8 = (100,60)
    _place(v, FB, (20, 20), (1514, 20))
    c = calibration.calibrate(v.query, *_grab(v), with_fallback())
    assert c.ok and c.used == "fallback"
    assert c.pair == list(FB)
    assert abs(c.scale - 0.8) < 0.001
    assert c.anchor == (100, 60)
    assert c.main.missing == [MAIN[0]]
    assert c.baseline == 1868.0


def test_偏移為零時與主對同點():
    """備用第一張就在主對第一張的位置 (偏移 0,0): 兩組量出同一個基準點."""
    both = with_fallback(fb_baseline=1500.0, offset=(0, 0))
    v = Vision()
    _place(v, MAIN, (300, 200), (1300, 200))
    _place(v, FB, (300, 200), (1800, 200))
    c_main = calibration.calibrate(v.query, *_grab(v), both)
    v2 = Vision()
    _place(v2, MAIN, None, (1300, 200))
    _place(v2, FB, (300, 200), (1800, 200))
    c_fb = calibration.calibrate(v2.query, *_grab(v2), both)
    assert (c_main.used, c_fb.used) == ("main", "fallback")
    assert c_main.anchor == c_fb.anchor == (300, 200)
    assert c_main.scale == c_fb.scale == 1.0


def test_主備都缺_列出兩組各缺哪張():
    v = Vision()
    _place(v, MAIN, None, (1100, 200))
    _place(v, FB, (20, 20), None)
    c = calibration.calibrate(v.query, *_grab(v), with_fallback())
    assert not c.ok and c.problem == "missing"
    text = c.describe()
    assert MAIN[0] in text and FB[1] in text
    assert "備用" in text
    assert c.anchor is None and c.scale is None


def test_備用對兩張重疊_不能當比例尺():
    v = Vision()
    _place(v, MAIN, None, (1100, 200))
    _place(v, FB, (20, 20), (20, 20))
    c = calibration.calibrate(v.query, *_grab(v), with_fallback())
    assert not c.ok and c.problem == "too_close"


def test_沒設備用對_主對缺一張照舊失敗():
    v = Vision()
    _place(v, MAIN, None, (1100, 200))
    c = calibration.calibrate(v.query, *_grab(v), cal(MAIN))
    assert not c.ok and c.used == "main"
    assert "備用" not in c.describe()


def test_備用對的倍率同樣貼齊1():
    v = Vision()
    _place(v, MAIN, None, (1100, 200))
    _place(v, FB, (20, 20), (1887, 20))     # 1867/1868: 抖動
    c = calibration.calibrate(v.query, *_grab(v), with_fallback())
    assert c.scale == 1.0
    assert c.anchor == (120, 70)


def test_編輯器設定備用對的偏移換算_與量測互逆():
    """設定時: 偏移＝(主基準點 − 備用第一張中心) ÷ 倍率; 量測時再乘回去."""
    anchor, fb_first, k = (190, 95), (10, 15), 0.9
    offset = calibration.fallback_offset(anchor, fb_first, k)
    assert offset == (200, 89)
    assert calibration.fallback_anchor(fb_first, offset, k) == (190, 95)


# ---------- 執行器 ----------

def test_執行器主對找不到改用備用對_印警告照跑_固定矩形落點對(harness):
    harness.vision.plan(MAIN[0], [None])
    harness.vision.plan(MAIN[1], [(1100, 200)])
    harness.vision.plan(FB[0], [(20, 20)])
    harness.vision.plan(FB[1], [(1514, 20)])     # ×0.8, 基準點 (100,60)
    rect = {"limit": {"kind": "rect", "x": 100, "y": 50, "w": 300, "h": 120}}
    harness.vision.plan("a", [(300, 160)])
    r = harness.run([find("a", target=rect), click(10, 20)],
                    calibration=with_fallback())
    assert r.ended == "done"
    text = harness.log_text(r)
    assert "主校準對找不到" in text and MAIN[0] in text
    assert "改用備用校準對" in text
    [rec] = harness.filelog.of("calibrate")
    assert rec["result"] == "ok" and rec["used"] == "fallback"
    assert rec["pair"] == ",".join(FB) and MAIN[0] in rec["main_missing"]
    [ft] = harness.filelog.of("find.target")
    assert ft["limit"] == "(180,100,240,96)", "基準點 (100,60) + 偏移×0.8"
    assert harness.clicks()[-1] == (308, 176), "相對找到的位置 + 偏移×0.8"


def test_執行器主對找得到_不碰備用對_紀錄不標備用(harness):
    harness.vision.plan(MAIN[0], [(300, 200)])
    harness.vision.plan(MAIN[1], [(1100, 200)])
    harness.vision.plan(FB[0], [(20, 20)])
    harness.vision.plan(FB[1], [(1514, 20)])
    r = harness.run([click(1, 1)], calibration=with_fallback())
    assert r.ended == "done"
    assert "備用" not in harness.log_text(r)
    [rec] = harness.filelog.of("calibrate")
    assert "used" not in rec
    assert not any(n in harness.vision.lookups for n in FB)


def test_執行器主備皆無_不送任何輸入_訊息列出兩組各缺哪張(harness):
    harness.vision.plan(MAIN[0], [None])
    harness.vision.plan(MAIN[1], [(1100, 200)])
    harness.vision.plan(FB[0], [None])
    harness.vision.plan(FB[1], [(1514, 20)])
    r = harness.run([click(1, 1), find("a")], calibration=with_fallback())
    assert r.ended == "error"
    assert harness.kinds() == []
    text = harness.log_text(r)
    assert MAIN[0] in text and FB[0] in text
    [rec] = harness.filelog.of("calibrate")
    assert rec["result"] == "missing"
    assert MAIN[0] in rec["missing"] and FB[0] in rec["fallback_missing"]


def test_備用對列入範本預載(harness):
    harness.vision.plan(MAIN[0], [(300, 200)])
    harness.vision.plan(MAIN[1], [(1100, 200)])
    harness.run([find("a")], calibration=with_fallback())
    assert harness.vision.preloads == [["a", *MAIN, *FB]]


def test_用備用對時找圖的預期尺度是備用對量到的倍率(harness):
    harness.vision.plan(MAIN[0], [None])
    harness.vision.plan(MAIN[1], [(1100, 200)])
    harness.vision.plan(FB[0], [(20, 20)])
    harness.vision.plan(FB[1], [(1514, 20)])
    harness.vision.plan("a", [(300, 160)])
    harness.run([find("a", confirm="appear", confirmTarget=tgt("ok"), interval=0.1)],
                calibration=with_fallback())
    assert all(abs(s - 0.8) < 0.001 for _, s in harness.expected_scales())

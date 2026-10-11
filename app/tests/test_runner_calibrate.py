"""執行開頭自動`校準` (flow-scale 票 02, ADR 0009).

流程自帶`校準對`與`基準距離`; 執行器開頭在畫面上用全範圍找校準對兩張圖,
中心距離 ÷ 基準距離＝這次執行的`畫面倍率`。之後每個座標乘上它、每次找圖把它
當`預期尺度`交給偵測器。任一張找不到或沒有校準資料＝一個輸入都不送。
斷言對象: 送出的輸入、每次查詢帶的預期尺度、執行紀錄與檔案日誌。
"""
import pytest

from harness import cal, click, drag, find, tgt

PAIR = ("標題列圖示", "關閉鈕")


def place(harness, left, right):
    harness.vision.plan(PAIR[0], [left])
    harness.vision.plan(PAIR[1], [right])


def run(harness, steps, calibration=None, **kw):
    return harness.run(steps, calibration=calibration or cal(PAIR, 1000.0),
                       **kw)


def test_兩張都找到_倍率是距離比_落點乘上倍率(harness):
    place(harness, (100, 40), (1000, 40))         # 距離 900 ÷ 基準 1000 = 0.9
    harness.vision.plan("a", [(500, 400)])
    r = run(harness, [find("a", offset=[50, 0]), click(100, -50)])
    assert r.ended == "done"
    assert harness.clicks() == [(545, 400), (635, 355)]
    assert "×0.900" in harness.log_text(r)


def test_其後每次查詢的預期尺度都是這個倍率(harness):
    place(harness, (100, 40), (1000, 40))         # 0.9
    harness.vision.plan("a", [(500, 400)])
    harness.vision.plan("ok", [None, (600, 300)])
    run(harness, [find("a", confirm="appear", confirm_target=tgt("ok"),
                       interval=0.1),
                  find("b", type="find")])
    seen = harness.expected_scales()
    assert {n for n, _ in seen} == {"a", "ok", "b"}
    assert all(s == 0.9 for _, s in seen), seen


def test_校準本身的查詢不帶預期尺度(harness):
    place(harness, (100, 40), (1000, 40))
    run(harness, [click(1, 1)])
    cal_queries = [(n, s) for n, s in harness.vision.expected_scales
                   if n in PAIR]
    assert cal_queries == [(PAIR[0], None), (PAIR[1], None)]


def test_倍率1時落點與原本完全相同(harness):
    place(harness, (100, 40), (1100, 40))
    harness.vision.plan("a", [(500, 400)])
    run(harness, [find("a", offset=[7, -3]), click(11, 13),
                  drag(1, 2, 30, 40)])
    assert harness.clicks() == [(507, 397), (518, 410)]
    ev = [e for e in harness.events if e[0] == "drag"][0]
    assert ev[1:5] == (519, 412, 548, 450)


def test_量測抖動內貼齊倍率1(harness):
    place(harness, (100, 40), (1099, 40))         # 999/1000: 抖動, 不是縮放
    harness.vision.plan("a", [(500, 400)])
    run(harness, [find("a", type="find"), click(519, 0)])
    assert harness.clicks() == [(1019, 400)], "原點 + 偏移原樣 (倍率貼齊 1)"


def test_其中一張找不到_一個輸入都不送_紀錄寫明是哪一張(harness):
    place(harness, (100, 40), None)
    r = run(harness, [click(10, 10), find("a"), drag(1, 1, 5, 5)])
    assert r.ended == "error"
    assert harness.kinds() == []
    assert PAIR[1] in harness.log_text(r)
    assert harness.lookups() == [], "沒校準成功就不往下找圖"
    [rec] = harness.filelog.of("calibrate")
    assert rec["result"] == "missing" and PAIR[1] in rec["missing"]
    assert "best" in rec


def test_沒有校準資料_一個輸入都不送_紀錄寫明要先設定校準對(harness):
    r = harness.run([click(10, 10), find("a")], calibration=None)
    assert r.ended == "error"
    assert harness.kinds() == []
    assert "校準對" in harness.log_text(r)
    [rec] = harness.filelog.of("calibrate")
    assert rec["result"] == "no_pair"


def test_兩張重疊在同一處_不能當比例尺(harness):
    place(harness, (100, 40), (100, 40))
    r = run(harness, [click(10, 10)])
    assert r.ended == "error" and harness.kinds() == []


def test_檔案日誌記兩張圖位置_距離_倍率(harness):
    place(harness, (100, 40), (1000, 40))
    run(harness, [click(1, 1)], scan_region=[0, 0, 1920, 1080])
    [rec] = harness.filelog.of("calibrate")
    assert rec["result"] == "ok"
    assert rec["centers"] == "(100,40);(1000,40)"
    assert rec["distance"] == "900.0" and rec["scale"] == "0.900"


def test_校準在搜尋範圍內找_位置是螢幕座標_第一張中心是基準點(harness):
    place(harness, (300, 240), (1200, 240))
    r = run(harness, [find("a")], scan_region=[200, 200, 1200, 700])
    assert harness.vision.grabs[0] == (200, 200, 1200, 700)
    [rec] = harness.filelog.of("calibrate")
    assert rec["centers"] == "(300,240);(1200,240)"
    assert "座標基準點 (300, 240)" in harness.log_text(r)


def test_校準對列入範本預載(harness):
    place(harness, (100, 40), (1000, 40))
    run(harness, [find("a")])
    assert harness.vision.preloads == [["a", *PAIR]]


def test_校準在第一個動作之前_延遲之後(harness):
    place(harness, (100, 40), (1000, 40))
    r = run(harness, [click(1, 1)], start_delay=3)
    logs = harness.logs(r)
    i_delay = next(i for i, m in enumerate(logs) if "秒後開始執行" in m)
    i_cal = next(i for i, m in enumerate(logs) if "校準" in m)
    assert i_delay < i_cal


# ---------- `支援倍率範圍`外不執行 (scale-out-of-range 票 01, ADR 0013 決策 1) ----------

def test_倍率小於支援倍率範圍_一個輸入都不送_紀錄寫倍率範圍與調大(harness):
    place(harness, (100, 40), (800, 40))          # 700 ÷ 1000 = 0.7
    harness.vision.plan("a", [(500, 400)])
    r = run(harness, [click(10, 10), find("a"), drag(1, 1, 5, 5)])
    assert r.ended == "error"
    assert harness.kinds() == []
    assert harness.lookups() == [], "出界就不往下找圖"
    text = harness.log_text(r)
    assert "×0.700" in text and "×0.85–1.15" in text and "調大" in text
    [rec] = harness.filelog.of("calibrate")
    assert rec["result"] == "out_of_range"
    assert rec["scale"] == "0.700" and rec["distance"] == "700.0"
    assert rec["baseline"] == "1000.0" and rec["pair"] == ",".join(PAIR)


def test_倍率大於支援倍率範圍_不執行_紀錄寫調小(harness):
    place(harness, (100, 40), (1300, 40))         # 1.2
    r = run(harness, [click(10, 10)])
    assert r.ended == "error" and harness.kinds() == []
    text = harness.log_text(r)
    assert "×1.200" in text and "調小" in text


@pytest.mark.parametrize("right, landing", [(950, (585, 400)),    # ×0.85
                                            (1250, (615, 400))])  # ×1.15
def test_支援倍率範圍兩端照常執行(harness, right, landing):
    place(harness, (100, 40), (right, 40))
    harness.vision.plan("a", [(500, 400)])
    r = run(harness, [find("a", type="find"), click(100, 0)])
    assert r.ended == "done"
    assert harness.clicks() == [landing]
    [rec] = harness.filelog.of("calibrate")
    assert rec["result"] == "ok"

from harness import click, drag, find, here

ROW1 = (500, 400)
LEAVES = dict(confirm="gone", interval=0.2)


def recs(harness):
    return harness.filelog.of("input.confirm")


def test_來源框仍有匹配就在補做間隔後重拖_框不見就生效_原點變終點(harness):
    harness.vision.plan("row1", [ROW1] * 6 + [(500, 100)])
    harness.run([find("row1", type="find"),
                 drag(0, 100, 0, -200, **LEAVES),
                 click(3, 3)])
    drags = [e[1:5] for e in harness.events if e[0] == "drag"]
    assert drags == [(500, 500, 500, 200)] * 2, "兩次拖曳座標相同"
    assert harness.clicks() == [(503, 203)], "生效後原點＝拖曳終點"
    [rec] = recs(harness)
    assert (rec["mode"], rec["result"], rec["inputs"]) == ("gone", "gone", 2)


def test_操作前不多查一次(harness):
    harness.vision.plan("row1", [ROW1, None])
    harness.run([find("row1", type="find"), drag(0, 100, 0, -200, **LEAVES)])
    assert harness.lookups() == ["row1", "row1"], "找圖一次 + 拖曳後輪詢一次"


def test_沿用來源找圖目標的限定範圍與比色_同款圖顏色不符不算還在(harness):
    orange, other = (500, 400, 0.99, 0.99), (500, 400, 0.99, 0.60)
    harness.vision.plan("anchor", [ROW1])
    harness.vision.plan("row1", [[orange], [other]])
    lim = [400, 300, 200, 200]
    harness.run([find("anchor", type="find"),
                 find("row1", target={"color": True, "within": lim},
                      type="find"),
                 drag(0, 100, 0, -200, **LEAVES)])
    [rec] = recs(harness)
    assert rec["result"] == "gone" and rec["inputs"] == 1
    assert harness.vision.color_checks[-1] == ("row1", True)


def test_原點來自點擊_無法執行_不送輸入_走找不到時(harness):
    r = harness.run([here(), click(100, 100), drag(0, 0, 0, -100, **LEAVES),
                     click(9, 9)])
    assert r.ended == "error", "預設停止"
    assert [e[0] for e in harness.events if e[0] != "park"] == ["click"], "拖曳沒送"
    [rec] = recs(harness)
    assert rec["result"] == "cannot_run"
    assert "原點不是來自找圖" in harness.log_text(r)


def test_原點來自拖曳_無法執行(harness):
    harness.vision.plan("row1", [ROW1])
    r = harness.run([find("row1", type="find"), drag(0, 0, 0, -100),
                     click(0, 0, confirm="gone", on_fail="skip")])
    assert r.ended == "done"
    assert recs(harness)[-1]["result"] == "cannot_run"
    assert harness.clicks() == []


def test_沒有原點_無法執行(harness):
    r = harness.run([click(10, 10, confirm="gone", on_fail="skip")])
    assert r.ended == "done" and harness.clicks() == []
    assert recs(harness) == [], "沒有原點: 相對座標先被跳過"
    assert "尚無原點" in harness.log_text(r)


def test_原點來自等待消失最後看到的位置_也算找圖來源(harness):
    harness.vision.plan("x", [ROW1, None])
    harness.vision.plan("row1", [ROW1, None])
    harness.run([find("row1", type="find"),
                 find("x", type="wait_gone", update_origin=False),
                 click(0, 0, confirm="gone", interval=0.2)])
    assert recs(harness)[0]["result"] == "gone"

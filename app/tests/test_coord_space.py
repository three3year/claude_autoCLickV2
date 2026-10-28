from harness import click, find, tgt


def test_執行紀錄寫出座標基準點位置(harness):
    r = harness.run([find("a")], anchor=(115, 76))
    assert "座標基準點 (115, 76)" in harness.log_text(r)


RECT = {"within": [100, 50, 300, 120]}


def test_固定矩形的查詢矩形跟著基準點走_與搜尋範圍框法無關(harness):
    harness.vision.plan("a", [(300, 160)])
    harness.run([find("a", target=RECT)], scan_region=[0, 0, 1920, 1080],
                anchor=(50, 60))
    [rec] = harness.filelog.of("find.target")
    assert rec["limit"] == "(150,110,300,120)"
    assert harness.clicks() == [(300, 160)]

    harness.events.clear()
    harness.filelog.records.clear()
    harness.run([find("a", target=RECT)], scan_region=[37, 23, 1500, 900],
                anchor=(50, 60))
    [rec] = harness.filelog.of("find.target")
    assert rec["limit"] == "(150,110,300,120)", "範圍框得鬆緊不同, 裁切矩形一樣"
    assert harness.clicks() == [(300, 160)]


def test_視窗挪位置後固定矩形跟著基準點搬(harness):
    harness.vision.plan("a", [(800, 460)])
    harness.run([find("a", target=RECT)], anchor=(550, 360))
    [rec] = harness.filelog.of("find.target")
    assert rec["limit"] == "(650,410,300,120)"
    assert harness.clicks() == [(800, 460)]


def test_固定矩形隨倍率縮放(harness):
    harness.vision.plan("a", [(400, 250)])
    harness.run([find("a", target=RECT)], anchor=(100, 100), scale=1.1)
    [rec] = harness.filelog.of("find.target")
    assert rec["limit"] == "(210,155,330,132)"


def test_固定矩形落在搜尋範圍外的部分照裁_裁掉那塊裡的圖找不到(harness):
    harness.vision.plan("a", [(1050, 160)])
    harness.run([find("a", target=RECT, timeout=0.3, interval=0.1)],
                scan_region=[0, 0, 1150, 1000], anchor=(900, 60))
    [rec] = harness.filelog.of("find.target")
    assert rec["limit"] == "(1000,110,150,120)"
    assert harness.clicks() == [(1050, 160)]

    harness.events.clear()
    harness.filelog.records.clear()
    harness.vision.plan("a", [(1050, 160)])
    harness.run([find("a", target=RECT, timeout=0.3, interval=0.1)],
                scan_region=[0, 0, 1030, 1000], anchor=(900, 60))
    assert harness.clicks() == [], "圖在被裁掉的那塊裡"


def test_確認圖與忙碌指示的固定矩形同樣以基準點為準(harness):
    harness.vision.plan("a", [(500, 400)])
    harness.vision.plan("ok", [None, (300, 160)])
    harness.vision.plan("busy", [None])
    harness.run([find("a", confirm="appear", interval=0.1,
                      confirm_target=tgt("ok", **RECT))],
                anchor=(50, 60), busy=tgt("busy", **RECT), retry_interval=0)
    limits = {(r["role"], r["template"]): r["limit"]
              for r in harness.filelog.of("find.target")}
    assert limits[("confirm_appear", "ok")] == "(150,110,300,120)"
    assert all(q == (150, 110, 300, 120) for n, q in harness.query_regions()
               if n in ("ok", "busy")), harness.query_regions()


def test_校準只在搜尋範圍內找_範圍內找不到就一個輸入都不送(harness):
    r = harness.run([click(1, 1), find("a")], scan_region=[600, 500, 800, 400],
                    anchor=(50, 60))
    assert r.ended == "error"
    assert harness.kinds() == []
    assert "找不到校準圖" in harness.log_text(r)
    assert harness.vision.grabs == [(600, 500, 800, 400)], "只在範圍內截圖找"
    assert harness.lookups() == []

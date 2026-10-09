"""存下的座標以`座標基準點`為原點 (coord-anchor 票 03/04, ADR 0012).

基準點＝開頭校準時`校準對`第一張圖的中心。`絕對座標`的落點＝基準點 + 偏移×倍率;
`固定矩形`的查詢矩形＝基準點 + 偏移×倍率再裁到搜尋範圍內。兩者都與搜尋範圍
框在哪裡、框得鬆緊無關——視窗挪位置、重框範圍後落點不變。
斷言對象: 送出的落點、每次查詢實際裁的矩形 (假偵測器收到的搜尋區域)。
"""
from harness import click, drag, find, tgt


def test_絕對座標以座標基準點為原點(harness):
    harness.run([click(30, 40)], scan_region=[100, 200, 800, 600],
                anchor=(150, 230))
    assert harness.clicks() == [(180, 270)]


def test_重新框範圍後絕對座標不變(harness):
    """同一份步驟、同一個基準點, 只換搜尋範圍 → 落點完全相同."""
    harness.run([click(30, 40)], scan_region=[0, 0, 800, 600], anchor=(50, 60))
    first = harness.clicks()[-1]
    harness.events.clear()
    harness.run([click(30, 40)], scan_region=[5, 3, 1200, 900], anchor=(50, 60))
    second = harness.clicks()[-1]
    assert first == second == (80, 100)


def test_視窗挪位置後絕對座標跟著基準點走(harness):
    harness.run([click(30, 40)], scan_region=[0, 0, 1920, 1080], anchor=(50, 60))
    harness.events.clear()
    harness.run([click(30, 40)], scan_region=[0, 0, 1920, 1080], anchor=(550, 360))
    assert harness.clicks() == [(580, 400)]


def test_拖曳的絕對座標同樣以基準點為原點(harness):
    harness.run([drag(10, 10, 60, 80)], scan_region=[100, 200, 800, 600],
                anchor=(120, 220))
    ev = [e for e in harness.events if e[0] == "drag"][0]
    assert (ev[1], ev[2], ev[3], ev[4]) == (130, 230, 180, 300)


def test_絕對座標乘上倍率再加基準點(harness):
    harness.run([click(30, -40)], anchor=(100, 200), scale=2.0)
    assert harness.clicks() == [(160, 120)]


def test_相對座標不受基準點影響(harness):
    """相對座標是以`原點`為基準, 換基準點不影響它與原點的相對關係."""
    harness.run([click(30, 40), click(5, 5, mode="prev")], anchor=(100, 200))
    assert harness.clicks() == [(130, 240), (135, 245)]


def test_沒有搜尋範圍時絕對座標照常執行_基準點來自校準(harness):
    harness.run([click(30, 40)], scan_region=None, anchor=(7, 9))
    assert harness.clicks() == [(37, 49)]


def test_執行紀錄寫出座標基準點位置(harness):
    r = harness.run([click(1, 1)], anchor=(115, 76))
    assert "座標基準點 (115, 76)" in harness.log_text(r)
    assert any("基準點 +1,+1" in m for m in harness.logs(r))


# ---------- 固定矩形 ----------

RECT = {"limit": {"kind": "rect", "x": 100, "y": 50, "w": 300, "h": 120}}


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
    harness.vision.plan("a", [(500, 300)])
    harness.run([find("a", target=RECT)], anchor=(100, 100), scale=2.0)
    [rec] = harness.filelog.of("find.target")
    assert rec["limit"] == "(300,200,600,240)"


def test_固定矩形落在搜尋範圍外的部分照裁_裁掉那塊裡的圖找不到(harness):
    # 基準點 (900,60) → 矩形 (1000,110) 300×120; 範圍右緣 1150 裁掉右半
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
                      confirmTarget=tgt("ok", **RECT))],
                anchor=(50, 60), busy=tgt("busy", **RECT), retry_interval=0)
    limits = {(r["role"], r["template"]): r["limit"]
              for r in harness.filelog.of("find.target")}
    assert limits[("confirm_appear", "ok")] == "(150,110,300,120)"
    assert all(q == (150, 110, 300, 120) for n, q in harness.query_regions()
               if n in ("ok", "busy")), harness.query_regions()


def test_校準只在搜尋範圍內找_範圍內找不到就一個輸入都不送(harness):
    """校準對在螢幕上, 但使用者忘了重框、範圍沒框到它 → 不執行、說明原因."""
    r = harness.run([click(1, 1), find("a")], scan_region=[600, 500, 800, 400],
                    anchor=(50, 60))
    assert r.ended == "error"
    assert harness.events == []
    assert "找不到校準圖" in harness.log_text(r)
    assert harness.vision.grabs == [(600, 500, 800, 400)], "只在範圍內截圖找"
    assert harness.lookups() == []

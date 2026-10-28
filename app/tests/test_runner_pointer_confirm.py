from harness import click, drag, find, here, tgt

AT = (500, 400)


def confirm_rec(harness):
    return harness.filelog.of("input.confirm")


def test_座標點擊_確認圖出現才往下(harness):
    harness.vision.plan("ok", [None, (300, 300)])
    r = harness.run([here(), click(100, 100, confirm="appear",
                           confirm_target=tgt("ok"), interval=0.2),
                     click(9, 9)])
    assert r.ended == "done"
    assert harness.clicks() == [(100, 100), (109, 109)], "生效後原點＝點擊落點"
    [rec] = confirm_rec(harness)
    assert (rec["kind"], rec["mode"], rec["result"]) == ("click", "appear",
                                                          "found")
    assert rec["inputs"] == 1 and rec["polls"] == 2


def test_座標點擊_沒出現就在補做間隔後補點_兩次落點相同(harness):
    harness.vision.plan("ok", [None] * 5 + [(300, 300)])
    harness.run([here(), click(100, 100, confirm="appear", confirm_target=tgt("ok"),
                       interval=0.2)])
    assert harness.clicks() == [(100, 100), (100, 100)], "1.0s 那次補一次"


def test_補做間隔與忙碌指示也把關座標點擊(harness):
    harness.vision.plan("ok", [None] * 8 + [(300, 300)])
    harness.vision.plan("busy", [None] * 4 + [(960, 1000)] * 3 + [None])
    harness.run([here(), click(100, 100, confirm="appear", confirm_target=tgt("ok"),
                       interval=0.2)], busy=tgt("busy"))
    assert harness.clicks() == [(100, 100), (100, 100)]
    [rec] = confirm_rec(harness)
    assert rec["busy_delay"] == "0.60"


def test_拖曳_下一步的圖出現_補做的起訖與第一次相同_原點生效後才變終點(harness):
    harness.vision.plan("anchor", [AT])
    harness.vision.plan("next", [None] * 5 + [(700, 300)])
    harness.run([find("anchor", type="find"),
                 drag(0, 100, 0, -200, confirm="next",
                      interval=0.2),
                 find("next", type="find"),
                 click(10, 0)])
    drags = [e[1:5] for e in harness.events if e[0] == "drag"]
    assert drags == [(500, 500, 500, 200)] * 2, "原點在生效前不動: 重拖同一段"
    assert harness.clicks() == [(710, 300)]


def test_拖曳生效後原點是拖曳終點(harness):
    harness.vision.plan("anchor", [AT])
    harness.vision.plan("ok", [(300, 300)])
    harness.run([find("anchor", type="find"),
                 drag(0, 100, 0, -200, confirm="appear",
                      confirm_target=tgt("ok")),
                 click(5, 5)])
    assert harness.clicks() == [(505, 205)]


def test_確認逾時預設停止流程(harness):
    harness.vision.plan("ok", [None])
    r = harness.run([here(), click(100, 100, confirm="appear", confirm_target=tgt("ok"),
                           timeout=1, interval=0.2), click(9, 9)])
    assert r.ended == "error"
    assert (9, 9) not in harness.clicks(), "後續步驟沒執行"
    [rec] = confirm_rec(harness)
    assert rec["result"] == "timeout"


def test_確認逾時可改跳過(harness):
    harness.vision.plan("ok", [None])
    r = harness.run([here(), click(100, 100, confirm="appear", confirm_target=tgt("ok"),
                           timeout=1, interval=0.2, on_fail="skip"),
                     click(9, 9)])
    assert r.ended == "done" and harness.clicks()[-1] == (9, 9)


def test_確認圖以操作後的原點為準(harness):
    near = {"pick": {"near": [0, 0]}}
    harness.vision.plan("ok", [[(110, 110), (850, 850)]])
    r = harness.run([here(), click(800, 800, confirm="appear",
                                   confirm_target=tgt("ok", **near))])
    [rec] = confirm_rec(harness)
    assert rec["result"] == "found" and rec["picked"] == "(830,840,40,20)"
    assert r.ended == "done"


def test_沒開確認的座標點擊與拖曳行為不變_並記一行座標(harness):
    harness.run([here(), click(100, 100), drag(10, 20, 30, 40)])
    assert harness.clicks() == [(100, 100)]
    recs = harness.filelog.of("input")
    assert [(r["kind"], r.get("at"), r.get("from"), r.get("to")) for r in recs] == [
        ("click", "(100,100)", None, None),
        ("drag", None, "(110,120)", "(130,140)")]
    assert confirm_rec(harness) == []


def test_下一步不是找圖_執行期退化成不確認(harness):
    r = harness.run([here(), click(100, 100, confirm="next"), click(9, 9)])
    assert r.ended == "done"
    assert harness.clicks() == [(100, 100), (109, 109)]
    assert "下一步不是找圖" in harness.log_text(r)


def test_確認圖列入範本預載(harness):
    harness.vision.plan("ok", [(300, 300)])
    harness.run([click(1, 1, confirm="appear", confirm_target=tgt("ok"))])
    assert "ok" in harness.vision.preloads[0]

"""座標點擊與拖曳的`生效確認` (effect-confirm 票 03, ADR 0008).

確認圖出現、下一步的圖出現: 送出後走與找圖點擊同一套確認/補做迴圈 (補做間隔、
忙碌指示把關); 補做送出與第一次相同的輸入, 原點在生效後才更新; 逾時預設停止。
沒開確認的照舊, 並在檔案日誌記一行座標。
"""
from harness import click, drag, find, tgt

AT = (500, 400)


def confirm_rec(harness):
    return harness.filelog.of("input.confirm")


def test_座標點擊_確認圖出現才往下(harness):
    harness.vision.plan("ok", [None, (300, 300)])
    r = harness.run([click(100, 100, confirm="appear",
                           confirmTarget=tgt("ok"), interval=0.2),
                     click(9, 9)])
    assert r.ended == "done"
    assert harness.clicks() == [(100, 100), (9, 9)]
    [rec] = confirm_rec(harness)
    assert (rec["kind"], rec["mode"], rec["result"]) == ("click", "appear",
                                                          "found")
    assert rec["inputs"] == 1 and rec["polls"] == 2


def test_座標點擊_沒出現就在補做間隔後補點_兩次落點相同(harness):
    harness.vision.plan("ok", [None] * 5 + [(300, 300)])
    harness.run([click(100, 100, confirm="appear", confirmTarget=tgt("ok"),
                       interval=0.2)])
    assert harness.clicks() == [(100, 100), (100, 100)], "1.0s 那次補一次"


def test_補做間隔與忙碌指示也把關座標點擊(harness):
    harness.vision.plan("ok", [None] * 8 + [(300, 300)])
    # 每輪沒生效都查 (`忙碌暫停`): 1.0/1.2/1.4 有指示, 1.6 消失 → 1.6s 補
    harness.vision.plan("busy", [None] * 4 + [(960, 1000)] * 3 + [None])
    harness.run([click(100, 100, confirm="appear", confirmTarget=tgt("ok"),
                       interval=0.2)], busy=tgt("busy"))
    assert harness.clicks() == [(100, 100), (100, 100)]
    [rec] = confirm_rec(harness)
    assert rec["busy_delay"] == "0.60"


def test_拖曳_下一步的圖出現_補做的起訖與第一次相同_原點生效後才變終點(harness):
    harness.vision.plan("anchor", [AT])
    harness.vision.plan("next", [None] * 5 + [(700, 300)])
    harness.run([find("anchor", action="none"),
                 drag(0, 100, 0, -200, mode="prev", confirm="next",
                      interval=0.2),
                 find("next", action="none"),
                 click(10, 0, mode="prev")])
    drags = [e[1:5] for e in harness.events if e[0] == "drag"]
    assert drags == [(500, 500, 500, 200)] * 2, "原點在生效前不動: 重拖同一段"
    assert harness.clicks() == [(710, 300)]


def test_拖曳生效後原點是拖曳終點(harness):
    harness.vision.plan("anchor", [AT])
    harness.vision.plan("ok", [(300, 300)])
    harness.run([find("anchor", action="none"),
                 drag(0, 100, 0, -200, mode="prev", confirm="appear",
                      confirmTarget=tgt("ok")),
                 click(5, 5, mode="prev")])
    assert harness.clicks() == [(505, 205)]


def test_確認逾時預設停止流程(harness):
    harness.vision.plan("ok", [None])
    r = harness.run([click(100, 100, confirm="appear", confirmTarget=tgt("ok"),
                           timeout=1, interval=0.2), click(9, 9)])
    assert r.ended == "error"
    assert (9, 9) not in harness.clicks(), "後續步驟沒執行"
    [rec] = confirm_rec(harness)
    assert rec["result"] == "timeout"


def test_確認逾時可改跳過(harness):
    harness.vision.plan("ok", [None])
    r = harness.run([click(100, 100, confirm="appear", confirmTarget=tgt("ok"),
                           timeout=1, interval=0.2, onNotFound="skip"),
                     click(9, 9)])
    assert r.ended == "done" and harness.clicks()[-1] == (9, 9)


def test_確認圖以操作後的原點為準(harness):
    """確認圖限定在原點附近: 原點是這次點擊的落點."""
    near = {"limit": {"kind": "origin", "x": -50, "y": -50, "w": 100, "h": 100}}
    harness.vision.plan("ok", [(110, 110)])
    r = harness.run([click(100, 100, confirm="appear",
                           confirmTarget=tgt("ok", **near))])
    assert confirm_rec(harness)[0]["result"] == "found"
    assert r.ended == "done"


def test_沒開確認的座標點擊與拖曳行為不變_並記一行座標(harness):
    harness.run([click(100, 100), drag(10, 20, 30, 40)])
    assert harness.clicks() == [(100, 100)]
    recs = harness.filelog.of("input")
    assert [(r["kind"], r.get("at"), r.get("from"), r.get("to")) for r in recs] == [
        ("click", "(100,100)", None, None),
        ("drag", None, "(10,20)", "(30,40)")]
    assert confirm_rec(harness) == []


def test_下一步不是找圖_執行期退化成不確認(harness):
    r = harness.run([click(100, 100, confirm="next"), click(9, 9)])
    assert r.ended == "done"
    assert harness.clicks() == [(100, 100), (9, 9)]
    assert "下一步不是找圖" in harness.log_text(r)


def test_確認圖列入範本預載(harness):
    harness.vision.plan("ok", [(300, 300)])
    harness.run([click(1, 1, confirm="appear", confirmTarget=tgt("ok"))])
    assert "ok" in harness.vision.preloads[0]

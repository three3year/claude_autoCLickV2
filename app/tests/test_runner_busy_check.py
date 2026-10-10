"""`忙碌檢查` (busy-check 票 02/03, ADR 0011).

勾了的步驟 (座標點擊、拖曳、找圖點擊): 送出輸入 → `忙碌出現等候`內輪詢
`忙碌指示`, 一次都沒看到＝放行 (就算確認其實已成立也等滿); 看到就等它消失 (挑中的
位置不再有匹配); 從送出起 60 秒沒消失＝停止流程。之後才做`生效確認`。補做重送後
不再另等。沒勾的步驟完全不變。
斷言對象: 輸入事件的時間點 (虛擬時鐘)、查詢順序、結束原因、檔案日誌 `busy.check`。
"""
import pytest

from harness import (branch_end, branch_or, branch_start, click, drag, find,
                     here, tgt)

AT = (500, 400)
BUSY_AT = (960, 1000)
BUSY = tgt("busy", within=[640, 720, 640, 360])
# 輪詢 0.5s 的步驟 (有生效確認的寫 interval=0.5): 送出後 0.5s 出現、3.0s 消失
# (0.0 沒有, 0.5..2.5 在, 3.0 消失); 沒有等待的座標點擊照預設表 0.3s 輪詢
# (0.0 沒有, 0.3..1.5 在, 1.8 消失)
APPEAR_THEN_GONE = [None] + [BUSY_AT] * 5 + [None]


def checks(harness):
    return harness.filelog.of("busy.check")


def gap(harness):
    """第一個輸入到第二個輸入之間經過的秒數."""
    times = harness.input_times()
    return times[1][1] - times[0][1]


def test_座標點擊勾了_忙碌出現後消失_下一步才送出(harness):
    harness.vision.plan("busy", APPEAR_THEN_GONE)
    r = harness.run([here(), click(100, 100, busy_check=True), click(9, 9)], busy=BUSY)
    assert r.ended == "done"
    assert harness.clicks() == [(100, 100), (109, 109)]
    assert gap(harness) == pytest.approx(1.8, abs=0.01), "沒有等待的點擊照預設 0.3s 輪詢"
    [rec] = checks(harness)
    assert (rec["step"], rec["result"], rec["waited"], rec["polls"]) == (
        2, "gone", "1.80", 7)
    assert rec["picked"] == "(940,990,40,20)", "看到時挑中的框"


def test_拖曳勾了有生效確認_確認在忙碌消失後才開始(harness):
    harness.vision.plan("busy", APPEAR_THEN_GONE)
    harness.vision.plan("ok", [(300, 300)])
    r = harness.run([here(), drag(10, 20, 30, 40, busy_check=True, confirm="appear",
                          confirm_target=tgt("ok"), interval=0.5),
                     click(9, 9)], busy=BUSY)
    assert r.ended == "done"
    assert harness.lookups() == ["busy"] * 7 + ["ok"], "等忙碌期間不查確認圖"
    assert gap(harness) == pytest.approx(3.5, abs=0.01), "消失後第一輪確認就生效"
    events = [e for e, _ in harness.filelog.records
              if e in ("busy.check", "input.confirm")]
    assert events == ["busy.check", "input.confirm"]
    [rec] = harness.filelog.of("input.confirm")
    assert rec["result"] == "found" and rec["inputs"] == 1


def test_確認逾時從忙碌檢查結束起算(harness):
    harness.vision.plan("busy", APPEAR_THEN_GONE)
    harness.vision.plan("ok", [None])
    r = harness.run([here(), click(100, 100, busy_check=True, confirm="appear",
                           confirm_target=tgt("ok"), timeout=1, interval=0.5,
                           on_fail="skip"),
                     click(9, 9)], busy=BUSY)
    assert r.ended == "done"
    # 3.0s 消失後才開始確認: 3.5s 沒生效且已過補做間隔 → 補做一次 (不再另等忙碌),
    # 4.0s 確認逾時 → 跳過 → 下一步
    # 沒生效 → 原點不更新, 下一步仍相對定位找圖的 (0, 0)
    assert harness.clicks() == [(100, 100), (100, 100), (9, 9)]
    times = [t for _, t in harness.input_times()]
    assert times[-1] - times[0] == pytest.approx(4.0, abs=0.01)


def test_找圖點擊勾了_找到點擊_等忙碌_再確認(harness):
    harness.vision.plan("a", [None, AT, None])   # 第 2 輪找到; 確認第 1 輪已消失
    harness.vision.plan("busy", [None, BUSY_AT, None])
    r = harness.run([find("a", busy_check=True, confirm="gone", interval=0.5)],
                    busy=BUSY)
    assert r.ended == "done" and harness.clicks() == [AT]
    assert harness.lookups() == ["a", "a", "busy", "busy", "busy", "a"], \
        "找圖階段不查忙碌; 點擊後等忙碌; 消失後才確認"
    seq = [(e, f.get("role"), f.get("result")) for e, f in harness.filelog.records
           if e in ("find.target", "busy.check")]
    assert seq == [("find.target", "find", "found"),
                   ("busy.check", None, "gone"),
                   ("find.target", "confirm_gone", "gone")]


def test_找圖點擊勾了沒設確認_點完等忙碌就結束(harness):
    harness.vision.plan("a", [AT])
    harness.vision.plan("busy", [None, BUSY_AT, BUSY_AT, None])
    r = harness.run([find("a", busy_check=True, interval=0.5), click(9, 9)],
                    busy=BUSY)
    assert r.ended == "done" and harness.clicks() == [AT, (509, 409)]
    assert gap(harness) == pytest.approx(1.5, abs=0.01)


def test_出現等候內沒看到_等滿才放行(harness):
    harness.vision.plan("busy", [None])
    r = harness.run([here(), click(100, 100, busy_check=True), click(9, 9)], busy=BUSY)
    assert r.ended == "done" and harness.clicks() == [(100, 100), (109, 109)]
    assert gap(harness) == pytest.approx(1.0, abs=0.01), "預設 1000ms"
    [rec] = checks(harness)
    assert (rec["result"], rec["waited"], rec["polls"]) == ("not_appeared",
                                                            "1.00", 5)
    assert "picked" not in rec


def test_確認條件已成立仍等滿出現等候(harness):
    harness.vision.plan("busy", [None])
    harness.vision.plan("ok", [(300, 300)])   # 一開始就在
    harness.run([here(), click(100, 100, busy_check=True, confirm="appear",
                       confirm_target=tgt("ok"), interval=0.5),
                 click(9, 9)], busy=BUSY)
    assert harness.lookups() == ["busy", "busy", "busy", "ok"]
    assert gap(harness) == pytest.approx(1.5, abs=0.01), "等滿 1.0s 才開始確認"


def test_忙碌60秒不消失_停止流程_不走找不到時(harness):
    harness.vision.plan("busy", [None, BUSY_AT])   # 0.5s 出現後一直在
    r = harness.run([here(), click(100, 100, busy_check=True, on_fail="skip"),
                     click(9, 9)], busy=BUSY)
    assert r.ended == "error", "停止流程, 不是跳過"
    assert harness.clicks() == [(100, 100)], "後面沒有任何輸入"
    [rec] = checks(harness)
    assert (rec["result"], rec["waited"]) == ("timeout", "60.00")
    assert any("忙碌指示" in m and "60 秒" in m for m in harness.logs(r))


def test_補做重送後不再等忙碌_補做門照舊(harness):
    # 出現等候 3 輪沒看到 → 1.0s 放行; 確認 1.5s 沒生效且已過補做間隔 → 補做;
    # 2.0s 生效。補做前查一次忙碌指示 (門), 重送後沒有第二次忙碌檢查
    harness.vision.plan("busy", [None])
    harness.vision.plan("ok", [None, (300, 300)])
    r = harness.run([here(), click(100, 100, busy_check=True, confirm="appear",
                           confirm_target=tgt("ok"), interval=0.5)], busy=BUSY)
    assert r.ended == "done"
    assert harness.clicks() == [(100, 100), (100, 100)]
    assert harness.lookups() == ["busy", "busy", "busy", "ok", "busy", "ok"]
    assert len(checks(harness)) == 1
    assert harness.filelog.of("input.confirm")[0]["inputs"] == 2


def test_補做門在忙碌時照舊不重送(harness):
    harness.vision.plan("busy", [None, None, None, BUSY_AT, None])
    harness.vision.plan("ok", [None, None, (300, 300)])
    harness.run([here(), click(100, 100, busy_check=True, confirm="appear",
                       confirm_target=tgt("ok"), interval=0.5)], busy=BUSY)
    assert harness.clicks() == [(100, 100), (100, 100)], "1.5s 忙碌不補, 2.0s 補"


def test_沒勾的步驟不變_也不查忙碌指示(harness):
    harness.vision.plan("busy", [BUSY_AT])
    harness.vision.plan("a", [AT])
    r = harness.run([here(), click(100, 100), drag(1, 2, 3, 4), find("a"),
                     click(9, 9)], busy=BUSY)
    assert r.ended == "done"
    assert "busy" not in harness.lookups()
    assert checks(harness) == []
    times = [t for _, t in harness.input_times()]
    assert times[-1] - times[0] == pytest.approx(0.0, abs=0.01), "不多等"


def test_分岔開頭的找圖點擊勾了_選中後點擊等忙碌(harness):
    harness.vision.plan("a", [AT])
    harness.vision.plan("b", [None])
    harness.vision.plan("busy", [None, BUSY_AT, None])
    r = harness.run([branch_start(), find("a", busy_check=True, interval=0.5),
                     branch_or(), find("b"), branch_end(), click(9, 9)],
                    busy=BUSY)
    assert r.ended == "done" and harness.clicks() == [AT, (509, 409)]
    assert gap(harness) == pytest.approx(1.0, abs=0.01)
    [rec] = checks(harness)
    assert rec["step"] == 2 and rec["result"] == "gone"


def test_找圖不點擊時勾了也不等(harness):
    harness.vision.plan("a", [AT])
    harness.vision.plan("busy", [BUSY_AT])
    r = harness.run([find("a", type="find", busy_check=True), click(9, 9)],
                    busy=BUSY)
    assert r.ended == "done" and checks(harness) == []
    assert "busy" not in harness.lookups()


def test_沒設忙碌指示卻勾了_記警告不等(harness):
    harness.vision.plan("busy", [BUSY_AT])
    r = harness.run([here(), click(100, 100, busy_check=True), click(9, 9)])
    assert r.ended == "done" and gap(harness) == 0.0
    assert any("沒設忙碌指示" in m for m in harness.logs(r))


def test_日誌順序_輸入那筆之後_確認之前(harness):
    harness.vision.plan("busy", [None])
    harness.run([here(), click(100, 100, busy_check=True)], busy=BUSY)
    assert [e for e, _ in harness.filelog.records
            if e in ("input", "busy.check")] == ["input", "busy.check"]

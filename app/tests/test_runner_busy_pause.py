"""`忙碌暫停` (busy-pause-fixed-rect 票 02, ADR 0010).

找圖在等待時 (分岔的條件、一般找圖、生效確認、等待消失), 這一輪沒達成就用
同一張截圖查一次`忙碌指示`; 看到忙碌的那段時間不算進逾時 (也不算進出現等候
上限)。同一步驟最多暫停累計 60 秒。
斷言對象: 點擊、結束原因、擷取時間 (虛擬時鐘)、查詢紀錄、檔案日誌。
"""
import pytest

from harness import branch_end, branch_or, branch_start, click, find, tgt

AT = (500, 400)
BUSY_AT = (960, 1000)
BUSY = tgt("busy", limit={"kind": "grid", "cells": [8]})


def busy_polls(n):
    """前 n 次查詢看得到忙碌指示, 之後消失."""
    return [BUSY_AT] * n + [None]


def span(harness):
    """第一步的第一次擷取到最後一次擷取經過的秒數."""
    times = harness.vision.grab_times[1:]   # 不含開頭校準
    return times[-1] - times[0]


def records(harness, event="find.target"):
    return harness.filelog.of(event)


def busy_lookups(harness):
    return harness.lookups().count("busy")


# ---------- 分岔 ----------

def _branch(timeout=5):
    return [branch_start(),
            find("a", timeout=timeout, interval=0.5),
            branch_or(),
            find("b", timeout=timeout, interval=0.5),
            branch_end()]


def test_分岔_沒有忙碌_照原本時間逾時(harness):
    harness.vision.plan("a", [None])
    harness.vision.plan("b", [None])
    harness.vision.plan("busy", [None])
    r = harness.run(_branch(), busy=BUSY)
    assert r.ended == "done" and harness.clicks() == []
    assert span(harness) == pytest.approx(5.0, abs=0.1)


def test_分岔_忙碌8秒_全部逾時晚約8秒(harness):
    harness.vision.plan("a", [None])
    harness.vision.plan("b", [None])
    harness.vision.plan("busy", busy_polls(16))   # 0.0..7.5s 都看得到, 8.0s 消失
    r = harness.run(_branch(), busy=BUSY)
    assert r.ended == "done" and harness.clicks() == []
    assert span(harness) == pytest.approx(13.0, abs=0.1)
    recs = [x for x in records(harness) if x["role"] == "branch"]
    assert [x["busy_pause"] for x in recs] == ["8.00", "8.00"], \
        "分岔整個算一步, 所有分支共用一個額度"


def test_分岔_忙碌結束後才出現的條件會被挑到(harness):
    harness.vision.plan("a", [None])
    harness.vision.plan("b", [None] * 18 + [AT])   # 9.0s 才出現 (逾時 3s)
    harness.vision.plan("busy", busy_polls(16))
    r = harness.run(_branch(timeout=3), busy=BUSY)
    assert r.ended == "done"
    assert harness.clicks() == [AT], "走分支 2 並點它"


# ---------- 一般找圖 ----------

def test_一般找圖_忙碌延後逾時(harness):
    harness.vision.plan("a", [None] * 12 + [AT])   # 6.0s 才出現 (逾時 2s)
    harness.vision.plan("busy", busy_polls(10))    # 0.0..4.5s 忙碌, 5.0s 消失
    r = harness.run([find("a", timeout=2, interval=0.5, onNotFound="stop")],
                    busy=BUSY)
    assert r.ended == "done" and harness.clicks() == [AT]
    [rec] = records(harness)
    assert rec["result"] == "found" and rec["busy_pause"] == "5.00"


def test_一般找圖_沒有忙碌就照原本時間逾時(harness):
    harness.vision.plan("a", [None])
    harness.vision.plan("busy", [None])
    r = harness.run([find("a", timeout=2, interval=0.5, onNotFound="skip"),
                     click(9, 9)], busy=BUSY)
    assert harness.clicks() == [(9, 9)]
    assert span(harness) == pytest.approx(2.0, abs=0.1)
    [rec] = records(harness)
    assert rec["result"] == "timeout" and rec["busy_pause"] == "0.00"


def test_忙碌一直不消失_累計60秒後照常逾時_走找不到時(harness):
    harness.vision.plan("a", [None])
    harness.vision.plan("busy", [BUSY_AT])
    r = harness.run([find("a", timeout=2, interval=0.5, onNotFound="stop"),
                     click(9, 9)], busy=BUSY)
    assert r.ended == "error", "找不到時＝停止"
    assert harness.clicks() == []
    assert span(harness) == pytest.approx(62.0, abs=0.1)
    [rec] = records(harness)
    assert rec["result"] == "timeout" and rec["busy_pause"] == "60.00"


def test_找到的那一輪不查忙碌指示(harness):
    harness.vision.plan("a", [None, None, AT])
    harness.vision.plan("busy", [None])
    harness.run([find("a", interval=0.5)], busy=BUSY)
    assert harness.lookups() == ["a", "busy", "a", "busy", "a"]


def test_一開始就找到_完全不查忙碌指示(harness):
    harness.vision.plan("a", [AT])
    harness.run([find("a"), find("b")], busy=BUSY)
    assert "busy" not in harness.lookups()


def test_沒設忙碌指示_時間點不變也不查(harness):
    harness.vision.plan("a", [None])
    harness.vision.plan("busy", [BUSY_AT])
    harness.run([find("a", timeout=2, interval=0.5, onNotFound="skip")])
    assert span(harness) == pytest.approx(2.0, abs=0.1)
    assert "busy" not in harness.lookups()


# ---------- 生效確認 ----------

def test_生效確認_忙碌延後逾時(harness):
    harness.vision.plan("a", [AT])
    harness.vision.plan("ok", [None] * 10 + [(300, 300)])   # 第 11 輪 (2.2s) 才出現
    harness.vision.plan("busy", busy_polls(5))   # 0.2..1.0s 忙碌, 1.2s 消失
    r = harness.run([find("a", confirm="appear", confirmTarget=tgt("ok"),
                          timeout=1.5, interval=0.2,
                          onNotFound="stop")], busy=BUSY)
    assert r.ended == "done"
    [rec] = [x for x in records(harness) if x["role"] == "confirm_appear"]
    assert rec["result"] == "found"
    assert rec["busy_pause"] == "1.00"
    [find_rec] = [x for x in records(harness) if x["role"] == "find"]
    assert find_rec["busy_pause"] == "0.00", "找圖階段與確認階段各自一個額度"


def test_生效確認_補做與暫停只查一次忙碌指示(harness):
    harness.vision.plan("a", [AT] * 6 + [None])   # 找到後確認 5 輪沒達成, 第 6 輪消失
    harness.vision.plan("busy", [None])
    harness.run([find("a", confirm="gone", interval=0.2)], busy=BUSY)
    assert busy_lookups(harness) == 5, "沒達成的 5 輪各查一次"
    assert harness.clicks() == [AT, AT], "1.0s 補做一次 (門檻照舊)"


def test_座標點擊的生效確認_忙碌延後逾時_日誌記暫停(harness):
    harness.vision.plan("ok", [None] * 10 + [(300, 300)])
    harness.vision.plan("busy", busy_polls(5))
    r = harness.run([click(9, 9, confirm="appear", confirmTarget=tgt("ok"),
                           timeout=1.5, interval=0.2)], busy=BUSY)
    assert r.ended == "done"
    [rec] = records(harness, "input.confirm")
    assert rec["result"] == "found" and rec["busy_pause"] == "1.00"


# ---------- 等待消失 ----------

GONE = dict(action="wait_gone", interval=0.5, timeout=2, onNotFound="stop")


def test_等待消失_忙碌延後逾時(harness):
    harness.vision.plan("x", [AT] * 8 + [None])    # 4.0s 才消失 (逾時 2s)
    harness.vision.plan("busy", busy_polls(6))     # 0.0..2.5s 忙碌, 3.0s 消失
    r = harness.run([find("x", **GONE), click(9, 9)], busy=BUSY)
    assert r.ended == "done" and harness.clicks() == [(9, 9)]
    [rec] = records(harness)
    assert rec["result"] == "gone" and rec["busy_pause"] == "3.00"


def test_出現等候上限也暫停(harness):
    harness.vision.plan("x", [None] * 6 + [AT, None])   # 3.0s 出現, 3.5s 消失
    harness.vision.plan("busy", busy_polls(4))          # 0.0..1.5s 忙碌, 2.0s 消失
    r = harness.run([find("x", appearLimitMs=1000, **dict(GONE, timeout=10)),
                     click(9, 9)], busy=BUSY)
    assert r.ended == "done"
    [rec] = records(harness)
    assert rec["result"] == "gone", "上限延到 3.0s: 看到它出現又消失"


def test_等待消失的目標就是忙碌指示_照樣暫停(harness):
    # 每輪查兩次 (步驟自己＋忙碌指示): 0.0..3.5s 都在, 4.0s 消失
    harness.vision.plan("busy", busy_polls(16))
    r = harness.run([find("busy", target={"limit": BUSY["limit"]}, **GONE),
                     click(9, 9)], busy=BUSY)
    assert r.ended == "done" and harness.clicks() == [(9, 9)]
    [rec] = records(harness)
    assert rec["result"] == "gone"

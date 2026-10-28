from harness import find, tgt

AT = (500, 400)
BUSY = tgt("busy", limit={"kind": "grid", "cells": [8]})


def confirm_records(harness):
    return [r for r in harness.filelog.of("find.target")
            if r["role"].startswith("confirm_")]


def test_未滿補做間隔不補點(harness):
    harness.vision.plan("a", [AT] * 4 + [None])
    harness.run([find("a", confirm="gone", interval=0.2)])
    assert harness.clicks() == [AT], "遊戲只是慢: 不重複點"


def test_滿補做間隔才補點(harness):
    harness.vision.plan("a", [AT] * 6 + [None])
    harness.run([find("a", confirm="gone", interval=0.2)])
    assert harness.clicks() == [AT, AT]


def test_補做間隔是流程設定(harness):
    harness.vision.plan("a", [AT] * 4 + [None])
    harness.run([find("a", confirm="gone", interval=0.2)], retry_interval=0.4)
    assert harness.clicks() == [AT, AT], "0.4s 那次就補"


def test_補點後重新計算間隔(harness):
    harness.vision.plan("a", [AT] * 12 + [None])
    harness.run([find("a", confirm="gone", interval=0.2)], retry_interval=1.0)
    assert harness.clicks() == [AT, AT, AT], "1.0s 與 2.0s 各補一次"


def test_畫面上有忙碌指示就延後_消失才補(harness):
    harness.vision.plan("a", [AT] * 9 + [None])
    harness.vision.plan("busy", [None] * 4 + [(960, 1000)] * 3 + [None])
    harness.run([find("a", confirm="gone", interval=0.2)], busy=BUSY)
    assert harness.clicks() == [AT, AT]
    [rec] = confirm_records(harness)
    assert rec["busy_delay"] == "0.60"


def test_沒設忙碌指示只看間隔(harness):
    harness.vision.plan("a", [AT] * 6 + [None])
    harness.vision.plan("busy", [(960, 1000)])
    harness.run([find("a", confirm="gone", interval=0.2)])
    assert harness.clicks() == [AT, AT]
    assert "busy" not in harness.lookups()


def test_一般輸入前不查忙碌指示_確認沒生效的那輪才查(harness):
    harness.vision.plan("a", [AT, AT, None])
    harness.run([find("a", confirm="gone", interval=0.2), find("b")],
                busy=BUSY)
    assert harness.lookups() == ["a", "a", "busy", "a", "b"]


def test_找圖目標圖消失_目標不在原位就不補點(harness):
    harness.vision.plan("a", [AT] + [(900, 100)] * 10)
    harness.vision.plan("ok", [None] * 8 + [(300, 300)])
    harness.run([find("a", confirm="appear", confirm_target=tgt("ok"),
                      interval=0.2)])
    assert harness.clicks() == [AT]


def test_確認紀錄帶延後補做的總時間_沒延後是0(harness):
    harness.vision.plan("a", [AT, None])
    harness.run([find("a", confirm="gone", interval=0.2)], busy=BUSY)
    [rec] = confirm_records(harness)
    assert rec["busy_delay"] == "0.00"


def test_逾時時延後中的時間也算進去(harness):
    harness.vision.plan("a", [AT])
    harness.vision.plan("busy", [(960, 1000)])
    harness.run([find("a", confirm="gone", interval=0.2, timeout=2,
                      on_fail="skip")], busy=BUSY)
    assert harness.clicks() == [AT], "指示一直在: 一次都不補"
    [rec] = confirm_records(harness)
    assert rec["result"] == "not_gone"
    assert "busy_pause" not in rec
    assert 0.9 <= float(rec["busy_delay"]) <= 1.1

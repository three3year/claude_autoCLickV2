"""`補做`的兩道門: `補做間隔`與`忙碌指示` (effect-confirm 票 01, ADR 0008).

生效確認還沒通過時, 重送輸入要同時滿足: 距上一次輸入已過補做間隔 (流程設定,
預設 1000ms), 且 (設了忙碌指示時) 畫面上沒有忙碌指示。忙碌指示只在補做判斷時查。
斷言對象: 送出的點擊次數、虛擬時鐘、查詢紀錄、檔案日誌。
"""
from harness import find, tgt

AT = (500, 400)
BUSY = tgt("busy", limit={"kind": "grid", "cells": [8]})


def confirm_records(harness):
    return [r for r in harness.filelog.of("find.target")
            if r["role"].startswith("confirm_")]


def test_未滿補做間隔不補點(harness):
    # 點擊後 0.2/0.4/0.6s 目標都還在 (不到 1s), 第 4 次輪詢已消失
    harness.vision.plan("a", [AT] * 4 + [None])
    harness.run([find("a", confirm="gone", interval=0.2)])
    assert harness.clicks() == [AT], "遊戲只是慢: 不重複點"


def test_滿補做間隔才補點(harness):
    # 0.2..1.0s 都還在 → 1.0s 那次補點一次, 之後消失
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
    # 1.0s 起該補了: 1.0/1.2/1.4 指示還在, 1.6 消失 → 1.6s 補
    harness.vision.plan("busy", [(960, 1000)] * 3 + [None])
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


def test_一般輸入前不查忙碌指示(harness):
    """第一次點擊、以及生效前還沒到補做時機時, 查詢紀錄裡都沒有忙碌指示."""
    harness.vision.plan("a", [AT, AT, None])
    harness.run([find("a", confirm="gone", interval=0.2), find("b")],
                busy=BUSY)
    assert "busy" not in harness.lookups()


def test_找圖目標圖消失_目標不在原位就不補點(harness):
    """點了之後目標移走 (別處有同款), 確認圖也還沒出現: 照舊不補點."""
    harness.vision.plan("a", [AT] + [(900, 100)] * 10)
    harness.vision.plan("ok", [None] * 8 + [(300, 300)])
    harness.run([find("a", confirm="appear", confirmTarget=tgt("ok"),
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
                      onNotFound="skip")], busy=BUSY)
    assert harness.clicks() == [AT], "指示一直在: 一次都不補"
    [rec] = confirm_records(harness)
    assert rec["result"] == "not_gone"
    assert 0.9 <= float(rec["busy_delay"]) <= 1.1


def test_找圖到補點仍是一個舞台原子區段(harness):
    st = harness.make_stage()
    harness.vision.plan("a", [AT] * 6 + [None])
    harness.vision.plan("busy", [(960, 1000), None])
    harness.run([find("a", confirm="gone", interval=0.2)], stage=st, busy=BUSY)
    kinds = [e[0] for e in harness.events]
    first, last = kinds.index("click"), len(kinds) - 1 - kinds[::-1].index("click")
    assert "release" not in kinds[first:last], "補做判斷 (含查忙碌指示) 不讓出舞台"

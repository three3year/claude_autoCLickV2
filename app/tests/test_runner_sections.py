"""區段 (`重複區段`、`分岔`) 與`跳出`的回歸網.

區段是平面標記步驟, 由執行器用堆疊與跳轉解譯 (見 ADR-0001)。
"""


from harness import (branch_end, branch_or, branch_start, click, find, here,
                     repeat, repeat_end)


def tap(x, y):
    """不更新原點的座標點擊: 跟在 here() 後面, 每次都點在 (x, y)."""
    return click(x, y, update_origin=False)


# ---------- 重複區段 ----------

def test_重複區段執行指定次數(harness):
    harness.run([here(), repeat(3), tap(1, 1), repeat_end()])
    assert harness.clicks() == [(1, 1)] * 3


def test_巢狀重複區段次數相乘(harness):
    harness.run([here(), repeat(2), repeat(3), tap(1, 1), repeat_end(), repeat_end()])
    assert len(harness.clicks()) == 6


def test_多輪從頭再跑一次(harness):
    harness.run([here(), tap(1, 1)], run_count=3)
    assert harness.clicks() == [(1, 1)] * 3


# ---------- 分岔 ----------

def test_分岔走第一個成立的分支(harness):
    harness.vision.plan("a.png", [None])
    harness.vision.plan("b.png", [(500, 400)])
    harness.run([
        branch_start(),
        find("a.png", type="find", interval=0.1), tap(1, 1),
        branch_or(),
        find("b.png", type="find", interval=0.1), tap(2, 2),
        branch_end(),
    ])
    # 條件找到的位置成為原點
    assert harness.clicks() == [(502, 402)], "應該走條件成立的那一支"


def test_分岔全部逾時時跳過整個分岔(harness):
    harness.vision.plan("a.png", [None])
    harness.vision.plan("b.png", [None])
    harness.run([
        here(),
        branch_start(),
        find("a.png", type="find", timeout=1, interval=0.1), tap(1, 1),
        branch_or(),
        find("b.png", type="find", timeout=1, interval=0.1), tap(2, 2),
        branch_end(),
        tap(9, 9),
    ])
    assert harness.clicks() == [(9, 9)]
    assert "沒有任何分支成立" in harness.log_text()


def test_分岔全部逾時時可停止整份流程(harness):
    harness.vision.plan("a.png", [None])
    harness.run([
        branch_start(),
        find("a.png", type="find", timeout=1, interval=0.1,
             on_fail="stop"),
        branch_end(),
        tap(9, 9),
    ])
    assert harness.clicks() == []
    assert "停止執行" in harness.log_text()


# ---------- 跳出 ----------

def test_跳出重複區段會放棄剩餘次數(harness):
    harness.vision.plan("a.png", [None])
    harness.run([
        here(),
        repeat(5),
        find("a.png", timeout=1, interval=0.1, on_fail="break"),
        tap(1, 1),
        repeat_end(),
        tap(9, 9),
    ])
    assert harness.clicks() == [(9, 9)], "跳出＝放棄整個區段, 不是跳過本次"
    assert "放棄剩餘次數" in harness.log_text()


def test_跳出後動作可連外層區段一起跳出(harness):
    harness.vision.plan("a.png", [None])
    harness.run([
        here(),
        repeat(5),
        repeat(5),
        find("a.png", timeout=1, interval=0.1, on_fail="break"),
        repeat_end(on_break="break"),
        tap(1, 1),
        repeat_end(),
        tap(9, 9),
    ])
    assert harness.clicks() == [(9, 9)], "內層跳出時應連外層一起跳出"


def test_跳出後動作預設停在本層區段之後繼續(harness):
    harness.vision.plan("a.png", [None])
    harness.run([
        here(),
        repeat(5),
        repeat(5),
        find("a.png", timeout=1, interval=0.1, on_fail="break"),
        repeat_end(),
        tap(1, 1),
        repeat_end(),
        tap(9, 9),
    ])
    assert harness.clicks() == [(1, 1)] * 5 + [(9, 9)]


def test_不在任何區段內跳出等同停止流程(harness):
    harness.vision.plan("a.png", [None])
    harness.run([
        find("a.png", timeout=1, interval=0.1, on_fail="break"),
        tap(9, 9),
    ])
    assert harness.clicks() == []
    assert "不在任何區段內" in harness.log_text()

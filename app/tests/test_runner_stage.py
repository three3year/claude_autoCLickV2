"""執行器的`舞台`讓出行為.

拍板規則 (舊專案 ADR-0004; 並行執行未移植, 接縫與回歸網保留):
- 唯一的`讓出點`是進入`等待`步驟
- `找圖`從找到、點擊到「點擊後確認」是原子區段, 中途絕不讓出
- `找圖`輪詢的重試間隔不是`讓出點`
- 任何退出路徑都必須交還`舞台`
"""


from harness import (branch_end, branch_start, click, drag, find, key, wait)


def stage_events(harness):
    return [e[0] for e in harness.events if e[0] in ("acquire", "release", "leave")]


# ---------- 未注入舞台 ----------

def test_未注入舞台時完全不碰舞台(harness):
    """單流程執行的回歸保護: 整份既有測試都在這個模式下跑."""
    harness.run([click(1, 1), wait(100), click(2, 2)])
    assert harness.kinds() == ["click", "click"]


# ---------- 讓出點 ----------

def test_第一個動作之前先上台(harness):
    harness.run([click(1, 1)], stage=harness.make_stage())
    assert harness.kinds() == ["acquire", "click", "leave"]


def test_等待期間讓出舞台(harness):
    harness.run([click(1, 1), wait(3000), click(2, 2)],
                stage=harness.make_stage())
    assert harness.kinds() == [
        "acquire", "click", "release", "acquire", "click", "leave"]


def test_再短的等待也讓出(harness):
    """使用者明確選擇不設讓出門檻 (見 ADR-0004)."""
    harness.run([wait(200)], stage=harness.make_stage())
    assert stage_events(harness) == ["acquire", "release", "acquire", "leave"]


def test_點擊拖曳按鍵都不讓出(harness):
    harness.run([
        click(1, 1),
        drag(0, 0, 5, 5),
        key("enter"),
    ], stage=harness.make_stage())
    assert stage_events(harness) == ["acquire", "leave"]


def test_拖曳之後才讓出時紀錄會標註(harness):
    """已知的高風險組合: 拖曳→等待→相對點擊, 出問題時要查得到."""
    harness.run([drag(0, 0, 50, 50), wait(1000)], stage=harness.make_stage())
    assert "上一步是拖曳" in harness.log_text()


def test_一般的等待不會標註拖曳(harness):
    harness.run([click(1, 1), wait(1000)], stage=harness.make_stage())
    assert "上一步是拖曳" not in harness.log_text()


def test_單流程執行不會冒出讓出標註(harness):
    harness.run([drag(0, 0, 50, 50), wait(1000)])
    assert "讓出舞台" not in harness.log_text()


# ---------- 找圖的原子性 ----------

def test_找圖輪詢失敗不讓出(harness):
    harness.vision.plan("a.png", [None, None, None, (500, 400)])
    harness.run([find("a.png", interval=0.5)], stage=harness.make_stage())
    assert stage_events(harness) == ["acquire", "leave"], \
        "輪詢的重試間隔不是讓出點"


def test_找圖到點擊到確認生效是一個原子區段(harness):
    harness.vision.plan("a.png", [(500, 400), (500, 400), None])
    harness.run([find("a.png", confirm="gone", interval=0.5)],
                stage=harness.make_stage())
    assert harness.kinds() == ["acquire", "click", "click", "leave"], \
        "找到→點擊→補點→生效之間不得交接"


def test_等待消失期間不讓出(harness):
    harness.vision.plan("a.png", [(500, 400), (500, 400), None])
    harness.run([find("a.png", action="wait_gone", interval=0.5)],
                stage=harness.make_stage())
    assert stage_events(harness) == ["acquire", "leave"]


def test_分岔輪詢期間不讓出(harness):
    harness.vision.plan("a.png", [None, None, (500, 400)])
    harness.run([
        branch_start(),
        find("a.png", action="none", interval=0.5),
        branch_end(),
    ], stage=harness.make_stage())
    assert stage_events(harness) == ["acquire", "leave"]


# ---------- 退出一定交還舞台 ----------

def test_正常跑完交還舞台(harness):
    st = harness.make_stage()
    harness.run([click(1, 1)], stage=st)
    assert st.left == 1


def test_執行錯誤時交還舞台(harness):
    st = harness.make_stage()
    harness.vision.missing("gone.png")
    harness.run([find("gone.png")], stage=st)
    assert "找不到範本圖片" in harness.log_text()
    assert st.left == 1


def test_找不到圖停止流程時交還舞台(harness):
    st = harness.make_stage()
    harness.vision.plan("a.png", [None])
    harness.run([find("a.png", timeout=1, interval=0.1, onNotFound="stop")],
                stage=st)
    assert st.left == 1


def test_急停時交還舞台且不再回頭搶(harness):
    st = harness.make_stage()
    r = harness.make_runner(st)

    def interrupt(n):
        if n >= 5:
            r.stop()

    harness.clock.on_sleep = interrupt
    harness.start(r, [wait(60000), click(9, 9)])
    r._thread.join(10)
    harness.runner = r

    assert not r._thread.is_alive()
    assert harness.clicks() == []
    assert stage_events(harness) == ["acquire", "release", "leave"], \
        "被停止後不該再去搶舞台"
    assert st.left == 1


def test_排隊等舞台時被急停也能收工(harness):
    """卡在 acquire 的流程必須被喚醒, 否則連 leave 都執行不到, 其他流程陪葬."""
    st = harness.make_stage(block=True)
    r = harness.make_runner(st)
    harness.start(r, [click(1, 1)])
    harness.runner = r

    assert st.blocked.wait(3), "測試前提: 執行器應該卡在 acquire 排隊"
    r.stop()
    r._thread.join(5)

    assert not r._thread.is_alive(), "被停之後仍卡在 acquire"
    assert harness.clicks() == []
    assert st.left == 1, "任何退出路徑都必須交還舞台"


# ---------- 整場結束 ----------

def test_取得舞台回傳否代表整場已結束(harness):
    st = harness.make_stage(acquire_returns=[False])
    harness.run([click(1, 1)], stage=st)
    assert harness.clicks() == [], "整場已結束就不該再有任何動作"
    assert st.left == 1


def test_排隊期間整場結束時不執行後續步驟(harness):
    st = harness.make_stage(acquire_returns=[True, False])
    harness.run([click(1, 1), wait(3000), click(2, 2)], stage=st)
    assert harness.clicks() == [(1, 1)]
    assert st.left == 1

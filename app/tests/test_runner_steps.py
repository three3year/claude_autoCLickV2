from harness import click, find, here, tgt, wait


def test_等待確實停留指定時間(harness):
    t0 = harness.clock.t
    harness.run([wait(5)])
    assert harness.clock.t - t0 >= 5.0


def test_等待可被急停中斷(harness):
    r = harness.make_runner()

    def interrupt(n):
        if n >= 5:
            r.stop()

    harness.clock.on_sleep = interrupt
    t0 = harness.clock.t
    harness.start(r, [wait(60), click(1, 1)])
    r._thread.join(10)
    harness.runner = r

    assert not r._thread.is_alive()
    assert harness.clock.t - t0 < 60.0, "急停後不該把整段等待睡完"
    assert harness.clicks() == [], "急停後不該再執行後續步驟"
    assert "已停止" in harness.log_text()


def test_找圖點擊在找到的位置點下去(harness):
    harness.vision.plan("a.png", [None, None, (500, 400)])
    harness.run([find("a.png", interval=0.1)])
    assert harness.clicks() == [(500, 400)]


def test_找圖偏移套用在找到位置上(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", offset=[10, -20])])
    assert harness.clicks() == [(510, 380)]


def test_找圖僅等待出現不點擊(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", type="find")])
    assert harness.clicks() == []
    assert "找到" in harness.log_text()


def test_等待消失需先看到再消失才通過(harness):
    harness.vision.plan("a.png", [(500, 400), (500, 400), None])
    harness.run([find("a.png", type="wait_gone", interval=0.1)])
    assert "已消失" in harness.log_text()
    assert harness.clicks() == []


def test_等待消失從未出現算逾時失敗(harness):
    harness.vision.plan("a.png", [None])
    harness.run([find("a.png", type="wait_gone", timeout=1, interval=0.1)])
    assert "從未出現" in harness.log_text()


def test_等待消失仍未消失算逾時失敗(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", type="wait_gone", timeout=1, interval=0.1)])
    assert "仍未消失" in harness.log_text()


def test_找圖逾時未找到依找不到時跳過(harness):
    harness.vision.plan("a.png", [None])
    harness.run([here(), find("a.png", timeout=1, interval=0.1, on_fail="skip"),
                 click(9, 9)])
    assert "跳過" in harness.log_text()
    assert harness.clicks() == [(9, 9)], "跳過後應繼續執行後續步驟"


def test_找圖逾時未找到可停止整份流程(harness):
    harness.vision.plan("a.png", [None])
    harness.run([here(), find("a.png", timeout=1, interval=0.1, on_fail="stop"),
                 click(9, 9)])
    assert harness.clicks() == []
    assert "停止執行" in harness.log_text()


def test_範本遺失時停止並說明是哪一張(harness):
    harness.vision.missing("gone.png")
    harness.run([find("gone.png")])
    assert "找不到範本圖片" in harness.log_text()
    assert "gone.png" in harness.log_text()


def test_點擊後確認目標消失前會自動補點(harness):
    harness.vision.plan("a.png", [(500, 400), (500, 400), None])
    harness.run(retry_interval=0, steps=[find("a.png", confirm="gone", interval=0.1)])
    assert harness.clicks() == [(500, 400), (500, 400)], "沒生效要補點一次"
    assert "已生效" in harness.log_text()


def test_點擊後確認圖出現才算生效(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.vision.plan("ok.png", [None, (700, 700)])
    harness.run(retry_interval=0, steps=[find("a.png", confirm="appear", confirm_target=tgt("ok.png"),
                      interval=0.1)])
    assert harness.clicks() == [(500, 400), (500, 400)]
    assert "已生效" in harness.log_text()


def test_點擊後確認逾時未生效依找不到時處置(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", confirm="gone", timeout=1, interval=0.1,
                      on_fail="skip"),
                 click(9, 9)])
    assert "未確認生效" in harness.log_text()
    assert harness.clicks()[-1] == (509, 409), "跳過後應繼續執行後續步驟"


def test_找圖只擷取指定的搜尋範圍(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png")], scan_region=[100, 50, 800, 600])
    assert harness.grabs() == [(100, 50, 800, 600)]


def test_找到位置以擷取原點換算成螢幕座標(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png")], scan_region=[100, 50, 800, 600])
    assert harness.clicks() == [(500, 400)], "座標應是螢幕絕對座標, 不是範圍內偏移"

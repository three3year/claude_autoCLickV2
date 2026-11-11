"""執行器記下每一次執行的結果種類 (ended) 與錯誤原因 (error_reason). 串接靠它判斷一份流程的成敗."""

from harness import CAL_PAIR, cal, click, find, wait

ERROR_PREFIX = "執行錯誤: "


def error_line(harness, runner):
    [line] = [m for m in harness.logs(runner) if m.startswith(ERROR_PREFIX)]
    return line[len(ERROR_PREFIX):]


def run_again(harness, runner, steps, **kw):
    harness.start(runner, steps, **kw)
    runner._thread.join(10)
    assert not runner._thread.is_alive(), "執行緒逾時未結束"
    return runner


def test_找不到圖錯誤結束後再執行一次完成_結果是完成且沒有殘留原因(harness):
    harness.vision.plan("a", [None])
    r = harness.run([find("a", timeout=1, interval=0.2)])
    assert r.ended == "error" and r.error_reason

    harness.vision.plan("a", [(500, 400)])
    run_again(harness, r, [find("a")])
    assert r.ended == "done"
    assert r.error_reason is None



def test_錯誤結束時原因等於執行紀錄那行冒號後的文字(harness):
    harness.vision.plan("a", [None])
    r = harness.run([find("a", timeout=1, interval=0.2)])
    assert r.ended == "error"
    assert r.error_reason == error_line(harness, r)


def test_開頭校準找不到圖是錯誤_原因與紀錄一致(harness):
    harness.vision.plan(CAL_PAIR[0], [(100, 40)])
    harness.vision.plan(CAL_PAIR[1], [None])
    r = harness.run([click(10, 10)], calibration=cal())
    assert r.ended == "error"
    assert CAL_PAIR[1] in r.error_reason
    assert r.error_reason == error_line(harness, r)


def test_沒有校準對是錯誤_原因與紀錄一致(harness):
    r = harness.run([click(10, 10)], calibration=None)
    assert r.ended == "error"
    assert "校準對" in r.error_reason
    assert r.error_reason == error_line(harness, r)


def test_倍率出界是錯誤_原因與紀錄一致(harness):
    r = harness.run([click(10, 10)], scale=0.7)
    assert r.ended == "error"
    assert "×0.700" in r.error_reason
    assert r.error_reason == error_line(harness, r)


def test_錯誤結束後再執行一次被停止_結果是停止且沒有錯誤原因(harness):
    harness.vision.plan("a", [None])
    r = harness.run([find("a", timeout=1, interval=0.2)])
    assert r.ended == "error"

    harness.stop_after_calibration(r, 3)
    run_again(harness, r, [wait(60), click(1, 1)])
    assert r.ended == "stopped"
    assert r.error_reason is None


def test_執行中讀到的結果是還沒結束_不是上一次的結果(harness):
    harness.vision.plan("a", [None])
    r = harness.run([find("a", timeout=1, interval=0.2)])
    assert r.ended == "error"

    seen = []
    harness.clock.on_sleep = lambda _n: seen.append(
        (r.running, r.ended, r.error_reason))
    run_again(harness, r, [wait(1)])
    assert seen, "執行中應該有虛擬睡眠"
    assert all(s == (True, None, None) for s in seen)
    assert r.ended == "done"

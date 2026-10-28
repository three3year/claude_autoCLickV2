import pytest

from harness import click

from automation import runner as runner_mod


def test_開始延遲_補做間隔_忙碌出現等候是固定行為():
    import inspect
    params = inspect.signature(runner_mod.Runner.start).parameters
    assert params["start_delay"].default == runner_mod.START_DELAY == 3.0
    assert params["retry_interval"].default == runner_mod.RETRY_INTERVAL == 1.0
    assert params["busy_appear"].default == runner_mod.BUSY_APPEAR == 1.0
    assert "avoid_hover" not in params, "避開游標一律開"

DELAY_LINE = "3 秒後開始執行 (按 F12 可隨時停止)"
WAITING = "等待準備範本完成"


def cal_time(harness):
    return harness.vision.grab_times[0]


def prerun_logs(harness, r):
    logs = harness.logs(r)
    end = next(i for i, m in enumerate(logs) if m.startswith("開頭校準"))
    return logs[:end]


def start_and_join(harness, runner, **kw):
    harness.start(runner, [click(1, 1)], **kw)
    runner._thread.join(10)
    assert not runner._thread.is_alive(), "執行緒逾時未結束"
    return runner


def watch_prerun_per_load(harness, runner):
    seen = []
    harness.vision.after_each_load = lambda: seen.append(
        runner.status()["prerun"])
    return seen


def test_預載提早完成_等到到期才校準(harness):
    harness.vision.preload_cost = 1.0
    t0 = harness.clock.t
    r = harness.run([click(1, 1)], start_delay=3)
    assert r.ended == "done"
    assert cal_time(harness) - t0 == pytest.approx(3.0, abs=0.06)
    assert prerun_logs(harness, r) == [
        DELAY_LINE, "準備範本中…（2 張）", "範本就緒"]


def test_預載超過延遲_預載一完成就校準(harness):
    harness.vision.preload_cost = 2.0
    t0 = harness.clock.t
    r = harness.run([click(1, 1)], start_delay=3)
    assert r.ended == "done"
    assert cal_time(harness) - t0 == pytest.approx(4.0, abs=0.01), \
        "不再額外等一輪延遲"
    assert prerun_logs(harness, r) == [
        DELAY_LINE, "準備範本中…（2 張）", WAITING, "範本就緒"]


def test_按下後已超過延遲才啟動_不寫倒數_一定寫等待範本(harness):
    r = harness.run([click(1, 1)], start_delay=3, pressed_at=harness.clock.t - 5)
    assert r.ended == "done"
    assert prerun_logs(harness, r) == [
        "準備範本中…（2 張）", WAITING, "範本就緒"]


def test_按下執行早於執行器啟動_從按下起算(harness):
    t0 = harness.clock.t
    r = harness.run([click(1, 1)], start_delay=3, pressed_at=t0 - 1.0)
    assert r.ended == "done"
    assert cal_time(harness) - t0 == pytest.approx(2.0, abs=0.06)


def test_預載失敗_立刻報錯_不等倒數_不校準(harness):
    harness.vision.missing("cal_right")
    t0 = harness.clock.t
    r = harness.run([click(1, 1)], start_delay=3)
    assert r.ended == "error"
    assert harness.clock.t - t0 < 0.01, "不空等倒數"
    assert harness.vision.grabs == []
    assert harness.kinds() == []


def test_倒數剩餘等待中停止_不校準不送輸入(harness):
    runner = harness.make_runner()
    harness.clock.on_sleep = lambda n: runner.stop() if n == 5 else None
    start_and_join(harness, runner, start_delay=3)
    assert runner.ended == "stopped"
    assert harness.vision.grabs == []
    assert harness.kinds() == []


def test_預載超過延遲_預載途中停止_不校準不送輸入(harness):
    harness.vision.preload_cost = 2.0
    runner = harness.make_runner()
    harness.vision.after_each_load = runner.stop
    start_and_join(harness, runner, start_delay=3)
    assert runner.ended == "stopped"
    assert harness.vision.grabs == []
    assert harness.kinds() == []


def test_開跑前階段_到期前倒數中_到期後等待範本(harness):
    harness.vision.preload_cost = 2.0
    runner = harness.make_runner()
    seen = watch_prerun_per_load(harness, runner)
    start_and_join(harness, runner, start_delay=3)
    assert runner.ended == "done"
    assert seen == ["countdown", "templates"]


def test_啟動當下已到期_啟動當下與預載期間都是等待範本(harness):
    harness.vision.preload_cost = 0.5
    runner = harness.make_runner()
    seen = watch_prerun_per_load(harness, runner)
    at_first_log = []
    log = runner.log
    runner.log = lambda msg, level="info": (
        at_first_log or at_first_log.append(runner.status()["prerun"]),
        log(msg, level))
    start_and_join(harness, runner, start_delay=3, pressed_at=harness.clock.t - 5)
    assert runner.ended == "done"
    assert at_first_log == ["templates"], "不閃一下「倒數啟動中…」"
    assert seen == ["templates", "templates"]


def test_預載提早完成_剩餘倒數仍是倒數中(harness):
    harness.vision.preload_cost = 0.5
    runner = harness.make_runner()
    seen = []
    harness.clock.on_sleep = lambda n: seen.append(runner.status()["prerun"])
    start_and_join(harness, runner, start_delay=3)
    assert seen and set(seen[:10]) == {"countdown"}


def test_開頭校準時開跑前階段已清除(harness, monkeypatch):
    runner = harness.make_runner()
    seen = []

    def grab(region=None):
        seen.append(runner.status()["prerun"])
        return harness.vision.grab(region)

    monkeypatch.setattr(runner_mod.capture, "grab", grab)
    start_and_join(harness, runner, start_delay=3)
    assert runner.ended == "done"
    assert seen[0] is None, "開頭校準那次截圖時已不在開跑前階段"

"""`開始延遲`是時間下限 (start-delay-floor 票 01、02).

從按下「執行」那一刻算起, 到`開頭校準`之前至少要經過設定的秒數;
`範本預載`在倒數期間同時進行——提早完成就等到到期, 超過了就一完成就開始。
斷言對象: 執行紀錄的內容與順序、開頭校準那次截圖的虛擬時間、狀態回報的
開跑前階段。假引擎的 preload_cost 讓每載一張範本推進虛擬時鐘
(這些測試的流程只引用校準對, 預載名單恰 2 張)。
"""
import pytest

from harness import click

from automation import runner as runner_mod


def test_開始延遲_補做間隔_忙碌出現等候是固定行為():
    """不是設定: app 不傳, 執行器用常數 (參數只留給測試縮短虛擬時間)."""
    import inspect
    params = inspect.signature(runner_mod.Runner.start).parameters
    assert params["start_delay"].default == runner_mod.START_DELAY == 3.0
    assert params["retry_interval"].default == runner_mod.RETRY_INTERVAL == 1.0
    assert params["busy_appear"].default == runner_mod.BUSY_APPEAR == 1.0
    assert "avoid_hover" not in params, "避開游標一律開"

DELAY_LINE = "3 秒後開始執行 (按 F12 可隨時停止)"
WAITING = "等待準備範本完成"


def cal_time(harness):
    """開頭校準那次截圖的虛擬時間 (第一次擷取)."""
    return harness.vision.grab_times[0]


def prerun_logs(harness, r):
    """開跑前的紀錄 (到開頭校準那行之前)."""
    logs = harness.logs(r)
    end = next(i for i, m in enumerate(logs) if m.startswith("開頭校準"))
    return logs[:end]


def start_and_join(harness, runner, **kw):
    """啟動已建好的執行器並等它結束 (測試要先在 runner 上掛觀察點時用)."""
    harness.start(runner, [click(1, 1)], **kw)
    runner._thread.join(10)
    assert not runner._thread.is_alive(), "執行緒逾時未結束"
    return runner


def watch_prerun_per_load(harness, runner):
    """每載完一張範本 (執行器的回呼之後) 記下狀態回報的開跑前階段."""
    seen = []
    harness.vision.after_each_load = lambda: seen.append(
        runner.status()["prerun"])
    return seen


# ---------- 時間下限 (票 01) ----------

def test_預載提早完成_等到到期才校準(harness):
    harness.vision.preload_cost = 1.0      # 預載共 2 秒
    t0 = harness.clock.t
    r = harness.run([click(1, 1)], start_delay=3)
    assert r.ended == "done"
    assert cal_time(harness) - t0 == pytest.approx(3.0, abs=0.06)
    assert prerun_logs(harness, r) == [
        DELAY_LINE, "準備範本中…（2 張）", "範本就緒"]


def test_預載超過延遲_預載一完成就校準(harness):
    harness.vision.preload_cost = 2.0      # 預載共 4 秒
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
    # 預載瞬間完成, 之後的 sleep 全是剩餘倒數; 第 5 拍 (0.25 秒) 時按停止
    harness.clock.on_sleep = lambda n: runner.stop() if n == 5 else None
    start_and_join(harness, runner, start_delay=3)
    assert runner.ended == "stopped"
    assert harness.vision.grabs == []
    assert harness.kinds() == []


def test_預載超過延遲_預載途中停止_不校準不送輸入(harness):
    harness.vision.preload_cost = 2.0      # 預載共 4 秒, 到期後沒有剩餘等待
    runner = harness.make_runner()
    harness.vision.after_each_load = runner.stop
    start_and_join(harness, runner, start_delay=3)
    assert runner.ended == "stopped"
    assert harness.vision.grabs == []
    assert harness.kinds() == []


# ---------- 開跑前階段 (票 02) ----------

def test_開跑前階段_到期前倒數中_到期後等待範本(harness):
    harness.vision.preload_cost = 2.0      # 第 1 張載完 t=2 (未到期), 第 2 張 t=4
    runner = harness.make_runner()
    seen = watch_prerun_per_load(harness, runner)
    start_and_join(harness, runner, start_delay=3)
    assert runner.ended == "done"
    assert seen == ["countdown", "templates"]


def test_啟動當下已到期_啟動當下與預載期間都是等待範本(harness):
    harness.vision.preload_cost = 0.5
    runner = harness.make_runner()
    seen = watch_prerun_per_load(harness, runner)
    at_first_log = []   # 第一行紀錄 (準備範本中…) 寫出時, 還沒做過任何到期檢查
    log = runner.log
    runner.log = lambda msg, level="info": (
        at_first_log or at_first_log.append(runner.status()["prerun"]),
        log(msg, level))
    start_and_join(harness, runner, start_delay=3, pressed_at=harness.clock.t - 5)
    assert runner.ended == "done"
    assert at_first_log == ["templates"], "不閃一下「倒數啟動中…」"
    assert seen == ["templates", "templates"]


def test_預載提早完成_剩餘倒數仍是倒數中(harness):
    harness.vision.preload_cost = 0.5      # 預載 1 秒, 剩 2 秒倒數 (40 拍)
    runner = harness.make_runner()
    seen = []
    harness.clock.on_sleep = lambda n: seen.append(runner.status()["prerun"])
    start_and_join(harness, runner, start_delay=3)
    assert seen and set(seen[:10]) == {"countdown"}   # 前 10 拍都還在倒數


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

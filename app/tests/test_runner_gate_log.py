"""執行紀錄說清楚哪一關沒過 (scale-range 票 02).

找圖逾時的執行紀錄寫沒過的那一關與該關分數 (粗篩/驗證/比色), 不再只印「最高相似度」;
生效確認逾時的 `input.confirm` 檔案紀錄帶最高分與沒過的那一關; 手動停止落在找圖或
生效確認的輪詢裡時, 先寫一筆結果為 stopped 的檔案紀錄再停止。
"""
from harness import click, drag, find, here, miss, tgt


def records(harness, event="find.target", role=None):
    out = harness.filelog.of(event)
    return [r for r in out if role is None or r.get("role") == role]


# ---------- 找圖逾時: 哪一關沒過 ----------

def test_粗篩沒過_訊息印粗篩最高分(harness):
    harness.vision.plan("a", [miss("match", 0.59)])
    r = harness.run([find("a", timeout=1, interval=0.5, onNotFound="skip")])
    msg = next(m for m in harness.logs(r) if "未找到「a」" in m)
    assert "粗篩最高 0.590" in msg
    assert "最高相似度" not in msg


def test_驗證沒過_訊息印驗證最高分(harness):
    harness.vision.plan("a", [miss("verify", 0.72)])
    r = harness.run([find("a", timeout=1, interval=0.5, onNotFound="skip")])
    msg = next(m for m in harness.logs(r) if "未找到「a」" in m)
    assert "驗證最高 0.720" in msg


def test_比色沒過_訊息同時印比色與圖形分數(harness):
    harness.vision.plan("btn", [[(500, 400, 0.974, 0.942)]])
    r = harness.run([find("btn", target={"colorCheck": True}, timeout=1,
                          interval=0.5, onNotFound="skip")])
    msg = next(m for m in harness.logs(r) if "未找到「btn」" in m)
    assert "比色最高 0.942（圖形 0.974）" in msg


def test_分數取輪詢中該關的最高(harness):
    harness.vision.plan("a", [miss("match", 0.40), miss("match", 0.59),
                              miss("match", 0.50)])
    r = harness.run([find("a", timeout=1, interval=0.5, onNotFound="skip")])
    msg = next(m for m in harness.logs(r) if "未找到「a」" in m)
    assert "粗篩最高 0.590" in msg


def test_挑選規則挑不到照現狀印數量(harness):
    harness.vision.plan("card", [[(200, 300), (400, 300)]])
    r = harness.run([find("card", target={"pick": {"kind": "top", "n": 3}},
                          timeout=1, interval=0.5, onNotFound="skip")])
    msg = next(m for m in harness.logs(r) if "未找到「card」" in m)
    assert "找到 2 個，挑選規則挑不到" in msg


def test_等待消失從未出現也印哪一關(harness):
    harness.vision.plan("a", [miss("verify", 0.66)])
    r = harness.run([find("a", action="wait_gone", timeout=1, interval=0.5,
                          onNotFound="skip")])
    msg = next(m for m in harness.logs(r) if "從未出現" in m)
    assert "驗證最高 0.660" in msg


# ---------- 生效確認逾時的檔案紀錄 ----------

def test_座標點擊確認圖逾時_紀錄帶最高分與沒過的那一關(harness):
    harness.vision.plan("ok", [miss("verify", 0.71)])
    harness.run([here(), click(100, 100, confirm="appear", confirmTarget=tgt("ok"),
                       timeout=1, interval=0.5, onNotFound="skip")])
    [rec] = records(harness, "input.confirm")
    assert rec["result"] == "timeout"
    assert (rec["best"], rec["failed"]) == ("0.710", "verify")


def test_拖曳原點的圖離開逾時_紀錄寫仍在原位與它的分數(harness):
    harness.vision.plan("anchor", [(500, 400, 0.93)])
    harness.run([find("anchor", action="none"),
                 drag(0, 100, 0, -200, mode="prev", confirm="gone",
                      timeout=1, interval=0.5, onNotFound="skip")])
    [rec] = records(harness, "input.confirm")
    assert rec["result"] == "timeout"
    assert (rec["best"], rec["failed"]) == ("0.930", "still_there")


def test_座標點擊確認圖逾時_訊息印哪一關(harness):
    harness.vision.plan("ok", [miss("match", 0.55)])
    r = harness.run([here(), click(100, 100, confirm="appear", confirmTarget=tgt("ok"),
                           timeout=1, interval=0.5, onNotFound="skip")])
    msg = next(m for m in harness.logs(r) if "未見確認圖「ok」" in m)
    assert "粗篩最高 0.550" in msg


def test_找圖點擊確認圖逾時_find_target紀錄與訊息(harness):
    harness.vision.plan("a", [(100, 100)])
    harness.vision.plan("ok", [miss("verify", 0.70)])
    r = harness.run([find("a", confirm="appear", confirmTarget=tgt("ok"),
                          interval=0.5, timeout=1, onNotFound="skip")])
    [rec] = records(harness, role="confirm_appear")
    assert (rec["result"], rec["best"], rec["failed"]) == ("timeout", "0.700",
                                                            "verify")
    msg = next(m for m in harness.logs(r) if "未確認生效" in m)
    assert "驗證最高 0.700" in msg


def test_等待消失仍未消失_紀錄帶仍在原位的分數與still_there(harness):
    harness.vision.plan("a", [(300, 300, 0.93)])
    harness.run([find("a", action="wait_gone", timeout=1, interval=0.5,
                      onNotFound="skip")])
    [rec] = records(harness, role="wait_gone")
    assert (rec["result"], rec["best"], rec["failed"]) == ("not_gone", "0.930", "still_there")


def test_找圖點擊目標圖沒消失_紀錄帶still_there(harness):
    harness.vision.plan("a", [(300, 300, 0.91)])
    harness.run([find("a", confirm="gone", timeout=1, interval=0.5,
                      onNotFound="skip")], retry_interval=0)
    [rec] = records(harness, role="confirm_gone")
    assert (rec["result"], rec["failed"]) == ("not_gone", "still_there")


# ---------- 手動停止也寫最後一筆 ----------

def _stop_at(harness, n_sleep):
    """第 n_sleep 次 time.sleep 之後按下停止 (可中斷等待每 0.05s 睡一次: 0.5s 的
    輪詢間隔＝10 次)."""
    def interrupt(n):
        if n >= n_sleep:
            harness.runner.stop()
    harness.clock.on_sleep = interrupt


def _run_stopping(harness, steps, n_sleep=3, **kw):
    r = harness.make_runner()
    harness.runner = r
    _stop_at(harness, n_sleep)
    harness.start(r, steps, **kw)
    r._thread.join(10)
    assert not r._thread.is_alive()
    return r


def test_手動停止落在找圖輪詢裡_寫一筆stopped帶最高分與那一關(harness):
    harness.vision.plan("a", [miss("match", 0.58)])
    r = _run_stopping(harness, [find("a", timeout=60, interval=0.5)])
    assert r.ended == "stopped"
    [rec] = records(harness, role="find")
    assert (rec["result"], rec["best"], rec["failed"]) == ("stopped", "0.580",
                                                            "match")
    assert rec["polls"] >= 1


def test_手動停止落在座標點擊確認裡_input_confirm寫stopped(harness):
    harness.vision.plan("ok", [miss("verify", 0.73)])
    r = _run_stopping(harness, [here(), click(100, 100, confirm="appear",
                                      confirmTarget=tgt("ok"), timeout=60,
                                      interval=0.5)], n_sleep=15)
    assert r.ended == "stopped"
    [rec] = records(harness, "input.confirm")
    assert (rec["result"], rec["best"], rec["failed"]) == ("stopped", "0.730",
                                                            "verify")


def test_手動停止落在找圖點擊確認裡_confirm紀錄寫stopped(harness):
    harness.vision.plan("a", [(100, 100)])
    harness.vision.plan("ok", [miss("match", 0.5)])
    r = _run_stopping(harness, [find("a", confirm="appear",
                                     confirmTarget=tgt("ok"), timeout=60,
                                     interval=0.5)], n_sleep=15)
    assert r.ended == "stopped"
    [f] = records(harness, role="find")
    assert f["result"] == "found"
    [c] = records(harness, role="confirm_appear")
    assert (c["result"], c["failed"]) == ("stopped", "match")


def test_手動停止落在等待消失裡_寫stopped(harness):
    harness.vision.plan("a", [(300, 300)])
    r = _run_stopping(harness, [find("a", action="wait_gone", timeout=60,
                                     interval=0.5)])
    assert r.ended == "stopped"
    [rec] = records(harness, role="wait_gone")
    assert rec["result"] == "stopped"
    assert rec["picked"] == "(280,290,40,20)", "記下看到的位置"


def test_停止前已找到的不多寫(harness):
    harness.vision.plan("a", [(300, 300)])
    r = _run_stopping(harness, [find("a"), {"type": "wait", "ms": 5000}],
                      n_sleep=2)
    assert r.ended == "stopped"
    assert [rec["result"] for rec in records(harness)] == ["found"]


def test_手動停止落在分岔輪詢裡_每個分支寫stopped(harness):
    from harness import branch_end, branch_or, branch_start
    harness.vision.plan("x", [miss("match", 0.3)])
    harness.vision.plan("y", [miss("verify", 0.7)])
    r = _run_stopping(harness, [branch_start(), find("x"), click(1, 1),
                                branch_or(), find("y"), click(2, 2),
                                branch_end()])
    assert r.ended == "stopped"
    by = {rec["step"]: rec for rec in records(harness, role="branch")}
    assert by[2]["result"] == "stopped" and by[2]["failed"] == "match"
    assert by[5]["result"] == "stopped" and by[5]["best"] == "0.700"

from harness import drag, find, here

from automation import flowdefaults


def test_找圖補齊_找不到時預設停止_輪詢預設0點3秒():
    s = flowdefaults.complete({"type": "find_click", "target": {"template": "a"}})
    assert (s["on_fail"], s["timeout"], s["interval"]) == ("stop", 5, 0.3)
    assert (s["confirm"], s["offset"], s["busy_check"], s["update_origin"]) == (
        "none", [0, 0], False, True)


def test_不點擊的找圖沒有生效確認與忙碌檢查欄位():
    for t in ("find", "wait_gone"):
        s = flowdefaults.complete({"type": t, "target": {"template": "a"}})
        assert "confirm" not in s and "busy_check" not in s, t
        assert s["on_fail"] == "stop", t


def test_沒設生效確認的點擊不補等待欄位_設了才補():
    s = flowdefaults.complete({"type": "click", "click": [1, 2]})
    assert not set(flowdefaults.WAIT) & set(s)
    s = flowdefaults.complete({"type": "click", "click": [1, 2], "confirm": "next"})
    assert (s["timeout"], s["interval"], s["on_fail"]) == (5, 0.3, "stop")


def test_拖曳缺時間用0點5秒():
    s = flowdefaults.complete({"type": "drag", "drag": [0, 0], "to": [0, 9]})
    assert (s["duration"], s["hold"]) == (0.5, 0.5)


def test_已寫的值不動_預設的串列不共用():
    a = flowdefaults.complete({"type": "find", "target": {"template": "a"},
                               "on_fail": "skip"})
    b = flowdefaults.complete({"type": "find", "target": {"template": "b"}})
    assert a["on_fail"] == "skip"
    a["offset"][0] = 99
    assert b["offset"] == [0, 0]


def test_拿掉等於預設的欄位_補齊再拿掉回到原樣():
    raw = {"type": "find_click", "target": {"template": "a"}, "timeout": 2,
           "on_fail": "skip", "busy_check": True}
    assert flowdefaults.strip(flowdefaults.complete(raw)) == raw
    raw = {"type": "drag", "drag": [1, 2], "to": [3, 4], "confirm": "gone"}
    assert flowdefaults.strip(flowdefaults.complete(raw)) == raw


def test_沒等待的步驟丟掉多餘的等待欄位():
    s = flowdefaults.complete({"type": "click", "click": [0, 0], "timeout": 3})
    assert "timeout" not in s


def test_新增步驟是完整步驟():
    s = flowdefaults.new_step("find_click")
    assert s["type"] == "find_click" and s["target"] == {"template": ""}
    assert s["on_fail"] == "stop"
    assert flowdefaults.new_step("repeat_end") == {"type": "repeat_end",
                                                    "on_break": "continue"}


def test_找圖沒寫找不到時_找不到就停止流程(harness):
    harness.vision.plan("a", [None])
    r = harness.run([here(), find("a", timeout=1), find("b")])
    assert r.ended == "error"
    assert "停止執行" in harness.log_text(r)
    assert "b" not in harness.lookups(), "停在 a, 後面不執行"


def test_拖曳沒寫時間_用0點5秒拖並停0點5秒(harness):
    harness.run([here(), drag(0, 0, 0, 100)])
    [ev] = [e for e in harness.events if e[0] == "drag"]
    assert ev[6:] == (500, 500), "duration_ms, hold_ms"

"""執行紀錄寫入 autoclick.log (find-target 票 06).

每個`找圖目標`的判定結束 (找到、逾時、無法執行) 寫一筆 `find.target`:
步驟位置、範本、限定矩形、每個匹配的位置與分數 (含比色分數)、挑選規則與挑中
哪個、點擊落點; 逾時另記最後一次查詢的最高分與未過原因。不逐次輪詢地寫。
實跑回報點錯後, Claude 靠它分辨「點錯哪個」與「沒找到」。
"""
from harness import branch_end, branch_or, branch_start, click, find, tgt

CARDS = [(200, 300), (400, 300), (600, 300), (800, 300)]


def records(harness, role=None):
    out = harness.filelog.of("find.target")
    return [r for r in out if role is None or r["role"] == role]


def test_找到時一筆_含每個匹配與挑中哪個與點擊落點(harness):
    harness.vision.plan("card", [CARDS])
    harness.run([find("card", target={"pick": {"kind": "top", "n": 3}},
                      offsetX=5)])
    [r] = records(harness)
    assert (r["step"], r["role"], r["template"], r["result"]) == \
        (1, "find", "card", "found")
    assert r["pick"] == "top:3"
    assert r["limit"] == "all"
    for x, y in CARDS:
        assert f"({x - 20},{y - 10},40,20) 0.990" in r["matches"]
    assert r["picked"] == "(580,290,40,20)"
    assert r["click"] == "(605,300)"


def test_輪詢多次只寫一筆(harness):
    harness.vision.plan("a", [None, None, None, (500, 400)])
    harness.run([find("a", interval=0.1)])
    assert len(records(harness)) == 1
    assert records(harness)[0]["polls"] == 4


def test_逾時記最後一次查詢的最高分與未過原因(harness):
    harness.vision.plan("a", [None])
    harness.run([find("a", timeout=1, interval=0.2, onNotFound="skip")])
    [r] = records(harness)
    assert r["result"] == "timeout"
    assert r["failed"] == "match"
    assert "best" in r and "click" not in r


def test_逾時原因_數不到N個(harness):
    harness.vision.plan("card", [CARDS[:2]])
    harness.run([find("card", target={"pick": {"kind": "left", "n": 3}},
                      timeout=1, interval=0.2, onNotFound="skip")])
    [r] = records(harness)
    assert (r["result"], r["failed"]) == ("timeout", "count")
    assert r["matches"].count("0.990") == 2


def test_逾時原因_比色門檻_並記下比色分數(harness):
    harness.vision.plan("btn", [[(500, 400, 0.97, 0.88)]])
    harness.run([find("btn", target={"colorCheck": True}, timeout=1,
                      interval=0.2, onNotFound="skip")])
    [r] = records(harness)
    assert (r["failed"], r["color"]) == ("color", "on")
    assert "c0.880" in r["rejected"]


def test_找到時記比色分數(harness):
    harness.vision.plan("btn", [[(500, 400, 0.97, 0.99)]])
    harness.run([find("btn", target={"colorCheck": True})])
    [r] = records(harness)
    assert "(480,390,40,20) 0.970 c0.990" in r["matches"]


def test_無法執行也寫一筆(harness):
    near = {"pick": {"kind": "near", "x": 0, "y": 0}}
    harness.run([find("card", target=near)])
    [r] = records(harness)
    assert (r["result"], r["failed"]) == ("cannot_run", "origin")


def test_記下實際的限定矩形(harness):
    harness.vision.plan("btn", [[(1800, 1000)]])
    harness.run([find("btn", target={"limit": {"kind": "rect", "x": 1280,
                                               "y": 720, "w": 640, "h": 360}})])
    [r] = records(harness)
    assert r["limit"] == "(1280,720,640,360)"


def test_點擊後確認_目標圖消失的判定也有紀錄(harness):
    harness.vision.plan("card", [CARDS, CARDS, CARDS[:2]])
    harness.run(retry_interval=0, steps=[find("card", target={"pick": {"kind": "top", "n": 3}},
                      confirm="gone", interval=0.1)])
    [f] = records(harness, "find")
    [c] = records(harness, "confirm_gone")
    assert c["result"] == "gone" and c["step"] == 1
    assert c["clicks"] == 2, "初次點擊＋補點一次"


def test_確認圖與下一步的判定各有紀錄(harness):
    harness.vision.plan("a", [(100, 100)])
    harness.vision.plan("ok", [None, (500, 500)])
    harness.vision.plan("b", [None, (700, 700)])
    harness.run([find("a", confirm="appear", confirmTarget=tgt("ok"),
                      interval=0.1),
                 find("a", confirm="next", interval=0.1),
                 find("b", interval=0.1)])
    [ap] = records(harness, "confirm_appear")
    assert (ap["template"], ap["result"]) == ("ok", "found")
    [nx] = records(harness, "confirm_next")
    assert (nx["template"], nx["step"], nx["result"]) == ("b", 2, "found")


def test_點擊後確認逾時也有紀錄(harness):
    harness.vision.plan("a", [(100, 100)])
    harness.vision.plan("ok", [None])
    harness.run([find("a", confirm="appear", confirmTarget=tgt("ok"),
                      interval=0.2, timeout=1, onNotFound="skip")])
    [ap] = records(harness, "confirm_appear")
    assert ap["result"] == "timeout"


def test_等待消失的判定一筆(harness):
    harness.vision.plan("a", [(300, 300), (300, 300), None])
    harness.run([find("a", action="wait_gone", interval=0.1)])
    [r] = records(harness)
    assert (r["role"], r["result"]) == ("wait_gone", "gone")
    assert r["picked"] == "(280,290,40,20)", "記先前挑中的位置"


def test_分岔條件的判定有紀錄(harness):
    harness.vision.plan("x", [None])
    harness.vision.plan("y", [None, (300, 300)])
    harness.run([branch_start(), find("x"), click(1, 1), branch_or(),
                 find("y"), click(2, 2), branch_end()])
    [b] = records(harness, "branch")
    assert (b["template"], b["step"], b["result"]) == ("y", 5, "found")


def test_寫進真的檔案日誌(tmp_path, monkeypatch):
    """沒注入時寫 applog (exe／repo 旁的 autoclick.log)."""
    import applog
    from automation import runner as runner_mod
    path = tmp_path / "autoclick.log"
    monkeypatch.setattr(applog, "_path", str(path))
    runner_mod._applog("find.target", step=3, template="a", result="found")
    text = path.read_text(encoding="utf-8")
    assert "find.target" in text and "step=3" in text and "template=a" in text


def test_分岔條件沒有原點_紀錄寫無法執行(harness):
    near = {"pick": {"kind": "near", "x": 0, "y": 0}}
    harness.vision.plan("y", [None])
    harness.run([branch_start(), find("x", target=near), click(1, 1),
                 branch_or(), find("y"), click(2, 2), branch_end()])
    by_step = {r["step"]: r for r in records(harness, "branch")}
    assert (by_step[2]["result"], by_step[2]["failed"]) == ("cannot_run",
                                                             "origin")
    assert by_step[5]["result"] == "timeout"

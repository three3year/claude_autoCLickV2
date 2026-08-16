"""`範本預載` (startup-speed 票 04): 執行前一次收集並載入流程引用的範本.

名單收集是純函式直測; 執行路徑用 harness 驗「預載恰在流程動作前發生
一次、失敗報明錯誤且不開跑」。
"""
from harness import (branch_end, branch_or, branch_start, click, find, loop,
                     loop_end, wait)

from automation.runner import flow_templates


# ---------- 名單收集 (純函式) ----------

def test_收集找圖範本_依出現順序去重():
    steps = [find("a"), wait(10), find("b"), find("a")]
    assert flow_templates(steps) == ["a", "b"]


def test_確認圖appear一併收集():
    steps = [find("a", confirm="appear", confirmTemplate="ok")]
    assert flow_templates(steps) == ["a", "ok"]


def test_點到下一步的圖出現_下一步範本已涵蓋():
    steps = [find("a", confirm="next"), find("b")]
    assert flow_templates(steps) == ["a", "b"]


def test_分岔條件與區段內找圖_自然涵蓋():
    steps = [loop(2), branch_start(), find("c1"), click(1, 2),
             branch_or(), find("c2"), branch_end(), loop_end()]
    assert flow_templates(steps) == ["c1", "c2"]


def test_非找圖步驟與空名不收集():
    steps = [click(1, 2), wait(5), {"type": "find_click", "template": ""}]
    assert flow_templates(steps) == []


def test_不點擊的找圖沒有確認圖語意():
    steps = [find("a", action="none", confirm="appear", confirmTemplate="x")]
    assert flow_templates(steps) == ["a"]  # 確認只有點擊時有意義


# ---------- 執行路徑 (harness) ----------

def test_執行前預載一次_名單含確認圖(harness):
    harness.vision.plan("a", [(500, 400)])
    harness.vision.plan("ok", [(600, 300)])
    r = harness.run([find("a", confirm="appear", confirmTemplate="ok")])
    assert r.ended == "done"
    assert harness.vision.preloads == [["a", "ok"]]
    assert harness.clicks()  # 預載後流程照常執行

def test_沒有找圖步驟_不預載(harness):
    r = harness.run([click(10, 20), wait(5)])
    assert r.ended == "done"
    assert harness.vision.preloads == []


def test_預載缺範本_報明錯誤且不開跑(harness):
    harness.vision.missing("nope")
    r = harness.run([find("a"), find("nope")])
    assert r.ended == "error"
    assert harness.vision.lookups == []   # 一步都沒查 (沒開跑)
    assert harness.clicks() == []
    assert "範本預載失敗" in harness.log_text(r)
    assert "nope" in harness.log_text(r)


def test_預載炸掉_報明錯誤且不開跑(harness):
    harness.vision.preload_error = RuntimeError("embedding.npy 損壞")
    r = harness.run([find("a")])
    assert r.ended == "error"
    assert harness.clicks() == []
    assert "範本預載失敗" in harness.log_text(r)
    assert "損壞" in harness.log_text(r)

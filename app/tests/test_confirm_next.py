"""「點到下一步的圖出現」(confirm: "next") 的執行與相連檢查回歸測試.

執行語意: 找到本步的圖 → 點一次 → 補點迴圈以「執行清單中下一步的範本圖
出現」為生效條件; 確認對象依清單位置現算 (不記名)。
"""
from harness import branch_end, branch_start, click, find, repeat, repeat_end, wait

from automation import runner as runner_mod


# ---------- 「找圖相連」檢查純函式 ----------

def test_相連_下一步為找圖三態皆合法():
    for action in ("click", "none", "wait_gone"):
        steps = [find("a", confirm="next"), find("b", action=action)]
        assert runner_mod.confirm_next_connected(steps, 0), action


def test_不相連_最後一步():
    assert not runner_mod.confirm_next_connected([find("a", confirm="next")], 0)


def test_不相連_下一步為區段標記或其他類型():
    others = (repeat(2), repeat_end(), branch_start(), branch_or_step(),
              branch_end(), wait(0.1), click(1, 2),
              drag_step())
    for nxt in others:
        steps = [find("a", confirm="next"), nxt]
        assert not runner_mod.confirm_next_connected(steps, 0), nxt["type"]


def branch_or_step():
    return {"type": "branch_or"}


def drag_step():
    return {"type": "drag", "drag": [0, 0], "to": [1, 1]}


def test_uses_confirm_next_只認動作為點擊的找圖步驟():
    assert runner_mod.uses_confirm_next(find("a", confirm="next"))
    assert not runner_mod.uses_confirm_next(find("a", confirm="appear"))
    assert not runner_mod.uses_confirm_next(find("a"))
    # 「不點擊」時確認無意義 (對話框也不會存出, 這裡守防禦)
    assert not runner_mod.uses_confirm_next(
        find("a", type="find", confirm="next"))
    assert not runner_mod.uses_confirm_next(click(1, 2))


# ---------- 執行路徑 (runner) ----------

def test_點到下一步的圖出現前會自動補點(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.vision.plan("b.png", [None, (700, 700)])
    harness.run(retry_interval=0, steps=[find("a.png", confirm="next", interval=0.1),
                 find("b.png", interval=0.1)])
    # a 點一次沒生效 → 補點一次; b 出現後進下一步、b 自己被點到
    assert harness.clicks() == [(500, 400), (500, 400), (700, 700)]
    assert "已生效" in harness.log_text()


def test_逾時未見下一步的圖依找不到時處置(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.vision.plan("b.png", [None])
    harness.run([find("a.png", confirm="next", timeout=1, interval=0.5),
                 find("b.png", timeout=1, interval=0.5),
                 click(9, 9)])
    assert "未見下一步的圖「b.png」" in harness.log_text()
    assert harness.clicks()[-1] == (509, 409), "跳過後應繼續執行後續步驟 (原點＝點 a 的落點)"


def test_下一步是僅等待出現也能當確認條件(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.vision.plan("b.png", [None, (700, 700)])
    harness.run(retry_interval=0, steps=[find("a.png", confirm="next", interval=0.1),
                 find("b.png", type="find", interval=0.1)])
    assert harness.clicks() == [(500, 400), (500, 400)], "b 僅等待, 不該被點"
    assert "已生效" in harness.log_text()


def test_下一步是等待消失也能當確認條件(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.vision.plan("b.png", [None, (700, 700), (700, 700), None])
    harness.run(retry_interval=0, steps=[find("a.png", confirm="next", interval=0.1),
                 find("b.png", type="wait_gone", interval=0.1)])
    assert harness.clicks() == [(500, 400), (500, 400)]
    assert "已生效" in harness.log_text()
    assert "已消失" in harness.log_text()


def test_下一步不相連時警告退化為不確認並繼續(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", confirm="next", interval=0.1),
                 click(9, 9)])
    assert harness.clicks() == [(500, 400), (509, 409)], "點一次就走, 不補點"
    assert "下一步不是找圖" in harness.log_text()
    assert harness.runner.ended == "done"


def test_最後一步用點到下一步同樣退化不崩潰(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.run([find("a.png", confirm="next", interval=0.1)])
    assert harness.clicks() == [(500, 400)]
    assert harness.runner.ended == "done"


def test_分岔分支內的找圖也能點到下一步(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.vision.plan("b.png", [None, (700, 700)])
    harness.run(retry_interval=0, steps=[branch_start(),
                 find("a.png", confirm="next", interval=0.1),
                 find("b.png", interval=0.1),
                 branch_end()])
    assert harness.clicks() == [(500, 400), (500, 400), (700, 700)]
    assert "已生效" in harness.log_text()


def test_重排後確認對象依位置跟隨新的下一步(harness):
    # 同一個步驟 dict 不記名: 換個位置執行, 確認對象就是新的下一步
    a = find("a.png", confirm="next", interval=0.1)
    b = find("b.png", interval=0.1)
    c = find("c.png", interval=0.1)
    r1 = harness.run([a, b, c])
    assert "下一步的圖「b.png」" in harness.log_text(r1)
    r2 = harness.run([a, c, b])
    assert "下一步的圖「c.png」" in harness.log_text(r2)


def test_確認成功訊息不改寫含出現二字的範本名(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.vision.plan("出現鈕.png", [(700, 700)])
    harness.run([find("a.png", confirm="next", interval=0.1),
                 find("出現鈕.png", interval=0.1)])
    assert "下一步的圖「出現鈕.png」已出現" in harness.log_text()


def test_補點更新原點供相對座標使用(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.vision.plan("b.png", [None, (700, 700)])
    harness.run(retry_interval=0, steps=[find("a.png", confirm="next", interval=0.1),
                 find("b.png", type="find", update_origin=False, interval=0.1),
                 click(7, 3)])
    assert harness.clicks() == [(500, 400), (500, 400), (507, 403)]


def test_勾掉更新原點時補點不影響原點(harness):
    harness.vision.plan("a.png", [(500, 400)])
    harness.vision.plan("b.png", [None, (700, 700)])
    harness.run(retry_interval=0, steps=[find("a.png", confirm="next", update_origin=False, interval=0.1),
                 find("b.png", type="find", update_origin=False, interval=0.1),
                 click(7, 3)])
    assert harness.clicks() == [(500, 400), (500, 400)]
    assert "尚無原點" in harness.log_text()

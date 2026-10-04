"""執行器的找圖點都照`找圖目標`判定 (find-target 票 03).

假偵測器可安排一次查詢有多個匹配 (harness.Vision.plan 的「一串位置」);
斷言點在哪、是否算消失、走哪個分支。框一律 40×20, 中心即安排的座標。
"""
from harness import branch_end, branch_or, branch_start, click, find, tgt

CARDS = [(200, 300), (400, 300), (600, 300), (800, 300)]   # 一排四張同款
TOP = {"pick": {"kind": "top", "n": 3}}


def test_四張同款時由上到下第3點到第三張(harness):
    harness.vision.plan("card", [CARDS])
    harness.run([find("card", target=TOP)])
    assert harness.clicks() == [(600, 300)]


def test_匹配不足N個繼續等_等到了才點(harness):
    harness.vision.plan("card", [CARDS[:2], CARDS[:2], CARDS])
    harness.run([find("card", target=TOP, interval=0.1)])
    assert harness.clicks() == [(600, 300)]


def test_匹配不足N個到逾時走找不到時_絕不退而點別個(harness):
    harness.vision.plan("card", [CARDS[:2]])
    harness.run([find("card", target=TOP, timeout=1, interval=0.2,
                      onNotFound="skip")])
    assert harness.clicks() == []
    assert "未找到" in harness.log_text()


def test_沒設挑選規則點分數最高的(harness):
    harness.vision.plan("card", [[(200, 300, 0.91), (600, 300, 0.98),
                                  (400, 300, 0.95)]])
    harness.run([find("card")])
    assert harness.clicks() == [(600, 300)]


def test_同款仍在時目標圖消失照樣成立_只看被點的位置(harness):
    others = [CARDS[0], CARDS[1], CARDS[3]]
    harness.vision.plan("card", [CARDS, others])
    harness.run([find("card", target=TOP, confirm="gone", interval=0.1)])
    assert harness.clicks() == [(600, 300)], "被點的那張不在了＝生效, 不補點"
    assert "已生效" in harness.log_text()


def test_被點的位置仍有匹配就補點那個位置(harness):
    harness.vision.plan("card", [CARDS, CARDS, CARDS[:2]])
    harness.run([find("card", target=TOP, confirm="gone", interval=0.1)])
    assert harness.clicks() == [(600, 300), (600, 300)]


def test_等待消失看先前挑中的位置_別處同款不影響(harness):
    harness.vision.plan("card", [CARDS, CARDS, [CARDS[0], CARDS[3]]])
    r = harness.run([find("card", target=TOP, action="wait_gone",
                          interval=0.1, timeout=5)])
    assert "已消失" in harness.log_text()
    assert r.ended == "done"


def test_等待消失_挑中位置一直在就逾時(harness):
    harness.vision.plan("card", [CARDS])
    harness.run([find("card", target=TOP, action="wait_gone", interval=0.2,
                      timeout=1, onNotFound="skip")])
    assert "仍未消失" in harness.log_text()


def test_點到下一步的圖出現套用下一步的挑選規則(harness):
    harness.vision.plan("a", [(100, 100)])
    harness.vision.plan("card", [CARDS[:2], CARDS])
    harness.run([find("a", confirm="next", interval=0.1),
                 find("card", target=TOP, interval=0.1)])
    # 下一步要第三張: 只有兩張時還不算出現 → 補點 a; 四張到齊才生效
    assert harness.clicks() == [(100, 100), (100, 100), (600, 300)]


def test_點到下一步的圖出現用點擊後的原點(harness):
    near = {"pick": {"kind": "near", "base": "origin", "x": 0, "y": 0}}
    harness.vision.plan("a", [(100, 100)])
    harness.vision.plan("card", [CARDS])
    # a 不更新原點, 之前也沒有任何原點 → 下一步的找圖目標無從判定
    r = harness.run([find("a", confirm="next", updateOrigin=False,
                          interval=0.1),
                     find("card", target=near, interval=0.1)])
    assert r.ended == "done"
    assert harness.clicks() == [(100, 100)], "確認無法判定 → 以不確認執行, 下一步無原點跳過"
    harness2_steps = [find("a", confirm="next", interval=0.1),
                      find("card", target=near, interval=0.1)]
    harness.events.clear()
    harness.run(harness2_steps)
    # 點擊後原點＝(100,100) → 最接近的是 (200,300)
    assert harness.clicks() == [(100, 100), (200, 300)]


def test_確認圖套用自己的挑選規則(harness):
    harness.vision.plan("a", [(100, 100)])
    harness.vision.plan("ok", [[(500, 500)], [(500, 500), (500, 700)]])
    two = tgt("ok", pick={"kind": "top", "n": 2})
    harness.run([find("a", confirm="appear", confirmTarget=two, interval=0.1)])
    assert harness.clicks() == [(100, 100), (100, 100)]
    assert "確認圖「ok」已出現" in harness.log_text()


def test_分支條件套用條件步驟的找圖目標(harness):
    harness.vision.plan("x", [[(100, 100)]])
    harness.vision.plan("y", [(300, 300)])
    second = {"pick": {"kind": "top", "n": 2}}
    harness.run([branch_start(),
                 find("x", target=second), click(1, 1),
                 branch_or(),
                 find("y"), click(2, 2),
                 branch_end()])
    assert harness.clicks() == [(300, 300), (2, 2)], "x 只有一個匹配, 第 2 個不成立"


def test_以原點為基準卻沒有原點_步驟無法執行而跳過(harness):
    near = {"pick": {"kind": "near", "base": "origin", "x": 0, "y": 0}}
    harness.vision.plan("card", [CARDS])
    r = harness.run([find("card", target=near, onNotFound="stop")])
    assert r.ended == "done", "與相對座標同處理: 跳過, 不走找不到時"
    assert harness.clicks() == []
    assert harness.vision.lookups == []
    assert "尚無原點" in harness.log_text()

"""執行器的找圖點都照`找圖目標`判定 (find-target 票 03).

假偵測器可安排一次查詢有多個匹配 (harness.Vision.plan 的「一串位置」);
斷言點在哪、是否算消失、走哪個分支。框一律 40×20, 中心即安排的座標。
"""
from harness import branch_end, branch_or, branch_start, click, find, tgt

CARDS = [(200, 300), (400, 300), (600, 300), (800, 300)]   # 一排四張同款
TOP = {"pick": {"top": 3}}


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
                      on_fail="skip")])
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
    harness.run(retry_interval=0, steps=[find("card", target=TOP, confirm="gone", interval=0.1)])
    assert harness.clicks() == [(600, 300), (600, 300)]


def test_等待消失看先前挑中的位置_別處同款不影響(harness):
    harness.vision.plan("card", [CARDS, CARDS, [CARDS[0], CARDS[3]]])
    r = harness.run([find("card", target=TOP, type="wait_gone",
                          interval=0.1, timeout=5)])
    assert "已消失" in harness.log_text()
    assert r.ended == "done"


def test_等待消失_挑中位置一直在就逾時(harness):
    harness.vision.plan("card", [CARDS])
    harness.run([find("card", target=TOP, type="wait_gone", interval=0.2,
                      timeout=1, on_fail="skip")])
    assert "仍未消失" in harness.log_text()


def test_點到下一步的圖出現套用下一步的挑選規則(harness):
    harness.vision.plan("a", [(100, 100)])
    harness.vision.plan("card", [CARDS[:2], CARDS])
    harness.run(retry_interval=0, steps=[find("a", confirm="next", interval=0.1),
                 find("card", target=TOP, interval=0.1)])
    # 下一步要第三張: 只有兩張時還不算出現 → 補點 a; 四張到齊才生效
    assert harness.clicks() == [(100, 100), (100, 100), (600, 300)]


def test_點到下一步的圖出現用點擊後的原點(harness):
    near = {"pick": {"near": [0, 0]}}
    harness.vision.plan("a", [(100, 100)])
    harness.vision.plan("card", [CARDS])
    # a 不更新原點, 之前也沒有任何原點 → 下一步的找圖目標無從判定
    r = harness.run([find("a", confirm="next", update_origin=False,
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
    two = tgt("ok", pick={"top": 2})
    harness.run(retry_interval=0, steps=[find("a", confirm="appear", confirm_target=two, interval=0.1)])
    assert harness.clicks() == [(100, 100), (100, 100)]
    assert "確認圖「ok」已出現" in harness.log_text()


def test_分支條件套用條件步驟的找圖目標(harness):
    harness.vision.plan("x", [[(100, 100)]])
    harness.vision.plan("y", [(300, 300)])
    second = {"pick": {"top": 2}}
    harness.run([branch_start(),
                 find("x", target=second), click(1, 1),
                 branch_or(),
                 find("y"), click(2, 2),
                 branch_end()])
    assert harness.clicks() == [(300, 300), (302, 302)], "x 只有一個匹配, 第 2 個不成立"


def test_以原點為基準卻沒有原點_步驟無法執行而跳過(harness):
    near = {"pick": {"near": [0, 0]}}
    harness.vision.plan("card", [CARDS])
    r = harness.run([find("card", target=near, on_fail="stop")])
    assert r.ended == "done", "與相對座標同處理: 跳過, 不走找不到時"
    assert harness.clicks() == []
    assert harness.lookups() == []
    assert "尚無原點" in harness.log_text()


# ---------- 比色 (票 04) ----------

def test_開比色的點擊步驟_按鈕變灰就判定目標圖消失(harness):
    orange, grey = (500, 400, 0.99, 0.99), (500, 400, 0.99, 0.88)
    harness.vision.plan("btn", [[orange], [grey]])
    harness.run([find("btn", target={"color": True}, confirm="gone",
                      interval=0.1)])
    assert harness.clicks() == [(500, 400)], "灰掉＝不再是匹配＝已消失, 不補點"
    assert "已生效" in harness.log_text()


def test_不開比色時灰色按鈕仍算在_會一直補點(harness):
    orange, grey = (500, 400, 0.99, 0.99), (500, 400, 0.99, 0.88)
    harness.vision.plan("btn", [[orange], [grey]])
    harness.run([find("btn", confirm="gone", interval=0.2, timeout=1,
                      on_fail="skip")])
    assert len(harness.clicks()) > 1


def test_灰色按鈕開比色時不會被點(harness):
    harness.vision.plan("btn", [[(500, 400, 0.99, 0.88)]])
    harness.run([find("btn", target={"color": True}, timeout=1,
                      interval=0.2, on_fail="skip")])
    assert harness.clicks() == []


# ---------- 限定範圍 (票 05) ----------
# harness 的搜尋範圍預設 (0, 0, 1920, 1080)、座標基準點 (0, 0)

BOTTOM_RIGHT = {"within": [1280, 720, 640, 360]}


def test_限定範圍外的同款不被找到也不被點(harness):
    harness.vision.plan("btn", [[(100, 100, 0.99), (1800, 1000, 0.90)]])
    harness.run([find("btn", target=BOTTOM_RIGHT)])
    assert harness.clicks() == [(1800, 1000)]


def test_目標不在限定範圍內時逾時走找不到時(harness):
    harness.vision.plan("btn", [[(100, 100)]])
    r = harness.run([find("btn", target=BOTTOM_RIGHT,
                          timeout=1, interval=0.2, on_fail="stop")])
    assert harness.clicks() == []
    assert r.ended == "error"


# ---------- 固定矩形 (busy-pause-fixed-rect 票 03; coord-anchor 票 04 改相對基準點) ----------
# harness 的搜尋範圍預設 (0, 0, 1920, 1080)、座標基準點預設 (0, 0)

FIXED = {"within": [960, 540, 480, 270]}


def _find_rec(harness, role="find"):
    return [r for r in harness.filelog.of("find.target") if r["role"] == role]


def test_固定矩形_只在基準點加偏移那一塊裡找(harness):
    harness.vision.plan("btn", [[(100, 100, 0.99), (1000, 600, 0.90)]])
    harness.run([find("btn", target=FIXED)])
    assert harness.clicks() == [(1000, 600)]
    [rec] = _find_rec(harness)
    assert rec["limit"] == "(960,540,480,270)"


def test_固定矩形_跟著基準點走_不跟搜尋範圍(harness):
    harness.vision.plan("btn", [(1200, 700)])
    harness.run([find("btn", target=FIXED)], scan_region=[200, 100, 1500, 900],
                anchor=(240, 160))
    assert harness.clicks() == [(1200, 700)]
    [rec] = _find_rec(harness)
    assert rec["limit"] == "(1200,700,480,270)"


def test_固定矩形_隨畫面倍率換算(harness):
    harness.vision.plan("btn", [(1300, 700)])
    harness.run([find("btn", target=FIXED)], scale=1.1)
    [rec] = _find_rec(harness)
    assert rec["limit"] == "(1056,594,528,297)", "位置與大小都 ×1.1"


def test_固定矩形_不合法就不找_逾時走找不到時(harness):
    harness.vision.plan("btn", [(1000, 600)])
    bad = {"within": [960, 540, 0, 270]}
    r = harness.run([find("btn", target=bad, timeout=1, interval=0.2,
                          on_fail="stop")])
    assert r.ended == "error" and harness.clicks() == []
    assert "btn" not in harness.lookups(), "絕不退回整個搜尋範圍"


def test_確認圖也能用固定矩形(harness):
    harness.vision.plan("a", [(100, 100)])
    harness.vision.plan("ok", [[(300, 300)], [(300, 300), (1000, 600)]])
    r = harness.run([find("a", confirm="appear",
                          confirm_target=tgt("ok", **FIXED), interval=0.2,
                          timeout=2, on_fail="stop")])
    assert r.ended == "done"
    [rec] = _find_rec(harness, "confirm_appear")
    assert rec["limit"] == "(960,540,480,270)"
    assert rec["picked"] == "(980,590,40,20)"


def test_固定矩形_倍率換算後超出搜尋範圍的部分照裁(harness):
    corner = {"within": [1600, 900, 400, 200]}
    harness.vision.plan("btn", [(1800, 1000)])
    harness.run([find("btn", target=corner)], scale=1.1)
    [rec] = _find_rec(harness)
    assert rec["limit"] == "(1760,990,160,90)", \
        "×1.1 → (1760,990) 440×220, 右下角 (2200,1210) 裁到搜尋範圍"
    assert harness.clicks() == [(1800, 1000)]

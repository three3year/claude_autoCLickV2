"""`找圖目標`模組 (find-target 票 03/05): 解析並執行一個找圖目標.

直接用假偵測器 (harness.Vision) 驅動: 給定畫面上有哪些匹配與找圖目標的設定,
斷言回報的匹配 (螢幕座標)、挑中哪一個、沒挑到的原因、位置是否仍有匹配。
假偵測器的匹配框一律 40×20 (中心即安排的座標)。
"""
from harness import Vision

from automation import findtarget

REGION = (100, 50, 1200, 900)   # 搜尋範圍 (螢幕座標 x, y, w, h)


def run(hits, target=None, origin=None, scale=1.0, region=REGION):
    """畫面上同時有 hits 這幾個匹配 (螢幕座標的框中心), 執行一次找圖目標."""
    vision = Vision()
    vision.plan("t", [list(hits)] if hits else [None])
    screen, org = vision.grab(region)
    tgt = dict({"template": "t"}, **(target or {}))
    return findtarget.find(tgt, vision, screen, org, origin=origin,
                           scale=scale), vision


def center(m):
    x, y, w, h = m.box
    return x + w // 2, y + h // 2


def picked(hits, **kw):
    r, _ = run(hits, **kw)
    return center(r.picked) if r.picked else None


def test_匹配以螢幕座標回報():
    r, _ = run([(300, 200), (700, 600)])
    assert sorted(center(m) for m in r.matches) == [(300, 200), (700, 600)]


def test_預設挑分數最高():
    hits = [(300, 200, 0.90), (700, 600, 0.97), (500, 400, 0.93)]
    assert picked(hits) == (700, 600)


def test_由上到下第N_先排列再排同列由左到右():
    grid = [(500, 300), (200, 500), (300, 300), (700, 300)]
    top = {"pick": {"kind": "top", "n": 1}}
    assert picked(grid, target=top) == (300, 300)
    assert picked(grid, target={"pick": {"kind": "top", "n": 3}}) == (700, 300)
    assert picked(grid, target={"pick": {"kind": "top", "n": 4}}) == (200, 500)


def test_中心高度差不到半個框高視為同一列():
    # 框高 20: 差 8 → 同列, 照左右排; 差 12 → 不同列, 高的先
    assert picked([(600, 292), (400, 300)],
                  target={"pick": {"kind": "top", "n": 1}}) == (400, 300)
    assert picked([(600, 288), (400, 300)],
                  target={"pick": {"kind": "top", "n": 1}}) == (600, 288)


def test_由左到右第N_同欄再由上到下():
    # 框寬 40: x 差 15 → 同欄
    hits = [(800, 200), (300, 600), (315, 200), (550, 400)]
    left = {"pick": {"kind": "left", "n": 1}}
    assert picked(hits, target=left) == (315, 200)
    assert picked(hits, target={"pick": {"kind": "left", "n": 2}}) == (300, 600)
    assert picked(hits, target={"pick": {"kind": "left", "n": 4}}) == (800, 200)


def test_匹配不足N個就是沒挑到():
    r, _ = run([(300, 200), (700, 600)],
               target={"pick": {"kind": "top", "n": 3}})
    assert r.picked is None
    assert r.reason == "count"
    assert len(r.matches) == 2, "匹配照樣回報 (供紀錄)"


def test_沒有匹配就是沒挑到():
    r, _ = run([])
    assert r.picked is None and r.reason == "none"


def test_最接近指定點_以搜尋範圍左上為基準():
    near = {"pick": {"kind": "near", "base": "region", "x": 500, "y": 300}}
    # 指定點＝(100+500, 50+300)＝(600, 350)
    assert picked([(300, 300), (650, 380), (900, 350)], target=near) == (650, 380)


def test_最接近指定點_以原點為基準():
    near = {"pick": {"kind": "near", "base": "origin", "x": -100, "y": 0}}
    assert picked([(300, 300), (650, 380), (900, 410)], target=near,
                  origin=(1000, 400)) == (900, 410)


def test_指定點隨畫面倍率換算():
    near = {"pick": {"kind": "near", "base": "origin", "x": 100, "y": 0}}
    hits = [(600, 400), (700, 400)]
    assert picked(hits, target=near, origin=(500, 400)) == (600, 400)
    assert picked(hits, target=near, origin=(500, 400), scale=2.0) == (700, 400)


def test_以原點為基準卻沒有原點_無法執行且不查詢():
    near = {"pick": {"kind": "near", "base": "origin", "x": 0, "y": 0}}
    r, vision = run([(300, 300)], target=near, origin=None)
    assert r.picked is None and r.reason == "origin"
    assert vision.lookups == []
    assert findtarget.needs_origin({"template": "t", **near})
    assert not findtarget.needs_origin({"template": "t"})


def test_位置是否仍有匹配_容差約半個框():
    r, _ = run([(300, 200), (700, 600)])
    box = next(m.box for m in r.matches if center(m) == (300, 200))
    moved, _ = run([(315, 205), (700, 600)])      # 偏 15/5 < 半框 20/10
    assert center(findtarget.still_there(box, moved.matches)) == (315, 205)
    gone, _ = run([(330, 200), (700, 600)])       # 偏 30 > 半框寬 20
    assert findtarget.still_there(box, gone.matches) is None


# ---------- 比色 (票 04) ----------

def test_比色開關傳到偵測器():
    _, vision = run([(300, 200)], target={"colorCheck": True})
    assert vision.color_checks == [("t", True)]
    _, vision = run([(300, 200)])
    assert vision.color_checks == [("t", False)]


def test_比色不符的不算進第N個():
    # 第三個值是分數, 第四個是比色分數 (假偵測器以 0.95 為門檻)
    hits = [(200, 300, 0.99, 0.99), (400, 300, 0.99, 0.80),
            (600, 300, 0.99, 0.98), (800, 300, 0.99, 0.97)]
    second = {"pick": {"kind": "left", "n": 2}, "colorCheck": True}
    assert picked(hits, target=second) == (600, 300)
    r, _ = run(hits, target={"colorCheck": True})
    assert len(r.matches) == 3
    assert all(m.color >= 0.95 for m in r.matches)

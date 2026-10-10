"""`找圖目標`模組 (find-target 票 03/05): 解析並執行一個找圖目標.

直接用假偵測器 (harness.Vision) 驅動: 給定畫面上有哪些匹配與找圖目標的設定,
斷言回報的匹配 (螢幕座標)、挑中哪一個、沒挑到的原因、位置是否仍有匹配。
假偵測器的匹配框一律 40×20 (中心即安排的座標)。
"""
from harness import Vision

from automation import findtarget

REGION = (100, 50, 1200, 900)   # 搜尋範圍 (螢幕座標 x, y, w, h)
ANCHOR = (300, 150)             # `座標基準點` (螢幕座標)


def run(hits, target=None, origin=None, scale=1.0, region=REGION,
        anchor=ANCHOR):
    """畫面上同時有 hits 這幾個匹配 (螢幕座標的框中心), 執行一次找圖目標."""
    vision = Vision()
    vision.plan("t", [list(hits)] if hits else [None])
    screen, org = vision.grab(region)
    tgt = dict({"template": "t"}, **(target or {}))
    return findtarget.find(tgt, vision, screen, org, origin=origin,
                           scale=scale, anchor=anchor), vision


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


# ---------- 最接近指定點: 只以`原點`為基準 (coord-anchor 票 06) ----------

def test_最接近指定點_原點加偏移():
    near = {"pick": {"kind": "near", "x": -100, "y": 0}}
    assert picked([(300, 300), (650, 380), (900, 410)], target=near,
                  origin=(1000, 400)) == (900, 410)


def test_偏移零就是最接近原點():
    near = {"pick": {"kind": "near", "x": 0, "y": 0}}
    assert picked([(300, 300), (650, 380), (900, 410)], target=near,
                  origin=(640, 390)) == (650, 380)


def test_指定點隨畫面倍率換算():
    near = {"pick": {"kind": "near", "x": 100, "y": 0}}
    hits = [(600, 400), (700, 400)]
    assert picked(hits, target=near, origin=(500, 400)) == (600, 400)
    assert picked(hits, target=near, origin=(500, 400), scale=2.0) == (700, 400)


def test_指定點與搜尋範圍框法無關():
    near = {"pick": {"kind": "near", "x": 100, "y": 0}}
    hits = [(600, 400), (700, 400)]
    assert picked(hits, target=near, origin=(500, 400),
                  region=(0, 0, 1920, 1080)) == (600, 400)
    assert picked(hits, target=near, origin=(500, 400),
                  region=(400, 300, 800, 600)) == (600, 400)


def test_以原點為基準卻沒有原點_無法執行且不查詢():
    near = {"pick": {"kind": "near", "x": 0, "y": 0}}
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


# ---------- 限定範圍 (票 05) ----------

def test_沒設限定範圍就是整個搜尋範圍():
    r, _ = run([(300, 200)])
    assert r.limit is None


def test_最接近指定點不受限定範圍裁切影響():
    tgt = {"limit": {"kind": "rect", "x": 600, "y": 600, "w": 400, "h": 200},
           "pick": {"kind": "near", "x": 300, "y": 200}}
    # 固定矩形 (900,750) 400×200 裁到搜尋範圍底 → (900,750,400,200); 指定點 (1200,900)
    r, _ = run([(1000, 800), (1250, 900)], target=tgt, origin=(900, 700))
    assert center(r.picked) == (1250, 900)


# ---------- 編輯器用的純邏輯 (票 07) ----------

def test_組找圖目標_預設值不寫進存檔():
    assert findtarget.make_target("a") == {"template": "a"}
    assert findtarget.make_target(
        "a", limit={"kind": "rect", "x": 3, "y": 1, "w": 10, "h": 20},
        pick={"kind": "top", "n": 2}, color=True) == {
        "template": "a", "limit": {"kind": "rect", "x": 3, "y": 1, "w": 10, "h": 20},
        "pick": {"kind": "top", "n": 2}, "colorCheck": True}
    assert findtarget.make_target("a", limit={"kind": "grid", "cells": [1]},
                                  pick={"kind": "score"}) == {"template": "a"}, \
        "九宮格已退場: 不寫進存檔"


def test_拾取的螢幕位置反除畫面倍率存成基準尺度():
    # 與相對座標拾取一致: (螢幕位置 − 基準點) ÷ 倍率
    assert findtarget.offset_from_screen((650, 280), (500, 300), 1.0) == (150, -20)
    assert findtarget.offset_from_screen((650, 280), (500, 300), 2.0) == (75, -10)


def test_步驟清單的簡短標記():
    assert findtarget.tags({"template": "a"}) == []
    assert findtarget.tags({"template": "a", "colorCheck": True,
                            "pick": {"kind": "top", "n": 3},
                            "limit": {"kind": "rect", "x": 0, "y": 0,
                                      "w": 9, "h": 9}}) == \
        ["限定", "由上到下第3", "比色"]
    assert findtarget.tags({"template": "a",
                            "pick": {"kind": "near", "x": 0, "y": 0}}) == \
        ["最接近指定點"]


def test_設定摘要():
    assert findtarget.summary({"template": "a"}) == "整個搜尋範圍；分數最高；不比色"
    text = findtarget.summary({
        "template": "a", "colorCheck": True,
        "pick": {"kind": "near", "x": 10, "y": 20}})
    assert text == "整個搜尋範圍；最接近原點 (+10,+20)；比色"
    assert findtarget.summary({"template": "a",
                               "limit": {"kind": "rect", "x": -5, "y": 40,
                                         "w": 300, "h": 60},
                               "pick": {"kind": "left", "n": 2}}) == \
        "固定矩形 (-5,+40) 300×60；由左到右第 2 個；不比色"
    assert findtarget.pick_text({"pick": {"kind": "near", "x": -3, "y": 4}}) == \
        "near(-3,+4)"


def test_畫面倍率同時當預期尺度交給偵測器():
    """flow-scale: 一個倍率兩個用途——像素設定 ×它, 查詢時當`預期尺度`."""
    _, vision = run([(300, 200)], scale=0.9)
    assert vision.expected_scales == [("t", 0.9)]


# ---------- 固定矩形: 相對`座標基準點` (coord-anchor 票 04) ----------
# 存的是相對基準點的偏移與寬高 (流程尺度); ANCHOR＝(300, 150), REGION＝(100, 50, 1200, 900)

def rect(x, y, w, h):
    return {"limit": {"kind": "rect", "x": x, "y": y, "w": w, "h": h}}


def test_固定矩形_查詢區域是基準點加偏移():
    r, _ = run([(700, 600), (300, 200)], target=rect(100, 350, 600, 225))
    assert r.limit == (400, 500, 600, 225)
    assert [center(m) for m in r.matches] == [(700, 600)]


def test_固定矩形_基準點移動後跟著移動_與搜尋範圍框法無關():
    tgt = rect(100, 350, 600, 225)
    r, _ = run([], target=tgt, anchor=(500, 250))
    assert r.limit == (600, 600, 600, 225)
    r, _ = run([], target=tgt, region=(0, 0, 1920, 1080))
    assert r.limit == (400, 500, 600, 225), "搜尋範圍框得鬆緊不影響"
    r, _ = run([], target=tgt, region=(95, 45, 1210, 910))
    assert r.limit == (400, 500, 600, 225)


def test_固定矩形_隨畫面倍率換算():
    r, _ = run([], target=rect(100, 350, 600, 225), scale=2.0)
    assert r.limit == (500, 850, 800, 100), "右下角也 ×2, 再裁到搜尋範圍底"
    r, _ = run([], target=rect(50, 25, 100, 50), scale=0.5)
    assert r.limit == (325, 163, 50, 25), "25×0.5＝12.5 進位成 13"


def test_固定矩形_不需要原點_但需要座標基準點():
    tgt = rect(100, 350, 600, 225)
    assert not findtarget.needs_origin(tgt)
    assert findtarget.needs_anchor(tgt)
    assert not findtarget.needs_anchor({"template": "t"})
    r, vision = run([(700, 600)], target=tgt, origin=None)
    assert center(r.picked) == (700, 600)
    r, vision = run([(700, 600)], target=tgt, anchor=None)
    assert r.picked is None and r.reason == "anchor" and r.failed == "anchor"
    assert vision.lookups == []


def test_固定矩形_超出搜尋範圍的部分被裁掉():
    r, _ = run([], target=rect(700, -500, 600, 2000))
    assert r.limit == (1000, 50, 300, 900)


def test_固定矩形_數值不合法或沒有交集_不找也不退成整個範圍():
    bad = [rect(0.5, 0, 10, 10), rect(0, 0, 0, 10), rect(0, 0, 10, -1),
           rect("a", 0, 10, 10), rect(True, 0, 10, 10),
           {"limit": {"kind": "rect", "x": 1}}, rect(5000, 0, 10, 10)]
    for tgt in bad:
        r, vision = run([(300, 300)], target=tgt)
        assert r.picked is None and r.matches == [], tgt
        assert vision.lookups == [], tgt
        assert r.limit[2] == 0 or r.limit[3] == 0, tgt


def test_固定矩形_標記與摘要():
    tgt = dict({"template": "a"}, **rect(100, 350, 600, 225))
    assert findtarget.tags(tgt) == ["限定"]
    assert findtarget.tag_text(tgt) == "〔限定〕"
    assert findtarget.summary(tgt) == "固定矩形 (+100,+350) 600×225；分數最高；不比色"
    assert findtarget.limit_text({"kind": "rect", "x": 0.1}) == "固定矩形（設定無效）"


def test_框選的螢幕矩形換算成相對基準點_倍率反除():
    lim = findtarget.fixed_rect_from_screen((400, 500, 600, 225), ANCHOR, 1.0)
    assert lim == {"kind": "rect", "x": 100, "y": 350, "w": 600, "h": 225}
    r, _ = run([], target={"limit": lim})
    assert r.limit == (400, 500, 600, 225), "換算回來是同一塊"
    lim = findtarget.fixed_rect_from_screen((400, 500, 600, 226), ANCHOR, 2.0)
    assert lim == {"kind": "rect", "x": 50, "y": 175, "w": 300, "h": 113}


def test_框選超出搜尋範圍也照存_執行時才裁():
    lim = findtarget.fixed_rect_from_screen((0, 0, 400, 350), ANCHOR, 1.0)
    assert lim == {"kind": "rect", "x": -300, "y": -150, "w": 400, "h": 350}
    r, _ = run([], target={"limit": lim})
    assert r.limit == (100, 50, 300, 300)

"""流程存檔的座標空間與換算 (純函式; 詞彙見 app/CONTEXT.md「座標與原點」).

存檔裡所有的座標數值 (`絕對座標`、`固定矩形`、範本拍攝位置) 都是相對`座標基準點`
的偏移、`流程尺度` (ADR 0012)。座標基準點＝`校準對`第一張圖的中心, 執行開頭與每次
拾取當下量得, 不存檔。這裡的兩個換算是執行器、編輯器、換算工具共用的唯一實作::

    存檔座標 → 螢幕:  基準點 + 偏移 ×畫面倍率   (to_screen / rect_to_screen)
    螢幕 → 存檔座標:  (螢幕 − 基準點) ÷ 倍率     (from_screen / rect_from_screen)

同一組數字在不同座標空間下意思不同, 所以存檔帶 `coordSpace` 標記; 不是現行值
(`anchor`) 的一律是舊格式——拒絕開啟 (舊格式沒記當時視窗在哪, 自動換算會靜靜換錯)。
"""
import math

COORD_SPACE = "coordSpace"
ANCHOR = "anchor"   # 現行: 座標相對`座標基準點` (ADR 0012)
# 舊值只在拒絕時認: "region"＝相對搜尋範圍左上角, 沒標記＝螢幕座標 (更早)

_ABS_KEYS = {"click": (("x", "y"),), "drag": (("x1", "y1"), ("x2", "y2"))}


def scale_px(v, k):
    """偏移量 ×`畫面倍率`後四捨五入為整數像素 (負值對稱進位); k=1 恆等.

    所有換算共用這一個進位規則, 兩邊才不會因捨入方向不同而各差 1px。
    """
    x = float(v) * k
    r = int(math.floor(abs(x) + 0.5))
    return r if x >= 0 else -r


def is_anchor_space(data):
    """這份流程資料的座標是否已相對`座標基準點` (不是＝舊格式)."""
    return isinstance(data, dict) and data.get(COORD_SPACE) == ANCHOR


# ================= 存檔座標 ⇄ 螢幕座標 =================

def to_screen(xy, anchor, k=1.0):
    """存檔座標 (相對基準點的偏移, 流程尺度) → 螢幕座標."""
    return (int(anchor[0]) + scale_px(xy[0], k), int(anchor[1]) + scale_px(xy[1], k))


def from_screen(xy, anchor, k=1.0):
    """螢幕座標 → 存檔座標 (相對基準點的偏移, 反除倍率換回流程尺度)."""
    return (scale_px(xy[0] - int(anchor[0]), 1.0 / k),
            scale_px(xy[1] - int(anchor[1]), 1.0 / k))


def rect_to_screen(rect, anchor, k=1.0):
    """存檔的矩形 {x, y, w, h} (相對基準點) → 螢幕矩形 (x, y, w, h).

    右下角各自換算再相減, 與左上角同一套捨入, 寬高才不會差 1px。
    """
    x0, y0 = to_screen((rect["x"], rect["y"]), anchor, k)
    x1, y1 = to_screen((rect["x"] + rect["w"], rect["y"] + rect["h"]), anchor, k)
    return (x0, y0, x1 - x0, y1 - y0)


def rect_from_screen(box, anchor, k=1.0):
    """螢幕矩形 (x, y, w, h) → 存檔的矩形 {x, y, w, h} (相對基準點, 流程尺度)."""
    x, y = from_screen(box[:2], anchor, k)
    return {"x": x, "y": y, "w": scale_px(box[2], 1.0 / k),
            "h": scale_px(box[3], 1.0 / k)}


# ================= 流程裡的絕對座標 =================

def abs_steps(steps):
    """流程中使用`絕對座標`的步驟 (1-based 序號, 步驟)."""
    return [(i + 1, s) for i, s in enumerate(steps)
            if s.get("type") in _ABS_KEYS and s.get("mode", "abs") == "abs"]


def remap_flow(data, point_fn, rect_fn=None):
    """整份流程資料裡存下的座標逐個重算 (就地); 回傳改動筆數.

    point_fn((x, y)) → 新偏移: 絕對座標 (座標點擊、拖曳兩端點); rect_fn({x, y, w, h}) →
    新矩形: `固定矩形` (步驟的找圖目標、確認圖、流程層級的忙碌指示), None＝不動矩形。
    相對座標、以原點為基準的設定不是相對基準點, 不動。
    """
    changed = 0
    steps = data.get("steps") or []
    for _, s in abs_steps(steps):
        for kx, ky in _ABS_KEYS[s["type"]]:
            s[kx], s[ky] = point_fn((int(s[kx]), int(s[ky])))
            changed += 1
    if rect_fn is None:
        return changed
    targets = [s.get(k) for s in steps for k in ("target", "confirmTarget")]
    targets.append(data.get("busyTarget"))
    for t in targets:
        lim = t.get("limit") if isinstance(t, dict) else None
        if isinstance(lim, dict) and lim.get("kind") == "rect":
            lim.update(rect_fn(lim))
            changed += 1
    return changed


def shift_flow(data, old_anchor, new_anchor, k=1.0):
    """換`校準對`＝換座標基準點 (ADR 0012): 所有存下的座標改成相對新基準點; 回傳改動筆數.

    每個座標都先用舊基準點換到螢幕 (這次的倍率 k), 再用新基準點換回來——
    落點在捨入誤差內不變 (流程尺度存整數, 誤差 ≤ k/2 px; 倍率 1 時完全不變),
    不另外累積一次四捨五入。範本拍攝位置由工作區自己重算 (Workspace.shift_pos, 同一對換算)。
    """
    return remap_flow(
        data,
        lambda xy: from_screen(to_screen(xy, old_anchor, k), new_anchor, k),
        lambda r: rect_from_screen(rect_to_screen(r, old_anchor, k), new_anchor, k))

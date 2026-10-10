"""流程存檔的座標空間與換算 (純函式; 詞彙見 app/CONTEXT.md「座標與原點」).

存檔裡所有的座標數值 (`固定矩形`、範本拍攝位置) 都是相對`座標基準點`
的偏移、`流程尺度` (ADR 0012)。座標基準點＝`校準對`第一張圖的中心, 執行開頭與每次
拾取當下量得, 不存檔。這裡的兩個換算是執行器、編輯器、換算工具共用的唯一實作::

    存檔座標 → 螢幕:  基準點 + 偏移 ×畫面倍率   (to_screen / rect_to_screen)
    螢幕 → 存檔座標:  (螢幕 − 基準點) ÷ 倍率     (from_screen / rect_from_screen)

flow.yaml 只有這一套座標空間 (舊的 zip 存檔由一次性轉換腳本轉過來, 程式不讀)。
"""
import math


def scale_px(v, k):
    """偏移量 ×`畫面倍率`後四捨五入為整數像素 (負值對稱進位); k=1 恆等.

    所有換算共用這一個進位規則, 兩邊才不會因捨入方向不同而各差 1px。
    """
    x = float(v) * k
    r = int(math.floor(abs(x) + 0.5))
    return r if x >= 0 else -r


# ================= 存檔座標 ⇄ 螢幕座標 =================

def to_screen(xy, anchor, k=1.0):
    """存檔座標 (相對基準點的偏移, 流程尺度) → 螢幕座標."""
    return (int(anchor[0]) + scale_px(xy[0], k), int(anchor[1]) + scale_px(xy[1], k))


def from_screen(xy, anchor, k=1.0):
    """螢幕座標 → 存檔座標 (相對基準點的偏移, 反除倍率換回流程尺度)."""
    return (scale_px(xy[0] - int(anchor[0]), 1.0 / k),
            scale_px(xy[1] - int(anchor[1]), 1.0 / k))


def rect_to_screen(rect, anchor, k=1.0):
    """存檔的矩形 [x, y, w, h] (相對基準點) → 螢幕矩形 (x, y, w, h).

    右下角各自換算再相減, 與左上角同一套捨入, 寬高才不會差 1px。
    """
    x, y, w, h = rect
    x0, y0 = to_screen((x, y), anchor, k)
    x1, y1 = to_screen((x + w, y + h), anchor, k)
    return (x0, y0, x1 - x0, y1 - y0)


def rect_from_screen(box, anchor, k=1.0):
    """螢幕矩形 (x, y, w, h) → 存檔的矩形 [x, y, w, h] (相對基準點, 流程尺度)."""
    x, y = from_screen(box[:2], anchor, k)
    return [x, y, scale_px(box[2], 1.0 / k), scale_px(box[3], 1.0 / k)]


# ================= 流程裡相對基準點的矩形 =================

def remap_flow(data, rect_fn):
    """整份流程資料裡相對座標基準點的矩形逐個重算 (就地); 回傳改動筆數.

    rect_fn([x, y, w, h]) → 新矩形: `固定矩形` (步驟的找圖目標、確認圖、流程層級的
    忙碌指示)。相對座標與指定點相對原點, 不動。
    """
    changed = 0
    steps = data.get("steps") or []
    targets = [s.get(k) for s in steps for k in ("target", "confirm_target")]
    targets.append(data.get("busy"))
    for t in targets:
        lim = t.get("within") if isinstance(t, dict) else None
        if isinstance(lim, list) and len(lim) == 4:
            t["within"] = list(rect_fn(lim))
            changed += 1
    return changed


def shift_flow(data, old_anchor, new_anchor, k=1.0):
    """換`校準對`＝換座標基準點 (ADR 0012): 所有存下的座標改成相對新基準點; 回傳改動筆數.

    每個座標都先用舊基準點換到螢幕 (這次的倍率 k), 再用新基準點換回來——
    落點在捨入誤差內不變 (流程尺度存整數, 誤差 ≤ k/2 px; 倍率 1 時完全不變),
    不另外累積一次四捨五入。範本拍攝位置由本流程的範本自己重算 (FlowTemplates.shift_pos, 同一對換算)。
    """
    return remap_flow(
        data,
        lambda r: rect_from_screen(rect_to_screen(r, old_anchor, k), new_anchor, k))

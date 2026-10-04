"""`找圖目標`: 「找一張圖」的通用單位 (詞彙見 app/CONTEXT.md「找圖語意」).

存檔裡的找圖目標是步驟上的巢狀物件 (flowFormat 3)::

    {"template": "範本名",
     "limit":      {"kind": "origin", "x", "y", "w", "h"}   以原點為基準的矩形
                 | {"kind": "grid", "cells": [1..9]}         搜尋範圍九宮格 (由左上起依列編號)
     "pick":       {"kind": "top" | "left", "n": N}          由上到下 / 由左到右第 N 個
                 | {"kind": "near", "base": "origin" | "region", "x", "y"}  最接近指定點
     "colorCheck": true}

缺欄位＝不限定 / 分數最高 / 不比色。找圖步驟的找圖目標在 `target`, `確認圖`在
`confirmTarget`; 「點到下一步的圖出現」沿用下一步的 `target`。像素欄位 (原點
矩形、指定點) 與步驟偏移一樣存「當前基準機器」的尺度, 執行期 ×`畫面倍率`。

本模組維持輕量 (不 import cv2/numpy): 存檔格式、編輯器、執行器、影片轉流程
都從這裡讀寫找圖目標, 解析並執行一個找圖目標的邏輯也在這裡 (三處行為一致)。
"""

from . import flowfmt

TARGET = "target"
CONFIRM_TARGET = "confirmTarget"

# flowFormat 2 的步驟欄位: 範本名直接掛在步驟上 (讀檔時單向遷移)
_V2_KEYS = (("template", TARGET), ("confirmTemplate", CONFIRM_TARGET))


# ================= 步驟上的找圖目標 =================

def target(step):
    """找圖步驟自己的找圖目標 (沒有＝空目標)."""
    return step.get(TARGET) or {}


def confirm_target(step):
    """`確認圖`的找圖目標 (沒有＝空目標)."""
    return step.get(CONFIRM_TARGET) or {}


def template(step):
    """找圖步驟的範本名 (未選＝空字串)."""
    return target(step).get("template", "")


def confirm_template(step):
    return confirm_target(step).get("template", "")


def uses_confirm_target(step):
    """`確認圖`是否生效: 只有動作為點擊、點擊後確認選「確認圖出現」時才有意義."""
    return (step.get("type") == "find_click"
            and step.get("action", "click") == "click"
            and step.get("confirm") == "appear")


def step_targets(step):
    """步驟上存在的找圖目標 [(鍵, 目標), ...] (改名/換算時走訪用)."""
    if step.get("type") != "find_click":
        return []
    return [(k, step[k]) for k in (TARGET, CONFIRM_TARGET)
            if isinstance(step.get(k), dict)]


def scale_target(tgt, k):
    """把找圖目標的像素設定 (原點矩形、指定點) 就地 ×k 四捨五入.

    `重定基準`與匯入換算經 `calibration.scale_steps` 呼叫; 九宮格是比例、
    挑選規則的 N 不是像素, 都不動。
    """
    limit = tgt.get("limit")
    if isinstance(limit, dict) and limit.get("kind") == "origin":
        for key in ("x", "y", "w", "h"):
            if key in limit:
                limit[key] = flowfmt.scale_px(limit[key], k)
    pick = tgt.get("pick")
    if isinstance(pick, dict) and pick.get("kind") == "near":
        for key in ("x", "y"):
            if key in pick:
                pick[key] = flowfmt.scale_px(pick[key], k)


def migrate_step(step):
    """flowFormat 2 → 3: 範本名與確認圖範本名搬進對應的找圖目標 (就地, 冪等).

    空的確認圖範本名不留空目標。回傳是否有改動。
    """
    changed = False
    for old, new in _V2_KEYS:
        if old not in step:
            continue
        name = step.pop(old)
        changed = True
        if isinstance(name, str) and name and not isinstance(step.get(new), dict):
            step[new] = {"template": name}
    return changed


# ================= 執行一個找圖目標 =================

class Match:
    """畫面上符合找圖目標的一處 (螢幕座標)."""
    __slots__ = ("box", "score", "color")

    def __init__(self, box, score, color=None):
        self.box = tuple(int(v) for v in box)   # (x, y, w, h) 螢幕座標
        self.score = float(score)
        self.color = color                       # 比色分數; None＝沒比色

    @property
    def center(self):
        x, y, w, h = self.box
        return x + w // 2, y + h // 2

    def __repr__(self):
        return f"Match({self.box}, {self.score:.3f}, color={self.color})"


class Found:
    """一次找圖目標判定的結果.

    limit: 實際的限定矩形 (螢幕座標, 已裁到搜尋範圍內; None＝整個搜尋範圍);
    matches: 全部匹配 (螢幕座標, 分數高者在前); picked: 挑選規則挑中的那個或
    None; reason: 沒挑到的原因——"none" 沒有匹配、"count" 匹配不足 N 個、
    "origin" 以原點為基準卻沒有原點 (無法執行, 沒有查詢); query: 引擎的
    原始結果 (最高分與未過的關卡, 供紀錄), 沒有查詢時為 None。
    """

    @property
    def failed(self):
        """沒挑到時未過的那一關: match / verify / color (引擎的門檻)、
        count (數不到 N 個)、origin (沒有原點)、limit (限定範圍在搜尋範圍外)."""
        if self.picked is not None:
            return None
        if self.reason in ("count", "origin"):
            return self.reason
        return self.query.failed if self.query is not None else "limit"

    def __init__(self, target, matches=(), picked=None, reason=None,
                 query=None, limit=None, rejected=()):
        self.target = target
        self.limit = limit
        self.rejected = list(rejected)   # 比色不符而淘汰的 (螢幕座標, 供紀錄)
        self.matches = list(matches)
        self.picked = picked
        self.reason = reason
        self.query = query

    @property
    def template(self):
        return self.target.get("template", "")


def needs_origin(tgt):
    """找圖目標的設定是否以`原點`為基準 (沒有原點時無法執行)."""
    pick = tgt.get("pick") or {}
    limit = tgt.get("limit") or {}
    return ((pick.get("kind") == "near" and pick.get("base") == "origin")
            or limit.get("kind") == "origin")


def limit_rect(tgt, region, origin, scale=1.0):
    """`限定範圍`的螢幕矩形 (x, y, w, h), 已裁到搜尋範圍 region 內.

    None＝不限定 (整個搜尋範圍); 裁完沒有交集時寬高為 0。以原點為基準的
    矩形 ×`畫面倍率`; 九宮格是搜尋範圍的比例 (格號 1–9 由左上起逐列),
    勾多格取包住它們的最小矩形。呼叫端保證以原點為基準時 origin 不是 None。
    """
    lim = tgt.get("limit") or {}
    kind = lim.get("kind")
    rx, ry, rw, rh = region
    if kind == "origin":
        x = origin[0] + flowfmt.scale_px(lim.get("x", 0), scale)
        y = origin[1] + flowfmt.scale_px(lim.get("y", 0), scale)
        x1 = x + flowfmt.scale_px(lim.get("w", 0), scale)
        y1 = y + flowfmt.scale_px(lim.get("h", 0), scale)
    elif kind == "grid" and lim.get("cells"):
        cols = [(c - 1) % 3 for c in lim["cells"]]
        rows = [(c - 1) // 3 for c in lim["cells"]]
        x, x1 = rx + rw * min(cols) // 3, rx + rw * (max(cols) + 1) // 3
        y, y1 = ry + rh * min(rows) // 3, ry + rh * (max(rows) + 1) // 3
    else:
        return None
    x0, y0 = max(x, rx), max(y, ry)
    x1, y1 = min(x1, rx + rw), min(y1, ry + rh)
    return (x0, y0, max(0, x1 - x0), max(0, y1 - y0))


def find(tgt, detector, screen, screen_origin, origin=None, scale=1.0):
    """執行一個找圖目標: 算限定矩形 → 裁圖 → 查詢 → 座標換回螢幕 → 依挑選規則挑.

    detector: 偵測接縫 (`query(範本名, 影像, color_check) → QueryResult`,
    範本不存在丟 KeyError——原樣往外拋; 開了`比色`時顏色不符的不是匹配,
    挑選規則根本看不到它們); screen: 整個`搜尋範圍`的截圖, screen_origin 是它
    左上角的螢幕座標; origin: 目前的`原點` (螢幕座標, 可能 None); scale:
    `畫面倍率` (找圖目標的像素設定 ×它)。
    """
    if origin is None and needs_origin(tgt):
        return Found(tgt, reason="origin")
    sh, sw = screen.shape[:2]
    limit = limit_rect(tgt, (screen_origin[0], screen_origin[1], sw, sh),
                       origin, scale)
    image, (ox, oy) = screen, screen_origin
    if limit is not None:
        if limit[2] <= 0 or limit[3] <= 0:
            return Found(tgt, reason="none", limit=limit)
        # 先裁圖再查詢: 限定範圍外的東西引擎根本看不到
        x0, y0 = limit[0] - screen_origin[0], limit[1] - screen_origin[1]
        image = screen[y0:y0 + limit[3], x0:x0 + limit[2]]
        ox, oy = limit[0], limit[1]
    r = detector.query(tgt.get("template", ""), image,
                       color_check=bool(tgt.get("colorCheck")))
    def screen_match(m):
        return Match((m.box[0] + ox, m.box[1] + oy, m.box[2], m.box[3]),
                     m.score, m.color)

    matches = [screen_match(m) for m in r.matches]
    rejected = [screen_match(m) for m in getattr(r, "rejected", ())]
    if not matches:
        return Found(tgt, reason="none", query=r, limit=limit,
                     rejected=rejected)
    chosen = _pick(matches, tgt.get("pick") or {}, origin, screen_origin, scale)
    return Found(tgt, matches, chosen, None if chosen else "count", r, limit,
                 rejected)


def _ordered(matches, axis):
    """依主軸排序並分組 (中心差不到半個框＝同一組), 組內依另一軸排序.

    axis 0＝由左到右 (分欄), 1＝由上到下 (分列)。
    """
    other = 1 - axis
    groups = []
    for m in sorted(matches, key=lambda m: m.center[axis]):
        if groups:
            anchor = groups[-1][0]
            if m.center[axis] - anchor.center[axis] < anchor.box[2 + axis] / 2:
                groups[-1].append(m)
                continue
        groups.append([m])
    return [m for g in groups for m in sorted(g, key=lambda m: m.center[other])]


def _pick(matches, rule, origin, screen_origin, scale):
    kind = rule.get("kind", "score")
    if kind in ("top", "left"):
        n = int(rule.get("n", 1))
        ordered = _ordered(matches, 1 if kind == "top" else 0)
        return ordered[n - 1] if 1 <= n <= len(ordered) else None
    if kind == "near":
        bx, by = origin if rule.get("base") == "origin" else screen_origin
        px = bx + flowfmt.scale_px(rule.get("x", 0), scale)
        py = by + flowfmt.scale_px(rule.get("y", 0), scale)
        return min(matches, key=lambda m: (m.center[0] - px) ** 2
                   + (m.center[1] - py) ** 2)
    return max(matches, key=lambda m: m.score)


def still_there(box, matches):
    """這個位置是否仍有匹配: 中心偏離不超過半個框的那個匹配, 沒有回 None.

    「目標圖消失」與`等待消失`只看先前挑中的那個位置——畫面別處的同款圖
    不影響判定。多個都在容差內時取最近的。
    """
    x, y, w, h = box
    cx, cy = x + w // 2, y + h // 2
    near = [m for m in matches
            if abs(m.center[0] - cx) <= w / 2 and abs(m.center[1] - cy) <= h / 2]
    return min(near, key=lambda m: (m.center[0] - cx) ** 2
               + (m.center[1] - cy) ** 2, default=None)


# ================= 給人看的描述 (執行紀錄、比對測試) =================

def fmt_box(box):
    return "({},{},{},{})".format(*box)


def fmt_match(m):
    """`(x,y,w,h) 分數[ c比色分數]`."""
    text = f"{fmt_box(m.box)} {m.score:.3f}"
    return text if m.color is None else text + f" c{m.color:.3f}"


def pick_text(tgt):
    """挑選規則的短代號: score / top:N / left:N / near:origin(+x,+y)."""
    pick = tgt.get("pick") or {}
    kind = pick.get("kind", "score")
    if kind in ("top", "left"):
        return f"{kind}:{pick.get('n', 1)}"
    if kind == "near":
        return (f"near:{pick.get('base', 'region')}"
                f"({int(pick.get('x', 0)):+d},{int(pick.get('y', 0)):+d})")
    return "score"

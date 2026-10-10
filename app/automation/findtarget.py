"""`找圖目標`: 「找一張圖」的通用單位 (詞彙見 app/CONTEXT.md「找圖語意」).

記憶體裡的找圖目標是步驟上的子 dict, 欄位名與值跟 flow.yaml 相同::

    {"template": "範本名",
     "within": [x, y, w, h]            `固定矩形`: 相對`座標基準點`的矩形
     "pick":   {"top": N} | {"left": N} 由上到下 / 由左到右第 N 個
             | {"near": [x, y]}         最接近指定點 (原點 + 偏移)
     "color":  true}

缺欄位＝不限定 / 分數最高 / 不比色。找圖步驟 (`type` 為 find_click / find / wait_gone)
的找圖目標在 `target`, `確認圖`在 `confirm_target`; 「點到下一步的圖出現」沿用下一步的
`target`。所有像素欄位
(固定矩形、指定點) 與步驟偏移一樣是`流程尺度`, 執行期 ×`畫面倍率` (ADR 0009);
固定矩形再加上`座標基準點`的螢幕位置 (ADR 0012)。九宮格、以原點為基準的矩形與
以搜尋範圍為基準的指定點已退場 (ADR 0014)。

本模組維持輕量 (不 import cv2/numpy): 編輯器、執行器、影片轉流程都經這裡的
存取函式讀寫步驟上的找圖目標, 解析並執行一個找圖目標的邏輯也在這裡 (三處行為
一致)。
"""

from . import flowfmt

TARGET = "target"
CONFIRM_TARGET = "confirm_target"

# `找圖三態`: 步驟的 type 就是找到之後做什麼 (點擊 / 只找不點 / 等它消失)
FIND_TYPES = ("find_click", "find", "wait_gone")


def is_find(step):
    """是不是找圖步驟 (三態皆是)."""
    return step.get("type") in FIND_TYPES


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


POINTER_TYPES = ("click", "drag")               # 座標點擊與拖曳
CONFIRMABLE = ("find_click",) + POINTER_TYPES   # 有`生效確認`的步驟種類


def uses_confirm_target(step):
    """`確認圖`是否生效: 生效確認選「確認圖出現」(找圖只有找到就點的才有確認)."""
    return step.get("type") in CONFIRMABLE and step.get("confirm") == "appear"


def referenced_templates(steps, extra=()):
    """被引用的範本名 (依出現順序去重): 找圖步驟的範本、生效確認的確認圖,
    再加上流程層級設定引用的 extra (校準對、忙碌指示).

    「被引用的範本」只有這一份定義: 存檔打包 (flowfile.flow_refs) 與
    `範本預載` (執行器) 都照它。「點到下一步的圖出現」引用的是下一步的範本、
    分岔條件是分支開頭的找圖步驟——都已涵蓋在「所有找圖步驟」之中。
    """
    seen = []
    for s in steps:
        names = [template(s)] if is_find(s) else []
        if uses_confirm_target(s):
            names.append(confirm_template(s))
        for n in names:
            if n and n not in seen:
                seen.append(n)
    for n in extra:
        if n and n not in seen:
            seen.append(n)
    return seen


def step_targets(step):
    """步驟上存在的找圖目標 [(鍵, 目標), ...] (改名時走訪用)."""
    t = step.get("type")
    keys = ((TARGET, CONFIRM_TARGET) if t in FIND_TYPES
            else (CONFIRM_TARGET,) if t in CONFIRMABLE else ())
    return [(k, step[k]) for k in keys if isinstance(step.get(k), dict)]


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
    "origin" 以原點為基準卻沒有原點、"anchor" 固定矩形卻沒有座標基準點 (後兩者
    無法執行, 沒有查詢); query: 引擎的原始結果 (最高分與未過的關卡, 供紀錄),
    沒有查詢時為 None。
    """

    @property
    def failed(self):
        """沒挑到時未過的那一關: match / verify / color (引擎的門檻)、
        count (數不到 N 個)、origin (沒有原點)、anchor (沒有座標基準點)、
        limit (限定範圍在搜尋範圍外)."""
        if self.picked is not None:
            return None
        if self.reason in ("count", "origin", "anchor"):
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


def pick_rule(tgt):
    """挑選規則拆成 (種類, 值): ("score", None) / ("top", N) / ("left", N) /
    ("near", [x, y]). 沒設或不成形＝分數最高."""
    pick = tgt.get("pick")
    if isinstance(pick, dict) and len(pick) == 1:
        (kind, value), = pick.items()
        if kind in ("top", "left", "near"):
            return kind, value
    return "score", None


def needs_origin(tgt):
    """找圖目標的設定是否以`原點`為基準 (沒有原點時無法執行): 最接近指定點."""
    return pick_rule(tgt)[0] == "near"


def needs_anchor(tgt):
    """找圖目標的設定是否要用到`座標基準點` (`固定矩形`); 沒有基準點時無法執行."""
    return tgt.get("within") is not None


def limit_rect(tgt, region, origin, scale=1.0, anchor=None):
    """`限定範圍`的螢幕矩形 (x, y, w, h), 已裁到搜尋範圍 region 內.

    None＝不限定 (整個搜尋範圍); 裁完沒有交集時寬高為 0。`固定矩形`＝`座標基準點` +
    偏移×`畫面倍率` (ADR 0012), 落在搜尋範圍外的部分照裁 (範圍框太小時被裁掉那塊裡的
    圖就找不到)。設定壞掉 (欄位不是整數、寬高不正) 時寬高為 0——不找, 絕不退成整個
    範圍。呼叫端保證固定矩形時 anchor 不是 None。
    """
    lim = tgt.get("within")
    rx, ry, rw, rh = region
    if lim is None:
        return None
    if not _valid_fixed_rect(lim):
        return (rx, ry, 0, 0)
    x, y, w, h = flowfmt.rect_to_screen(lim, anchor, scale)
    x1, y1 = x + w, y + h
    x0, y0 = max(x, rx), max(y, ry)
    x1, y1 = min(x1, rx + rw), min(y1, ry + rh)
    return (x0, y0, max(0, x1 - x0), max(0, y1 - y0))


def valid_fixed_rect(lim):
    """`固定矩形` [x, y, w, h] 四個值都是整數 (流程尺度像素), 寬高大於 0."""
    if not isinstance(lim, (list, tuple)) or len(lim) != 4:
        return False
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in lim):
        return False
    return lim[2] > 0 and lim[3] > 0


_valid_fixed_rect = valid_fixed_rect

# 引擎沒過的那一關的中文名 (執行紀錄、拾取檢查共用; QueryResult.failed 的值)
GATE_ZH = {"match": "粗篩", "verify": "驗證", "color": "比色"}


def find(tgt, detector, screen, screen_origin, origin=None, scale=1.0,
         anchor=None):
    """執行一個找圖目標: 算限定矩形 → 裁圖 → 查詢 → 座標換回螢幕 → 依挑選規則挑.

    detector: 偵測接縫 (`query(範本名, 影像, color_check) → QueryResult`,
    範本不存在丟 KeyError——原樣往外拋; 開了`比色`時顏色不符的不是匹配,
    挑選規則根本看不到它們); screen: 整個`搜尋範圍`的截圖, screen_origin 是它
    左上角的螢幕座標; origin: 目前的`原點` (螢幕座標, 可能 None); scale:
    `畫面倍率`——一個倍率兩個用途 (ADR 0009): 找圖目標的像素設定 ×它, 查詢時
    當`預期尺度`交給偵測器 (範本是流程尺度, 畫面上大約是它的 scale 倍);
    anchor: 這次的`座標基準點` (螢幕座標; 固定矩形要用, 沒有＝無法執行)。
    """
    if origin is None and needs_origin(tgt):
        return Found(tgt, reason="origin")
    if anchor is None and needs_anchor(tgt):
        return Found(tgt, reason="anchor")
    sh, sw = screen.shape[:2]
    limit = limit_rect(tgt, (screen_origin[0], screen_origin[1], sw, sh),
                       origin, scale, anchor)
    image, (ox, oy) = screen, screen_origin
    if limit is not None:
        if limit[2] <= 0 or limit[3] <= 0:
            return Found(tgt, reason="none", limit=limit)
        # 先裁圖再查詢: 限定範圍外的東西引擎根本看不到
        x0, y0 = limit[0] - screen_origin[0], limit[1] - screen_origin[1]
        image = screen[y0:y0 + limit[3], x0:x0 + limit[2]]
        ox, oy = limit[0], limit[1]
    r = detector.query(tgt.get("template", ""), image,
                       color_check=bool(tgt.get("color")),
                       expected_scale=scale)
    def screen_match(m):
        return Match((m.box[0] + ox, m.box[1] + oy, m.box[2], m.box[3]),
                     m.score, m.color)

    matches = [screen_match(m) for m in r.matches]
    rejected = [screen_match(m) for m in getattr(r, "rejected", ())]
    if not matches:
        return Found(tgt, reason="none", query=r, limit=limit,
                     rejected=rejected)
    chosen = _pick(matches, tgt, origin, scale)
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


def _pick(matches, tgt, origin, scale):
    kind, value = pick_rule(tgt)
    if kind in ("top", "left"):
        n = int(value)
        ordered = _ordered(matches, 1 if kind == "top" else 0)
        return ordered[n - 1] if 1 <= n <= len(ordered) else None
    if kind == "near":
        # 指定點＝`原點` + 偏移×倍率 (偏移 (0,0)＝最接近原點); 呼叫端保證有原點
        px, py = flowfmt.to_screen(value, origin, scale)
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
    """挑選規則的短代號: score / top:N / left:N / near(+x,+y) (相對原點)."""
    kind, value = pick_rule(tgt)
    if kind in ("top", "left"):
        return f"{kind}:{value}"
    if kind == "near":
        return f"near({int(value[0]):+d},{int(value[1]):+d})"
    return "score"


# ================= 編輯器: 組找圖目標、拾取換算、標記 =================

def make_target(template, within=None, pick=None, color=False):
    """由表單值組一個找圖目標; 預設值 (不限定/分數最高/不比色) 不寫進去."""
    tgt = {"template": template}
    if within is not None:
        tgt["within"] = list(within)
    if pick_rule({"pick": pick})[0] != "score":
        tgt["pick"] = dict(pick)
    if color:
        tgt["color"] = True
    return tgt


def offset_from_screen(xy, base, k):
    """拾取到的螢幕位置 → 相對基準點的偏移, 反除`畫面倍率`換回流程尺度
    (與相對座標拾取同一套換算)."""
    return (flowfmt.scale_px(xy[0] - base[0], 1.0 / k),
            flowfmt.scale_px(xy[1] - base[1], 1.0 / k))


def fixed_rect_from_screen(box, anchor, k):
    """框選到的螢幕矩形 → `固定矩形` [x, y, w, h] (相對`座標基準點`, 流程尺度).

    不裁到搜尋範圍: 存的是相對基準點的位置, 執行時才依當時的搜尋範圍裁。
    """
    return flowfmt.rect_from_screen(box, anchor, k)


def tag_text(tgt):
    """步驟清單/交付報告用的標記字串 〔限定、由上到下第3、比色〕; 沒有特別設定＝空."""
    t = tags(tgt)
    return f"〔{'、'.join(t)}〕" if t else ""


def tags(tgt):
    """步驟清單上的簡短標記: 有特別設定的屬性 (限定範圍、挑選規則、比色)."""
    out = []
    if tgt.get("within") is not None:
        out.append("限定")
    kind, value = pick_rule(tgt)
    if kind == "top":
        out.append(f"由上到下第{value}")
    elif kind == "left":
        out.append(f"由左到右第{value}")
    elif kind == "near":
        out.append("最接近指定點")
    if tgt.get("color"):
        out.append("比色")
    return out


def limit_text(lim):
    """`限定範圍`的一段描述 (摘要的第一段; 編輯器顯示固定矩形的值)."""
    if lim is not None:
        if not _valid_fixed_rect(lim):
            return "固定矩形（設定無效）"
        x, y, w, h = lim
        return f"固定矩形 ({x:+d},{y:+d}) {w}×{h}"
    return "整個搜尋範圍"


def summary(tgt):
    """找圖設定一行摘要: 限定範圍；挑選規則；比色."""
    part1 = limit_text(tgt.get("within"))
    kind, value = pick_rule(tgt)
    if kind == "top":
        part2 = f"由上到下第 {value} 個"
    elif kind == "left":
        part2 = f"由左到右第 {value} 個"
    elif kind == "near":
        part2 = f"最接近原點 ({int(value[0]):+d},{int(value[1]):+d})"
    else:
        part2 = "分數最高"
    return "；".join((part1, part2, "比色" if tgt.get("color") else "不比色"))

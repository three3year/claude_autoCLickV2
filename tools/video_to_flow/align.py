"""`對齊圖`: 補充影片裡清單捲在別處時, 量出`對齊位移`並套到插入段 (詞彙見 app/CONTEXT.md).

全部在`流程尺度` (計畫已 ÷影片倍率), 在原點推算之前::

    何時必填 (require) → 核對參考步驟 (reference)、插入段的區段 (check_segment) → 量位移 (measure_shift) →
    套用 (apply: 第一次拖曳之前平移、第一次拖曳吸收、之後照影片)

執行時位置＝參考步驟`固定矩形`的中心; 影片位置＝align.frame 那一幀上離 at 最近的匹配;
位移＝執行時 − 影片。套用後的計畫位置是執行時的位置, 但找圖仍在影片影格上挑框——每步的
位移交給 `Checker.locate_target(shift=)` 換回影片位置去挑, 挑中的框再加回位移。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from automation import findtarget

from .errors import ToolError
from .geom import center

MAX_RATIO = 6   # 參考步驟的框在捲動軸上最多是範本該軸的幾倍 (中心才代表位置)
_AXIS = {"vertical": 1, "horizontal": 0}
_AXIS_ZH = {"vertical": "直向", "horizontal": "橫向"}


def _err(msg):
    raise ToolError(f"對齊圖（align）：{msg}")


def first_drag(steps):
    """插入段 (平面, 含巢狀區段) 第一個拖曳的索引; 沒有＝None."""
    return next((i for i, s in enumerate(steps) if s["type"] == "drag"), None)


def scroll_axis(p):
    """捲動軸: 第一次拖曳的主要方向; 沒有拖曳時取找圖宣告的捲動軸; 都沒有＝None."""
    i = first_drag(p.steps)
    if i is not None:
        s = p.steps[i]
        dx, dy = s["to"][0] - s["drag"][0], s["to"][1] - s["drag"][1]
        return "vertical" if abs(dy) >= abs(dx) else "horizontal"
    return next((ev["scroll"] for ev in p.evidence if ev and ev.get("scroll")), None)


def require(p):
    """插入段有拖曳、或有找圖宣告了捲動軸, 計畫就得寫 align (刻意不對齊寫 align: null)."""
    if p.align_set:
        return
    if first_drag(p.steps) is not None:
        why = "插入段有拖曳"
    elif any(ev and ev.get("scroll") for ev in p.evidence):
        why = "插入段有找圖宣告了捲動軸"
    else:
        return
    raise ToolError(
        f"轉換計畫有誤：align：{why}，影片裡的清單可能跟執行時捲在不同位置——寫 align "
        "指定對齊圖（{\"find\": 範本名, \"frame\": 影片幀, \"at\": [x, y], \"step\": N}）；"
        "影片確定是從插入點的畫面開始錄、刻意不對齊就寫 align: null")


def reference(p, old, pos, existing, label):
    """核對 align.step: 插入點之前、找這張既有範本、有固定矩形 → 參考步驟的找圖目標."""
    a = p.align
    n = a["step"]
    if a["find"] not in existing:
        _err(f"「{a['find']}」不是既有流程的範本：對齊圖要是插入點前既有流程已經用固定矩形"
             "定位過的圖")
    if n > len(old):
        _err(f"step: {n} 超出流程（共 {len(old)} 步）")
    s = old[n - 1]
    if not findtarget.is_find(s) or findtarget.template(s) != a["find"]:
        _err(f"第 {n} 步是「{label(s)}」，不是找「{a['find']}」的找圖步驟——步驟編號可能寫錯"
             "（編號是 flow.yaml 行尾的 # N）")
    if n - 1 >= pos:
        _err(f"第 {n} 步不在插入點之前：參考步驟要是流程跑到插入點之前已經定位過這張圖的那一步")
    tgt = findtarget.target(s)
    if not findtarget.valid_fixed_rect(tgt.get("within")):
        _err(f"第 {n} 步（{label(s)}）沒有固定矩形：執行時位置取那一步固定矩形的中心，"
             "沒有就量不出來——換一張有固定矩形的對齊圖")
    return tgt


def check_segment(p):
    """「第一次拖曳之前／之後」要對每一條執行路徑都成立: 插進重複區段 (into)、第一次拖曳在
    重複區段裡 (每一輪都會拖縮短後的距離)、第一次拖曳所在的分岔後面還有別的分支 (那些分支
    沒拖, 卻會被當成拖完) 都不支援 → 報錯."""
    if p.into is not None:
        _err("into（插進重複區段）不能對齊：每一輪開始時清單捲的位置不同——插在區段外，或寫 "
             "align: null 並請使用者從插入點的畫面錄")
    fd = first_drag(p.steps)
    if fd is None:
        return
    stack = []
    for s in p.steps[:fd]:
        if s["type"] in ("repeat_start", "branch_start"):
            stack.append(s["type"])
        elif s["type"] in ("repeat_end", "branch_end"):
            stack.pop()
    if "repeat_start" in stack:
        _err("插入段的第一次拖曳在重複區段裡：每一輪都會拖同一段縮短後的距離——把這段拆成"
             "區段外先拖一次，或寫 align: null 並請使用者從插入點的畫面錄")
    if stack:   # 拖曳所在的分岔 (最內層): 拖曳之後同一層還有「或」＝還有別的分支
        depth = 0
        for s in p.steps[fd + 1:]:
            t = s["type"]
            if t in ("repeat_start", "branch_start"):
                depth += 1
            elif t in ("repeat_end", "branch_end"):
                if depth == 0:
                    break
                depth -= 1
            elif t == "branch_or" and depth == 0:
                _err("插入段的第一次拖曳所在的分岔後面還有別的分支：那些分支沒拖，位置卻會照"
                     "拖完的畫面量——把拖曳移到分岔外，或拆成兩次補充")


@dataclass
class Shift:
    d: tuple            # 對齊位移 (執行時 − 影片), 流程尺度
    video: tuple        # 對齊圖在影片裡的中心 (流程尺度的影格座標)
    runtime: tuple      # 對齊圖執行時的位置 (參考步驟固定矩形的中心, 同一座標)
    axis: str | None    # 捲動軸


def measure_shift(p, tgt, tpl_size, frames, detector, anchor):
    """量對齊位移 (p 已是流程尺度; tpl_size: 對齊圖範本的 (寬, 高))."""
    a = p.align
    w, h = tpl_size
    ax = scroll_axis(p)
    x, y, rw, rh = tgt["within"]
    for name, length, size in (("vertical", rh, h), ("horizontal", rw, w)):
        if ax in (None, name) and length > MAX_RATIO * size:
            _err(f"參考步驟的固定矩形{_AXIS_ZH[name]}長 {length}，超過範本的 {MAX_RATIO} 倍"
                 f"（{MAX_RATIO * size}）：框沿捲動方向拉得太長，中心不代表圖的位置——換一張"
                 "固定矩形比較緊的對齊圖，或請使用者從插入點的畫面重錄")
    fd = first_drag(p.steps)
    if fd is not None:
        f = (p.evidence[fd] or {}).get("frame")
        if f is None:
            _err("對齊時插入段第一次拖曳要寫 frame（按下去的那一幀），工具要核對對齊圖的幀在它之前")
        if a["frame"] > f:
            _err(f"frame: {a['frame']} 在第一次拖曳（第 {f} 幀）之後：對齊圖要在清單第一次捲動"
                 "之前那一刻量")
    runtime = (anchor[0] + x + rw // 2, anchor[1] + y + rh // 2)
    if a["frame"] not in frames:
        raise ToolError(f"工具錯誤：第 {a['frame']} 幀沒有讀進來")
    r = detector.query(a["find"], frames[a["frame"]], color_check=bool(tgt.get("color")),
                       expected_scale=1.0)
    boxes = [tuple(int(v) for v in m.box) for m in r.matches]
    at = a["at"]
    if not boxes:
        _err(f"第 {a['frame']} 幀上找不到「{a['find']}」：frame 寫錯，或那一幀被遮住——換一幀")
    best = center(min(boxes, key=lambda b: math.dist(center(b), at)))
    if abs(best[0] - at[0]) > w or abs(best[1] - at[1]) > h:
        _err(f"第 {a['frame']} 幀上離 at {list(at)} 最近的「{a['find']}」在 {list(best)}，"
             "偏超過範本尺寸：at 寫錯，或那附近沒有這張圖")
    d = (runtime[0] - best[0], runtime[1] - best[1])
    if ax is not None:
        k = 1 - _AXIS[ax]
        if abs(d[k]) > (w, h)[k] / 2:
            _err(f"捲動軸（{_AXIS_ZH[ax]}）以外那一軸差了 {abs(d[k])} px，超過範本該軸的一半："
                 "對到的可能不是同一張圖，或影片跟執行時的畫面根本不同——換對齊圖，或請使用者"
                 "從插入點的畫面重錄")
    return Shift(d, best, runtime, ax)


def _add(v, d):
    return [v[0] + d[0], v[1] + d[1]]


def apply(p, d):
    """位移套到插入段 → (新計畫, 每步的位移 [(dx, dy)], 第一次拖曳 (舊距離, 新距離) 或 None).

    第一次拖曳之前的位置 (點擊、找圖的 at、pick near) 加位移; 第一次拖曳起點加位移, 距離減掉
    位移在拖曳方向上的分量 (清單停到影片裡拖完的狀態); 之後照影片。沒有拖曳＝整段平移。
    """
    fd = first_drag(p.steps)
    end = len(p.steps) if fd is None else fd
    steps, evidence, shifts = [], [], []
    change = None
    for i, (s, ev) in enumerate(zip(p.steps, p.evidence)):
        s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in s.items()}
        step_shift = tuple(d) if i < end else (0, 0)
        if i < end:
            if "click" in s:
                s["click"] = _add(s["click"], d)
            for key in ("target", "confirm_target"):
                tgt = s.get(key)
                if isinstance(tgt, dict) and findtarget.pick_rule(tgt)[0] == "near":
                    tgt["pick"] = {"near": _add(tgt["pick"]["near"], d)}
            if ev and ev.get("at"):
                ev = dict(ev, at=_add(ev["at"], d))
        elif i == fd:
            a, b = s["drag"], s["to"]
            vx, vy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(vx, vy)
            along = (d[0] * vx + d[1] * vy) / length if length else 0.0
            new = length - along
            if new <= 0:
                _err(f"第一次拖曳要拖 {round(length)} px，扣掉對齊位移在拖曳方向上的 "
                     f"{round(along)} px 後不是正的：執行時清單已經捲到影片拖完的位置之後——"
                     "插入段不必再拖這一下，或請使用者從插入點的畫面重錄")
            start = _add(a, d)
            s["drag"] = start
            s["to"] = [int(round(start[0] + vx * new / length)),
                       int(round(start[1] + vy * new / length))]
            change = (round(length), round(new))
        steps.append(s)
        evidence.append(ev)
        shifts.append(step_shift)
    return replace(p, steps=steps, evidence=evidence), shifts, change

from __future__ import annotations

from automation import findtarget

from .errors import ToolError
from .geom import center as _center


def _no_origin(no, step, why):
    kind = "拖曳" if step["type"] == "drag" else "相對座標點擊"
    raise ToolError(
        f"轉換計畫有誤：步驟 {no}：{kind}之前沒有原點{why}——請在它前面補一個"
        "定位找圖（{\"find\": 範本名}，更新原點），用畫面上有辨識度的東西當原點")


def _near_relative(no, tgt, origin, why, what):
    kind, value = findtarget.pick_rule(tgt)
    if kind != "near":
        return
    if origin is None:
        raise ToolError(
            f"轉換計畫有誤：步驟 {no}：{what}的 pick near 以原點為基準，但這一步之前沒有"
            f"原點{why}——請在它前面補一個定位找圖（{{\"find\": 範本名}}）")
    tgt["pick"] = {"near": [int(value[0]) - origin[0], int(value[1]) - origin[1]]}


_IN_LOOP = "（位於重複區段內：第二輪起原點會變成上一輪的結尾，原點必須來自區段內）"
_AFTER_BRANCH = "（分岔結束後走了哪一支不確定，原點必須在分岔之後重新取得）"


def derive(steps, evidence, templates, locate=None, locate_confirm=None):
    origin, why = None, ""
    stack = []
    out = []
    for i, src in enumerate(steps):
        no = i + 1
        s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in src.items()}
        ev = evidence[i] or {}
        t = s["type"]
        if t == "repeat_start":
            stack.append(("loop", origin, why))
            origin, why = None, _IN_LOOP
        elif t == "branch_start":
            stack.append(("branch", origin, why))
        elif t == "branch_or":
            _, origin, why = stack[-1]
        elif t == "repeat_end":
            _, before, before_why = stack.pop()
            if origin is None:
                origin, why = before, before_why
        elif t == "branch_end":
            stack.pop()
            origin, why = None, _AFTER_BRANCH
        elif t in findtarget.FIND_TYPES:
            tgt = s["target"]
            _near_relative(no, tgt, origin, why, "找圖目標")
            if locate:
                box, within = locate(i, s, tgt, origin)
            else:
                box, within = templates[tgt["template"]]["box"], None
            if box is None:
                raise ToolError(f"轉換計畫有誤：步驟 {no}：引用的既有範本「{tgt['template']}」在它寫的那一幀"
                                "找不到——frame 寫錯，或影片裡的圖跟既有範本對不上（改裁新範本）")
            if within is not None:
                tgt["within"] = within
            cx, cy = _center(box)
            at = ev.get("at") or [cx, cy]
            s["offset"] = [at[0] - cx, at[1] - cy]
            if s["update_origin"]:
                origin, why = (at[0], at[1]), ""
            _confirm_target(no, s, origin, why, locate_confirm, i)
        elif t == "click":
            at = s["click"]
            if origin is None:
                _no_origin(no, s, why)
            s["click"] = [at[0] - origin[0], at[1] - origin[1]]
            if s["update_origin"]:
                origin = (at[0], at[1])
            _confirm_target(no, s, origin, why, locate_confirm, i)
        elif t == "drag":
            a, b = s["drag"], s["to"]
            if origin is None:
                _no_origin(no, s, why)
            s["drag"] = [a[0] - origin[0], a[1] - origin[1]]
            s["to"] = [b[0] - origin[0], b[1] - origin[1]]
            origin = (b[0], b[1])
            _confirm_target(no, s, origin, why, locate_confirm, i)
        out.append(s)
    return out


def _confirm_target(no, s, origin, why, locate_confirm, i):
    if not findtarget.uses_confirm_target(s):
        return
    ctgt = s["confirm_target"]
    _near_relative(no, ctgt, origin, why, "確認圖")
    if locate_confirm:
        within = locate_confirm(i, s, ctgt, origin)
        if within is not None:
            ctgt["within"] = within

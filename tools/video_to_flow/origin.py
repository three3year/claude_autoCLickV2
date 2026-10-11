"""原點推算: 計畫的影片像素位置 → 流程步驟的偏移 (流程尺度).

依 runner 的`原點`規則模擬執行順序 (app/automation/runner.py):

- 找圖 (三態): 原點＝在該幀實際挑中的框中心 + 偏移
- 座標點擊: 原點＝落點; 拖曳: 原點＝終點 (一律更新)
- `更新原點`取消者不更新

座標點擊/拖曳一律是`相對座標`, 偏移＝位置 − 當下原點; 找圖的偏移＝`at` − 挑中的框中心。

區段的保守規則 (計畫只描述影片裡走過的那一次):

- 重複區段: 第二輪起的原點是上一輪結尾, 與第一輪不同 → 區段開頭視為沒有
  原點, 區段內的相對座標必須先有區段內的原點來源
- 分岔: 每個分支從分岔開始時的原點出發; 分岔結束後走了哪支不確定 →
  視為沒有原點
"""
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
    """找圖目標的 pick near (影片像素的畫面位置) → 相對 origin 的偏移 (就地改)."""
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
    """推算偏移; 回傳新的步驟清單 (偏移已是相對值).

    locate(i, step, target, origin) → (挑中的框, within 或 None): 找圖步驟照它的找圖目標
    (pick near 已換成相對值) 在它那一幀挑; origin 是這一步之前的原點。
    locate_confirm(i, step, target, origin) → within 或 None: 確認圖 (origin＝操作後的)。
    兩者為 None 時只做「有沒有原點」的檢查 (框＝範本取材框, 偏移不可信)。
    """
    origin, why = None, ""
    stack = []   # [(種類, 進入區段時的原點, 沒有原點的原因)]
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
            if origin is None:   # 區段內沒有任何原點來源 → 原點仍是進區段前那個
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
    """確認圖的找圖目標以操作後的原點為基準 (同 runner)."""
    if not findtarget.uses_confirm_target(s):
        return
    ctgt = s["confirm_target"]
    _near_relative(no, ctgt, origin, why, "確認圖")
    if locate_confirm:
        within = locate_confirm(i, s, ctgt, origin)
        if within is not None:
            ctgt["within"] = within

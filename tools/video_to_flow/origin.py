"""原點推算: 計畫的影片像素位置 → 存檔步驟的偏移 (仍是影片像素).

依 runner 的`原點`規則模擬執行順序 (app/automation/runner.py):

- 找圖 (三態): 原點＝引擎在該幀實際找到的框中心 + 偏移
- 座標點擊: 原點＝落點; 拖曳: 原點＝終點 (一律更新)
- `更新原點`取消者不更新

座標點擊/拖曳一律是`相對座標` (唯一的座標模式), 偏移＝位置 − 當下原點;
找圖點擊的偏移＝點擊位置 − 找到框中心。

區段的保守規則 (計畫只描述影片裡走過的那一次):

- 重複區段: 第二輪起的原點是上一輪結尾, 與第一輪不同 → 區段開頭視為沒有
  原點, 區段內的相對座標必須先有區段內的原點來源
- 分岔: 每個分支從分岔開始時的原點出發; 分岔結束後走了哪支不確定 →
  視為沒有原點
"""
from __future__ import annotations

from automation import findtarget

from . import keys
from .errors import ToolError
from .geom import center as _center


def _no_origin(no, step, why):
    kind = "拖曳" if step["type"] == "drag" else "相對座標點擊"
    raise ToolError(
        f"轉換計畫有誤：步驟 {no}：{kind}之前沒有原點{why}——請在它前面補一個"
        "定位找圖（動作「僅等待出現」、更新原點），用畫面上有辨識度的東西當原點")


def _target_no_origin(no, what, why):
    raise ToolError(
        f"轉換計畫有誤：步驟 {no}：{what}以原點為基準，但這一步之前沒有原點{why}——"
        "請在它前面補一個定位找圖（動作「僅等待出現」、更新原點）")


def _target(no, name, attrs, origin, why, what):
    """計畫的找圖目標屬性 (影片像素的畫面位置) → 存檔的`找圖目標`.

    指定點換成相對 origin 的偏移。影片像素就是`流程尺度`, 原樣進存檔 (ADR 0009)。
    工具不產出限定範圍 (固定矩形留到影片轉流程階段, ADR 0014)。
    """
    pick = attrs.get("pick")
    if pick and pick["kind"] == "near":
        if origin is None:
            _target_no_origin(no, f"{what}的指定點", why)
        x, y = pick["at"]
        pick = {"kind": "near", "x": x - origin[0], "y": y - origin[1]}
    return findtarget.make_target(name, pick=keys.flow_pick(pick),
                                  color=attrs.get("colorCheck", False))


def _pointer_confirm_target(no, s, origin, why):
    """座標點擊/拖曳的確認圖: 以操作後的原點換成相對值 (同找圖的確認圖)."""
    cfm = s.pop("confirmTarget", None)
    if cfm:
        s["confirm_target"] = _target(no, cfm["template"], cfm, origin, why,
                                      "確認圖")


_IN_LOOP = "（位於重複區段內：第二輪起原點會變成上一輪的結尾，原點必須來自區段內）"
_AFTER_BRANCH = "（分岔結束後走了哪一支不確定，原點必須在分岔之後重新取得）"


def derive(steps, templates, located):
    """推算偏移; 回傳流程的步驟清單 (位置詞彙換成偏移欄位, 鍵名換成流程模型的).

    located(i, step, target, origin) → 找圖步驟照它的找圖目標在它那一幀挑中的
    框 (影片像素; target 已換成相對值, origin 是這一步之前的原點); 呼叫端決定
    挑不到時退回什麼框。located 為 None 時只做「有沒有原點」的檢查, 偏移不可信
    (組裝前的結構檢查用)。找圖步驟輸出流程的`找圖目標` (target/confirm_target)。
    """
    origin, why = None, ""
    stack = []   # [(種類, 進入區段時的原點, 沒有原點的原因)]
    out = []
    for i, s in enumerate(steps):
        no = i + 1
        s = dict(s)
        t = s["type"]
        if t == "loop_start":
            stack.append(("loop", origin, why))
            origin, why = None, _IN_LOOP
        elif t == "branch_start":
            stack.append(("branch", origin, why))
        elif t == "branch_or":
            _, origin, why = stack[-1]
        elif t == "loop_end":
            _, before, before_why = stack.pop()
            if origin is None:   # 區段內沒有任何原點來源 → 原點仍是進區段前那個
                origin, why = before, before_why
        elif t == "branch_end":
            stack.pop()
            origin, why = None, _AFTER_BRANCH
        elif t == "find_click":
            plan_step = dict(s)
            tgt = _target(no, s["template"], s, origin, why, "找圖目標")
            box = (located(i, plan_step, tgt, origin) if located
                   else templates[s["template"]]["box"])
            cx, cy = _center(box)
            at = s.pop("at", None) or [cx, cy]
            s["offset"] = [at[0] - cx, at[1] - cy]
            if s.get("updateOrigin", True):
                origin, why = tuple(at), ""
            # 確認圖的找圖目標以點擊後的原點為基準
            cfm = s.pop("confirmTarget", None)
            if cfm:
                s["confirm_target"] = _target(no, cfm["template"], cfm, origin,
                                              why, "確認圖")
            for k in ("template", "colorCheck", "pick"):
                s.pop(k, None)
            s["target"] = tgt
        elif t == "click":
            at = s.pop("at")
            if origin is None:
                _no_origin(no, s, why)
            s["click"] = [at[0] - origin[0], at[1] - origin[1]]
            if s.get("updateOrigin", True):
                origin = tuple(at)
            _pointer_confirm_target(no, s, origin, why)
        elif t == "drag":
            a, b = s.pop("from"), s.pop("to")
            if origin is None:
                _no_origin(no, s, why)
            s["drag"] = [a[0] - origin[0], a[1] - origin[1]]
            s["to"] = [b[0] - origin[0], b[1] - origin[1]]
            origin = tuple(b)
            _pointer_confirm_target(no, s, origin, why)
        s.pop("frame", None)
        out.append(keys.flow_step(s))
    return out

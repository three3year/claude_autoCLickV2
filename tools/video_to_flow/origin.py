"""原點推算: 計畫的影片像素位置 → 存檔步驟的偏移 (仍是影片像素).

依 runner 的`原點`規則模擬執行順序 (app/automation/runner.py):

- 找圖 (三態): 原點＝引擎在該幀實際找到的框中心 + 偏移
- 座標點擊: 原點＝落點; 拖曳: 原點＝終點 (一律更新)
- `更新原點`取消者不更新

座標點擊/拖曳一律輸出`相對座標` (mode: prev), 偏移＝位置 − 當下原點;
找圖點擊的偏移＝點擊位置 − 找到框中心。不產出`絕對座標`。

區段的保守規則 (計畫只描述影片裡走過的那一次):

- 重複區段: 第二輪起的原點是上一輪結尾, 與第一輪不同 → 區段開頭視為沒有
  原點, 區段內的相對座標必須先有區段內的原點來源
- 分岔: 每個分支從分岔開始時的原點出發; 分岔結束後走了哪支不確定 →
  視為沒有原點
"""
from __future__ import annotations

from .errors import ToolError


def _center(box):
    x, y, w, h = box
    return x + w // 2, y + h // 2


def _no_origin(no, step, why):
    kind = "拖曳" if step["type"] == "drag" else "相對座標點擊"
    raise ToolError(
        f"轉換計畫有誤：步驟 {no}：{kind}之前沒有原點{why}——請在它前面補一個"
        "定位找圖（動作「僅等待出現」、更新原點），用畫面上有辨識度的東西當原點")


_IN_LOOP = "（位於重複區段內：第二輪起原點會變成上一輪的結尾，原點必須來自區段內）"
_AFTER_BRANCH = "（分岔結束後走了哪一支不確定，原點必須在分岔之後重新取得）"


def derive(steps, templates, located):
    """推算偏移; 回傳新的步驟清單 (位置詞彙換成偏移欄位).

    located(i, step) → 找圖步驟在它那一幀被找到的框 (影片像素); 呼叫端決定
    找不到時退回什麼框。located 為 None 時只做「有沒有原點」的檢查,
    偏移不可信 (組裝前的結構檢查用)。
    """
    origin, why = None, ""
    stack = []   # [(種類, 進入區段時的原點)]
    out = []
    for i, s in enumerate(steps):
        no = i + 1
        s = dict(s)
        t = s["type"]
        if t == "loop_start":
            stack.append(("loop", origin))
            origin, why = None, _IN_LOOP
        elif t == "branch_start":
            stack.append(("branch", origin))
        elif t == "branch_or":
            origin = stack[-1][1]
        elif t == "loop_end":
            _, before = stack.pop()
            if origin is None:   # 區段內沒有任何原點來源 → 原點仍是進區段前那個
                origin, why = before, ""
        elif t == "branch_end":
            stack.pop()
            origin, why = None, _AFTER_BRANCH
        elif t == "find_click":
            box = located(i, s) if located else templates[s["template"]]["box"]
            cx, cy = _center(box)
            at = s.pop("at", None) or [cx, cy]
            s.update(offsetX=at[0] - cx, offsetY=at[1] - cy)
            if s.get("updateOrigin", True):
                origin = tuple(at)
        elif t == "click":
            at = s.pop("at")
            if origin is None:
                _no_origin(no, s, why)
            s.update(mode="prev", x=at[0] - origin[0], y=at[1] - origin[1])
            if s.get("updateOrigin", True):
                origin = tuple(at)
        elif t == "drag":
            a, b = s.pop("from"), s.pop("to")
            if origin is None:
                _no_origin(no, s, why)
            s.update(mode="prev", x1=a[0] - origin[0], y1=a[1] - origin[1],
                     x2=b[0] - origin[0], y2=b[1] - origin[1])
            origin = tuple(b)
        s.pop("frame", None)
        out.append(s)
    return out

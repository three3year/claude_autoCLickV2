"""`轉換計畫`的鍵名 → 流程記憶體模型的鍵名 (過渡: 計畫格式照舊, 影片轉流程階段改成 yaml 鍵).

計畫沿用舊的步驟詞彙 (`action`、`onNotFound`、毫秒…); 組裝出來的流程一律是 app 記憶體
的模型 (鍵名與單位跟 flow.yaml 相同, 見 app/CONTEXT.md)。名字與單位的換算只在這裡。
"""
from __future__ import annotations

_RENAMES = (("onNotFound", "on_fail"), ("updateOrigin", "update_origin"),
            ("busyCheck", "busy_check"), ("onBreak", "on_break"))
_ACTION_TYPE = {"click": "find_click", "none": "find", "wait_gone": "wait_gone"}


def _secs(ms):
    s = float(ms) / 1000.0
    return int(s) if s.is_integer() else s


def flow_pick(pick):
    """計畫的挑選規則 → 流程的: {kind: top/left, n} → {top: n}; near 的 at 要先換成偏移
    (呼叫端給 {"kind": "near", "x", "y"}) → {near: [x, y]}; 沒有或分數最高 → None."""
    if not pick:
        return None
    kind = pick.get("kind")
    if kind in ("top", "left"):
        return {kind: pick["n"]}
    if kind == "near":
        return {"near": [pick["x"], pick["y"]]}
    return None


def flow_type(step):
    """計畫步驟的種類 → 流程步驟的 type (找圖三態併進 type、重複區段改名)."""
    t = step.get("type")
    if t == "find_click":
        return _ACTION_TYPE[step.get("action", "click")]
    return {"loop_start": "repeat_start", "loop_end": "repeat_end"}.get(t, t)


def flow_step(step):
    """計畫步驟 (位置已換成偏移欄位之後) 的其餘鍵改名、毫秒改秒; 回傳新 dict."""
    s = dict(step)
    s["type"] = flow_type(step)
    s.pop("action", None)
    for old, new in _RENAMES:
        if old in s:
            s[new] = s.pop(old)
    if "confirmTarget" in s:
        s["confirm_target"] = s.pop("confirmTarget")
    t = s["type"]
    if t == "wait" and "ms" in s:
        s["wait"] = _secs(s.pop("ms"))
    elif t == "drag":
        if "ms" in s:
            s["duration"] = _secs(s.pop("ms"))
        if "holdMs" in s:
            s["hold"] = _secs(s.pop("holdMs"))
    elif t == "repeat_start" and "count" in s:
        s["repeat"] = s.pop("count")
    return s

"""流程的「沒寫＝」表: flow.yaml 省略的欄位在記憶體裡是什麼值 (唯一的一份預設).

讀檔與新增步驟時用 `complete` 補成完整步驟, 存檔時用 `strip` 把等於預設的拿掉;
執行器、編輯器、影片轉流程工具都讀完整步驟, 不各自帶預設 (ADR 0014)。

`timeout` / `interval` / `on_fail` 只屬於有等待的步驟: 找圖三態, 以及設了`生效確認`的
座標點擊與拖曳。沒有等待的步驟不補、也不留這三個欄位。
"""
from .findtarget import FIND_TYPES, POINTER_TYPES

WAIT = {"timeout": 5, "interval": 0.3, "on_fail": "stop"}

STEP = {
    "find_click": {"offset": [0, 0], "confirm": "none", "busy_check": False,
                   "update_origin": True},
    "find": {"offset": [0, 0], "update_origin": True},
    "wait_gone": {"offset": [0, 0], "update_origin": True},
    "click": {"confirm": "none", "busy_check": False, "update_origin": True},
    "drag": {"duration": 0.5, "hold": 0.5, "confirm": "none", "busy_check": False},
    "repeat_end": {"on_break": "continue"},
    "branch_end": {"on_break": "continue"},
}

FLOW = {"run": 1}

_CONFIRM_KEYS = {"confirm", "confirm_target", "timeout", "interval", "on_fail",
                 "busy_check"}
_FIND_KEYS = {"type", "target", "offset", "timeout", "interval", "on_fail",
              "update_origin"}
KEYS = {
    "find_click": _FIND_KEYS | _CONFIRM_KEYS,
    "find": _FIND_KEYS,
    "wait_gone": _FIND_KEYS,
    "click": {"type", "click", "update_origin"} | _CONFIRM_KEYS,
    "drag": {"type", "drag", "to", "duration", "hold"} | _CONFIRM_KEYS,
    "wait": {"type", "wait"},
    "repeat_start": {"type", "repeat"},
    "repeat_end": {"type", "on_break"},
    "branch_start": {"type"},
    "branch_or": {"type"},
    "branch_end": {"type", "on_break"},
}


def has_wait(step):
    """這一步有沒有等待 (找圖三態; 座標點擊、拖曳要設了生效確認)."""
    t = step.get("type")
    if t in FIND_TYPES:
        return True
    return t in POINTER_TYPES and step.get("confirm", "none") != "none"


def defaults(step):
    d = dict(STEP.get(step.get("type"), {}))
    if has_wait(step):
        d.update(WAIT)
    return d


def complete(step):
    """補成完整步驟 (回傳新 dict; 已寫的值不動). 沒有等待的步驟拿掉等待欄位."""
    s = {k: (list(v) if isinstance(v, list) else v)
         for k, v in defaults(step).items()}
    s.update(step)
    if not has_wait(s):
        for k in WAIT:
            s.pop(k, None)
    return s


def strip(step):
    """存檔用: 拿掉等於預設的欄位 (回傳新 dict)."""
    d = defaults(step)
    return {k: v for k, v in step.items() if k not in d or not _same(v, d[k])}


def _same(a, b):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return list(a) == list(b)
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return a == b


def new_step(t):
    """新增步驟時的完整步驟 (編輯器開對話框前用)."""
    base = {"find_click": {"target": {"template": ""}},
            "click": {"click": [0, 0]},
            "drag": {"drag": [0, 0], "to": [0, -100]},
            "wait": {"wait": 1},
            "repeat_start": {"repeat": 3}}.get(t, {})
    return complete(dict(base, type=t))

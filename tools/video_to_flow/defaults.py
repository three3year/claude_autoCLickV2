"""計畫沒寫的欄位依規則補預設, 補完的步驟與編輯器建出來的長得一樣.

- 找圖點擊的`點擊後確認`: 下一步是找圖 → 點到下一步的圖出現 (next),
  否則 (含最後一步、下一步是區段標記) → 目標圖消失 (gone); 不點擊的找圖
  一律 none (只有點擊才有意義)
- `找不到時`預設停止: 流程不在錯誤的畫面上繼續亂點
- 逾時預設 10 秒; 計畫可依影片觀察到的載入時間放寬
- 其餘欄位與 app 新增步驟的預設一致 (app.App.add_step)
"""
from __future__ import annotations

from automation.runner import confirm_next_connected

FIND = {"timeout": 10, "interval": 0.5, "action": "click", "button": "left",
        "clicks": 1, "onNotFound": "stop", "updateOrigin": True}
CLICK = {"button": "left", "clicks": 1, "updateOrigin": True}
DRAG = {"button": "left", "ms": 500, "holdMs": 500}
WAIT = {"ms": 1000}


def apply(steps):
    """就地補預設; 回傳同一份清單."""
    for i, s in enumerate(steps):
        t = s["type"]
        if t == "find_click":
            for k, v in FIND.items():
                s.setdefault(k, v)
            if s["action"] != "click":
                s["confirm"] = "none"
            elif "confirm" not in s:
                s["confirm"] = "next" if confirm_next_connected(steps, i) else "gone"
        elif t == "click":
            for k, v in CLICK.items():
                s.setdefault(k, v)
        elif t == "drag":
            for k, v in DRAG.items():
                s.setdefault(k, v)
        elif t == "wait":
            for k, v in WAIT.items():
                s.setdefault(k, v)
    return steps

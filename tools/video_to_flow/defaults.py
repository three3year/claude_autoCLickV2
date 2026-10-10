"""計畫沒寫的欄位依規則補預設, 補完的步驟與編輯器建出來的長得一樣.

- 找圖點擊的`生效確認`: 下一步是找圖 → 點到下一步的圖出現 (next),
  否則 (含最後一步、下一步是區段標記) → 目標圖消失 (gone); 不點擊的找圖
  一律 none (只有點擊才有意義)
- `找不到時`預設停止: 流程不在錯誤的畫面上繼續亂點
- 逾時預設 10 秒; 計畫可依影片觀察到的載入時間放寬
- 拖曳的原點來自找圖時: `生效確認`預設`原點的圖離開` (confirm: gone)、找不到時
  停止——捲動被吃掉時重拖, 不在後面靜靜點錯列 (ADR 0008); 原點不是找圖時不設
- 座標點擊/拖曳寫了生效確認時, 逾時/輪詢/找不到時補編輯器的預設 (10s、0.5s、停止)
- 其餘欄位與 app 新增步驟的預設一致 (app.App.add_step)
"""
from __future__ import annotations

from automation.findtarget import FIND_TYPES
from automation.runner import POINTER_TYPES, confirm_next_connected, origin_source

FIND = {"timeout": 10, "interval": 0.5, "on_fail": "stop", "update_origin": True}
CLICK = {"update_origin": True}
DRAG = {"duration": 0.5, "hold": 0.5}
CONFIRM = {"timeout": 10, "interval": 0.5, "on_fail": "stop"}
WAIT = {"wait": 1}


def apply(steps):
    """就地補預設; 回傳同一份清單."""
    for i, s in enumerate(steps):
        t = s["type"]
        if t in FIND_TYPES:
            for k, v in FIND.items():
                s.setdefault(k, v)
            if t != "find_click":
                s["confirm"] = "none"
            elif "confirm" not in s:
                s["confirm"] = "next" if confirm_next_connected(steps, i) else "gone"
        elif t == "click":
            for k, v in CLICK.items():
                s.setdefault(k, v)
        elif t == "drag":
            for k, v in DRAG.items():
                s.setdefault(k, v)
            if "confirm" not in s and origin_source(steps, i) == "find":
                s["confirm"] = "gone"
        elif t == "wait":
            for k, v in WAIT.items():
                s.setdefault(k, v)
        if t in POINTER_TYPES and s.get("confirm", "none") != "none":
            for k, v in CONFIRM.items():
                s.setdefault(k, v)
    return steps

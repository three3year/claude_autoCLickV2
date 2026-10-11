"""步驟的內容指稱 (報告、待確認、待重拍原因、錯誤訊息共用的唯一一份稱呼).

不寫步驟編號——補充插入後編號會位移。app 的 `flowcheck.STEP_LABELS` 是編輯器標籤
(找圖三態共用一個), 這裡要分得出找到之後做什麼。
"""
from automation import findtarget

FIND_ACTION = {"find_click": "找圖點擊", "find": "找圖（不點）", "wait_gone": "等待消失"}
STEP = {"click": "座標點擊", "drag": "拖曳", "wait": "等待"}


def label(s):
    """找圖: 動作＋範本名; 其他步驟: 種類名."""
    t = s["type"]
    if t in findtarget.FIND_TYPES:
        return f"{FIND_ACTION[t]}「{findtarget.template(s)}」"
    return STEP.get(t, t)

from automation import findtarget

FIND_ACTION = {"find_click": "找圖點擊", "find": "找圖（不點）", "wait_gone": "等待消失"}
STEP = {"click": "座標點擊", "drag": "拖曳", "wait": "等待"}


def label(s):
    t = s["type"]
    if t in findtarget.FIND_TYPES:
        return f"{FIND_ACTION[t]}「{findtarget.template(s)}」"
    return STEP.get(t, t)

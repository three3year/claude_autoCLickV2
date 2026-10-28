"""流程的結構檢查: 不依賴視窗的純函式.

輸入是記憶體裡的完整步驟清單 (平面標記, 見 flowfile), 回傳給人看的錯誤訊息。
"""
from . import findtarget
from .runner import (branch_layout, confirm_next_connected, has_busy_check,
                     origin_source, uses_confirm_next, uses_origin_leaves)

STEP_LABELS = {
    "find_click": "找圖點擊",
    "find": "找圖點擊",
    "wait_gone": "找圖點擊",
    "click": "座標點擊",
    "drag": "滑鼠拖曳",
    "wait": "等待",
    "repeat_start": "重複開始",
    "repeat_end": "重複結束",
    "branch_start": "分岔開始",
    "branch_or": "分岔（或）",
    "branch_end": "分岔結束",
}


def section_error(steps):
    """區段結構檢查, 回傳錯誤訊息或 None.

    堆疊掃描: 除了成對, 也擋交錯區段 (如 重複開始→分岔開始→
    重複結束→分岔結束), runner 的跳轉解譯無法正確執行交錯結構;
    分岔的每個分支開頭必須是找圖、「或」必須直接在分岔內。
    """
    zh = {"repeat_start": "重複", "branch_start": "分岔"}
    stack = []
    for i, s in enumerate(steps):
        t = s["type"]
        if t in ("repeat_start", "branch_start"):
            if t == "branch_start":
                lay = branch_layout(steps, i)
                if lay is None:
                    return "分岔標記不成對（缺少「分岔結束」）"
                segs, end = lay
                for st in segs:
                    if st >= end or not findtarget.is_find(steps[st]):
                        return "分岔的每個分支開頭必須是「找圖點擊」步驟"
            stack.append((t, i + 1))
        elif t in ("repeat_end", "branch_end"):
            need = "repeat_start" if t == "repeat_end" else "branch_start"
            if not stack:
                return f"步驟 {i + 1}「{STEP_LABELS[t]}」缺少對應的開始標記"
            if stack[-1][0] != need:
                return (f"區段交錯：步驟 {i + 1}「{STEP_LABELS[t]}」之前，"
                        f"必須先結束步驟 {stack[-1][1]} 開始的"
                        f"「{zh[stack[-1][0]]}」區段（區段不可交錯）")
            stack.pop()
        elif t == "branch_or":
            if not stack or stack[-1][0] != "branch_start":
                return "「分岔（或）」必須直接位於分岔區段內"
    if stack:
        return (f"步驟 {stack[-1][1]}「{STEP_LABELS[stack[-1][0]]}」"
                f"缺少對應的結束標記")
    return None


def no_origin(steps):
    """執行到時必然沒有原點的「以原點為基準」步驟索引 (0-based).

    原點來源: 點擊/拖曳 (本身也要先有原點)、找圖步驟; 以原點為基準的步驟
    (座標點擊、拖曳、指定點相對原點的`找圖目標`) 在原點出現前執行只會被
    runner 跳過。測試選取時傳入的是片段。
    """
    have = False
    bad = []
    for k, s in enumerate(steps):
        t = s.get("type")
        if t in ("click", "drag"):
            if not have:
                bad.append(k)
            elif t == "drag" or s["update_origin"]:
                have = True
        elif t in findtarget.FIND_TYPES:
            if not have and findtarget.needs_origin(findtarget.target(s)):
                bad.append(k)
            elif s["update_origin"]:
                have = True
    return bad


def origin_leaves_bad(steps):
    """「原點的圖離開」但原點不是來自找圖的座標點擊/拖曳索引 (0-based)."""
    return [i for i, s in enumerate(steps)
            if uses_origin_leaves(s) and origin_source(steps, i) != "find"]


def confirm_next_bad(steps):
    """`找圖相連`不成立的「點到下一步的圖出現」步驟索引 (0-based)."""
    return [i for i, s in enumerate(steps)
            if uses_confirm_next(s) and not confirm_next_connected(steps, i)]


def busy_check_bad(steps, busy):
    """勾了`忙碌檢查`、流程卻沒設`忙碌指示`的步驟索引 (0-based; 有忙碌指示＝空)."""
    if busy:
        return []
    return [i for i, s in enumerate(steps) if has_busy_check(s)]


def _nos(idx):
    return "、".join(str(i + 1) for i in idx)


def flow_errors(flow):
    """整份流程 (記憶體模型) 執行前一定會被擋下的問題, 一則一行 (空清單＝沒有).

    與 app 執行前的檢查同一套判斷: 沒有校準對、區段結構、相對座標前沒有原點、
    「原點的圖離開」的原點不是找圖、「點到下一步的圖出現」不相連、勾了忙碌檢查
    卻沒設忙碌指示。缺圖不在這裡 (那是檔案的事)。
    """
    steps = flow.get("steps") or []
    out = []
    if not flow.get("calibration"):
        out.append("沒有校準對（calibration）：app 不執行沒有校準對的流程")
    err = section_error(steps)
    if err:
        out.append(err)
    for i in no_origin(steps):
        what = ("找圖的指定點（pick: near）" if findtarget.is_find(steps[i])
                else STEP_LABELS[steps[i]["type"]])
        out.append(f"步驟 {i + 1}：{what}以原點為基準，但之前沒有任何原點來源"
                   "（前面要有找圖、或更新原點的點擊／拖曳）")
    bad = origin_leaves_bad(steps)
    if bad:
        out.append(f"步驟 {_nos(bad)}：「原點的圖離開」（confirm: gone）需要原點來自"
                   "找圖，但前面最近的原點來自點擊／拖曳（或沒有原點）")
    bad = confirm_next_bad(steps)
    if bad:
        out.append(f"步驟 {_nos(bad)}：「點到下一步的圖出現」（confirm: next）需要下一步"
                   "是找圖步驟（不能是最後一步或區段標記）")
    bad = busy_check_bad(steps, flow.get("busy"))
    if bad:
        out.append(f"步驟 {_nos(bad)}：勾了忙碌檢查（busy_check），但流程沒有設忙碌指示"
                   "（busy）")
    return out

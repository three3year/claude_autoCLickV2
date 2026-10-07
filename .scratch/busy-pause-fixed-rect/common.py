"""忙碌暫停、固定矩形: 建構與驗證腳本共用的路徑與流程存檔存取 (見 spec.md).

流程存檔只經 app 的流程存檔模組 (app/flowfile.py) 讀寫。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
APP = os.path.join(ROOT, "app")
PROFILE = os.path.join(APP, "dist", "AutoClick", "profiles", "arknights")
FLOWS = os.path.join(PROFILE, "flows")
BACKUP = os.path.join(APP, "dist", "profiles-backup-2026-10-07-busy-pause-fixed-rect")
RESULTS = os.path.join(HERE, "results")

for p in (APP, os.path.join(APP, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

MORNING = ["早_簡中", "早_繁中"]
EVENING = ["晚_簡中", "晚_繁中"]
FLOW_NAMES = MORNING + EVENING


def flow_path(name, flows=FLOWS):
    import flowfile
    return os.path.join(flows, name + flowfile.EXT)


def autoclick_running():
    """AutoClick (含 noUAC 版) 正在執行嗎: 開著時它的草稿會把改動蓋回去."""
    import subprocess
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                         text=True, errors="replace").stdout.lower()
    return '"autoclick.exe"' in out or '"autoclick-nouac.exe"' in out


def preflight(flows):
    """改正式流程前的檢查: AutoClick 已關、備份已在. 改的是別的目錄 (試跑) 就只查前者."""
    if autoclick_running():
        raise SystemExit("AutoClick 正在執行: 請先關掉 (不然草稿會把改動蓋回去)")
    if (os.path.normcase(os.path.abspath(flows)) == os.path.normcase(FLOWS)
            and not os.path.isdir(BACKUP)):
        raise SystemExit(f"還沒備份: 先把 profiles 複製到 {BACKUP}")


def is_busy_wait(step, busy):
    """「忙碌指示 → 等待消失」步驟: 等待消失, 範本就是流程層級的忙碌指示."""
    from automation import findtarget
    return (busy is not None and step.get("type") == "find_click"
            and step.get("action") == "wait_gone"
            and findtarget.template(step) == busy.get("template"))


def write_flow(path, data, images, pos):
    """寫存檔並讀回驗證: 每個被引用的範本都在存檔裡; 回傳讀回的結果."""
    import flowfile
    missing = flowfile.write(path, data, images, pos)
    if missing:
        raise SystemExit(f"存檔引用了不存在的範本: {'、'.join(missing)}")
    back = flowfile.read(path)
    lost = set(flowfile.flow_refs(back["data"])) - set(back["images"])
    if lost:
        raise SystemExit(f"讀回後缺範本: {'、'.join(sorted(lost))}")
    return back


def current_flow(profile=PROFILE):
    """草稿 (_autosave.json) 屬於哪一份存檔 (工作區的 state.json)."""
    import flowfile
    p = flowfile.Workspace(profile).flow_path()
    return os.path.normcase(os.path.abspath(p)) if p else None


def sync_draft(path, profile=PROFILE):
    """草稿屬於 path 這份存檔時, 改寫成存檔讀回的內容 (同 App._flow_data 的形狀).

    回傳是否改寫。草稿屬於別份存檔時不動。
    """
    import flowfile
    cur = current_flow(profile)
    if cur != os.path.normcase(os.path.abspath(path)):
        return False
    data = dict(flowfile.read(path)["data"])
    data.pop("flowFormat", None)
    data[flowfile.RETRY_KEY] = flowfile.retry_interval_ms(data)
    flowfile.write_draft(profile, data)
    return True


def section_error(steps):
    """區段完整性 (同 App._flow_error 的堆疊掃描): 錯誤訊息或 None."""
    from automation.runner import branch_layout
    stack = []
    for i, s in enumerate(steps):
        t = s["type"]
        if t in ("loop_start", "branch_start"):
            if t == "branch_start":
                lay = branch_layout(steps, i)
                if lay is None:
                    return f"第 {i + 1} 步: 分岔標記不成對"
                segs, end = lay
                for st in segs:
                    if st >= end or steps[st]["type"] != "find_click":
                        return f"第 {i + 1} 步: 分支開頭不是找圖步驟"
            stack.append(t)
        elif t in ("loop_end", "branch_end"):
            need = "loop_start" if t == "loop_end" else "branch_start"
            if not stack or stack[-1] != need:
                return f"第 {i + 1} 步: {t} 沒有對應的開始標記 (或區段交錯)"
            stack.pop()
        elif t == "branch_or" and (not stack or stack[-1] != "branch_start"):
            return f"第 {i + 1} 步: 分岔（或）不在分岔區段內"
    return f"{stack[-1]} 缺少結束標記" if stack else None

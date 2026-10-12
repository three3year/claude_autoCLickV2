"""一次性轉換: 逾時預設 10 → 5 之前, 把四份在用流程裡「沒寫＝10 秒」的逾時寫明 (ui-slim 票 02).

不進 tools/、不寫正式測試、之後不維護; 跟著提交當紀錄。

    .venv/Scripts/python.exe .scratch/ui-slim/convert_timeout.py [流程預設位置]

做法比照格式階段的轉換工具: 用改前的預設 (10) 讀, 寫的時候**每個有等待的步驟都寫明逾時**——
每個實際逾時 10 秒的步驟寫成明確的 `timeout: 10`, 原本就寫著 `timeout: 5` 的也留著 (spec 原寫
「用改後的預設寫」會把它們拿掉, 但新版過關前使用者照常用舊打包版跑, 舊版的預設是 10, 會把拿掉
的讀成 10; 兩個值都寫明, 新舊兩版讀起來一樣。新版之後存檔時等於 5 的自然不寫)。
只動 flow.yaml (寫回前備份成 flow.yaml.bak-<時間>), templates/ 不碰。寫完逐份分別用改前與改後的
預設讀回, 整份記憶體模型 (每一步的實際逾時、間隔、找不到時……) 都要與轉換前相同, 不同就報錯。
app 的預設表此時可能已經是 5 或還是 10: 讀與寫都在這裡明確指定, 不依賴它。
"""
import os
import shutil
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "app"))

import flowfile  # noqa: E402
from automation import flowdefaults  # noqa: E402

FLOWS = ("早_簡中", "早_繁中", "晚_簡中", "晚_繁中")   # 三份複本不轉 (spec 決策 b)
OLD, NEW = 10, 5


def with_default(timeout, fn, *args):
    saved = flowdefaults.WAIT["timeout"]
    flowdefaults.WAIT["timeout"] = timeout
    try:
        return fn(*args)
    finally:
        flowdefaults.WAIT["timeout"] = saved


def waits(flow):
    return [(s.get("timeout"), s.get("interval"), s.get("on_fail")) for s in flow["steps"]]


def convert(folder):
    before = with_default(OLD, flowfile.read_flow, folder)
    text = with_default(None, flowfile.dump_flow, before)   # 沒有值等於預設: 逾時一律寫明
    for d in (OLD, NEW):
        after = with_default(d, flowfile.parse_flow, text)
        if after != before or waits(after) != waits(before):
            raise SystemExit(f"{folder}: 轉換後用預設 {d} 讀回與轉換前不同, 什麼都沒寫")
    path = os.path.join(folder, flowfile.FLOW_YAML)
    bak = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, bak)
    flowfile.replace_flow_yaml(folder, text)
    for d in (OLD, NEW):
        if with_default(d, flowfile.read_flow, folder) != before:
            raise SystemExit(f"{folder}: 寫回後用預設 {d} 讀回與轉換前不同 (備份在 {bak})")
    tens = sum(1 for s in before["steps"] if s.get("timeout") == OLD)
    timed = sum(1 for s in before["steps"] if "timeout" in s)
    print(f"{os.path.basename(folder)}: {len(before['steps'])} 步, 有等待 {timed} 步, "
          f"逾時 10 秒 {tens} 步已寫明; 新舊預設讀回都一致; 備份 {os.path.basename(bak)}")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ["USERPROFILE"],
                                                               "AutoClick")
    for name in FLOWS:
        convert(os.path.join(root, name))


if __name__ == "__main__":
    main()

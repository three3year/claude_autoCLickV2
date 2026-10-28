import os
import shutil
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "app"))

import flowfile  # noqa: E402
from automation import flowdefaults  # noqa: E402

FLOWS = ("早_簡中", "早_繁中", "晚_簡中", "晚_繁中")
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
    text = with_default(None, flowfile.dump_flow, before)
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

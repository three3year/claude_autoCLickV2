from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "busy-pause-fixed-rect"))
import common  # noqa: E402

from automation import findtarget  # noqa: E402

NAME = "早_簡中"
BACKUP = os.path.join(common.APP, "dist", "profiles-backup-2026-10-08-cn-start-busy-wait")
APPEAR_MS = 3000
TIMEOUT_S = 60


def wait_step(busy):
    return {"type": "find_click", "interval": 0.3, "confirm": "none", "action": "wait_gone",
            "timeout": TIMEOUT_S, "onNotFound": "stop", "appearLimitMs": APPEAR_MS,
            "offsetX": 0, "offsetY": 0, "button": "left", "clicks": 1,
            "updateOrigin": False, "target": json.loads(json.dumps(busy))}


def insert_at(steps):
    i = next(i for i, s in enumerate(steps) if s.get("type") == "loop_start")
    nxt = steps[i + 1]
    if nxt.get("action") == "wait_gone":
        return None
    if nxt.get("type") != "branch_start":
        raise SystemExit(f"迴圈開頭不是分岔: {nxt}")
    return i + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    path = common.flow_path(NAME)
    import flowfile
    r = flowfile.read(path)
    data = r["data"]
    busy = data.get("busyTarget")
    if not busy or findtarget.template({"target": busy}) != "忙碌指示":
        raise SystemExit(f"流程沒有忙碌指示: {busy}")
    steps = list(data["steps"])
    at = insert_at(steps)
    if at is None:
        print("已插過, 不動")
        return
    step = wait_step(busy)
    print(f"{NAME}: 插在第 {at + 1} 步 (原 {len(steps)} 步 → {len(steps) + 1})")
    print(json.dumps(step, ensure_ascii=False))
    if not args.apply:
        return

    common.preflight(common.FLOWS, BACKUP)
    new = steps[:at] + [step] + steps[at:]
    back = common.write_flow(path, dict(data, steps=new), r["images"], r["pos"])
    got = back["data"]["steps"]
    if got[at] != step or got[:at] + got[at + 1:] != steps:
        raise SystemExit("讀回不符: 插入的步驟或其他步驟有變")
    print("存檔已寫回並讀回驗證")
    if common.sync_draft(path):
        print("草稿已同步")


if __name__ == "__main__":
    main()

"""票 05: 把四份流程裡「忙碌指示 → 等待消失」的步驟全部拿掉 (ADR 0010 決策 3).

    .venv/Scripts/python.exe .scratch/busy-pause-fixed-rect/remove_busy_waits.py [--dry-run]

可以重跑: 已拿掉的流程再跑一次＝沒有可拿的步驟, 存檔不動。
- 以內容認步驟, 不靠編號: 找圖、動作＝等待消失、範本＝流程層級的忙碌指示。
- 拿掉後區段完整性照執行前檢查 (同 App._flow_error) 再驗一次。
- 改正式流程前檢查 AutoClick 已關、備份已在 (common.preflight)。
- 草稿 (_autosave.json) 屬於改到的那份存檔時, 改寫成讀回的內容。
- 結果 (每份拿掉哪幾步、前後步驟) 寫 results/remove_busy_waits.json, 交付報告用。
流程存檔只經 app/flowfile.py 讀寫。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import common

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402


def describe(step):
    t = step.get("type")
    if t == "find_click":
        return f"找圖 {findtarget.template(step)}"
    if t == "click":
        return f"點擊 {step.get('mode', 'abs')} ({step.get('x')},{step.get('y')})"
    return t


def strip(steps, busy):
    """回傳 (新 steps, 拿掉的 [{no, before, after}]); no 是改動前的 1-based 編號."""
    kept, removed = [], []
    for i, s in enumerate(steps):
        if common.is_busy_wait(s, busy):
            if s.get("updateOrigin", True):
                # 它會更新原點: 拿掉會讓後面的相對座標改變基準, 不認得的寫法
                raise SystemExit(f"第 {i + 1} 步的忙碌等待會更新原點, 不能直接拿掉")
            removed.append({"no": i + 1, "before": describe(steps[i - 1]),
                            "after": describe(steps[i + 1])
                            if i + 1 < len(steps) else "（結尾）"})
            continue
        kept.append(s)
    return kept, removed


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只列出要拿掉的步驟")
    ap.add_argument("--flows", default=common.FLOWS, help="流程存檔目錄")
    args = ap.parse_args(argv)
    if not args.dry_run:
        common.preflight(args.flows)

    report = {}
    for name in common.FLOW_NAMES:
        path = common.flow_path(name, args.flows)
        r = flowfile.read(path)
        data = r["data"]
        n0 = len(data["steps"])
        steps, removed = strip(data["steps"], flowfile.busy_target(data))
        err = common.section_error(steps)
        if err:
            raise SystemExit(f"{name}: 拿掉後區段不完整: {err}")
        report[name] = {"before": n0, "after": len(steps), "removed": removed}
        print(f"{name}: {n0} → {len(steps)} 步；拿掉 "
              + ("、".join(str(x["no"]) for x in removed) or "無"))
        for x in removed:
            print(f"    第 {x['no']} 步（{x['before']} 之後 → 接 {x['after']}）")
        if args.dry_run or not removed:
            continue
        data["steps"] = steps
        back = common.write_flow(path, data, r["images"], r["pos"])
        if back["data"]["steps"] != steps:
            raise SystemExit(f"{name}: 讀回的步驟與寫入的不同")
        if common.sync_draft(path, os.path.dirname(args.flows)):
            print("    草稿 _autosave.json 已同步")
    if not args.dry_run:
        os.makedirs(common.RESULTS, exist_ok=True)
        out = os.path.join(common.RESULTS, "remove_busy_waits.json")
        old = {}
        if os.path.isfile(out):   # 重跑時保留第一次的紀錄 (重跑已沒有可拿的步驟)
            with open(out, encoding="utf-8") as f:
                old = json.load(f)
        for name, rec in report.items():
            if rec["removed"] or name not in old:
                old[name] = rec
        with open(out, "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

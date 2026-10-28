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
    kept, removed = [], []
    for i, s in enumerate(steps):
        if common.is_busy_wait(s, busy):
            if s.get("updateOrigin", True):
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
        if os.path.isfile(out):
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

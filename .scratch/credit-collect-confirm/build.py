from __future__ import annotations

import argparse
import json
import os
import sys

import collect
from collect import bp

import flowfile  # noqa: E402


def rebuild(lang, data):
    steps = data["steps"]
    i = collect.credit_index(steps, lang)
    new = collect.changed_step(steps[i], steps[i + 1])
    if new == steps[i]:
        return data, i, "已是新版"
    out = list(steps)
    out[i] = new
    return dict(data, steps=out), i, "改三個欄位"


def ensure_backup(lang, path, flows):
    bp.preflight(flows, collect.BACKUP)
    if os.path.normcase(os.path.abspath(flows)) != os.path.normcase(bp.FLOWS):
        return None
    cfg = collect.LANGS[lang]
    cur = flowfile.read(path)
    orig = flowfile.read(bp.flow_path(cfg["flow"], collect.BACKUP_FLOWS))
    built, _, _ = rebuild(lang, orig["data"])
    if cur["images"] == orig["images"] and cur["data"] in (orig["data"], built):
        return collect.BACKUP_FLOWS
    bp.preflight(flows, collect.ticket_backup(lang))
    return collect.orig_flows(lang)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(collect.LANGS), required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--flows", default=bp.FLOWS)
    args = ap.parse_args(argv)
    cfg = collect.LANGS[args.lang]
    path = bp.flow_path(cfg["flow"], args.flows)
    r = flowfile.read(path)
    data, i, note = rebuild(args.lang, r["data"])
    err = bp.section_error(data["steps"])
    if err:
        raise SystemExit(f"{cfg['flow']}: 區段不完整: {err}")
    step = data["steps"][i]
    print(f"{cfg['flow']}: 第 {i + 1} 步收取信用 {note}（共 {len(data['steps'])} 步）")
    for k in collect.CHANGED:
        print(f"    {k}: {json.dumps(r['data']['steps'][i].get(k), ensure_ascii=False)}"
              f" → {json.dumps(step.get(k), ensure_ascii=False)}")
    if not args.apply:
        return 0
    orig_flows = ensure_backup(args.lang, path, args.flows)
    if data != r["data"]:
        back = bp.write_flow(path, data, r["images"], r["pos"])
        if back["data"]["steps"] != data["steps"] or back["images"] != r["images"]:
            raise SystemExit(f"{cfg['flow']}: 讀回的內容與寫入的不同")
        print(f"{cfg['flow']}: 已寫回")
    if bp.sync_draft(path, os.path.dirname(args.flows)):
        print("    草稿與工作區已同步")
    os.makedirs(collect.RESULTS, exist_ok=True)
    with open(os.path.join(collect.RESULTS, f"build_{args.lang}.json"), "w",
              encoding="utf-8") as f:
        json.dump({"flow": cfg["flow"], "step": i + 1, "steps": len(data["steps"]),
                   "orig_flows": orig_flows,
                   "before": {k: r["data"]["steps"][i].get(k) for k in collect.CHANGED},
                   "after": {k: step.get(k) for k in collect.CHANGED}},
                  f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

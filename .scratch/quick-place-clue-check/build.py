from __future__ import annotations

import argparse
import json
import os
import sys

import clue
from clue import bp

import app  # noqa: E402
import flowfile  # noqa: E402


def source(lang, flows):
    cfg = clue.LANGS[lang]
    cur = flowfile.read(bp.flow_path(cfg["flow"], flows))
    if not clue.is_new(cur["data"]["steps"], lang):
        return cur, cur
    if not os.path.isdir(clue.BACKUP_FLOWS):
        raise SystemExit(f"{cfg['flow']}: 已是新版, 但找不到改前的備份 {clue.BACKUP_FLOWS}")
    return cur, flowfile.read(bp.flow_path(cfg["flow"], clue.BACKUP_FLOWS))


def build(lang, orig):
    data = orig["data"]
    steps = clue.rebuild(data["steps"], lang, data["scanRegion"])
    images = dict(orig["images"])
    images.update(clue.load_templates(lang))
    return dict(data, steps=steps), images


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(clue.LANGS), required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--flows", default=bp.FLOWS)
    args = ap.parse_args(argv)
    cfg = clue.LANGS[args.lang]
    path = bp.flow_path(cfg["flow"], args.flows)
    cur, orig = source(args.lang, args.flows)
    data, images = build(args.lang, orig)
    err = bp.section_error(data["steps"])
    if err:
        raise SystemExit(f"{cfg['flow']}: 區段不完整: {err}")
    lay = clue.new_layout(data["steps"], args.lang)
    a, b = lay["recv"][0], lay["unlock"][0]
    print(f"{cfg['flow']}: {len(orig['data']['steps'])} → {len(data['steps'])} 步；"
          f"第 {a + 1}–{b} 步是新的會客室段（接收→開面板→檢查→補關）")
    for i in range(a, lay["entry"] + 1):
        print(f"  {i + 1:>3} {app.step_desc(data['steps'][i])}")
    if not args.apply:
        return 0
    bp.preflight(args.flows, clue.BACKUP)
    same = (cur["data"]["steps"] == data["steps"]
            and {k: v for k, v in cur["data"].items() if k != "steps"}
            == {k: v for k, v in data.items() if k != "steps"}
            and set(cur["images"]) == set(flowfile.flow_refs(data))
            and all(cur["images"][n] == images[n] for n in cur["images"]))
    if not same:
        back = bp.write_flow(path, data, images, orig["pos"])
        if back["data"]["steps"] != data["steps"]:
            raise SystemExit(f"{cfg['flow']}: 讀回的步驟與寫入的不同")
        print(f"{cfg['flow']}: 已寫回")
    else:
        print(f"{cfg['flow']}: 已是新版, 不動")
    if bp.sync_draft(path, os.path.dirname(args.flows)):
        print("    草稿與工作區已同步")
    os.makedirs(clue.RESULTS, exist_ok=True)
    with open(os.path.join(clue.RESULTS, f"build_{args.lang}.json"), "w", encoding="utf-8") as f:
        json.dump({"flow": cfg["flow"], "flows": args.flows,
                   "backup": clue.BACKUP if os.path.normcase(os.path.abspath(args.flows))
                   == os.path.normcase(bp.FLOWS) else None,
                   "steps_before": len(orig["data"]["steps"]), "steps": len(data["steps"]),
                   "layout": {k: (v if isinstance(v, int) else list(v)) for k, v in lay.items()},
                   "label": clue.LABEL[args.lang]},
                  f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

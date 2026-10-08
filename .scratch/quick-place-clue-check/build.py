"""票 01、02: 早班會客室改成先接收线索、再開面板逐號查 1–7, 都有才按快速置入 (見 spec.md).

    .venv/Scripts/python.exe .scratch/quick-place-clue-check/build.py --lang cn            # 只算、印出
    .venv/Scripts/python.exe .scratch/quick-place-clue-check/build.py --lang cn --apply    # 寫回存檔與草稿
    .venv/Scripts/python.exe .scratch/quick-place-clue-check/build.py --lang cn --apply --flows <試跑目錄>

- 以內容定位 (clue.locate): 「領取 → 交流中分岔 → 解鎖分岔 → 線索入口 → 接收分岔」, 編號與步驟數
  只拿來核對。改成「領取 → 接收分岔 → 開面板 → 檢查區段 → 補關面板分岔 → 解鎖分岔 → 線索入口」,
  其餘步驟一字不改 (clue.rebuild)。新範本從 templates/<lang>/ 讀 (crop.py 裁的); 交流中範本
  沒人引用了, 寫存檔時自然不帶。
- 可以重跑: 已是新版時從改前的備份重建, 結果相同就不寫。
- 寫回前: AutoClick 要關著、profiles 備份到本功能的備份目錄 (不在才複製)。寫回後讀回驗證,
  草稿屬於這份存檔時連草稿與工作區一起同步。之後跑 check.py、frames.py、sim.py。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import clue
from clue import bp

import app  # noqa: E402  (步驟描述同編輯器: app.step_desc)
import flowfile  # noqa: E402


def source(lang, flows):
    """改前的存檔內容: 目前的還沒改就用它, 已改過就用本功能的備份."""
    cfg = clue.LANGS[lang]
    cur = flowfile.read(bp.flow_path(cfg["flow"], flows))
    if not clue.is_new(cur["data"]["steps"], lang):
        return cur, cur
    if not os.path.isdir(clue.BACKUP_FLOWS):
        raise SystemExit(f"{cfg['flow']}: 已是新版, 但找不到改前的備份 {clue.BACKUP_FLOWS}")
    return cur, flowfile.read(bp.flow_path(cfg["flow"], clue.BACKUP_FLOWS))


def build(lang, orig):
    """回傳 (新 data, 新 images)."""
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

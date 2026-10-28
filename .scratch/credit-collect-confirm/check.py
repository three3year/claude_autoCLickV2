from __future__ import annotations

import argparse
import json
import os
import sys

import collect
from collect import bp

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402

SKIP = ("steps", "flowFormat", flowfile.RETRY_KEY)


def _settings(data):
    return {k: v for k, v in data.items() if k not in SKIP}


def check_flow(lang, data, images, orig):
    steps, before = data["steps"], orig["data"]["steps"]
    i = collect.credit_index(before, lang)
    diff = [k for k, (a, b) in enumerate(zip(steps, before)) if a != b]
    step, old = (steps[i], before[i]) if len(steps) > i else ({}, before[i])
    keys = sorted(k for k in set(step) | set(old) if step.get(k) != old.get(k))
    want_ct = findtarget.target(before[i + 1])
    return [
        ("步驟數不變", len(steps) == len(before), f"{len(before)} → {len(steps)}"),
        ("只有收取信用那一步不同", diff == [i],
         f"不同的步驟：{[k + 1 for k in diff]}（收取信用是第 {i + 1} 步）"),
        ("只改三個欄位", keys == sorted(collect.CHANGED), f"改了：{keys}"),
        ("生效確認＝確認圖出現", step.get("confirm") == "appear", str(step.get("confirm"))),
        ("找不到時＝跳出", step.get("onNotFound") == "break", str(step.get("onNotFound"))),
        ("確認圖＝下一步的找圖目標", step.get("confirmTarget") == want_ct,
         json.dumps(step.get("confirmTarget"), ensure_ascii=False)),
        ("流程層級設定不變", _settings(data) == _settings(orig["data"])
         and flowfile.retry_interval_ms(data) == flowfile.retry_interval_ms(orig["data"]),
         "相同" if _settings(data) == _settings(orig["data"]) else "不同"),
        ("範本不變", images == orig["images"], f"{len(images)} 張"),
        ("區段完整", bp.section_error(steps) is None, bp.section_error(steps) or "完整"),
    ]


def check_draft(flow, draft, ws_images):
    data = flow["data"]
    return [
        ("草稿步驟與存檔相同", draft["steps"] == data["steps"],
         next((f"第 {k + 1} 步不同" for k, (a, b) in enumerate(zip(draft["steps"], data["steps"]))
               if a != b), "相同" if draft["steps"] == data["steps"] else "步數不同")),
        ("草稿設定與存檔相同", _settings(draft) == _settings(data)
         and flowfile.retry_interval_ms(draft) == flowfile.retry_interval_ms(data),
         "相同" if _settings(draft) == _settings(data) else "不同"),
        ("工作區範本與存檔相同", ws_images == flow["images"], f"{len(ws_images)} 張"),
    ]


def _ws_images(profile):
    out = {}
    for n, p in flowfile.Workspace(profile).images().items():
        with open(p, "rb") as f:
            out[n] = f.read()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(collect.LANGS), required=True)
    ap.add_argument("--flows", default=bp.FLOWS)
    ap.add_argument("--orig", help="改動前的流程資料夾 (預設本功能的備份)")
    args = ap.parse_args(argv)
    cfg = collect.LANGS[args.lang]
    orig_dir = args.orig or collect.orig_flows(args.lang)
    path = bp.flow_path(cfg["flow"], args.flows)
    profile = os.path.dirname(args.flows)
    flow = flowfile.read(path)
    orig = flowfile.read(bp.flow_path(cfg["flow"], orig_dir))
    res = {"orig": orig_dir, "flow": check_flow(args.lang, flow["data"], flow["images"], orig)}
    if bp.current_flow(profile) == os.path.normcase(os.path.abspath(path)):
        draft = flowfile.read_draft(profile)
        res["draft"] = (check_draft(flow, draft, _ws_images(profile)) if draft
                        else [("草稿", False, "讀不到")])
    bad = []
    for kind in ("flow", "draft"):
        if kind not in res:
            print(f"  （草稿屬於別份存檔：{os.path.basename(bp.current_flow(profile) or '')}）")
            continue
        print(f"== {cfg['flow']} {'存檔' if kind == 'flow' else '草稿＋工作區'}（對 {orig_dir}）")
        for item, ok, note in res[kind]:
            print(f"  {'OK ' if ok else 'NG '} {item}：{note}")
            if not ok:
                bad.append((kind, item))
    os.makedirs(collect.RESULTS, exist_ok=True)
    with open(os.path.join(collect.RESULTS, f"check_{args.lang}.json"), "w", encoding="utf-8") as f:
        json.dump({k: v if k == "orig" else [{"item": a, "ok": b, "note": c} for a, b, c in v]
                   for k, v in res.items()}, f, ensure_ascii=False, indent=1)
    print("讀回檢查通過" if not bad else f"**不通過**：{bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

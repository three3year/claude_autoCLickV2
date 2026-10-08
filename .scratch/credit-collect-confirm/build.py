"""票 01、02: 早班「收取信用」改成點到物資彈窗出現, 等不到就跳出分岔 (見 spec.md).

    .venv/Scripts/python.exe .scratch/credit-collect-confirm/build.py --lang tw            # 只算、印出
    .venv/Scripts/python.exe .scratch/credit-collect-confirm/build.py --lang tw --apply    # 寫回存檔與草稿

- 收取信用分岔的條件步驟 (繁中第 113 步、簡中第 124 步) 只改三個欄位: 生效確認 → 確認圖出現;
  確認圖 → 照抄緊接的下一步 (獲得物資／获得物资) 的找圖目標; 找不到時 → 跳出。
  逾時 3 秒、偏移、比色、忙碌檢查不勾都不動; 其餘步驟、流程層級設定、範本一字不改。
- 步驟以內容定位 (collect.credit_index), 編號與步驟數只拿來核對。可以重跑: 已改過就不動。
- 寫回前: AutoClick 要關著、備份 profiles (本功能的備份目錄不在才複製; 備份之後這份存檔又被
  別的改動動過時, 另備一份 `<備份>-<票號>`)。寫回後讀回驗證, 草稿屬於這份存檔時連草稿與
  工作區一起同步。之後跑 check.py 做完整讀回檢查、sim.py 跑無頭執行器。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import collect
from collect import bp

import flowfile  # noqa: E402


def rebuild(lang, data):
    """回傳 (新 data, 收取信用的索引, 說明)."""
    steps = data["steps"]
    i = collect.credit_index(steps, lang)
    new = collect.changed_step(steps[i], steps[i + 1])
    if new == steps[i]:
        return data, i, "已是新版"
    out = list(steps)
    out[i] = new
    return dict(data, steps=out), i, "改三個欄位"


def ensure_backup(lang, path, flows):
    """改正式存檔前的備份 (同時查 AutoClick 已關). 回傳這份存檔改動前的備份流程資料夾."""
    bp.preflight(flows, collect.BACKUP)
    if os.path.normcase(os.path.abspath(flows)) != os.path.normcase(bp.FLOWS):
        return None
    cfg = collect.LANGS[lang]
    cur = flowfile.read(path)
    orig = flowfile.read(bp.flow_path(cfg["flow"], collect.BACKUP_FLOWS))
    built, _, _ = rebuild(lang, orig["data"])
    if cur["images"] == orig["images"] and cur["data"] in (orig["data"], built):
        return collect.BACKUP_FLOWS
    # 備份之後這份存檔又被別的改動動過: 另備一份, 讀回檢查拿它當改動前的版本
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

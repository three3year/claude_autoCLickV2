"""接縫三: 讀回檢查兩份晚班存檔與草稿 (見 spec.md「接縫三」).

    .venv/Scripts/python.exe .scratch/evening-notice-close/check.py [--flows 目錄] [--orig 目錄]

--orig: 改動前的流程資料夾 (預設本功能的備份), 原本的步驟從那裡讀。
每份存檔 (與屬於它的草稿) 要符合:
- 共 原本+1 步, 第 1 步＝規格寫定的設定 (notice.expected_first_step)。
- 第 2 步起跟原本的第 1 步起逐一相同。
- 第 1 步用到的範本在存檔裡, 位元組跟早班那張相同; 草稿的話工作區也要有。
- 晚_繁中: 忙碌指示的圖跟早_繁中相同, 限定範圍不變 (九宮格 [8, 9])。
結果寫 results/check.json; 有任何一項不符時結束碼 1。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import notice
from notice import bp

import flowfile  # noqa: E402


def _ws_images(profile):
    out = {}
    for n, p in flowfile.Workspace(profile).images().items():
        with open(p, "rb") as f:
            out[n] = f.read()
    return out


def check_one(lang, data, images, orig, src):
    """一份 (存檔或草稿) 的檢查: [(項目, 是否通過, 說明)]."""
    cfg = notice.LANGS[lang]
    steps, before = data["steps"], orig["data"]["steps"]
    want = notice.expected_first_step(lang)
    rows = [
        ("步數", len(steps) == len(before) + 1, f"{len(before)} → {len(steps)}"),
        ("第 1 步設定", steps[0] == want if steps else False,
         json.dumps(steps[0] if steps else None, ensure_ascii=False)),
        ("第 2 步起與原本相同", steps[1:] == before,
         next((f"第 {i + 2} 步不同" for i, (a, b) in enumerate(zip(steps[1:], before))
               if a != b), "逐一相同" if steps[1:] == before else "步數不同")),
        ("區段完整", bp.section_error(steps) is None, bp.section_error(steps) or "完整"),
        (f"範本「{cfg['template']}」", images.get(cfg["template"]) == src["images"][cfg["template"]],
         "與早班位元組相同" if images.get(cfg["template"]) == src["images"][cfg["template"]]
         else ("缺" if cfg["template"] not in images else "與早班不同")),
        ("忙碌指示限定範圍不變", flowfile.busy_target(data) == flowfile.busy_target(orig["data"]),
         json.dumps(flowfile.busy_target(data), ensure_ascii=False)),
    ]
    if cfg["swap_busy"]:
        same = images.get(notice.BUSY) == src["images"][notice.BUSY]
        rows.append(("忙碌指示圖與早班相同", same, "相同" if same else "不同"))
    others = {n for n in orig["images"] if n != notice.BUSY or not cfg["swap_busy"]}
    kept = all(images.get(n) == orig["images"][n] for n in others)
    rows.append(("其他範本不變", kept, f"{len(others)} 張"))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default=bp.FLOWS)
    ap.add_argument("--orig", default=notice.BACKUP_FLOWS)
    args = ap.parse_args(argv)
    profile = os.path.dirname(args.flows)
    draft_owner = bp.current_flow(profile)
    out, bad = {}, []
    for lang, cfg in notice.LANGS.items():
        path = bp.flow_path(cfg["flow"], args.flows)
        orig = flowfile.read(bp.flow_path(cfg["flow"], args.orig))
        src = flowfile.read(bp.flow_path(cfg["src"], args.flows))
        r = flowfile.read(path)
        res = {"flow": check_one(lang, r["data"], r["images"], orig, src)}
        if draft_owner == os.path.normcase(os.path.abspath(path)):
            draft = flowfile.read_draft(profile)
            res["draft"] = (check_one(lang, draft, _ws_images(profile), orig, src)
                            if draft else [("草稿", False, "讀不到")])
        out[cfg["flow"]] = res
        for kind, rows in res.items():
            print(f"== {cfg['flow']} {'存檔' if kind == 'flow' else '草稿＋工作區'}")
            for item, ok, note in rows:
                print(f"  {'OK ' if ok else 'NG '} {item}：{note}")
                if not ok:
                    bad.append((cfg["flow"], kind, item))
        if "draft" not in res:
            print(f"  （草稿屬於別份存檔：{os.path.basename(draft_owner or '')}）")
    os.makedirs(notice.RESULTS, exist_ok=True)
    with open(os.path.join(notice.RESULTS, "check.json"), "w", encoding="utf-8") as f:
        json.dump({k: {kind: [{"item": a, "ok": b, "note": c} for a, b, c in rows]
                       for kind, rows in v.items()} for k, v in out.items()},
                  f, ensure_ascii=False, indent=1)
    print("讀回檢查通過" if not bad else f"**不通過**：{bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

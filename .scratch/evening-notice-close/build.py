"""票 01、02: 晚班兩份開頭加「找公告 X → 點到消失, 2 秒找不到就跳過」(見 spec.md).

    .venv/Scripts/python.exe .scratch/evening-notice-close/build.py            # 只算、印出
    .venv/Scripts/python.exe .scratch/evening-notice-close/build.py --apply    # 寫回存檔與草稿

- 新的第 1 步從早班同一步原樣複製 (簡中「公告关闭」、繁中「圓形叉叉」, 連固定矩形),
  只把逾時改成 2 秒; 範本圖從早班存檔搬 (同一客戶端的校準對基準距離、搜尋範圍都相同, 不換算)。
- 晚_繁中的忙碌指示圖換成早_繁中那張 (票 06 從 demo2 重截的), 限定範圍不動。
- 其餘步驟一字不改, 編號 +1。可以重跑: 第 1 步已經是關公告那步就不再插。
- 寫回前: AutoClick 要關著、備份 profiles (本功能的備份目錄不在才複製); 寫回後讀回驗證、
  草稿屬於這份存檔時連草稿與工作區一起同步。之後跑 check.py 做完整讀回檢查。
"""
from __future__ import annotations

import argparse
import copy
import os
import sys

import notice
from notice import bp

import flowfile  # noqa: E402


def source_step(lang, src):
    """早班那一步 (唯一一個用這張範本的找圖步驟) 複製一份, 逾時改 2 秒."""
    tmpl = notice.LANGS[lang]["template"]
    hits = [s for s in src["data"]["steps"] if notice.is_notice_step(s, lang)]
    if len(hits) != 1:
        raise SystemExit(f"{notice.LANGS[lang]['src']}: 用「{tmpl}」的步驟有 {len(hits)} 個, 預期 1 個")
    step = copy.deepcopy(hits[0])
    step["timeout"] = notice.TIMEOUT
    if step != notice.expected_first_step(lang):
        raise SystemExit(f"{notice.LANGS[lang]['src']} 的「{tmpl}」步驟跟規格寫的不同: {step}")
    return step


def rebuild(lang, r, src):
    """回傳 (新 data, 新 images, 說明)."""
    cfg = notice.LANGS[lang]
    data, images = r["data"], dict(r["images"])
    steps = data["steps"]
    rest = steps[1:] if steps and notice.is_notice_step(steps[0], lang) else steps
    if any(notice.is_notice_step(s, lang) for s in rest):
        raise SystemExit(f"{cfg['flow']}: 第 1 步以外已有「{cfg['template']}」步驟, 不認得的寫法")
    new_steps = [source_step(lang, src)] + rest
    tmpl = cfg["template"]
    if tmpl in images and images[tmpl] != src["images"][tmpl] and rest is steps:
        raise SystemExit(f"{cfg['flow']}: 已有同名但不同圖的「{tmpl}」範本")
    images[tmpl] = src["images"][tmpl]
    notes = [f"第 1 步插入「{tmpl}」({len(rest)} → {len(new_steps)} 步)"
             if rest is steps else "第 1 步已是關公告那步 (重跑, 換成最新的)"]
    if cfg["swap_busy"]:
        busy, sbusy = flowfile.busy_target(data), flowfile.busy_target(src["data"])
        if busy != sbusy:
            raise SystemExit(f"{cfg['flow']} 與 {cfg['src']} 的忙碌指示設定不同: {busy} / {sbusy}")
        if images[notice.BUSY] != src["images"][notice.BUSY]:
            notes.append("忙碌指示圖換成早班那張")
        images[notice.BUSY] = src["images"][notice.BUSY]
    unused = set(images) - set(flowfile.flow_refs(dict(data, steps=new_steps)))
    if unused & {tmpl, notice.BUSY}:
        raise SystemExit(f"{cfg['flow']}: 搬進來的範本沒被引用: {unused}")
    return dict(data, steps=new_steps), images, notes


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--flows", default=bp.FLOWS)
    args = ap.parse_args(argv)
    built = []
    for lang, cfg in notice.LANGS.items():
        path = bp.flow_path(cfg["flow"], args.flows)
        r = flowfile.read(path)
        src = flowfile.read(bp.flow_path(cfg["src"], args.flows))
        data, images, notes = rebuild(lang, r, src)
        err = bp.section_error(data["steps"])
        if err:
            raise SystemExit(f"{cfg['flow']}: 區段不完整: {err}")
        print(f"{cfg['flow']}: {'；'.join(notes)}")
        if data == r["data"] and images == r["images"]:
            print("    已是新版, 不動")
            continue
        built.append((path, data, images, r["pos"]))
    if not args.apply or not built:
        return 0
    bp.preflight(args.flows, notice.BACKUP)
    for path, data, images, pos in built:
        back = bp.write_flow(path, data, images, pos)
        if back["data"]["steps"] != data["steps"] or back["images"] != images:
            raise SystemExit(f"{os.path.basename(path)}: 讀回的內容與寫入的不同")
        print(f"{os.path.basename(path)}: 已寫回")
        if bp.sync_draft(path, os.path.dirname(args.flows)):
            print("    草稿與工作區已同步")
    return 0


if __name__ == "__main__":
    sys.exit(main())

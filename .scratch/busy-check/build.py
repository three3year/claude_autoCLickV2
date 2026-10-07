"""票 05: 四份流程 (早_簡中、早_繁中、晚_簡中、晚_繁中) 在會讓遊戲忙的步驟勾`忙碌檢查` (見 spec.md).

    .venv/Scripts/python.exe .scratch/busy-check/build.py            # 只算、印出要勾的步驟
    .venv/Scripts/python.exe .scratch/busy-check/build.py --apply    # 寫回存檔與草稿, 讀回驗證
    .venv/Scripts/python.exe .scratch/busy-check/build.py --check    # 只做讀回驗證 (對備份比)

要勾的步驟以內容定位、不靠編號 (該流程沒有的就略過):

- ADR 0010 拿掉「忙碌指示 → 等待消失」的位置＝換班段 (「非工作區 → 僅等待出現」到
  「非工作區 → 點擊」之間) 的每一個相對座標點擊 (點 ⇄; busy-pause-fixed-rect
  `results/remove_busy_waits.json` 記的「緊接在前」那一步)。
- 換班段的每一個拖曳。
- 開頭清彈窗 (基建入口之前) 的關閉點擊: 簽到、活動、公告 (晚班開頭新加的公告也算)、
  獲得物資 (繁中是找圖點擊; 簡中是「找圖 获得物资 僅等待 → 相對點擊」, 勾那個點擊)。
- 傳遞線索的點擊。
- 可收獲、幹員信賴、確定 (找圖點擊)。

忙碌出現等候不寫鍵 (預設 1000ms)。其餘步驟一字不改。可以重跑 (已勾的不再變)。
寫回前: AutoClick 要關著、備份 profiles 到 app/dist/profiles-backup-2026-10-08-busy-check/
(不在才複製); 寫回後讀回驗證 (勾選集合＝預期、其他內容與備份相同、流程有忙碌指示),
草稿屬於這份存檔時連草稿一起同步。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "busy-pause-fixed-rect"))
import common  # noqa: E402  (busy-pause-fixed-rect/common.py: 路徑、preflight、write_flow、sync_draft)

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402
from automation.runner import BUSY_CHECK_KEY, busy_check  # noqa: E402

BACKUP = os.path.join(common.APP, "dist", "profiles-backup-2026-10-08-busy-check")
RESULTS = os.path.join(HERE, "results")

SHIFT_ANCHOR = {"非工作区", "非工作區"}           # 換班段的頭尾: 僅等待出現 … 點擊
BASE_ENTRY = {"基建入口", "基建BASE", "基建图标"}  # 開頭清彈窗到此為止
POPUP_CLOSE = {"签到关闭", "活动关闭", "公告关闭", "圓形叉叉", "獲得物資"}   # 找圖點擊
POPUP_WAIT_THEN_CLICK = {"获得物资"}   # 簡中: 找圖僅等待 → 相對點擊 (勾那個點擊)
CLUE_PASS = {"传递线索", "傳遞線索"}
BUSY_CLICKS = {"可收获", "可收穫", "干员信赖", "幹員信賴", "确定", "確定"}


def _tmpl(s):
    return findtarget.template(s) if s.get("type") == "find_click" else None


def _find_click(s):
    return s.get("type") == "find_click" and s.get("action", "click") == "click"


def _find_wait(s):
    return s.get("type") == "find_click" and s.get("action") == "none"


def shift_range(steps):
    """換班段 (索引區間, 含頭尾): 「非工作區 僅等待出現」到「非工作區 點擊」."""
    start = next((i for i, s in enumerate(steps)
                  if _find_wait(s) and _tmpl(s) in SHIFT_ANCHOR), None)
    end = next((i for i, s in enumerate(steps)
                if _find_click(s) and _tmpl(s) in SHIFT_ANCHOR), None)
    if start is None or end is None or end <= start:
        raise SystemExit(f"找不到換班段 (非工作區 僅等待 {start} / 點擊 {end})")
    return start, end


def plan(steps):
    """回傳 {索引: 理由} (0-based)."""
    out = {}
    lo, hi = shift_range(steps)
    for i in range(lo, hi):
        s = steps[i]
        if s.get("type") == "click" and s.get("mode") == "prev" and "confirm" not in s:
            out[i] = "換班點 ⇄ (ADR 0010 拿掉等待步驟的位置)"
        elif s.get("type") == "drag":
            out[i] = "換班拖曳"
    base = next((i for i, s in enumerate(steps)
                 if _find_click(s) and _tmpl(s) in BASE_ENTRY), None)
    if base is None:
        raise SystemExit("找不到基建入口")
    for i in range(base):
        s = steps[i]
        if _find_click(s) and _tmpl(s) in POPUP_CLOSE:
            out[i] = f"開頭清彈窗: 關閉「{_tmpl(s)}」"
        elif (s.get("type") == "click" and i > 0 and _find_wait(steps[i - 1])
              and _tmpl(steps[i - 1]) in POPUP_WAIT_THEN_CLICK):
            out[i] = f"開頭清彈窗: 關閉「{_tmpl(steps[i - 1])}」(點擊)"
    for i, s in enumerate(steps):
        if _find_click(s) and _tmpl(s) in CLUE_PASS:
            out[i] = "傳遞線索"
        elif _find_click(s) and _tmpl(s) in BUSY_CLICKS:
            out[i] = f"確認會被忙碌拖到逾時的點擊「{_tmpl(s)}」"
    return dict(sorted(out.items()))


def apply_plan(steps, picks):
    new = copy.deepcopy(steps)
    for i in picks:
        new[i][BUSY_CHECK_KEY] = True
    return new


def check_flow(name, data, images, expect, base):
    """讀回驗證: 勾選集合＝預期、其他內容與 base (備份) 相同、忙碌指示在、沒寫出現等候鍵."""
    errs = []
    steps = data["steps"]
    got = [i for i, s in enumerate(steps) if busy_check(s)]
    if got != sorted(expect):
        errs.append(f"勾選集合不同: 預期 {[i + 1 for i in expect]} 實際 {[i + 1 for i in got]}")
    bsteps = base["data"]["steps"]
    if len(bsteps) != len(steps):
        errs.append(f"步驟數不同: 備份 {len(bsteps)} 現在 {len(steps)}")
    else:
        for i, (a, b) in enumerate(zip(steps, bsteps)):
            a2 = {k: v for k, v in a.items() if k != BUSY_CHECK_KEY}
            if a2 != b:
                errs.append(f"第 {i + 1} 步除了忙碌檢查以外有改動")
    others = {k: v for k, v in data.items() if k != "steps"}
    bothers = {k: v for k, v in base["data"].items() if k != "steps"}
    if others != bothers:
        errs.append(f"流程層級設定有改動: {sorted(set(others) ^ set(bothers)) or '值不同'}")
    if flowfile.BUSY_APPEAR_KEY in data:
        errs.append("不該寫忙碌出現等候鍵 (用預設)")
    if flowfile.busy_target(data) is None:
        errs.append("流程沒有忙碌指示, 執行前檢查會擋")
    if images != base["images"]:
        errs.append("範本圖有改動")
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--flows", default=common.FLOWS)
    args = ap.parse_args(argv)
    os.makedirs(RESULTS, exist_ok=True)
    summary = {}
    built = []
    for name in common.FLOW_NAMES:
        path = common.flow_path(name, args.flows)
        r = flowfile.read(path)
        steps = r["data"]["steps"]
        picks = plan(steps)
        already = [i for i in picks if busy_check(steps[i])]
        extra = [i for i, s in enumerate(steps) if busy_check(s) and i not in picks]
        print(f"===== {name}: {len(steps)} 步, 要勾 {len(picks)} 步"
              f"{f' (已勾 {len(already)})' if already else ''}"
              f"{f' **另有不在計畫內的勾選 {[i + 1 for i in extra]}**' if extra else ''}")
        for i, why in picks.items():
            import app
            print(f"  {i + 1:3d} {app.step_desc(steps[i])[:60]}  ← {why}")
        summary[name] = {"steps": len(steps),
                         "checked": [{"no": i + 1, "type": steps[i]["type"],
                                      "why": why} for i, why in picks.items()]}
        if args.check:
            continue
        new = apply_plan(steps, picks)
        if new == steps:
            print("    已是新版, 不動")
            continue
        built.append((name, path, dict(r["data"], steps=new), r["images"], r["pos"],
                      sorted(picks)))
    with open(os.path.join(RESULTS, "build.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    if args.apply and built:
        common.preflight(args.flows, BACKUP)
        for name, path, data, images, pos, picks in built:
            back = common.write_flow(path, data, images, pos)
            if back["data"]["steps"] != data["steps"]:
                raise SystemExit(f"{name}: 讀回的步驟與寫入的不同")
            print(f"{name}: 已寫回")
            if common.sync_draft(path, os.path.dirname(args.flows)):
                print("    草稿與工作區已同步")

    if args.apply or args.check:
        bad = 0
        for name in common.FLOW_NAMES:
            path = common.flow_path(name, args.flows)
            r = flowfile.read(path)
            bpath = os.path.join(BACKUP, "arknights", "flows", os.path.basename(path))
            if not os.path.isfile(bpath):
                print(f"{name}: 沒有備份可比 ({bpath})")
                bad += 1
                continue
            base = flowfile.read(bpath)
            errs = check_flow(name, r["data"], r["images"],
                              list(plan(base["data"]["steps"])), base)
            draft_note = ""
            if common.current_flow(os.path.dirname(args.flows)) == os.path.normcase(
                    os.path.abspath(path)):
                d = flowfile.read_draft(os.path.dirname(args.flows))
                same = d is not None and d.get("steps") == r["data"]["steps"]
                draft_note = "、草稿一致" if same else "、**草稿不一致**"
                bad += 0 if same else 1
            print(f"{name}: {'讀回驗證通過' if not errs else '; '.join(errs)}{draft_note}")
            bad += len(errs)
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

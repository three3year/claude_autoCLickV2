"""早_簡中: 辦公室換班之後加一站「回收站」換班 (示範影片 add5.mp4, 簡中視窗 1696×912, 2026-10-10).

    .venv/Scripts/python .scratch/scale-range/add_recycle.py [--dry]

影片: 進駐總覽從清單頂端一路往下拖, 最後一次拖完 (f164 起) 辦公室標題在影片 (821,216)、
回收站 ⇌ 在 (1622,533), f199 點 ⇌。回收站標題＝辦公室標題 +217 (類別標題間距, 同 LAYOUT)。

流程狀態 (發電站拖完, 捲 1718) 辦公室標題在螢幕 y=606, 回收站的 ⇌ 會落在視窗底邊、
忙碌指示帶附近 → 照影片再拖一次 (333px, 到影片最終狀態 捲 2051), 回收站標題預期落在
螢幕 y=490, 再照票 10 的定位法: 標題窄帶 + 由上到下第 1 個 → 相對座標點 ⇌。
整段包成單分支分岔: 辦公室標題找不到 (捲動漂走) 就整段跳過, 不停掉後面的好友與採購。

自我驗證同 shift_build: 影片最終狀態的幾幀貼到搜尋範圍畫布上, ×0.85/×1.0/×1.15 帶內要挑到
回收站標題本身, 落點離一個 ⇌ 中心 ≤ SWAP_TOL; 拖曳前的定位 (辦公室窄帶) 用 f152 (漂 +45px) 驗。
"""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile

import srcommon as sr
from srcommon import bp
from shift_build import BAND, HEADER_TOL, SWAP_TOL

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402

LANG, FLOW, VIDEO = "cn", "早_簡中", "add5"
HEADER = "标题_回收站"
OFFICE = "标题_办公室"
HEADER_GAP = 217                 # 類別標題 → 下一個類別標題 (各一列時): label_dy 53 + gap 164
CLEAN_FRAME = 168                # 影片最終狀態、游標停在清單頂端 (1419,182) 的幀
OFFICE_AT = (821, 216)           # 最終狀態辦公室標題中心 (影片座標, 用既有範本量到)
RECYCLE_SWAP = (1622, 533)       # 最終狀態回收站 ⇌ 中心 (影片座標)
FINAL_FRAMES = [168, 176, 196, 230]   # 最終狀態 (230 是點 ⇌ 之後, 該列反白)
PRE_DRAG_FRAME = 152             # 辦公室標題在影片 y=594 (流程狀態 549, 漂 +45)
DRAG_X = 626                     # 其他站的拖曳欄 (螢幕 1542 / 影片 1447, 影片裡使用者也拖這欄)
DRAG_FROM_VIDEO_Y = 721          # 影片裡每次拖曳的起點 y
OFFICE_TOP = 2324                # 辦公室標題頂端狀態的螢幕 y (shift_cn.json tops)
SCROLLED_BEFORE = 1718           # 發電站拖完的累計捲動量 (shift_cn.json)
BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-10-recycle-shift")


def crop_header():
    x, y = OFFICE_AT[0], OFFICE_AT[1] + HEADER_GAP
    box = (x - 51, y - 20, 102, 40)         # 同 rebuild_shift HEADERS cn 的框 (770, y-20, 102, 40)
    img = sr.crop(sr.frame(VIDEO, CLEAN_FRAME), box)
    d = os.path.join(sr.TEMPLATES, LANG)
    os.makedirs(d, exist_ok=True)
    bp.write_img(os.path.join(d, HEADER + ".png"), img)
    return bp.encode(img), box


def band_rect(expected_y, anchor, region):
    x0, x1 = (766, 890)
    ox, _ = sr.offset(LANG)
    col = (x0 + ox, region[1], x1 - x0, region[3])
    hh = 44
    scr = (col[0], int(round(expected_y - BAND - hh / 2)), col[2], int(2 * BAND + hh))
    return findtarget.fixed_rect_from_screen(scr, anchor, 1.0)


def build_steps(office_step, anchor, region):
    ox, oy = sr.offset(LANG)
    office_y = OFFICE_TOP - SCROLLED_BEFORE                     # 606
    final_scroll = OFFICE_TOP - oy - OFFICE_AT[1]               # 2051
    drag = final_scroll - SCROLLED_BEFORE                       # 333
    y1 = DRAG_FROM_VIDEO_Y + oy - office_y                      # 相對辦公室標題
    recycle_y = OFFICE_TOP + HEADER_GAP - final_scroll          # 490
    header_x = OFFICE_AT[0] + ox                                # 916
    rel = (RECYCLE_SWAP[0] + ox - header_x, RECYCLE_SWAP[1] + oy - recycle_y)
    locate_office = {
        "type": "find_click", "target": dict(findtarget.target(office_step)),
        "action": "none", "timeout": 3, "interval": 0.3, "onNotFound": "skip",
        "updateOrigin": True, "offsetX": 0, "offsetY": 0}
    steps = [
        {"type": "branch_start"},
        locate_office,
        {"type": "drag", "ms": 500, "holdMs": 500, "mode": "prev",
         "x1": DRAG_X, "y1": y1, "x2": DRAG_X, "y2": y1 - drag, "button": "left",
         "confirm": "gone", "timeout": 10, "interval": 0.3, "onNotFound": "break",
         "busyCheck": True},
        {"type": "find_click",
         "target": findtarget.make_target(HEADER, limit=band_rect(recycle_y, anchor, region),
                                          pick={"kind": "top", "n": 1}),
         "action": "none", "timeout": 10, "interval": 0.3, "onNotFound": "break",
         "updateOrigin": True, "offsetX": 0, "offsetY": 0},
        {"type": "click", "mode": "prev", "x": rel[0], "y": rel[1], "button": "left",
         "clicks": 1, "updateOrigin": True, "busyCheck": True},
        {"type": "branch_end"},
    ]
    info = {"office_y": office_y, "final_scroll": final_scroll, "drag": drag,
            "recycle_y": recycle_y, "rel": rel}
    return steps, info


def find_insert(steps):
    """辦公室站 (找 标题_办公室 → 點 ⇌ → branch_end) 之後的位置 (0-based)."""
    idx = [i for i, s in enumerate(steps)
           if s["type"] == "find_click" and findtarget.template(s) == OFFICE]
    assert len(idx) == 1, idx
    i = idx[0]
    assert steps[i + 1]["type"] == "click" and steps[i + 2]["type"] == "branch_end", steps[i:i + 3]
    assert findtarget.template(steps[i + 3]) == "非工作区", steps[i + 3]
    return i, i + 3


def self_check(hub, anchor, region, steps, info):
    place = sr.place(LANG, region)
    ox, oy = sr.offset(LANG)
    sr.prefetch([(VIDEO, f) for f in FINAL_FRAMES + [PRE_DRAG_FRAME]])
    rows = []
    locate = steps[3]
    tgt = findtarget.target(locate)
    for fn in FINAL_FRAMES:
        canvas, org = place(sr.frame(VIDEO, fn))
        f_sw = sr.find_scaled(hub, {"template": "_swap"}, canvas, org, anchor, 1.0)
        swaps = sorted(sr.center(m.box) for m in f_sw.matches)
        expected = (OFFICE_AT[0] + ox, info["recycle_y"])
        per, ok = {}, True
        for s in sr.PICK_SCALES:
            f = sr.find_scaled(hub, tgt, canvas, org, anchor, s)
            e = {"n": len(f.matches), "found": f.picked is not None}
            if f.picked is not None:
                c = sr.center(f.picked.box)
                c1 = (c[0] / s, c[1] / s)
                e["center"] = (round(c1[0]), round(c1[1]))
                e["score"] = round(float(f.picked.score), 3)
                e["is_header"] = abs(c1[1] - expected[1]) <= HEADER_TOL and abs(c1[0] - expected[0]) <= HEADER_TOL
                p = (c1[0] + info["rel"][0], c1[1] + info["rel"][1])
                near = min(swaps, key=lambda q: (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) if swaps else None
                d = ((near[0] - p[0]) ** 2 + (near[1] - p[1]) ** 2) ** 0.5 if near else None
                e["point"] = (round(p[0]), round(p[1]))
                e["swap"] = near
                e["dist"] = round(d, 1) if d is not None else None
                e["ok"] = bool(e["is_header"] and d is not None and d <= SWAP_TOL)
            else:
                e["ok"] = False
            ok = ok and e["ok"]
            per[str(s)] = e
        rows.append({"frame": fn, "ok": ok, "scales": per})
        print(f"  f{fn} {'OK' if ok else 'NG'} 預期標題 {expected}: " + "; ".join(
            f"×{s}: {e['n']}個 "
            + (f"挑 {e['center']} {e['score']} {'標題' if e['is_header'] else '別的'} 落點 {e['point']}→⇌{e['swap']} {e['dist']}px"
               if e["found"] else "無")
            for s, e in per.items()))
    # 拖曳前的定位: 辦公室窄帶在漂了 +45px 的幀上要挑到辦公室標題
    canvas, org = place(sr.frame(VIDEO, PRE_DRAG_FRAME))
    tgt_o = findtarget.target(steps[1])
    expected_o = (OFFICE_AT[0] + ox, 594 + oy)
    pre = {}
    for s in sr.PICK_SCALES:
        f = sr.find_scaled(hub, tgt_o, canvas, org, anchor, s)
        if f.picked is None:
            pre[str(s)] = {"found": False, "ok": False}
            continue
        c = sr.center(f.picked.box)
        c1 = (round(c[0] / s), round(c[1] / s))
        pre[str(s)] = {"found": True, "n": len(f.matches), "center": c1,
                       "ok": abs(c1[1] - expected_o[1]) <= HEADER_TOL}
    print(f"  拖曳前定位 f{PRE_DRAG_FRAME} (辦公室標題應在 {expected_o}): " + "; ".join(
        f"×{s}: " + (f"{e['n']}個 挑 {e['center']} {'OK' if e['ok'] else 'NG'}" if e["found"] else "無")
        for s, e in pre.items()))
    return {"recycle": rows, "pre_drag": pre,
            "ok": all(r["ok"] for r in rows) and all(e["ok"] for e in pre.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只驗證不寫檔")
    args = ap.parse_args()
    if bp.autoclick_running():
        raise SystemExit("AutoClick 正在執行: 請先關掉")
    src = bp.flow_path(FLOW, sr.FLOWS)
    r = flowfile.read(src)
    data, images, pos = r["data"], dict(r["images"]), dict(r["pos"])
    steps = data["steps"]
    if any(findtarget.template(s) == HEADER for s in steps if s["type"] == "find_click"):
        raise SystemExit(f"{FLOW} 已經有 {HEADER} 的步驟, 不重複加")
    region = data["scanRegion"]
    anchor = tuple(sr.load(os.path.join(sr.RESULTS, f"convert_{LANG}.json"))[FLOW]["pair"]["new_anchor"])
    office_i, insert_at = find_insert(steps)
    header_png, box = crop_header()
    print(f"範本 {HEADER}: {VIDEO} f{CLEAN_FRAME} 框 {box}")
    new_steps, info = build_steps(steps[office_i], anchor, region)
    print(f"幾何: 辦公室標題 y={info['office_y']} → 拖 {info['drag']}px (影片最終捲 {info['final_scroll']}), "
          f"回收站標題預期 y={info['recycle_y']}, ⇌ 相對 {info['rel']}; 插在第 {insert_at + 1} 步前")
    for k, s in enumerate(new_steps, insert_at + 1):
        print(f"  {k} {s}")
    with open(os.path.join(sr.TEMPLATES, LANG, "_swap.png"), "rb") as f:
        swap_png = f.read()
    tmp = tempfile.mkdtemp(prefix="sr_recycle_")
    try:
        hub = bp.make_hub({OFFICE: images[OFFICE], HEADER: header_png, "_swap": swap_png},
                          [OFFICE, HEADER, "_swap"], tmp)
        print("自我驗證:")
        check = self_check(hub, anchor, region, new_steps, info)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sr.dump(os.path.join(sr.RESULTS, "recycle_cn.json"),
            {"info": info, "steps": new_steps, "insert_at": insert_at + 1, "check": check})
    if not check["ok"]:
        raise SystemExit("自我驗證沒過, 不寫檔 (見 results/recycle_cn.json)")
    if args.dry:
        print("--dry: 不寫檔")
        return
    os.makedirs(BACKUP, exist_ok=True)
    shutil.copyfile(src, os.path.join(BACKUP, os.path.basename(src)))
    steps[insert_at:insert_at] = new_steps
    images[HEADER] = header_png
    data.pop("flowFormat", None)
    targets = [src]
    conv = bp.flow_path(FLOW, sr.CONVERTED)
    if os.path.exists(conv):
        targets.append(conv)
    for path in targets:
        missing = flowfile.write(path, data, images, pos)
        assert not missing, missing
        back = flowfile.read(path)
        assert HEADER in back["images"] and len(back["data"]["steps"]) == len(steps)
        print(f"寫出 {path}: {len(back['data']['steps'])} 步、{len(back['images'])} 張範本")
    print("草稿同步:", "已改寫" if bp.sync_draft(src) else "草稿不屬於這份, 不動")
    print(f"備份: {BACKUP}")


if __name__ == "__main__":
    main()

"""票 02: 早班兩版的接收線索改成真的按「全部收取」(見 issues/02-tw-receive-clues.md).

    .venv/Scripts/python.exe .scratch/run-1007-fixes/build_clues.py            # 只驗證
    .venv/Scripts/python.exe .scratch/run-1007-fixes/build_clues.py --apply    # 驗證全過才寫回

範本從使用者 10/07 錄的 add1.mp4 (簡中)、add2.mp4 (繁中) 裁 (影片座標, 與流程同尺度):
- 接收線索 (繁中): add2 f160 (1790,350,58,58)——收完、沒有 NEW 標籤的那格; 有 NEW 時也找得到。
  簡中沿用原本的 接收线索 範本與固定矩形。
- 全部收取: 繁中 add2 f80 (1554,958,192,52)、簡中 add1 f100 (1378,852,170,46), 可按的藍色版
  (簡中原本的範本是收完後的暗色版)。比色分不出藍色與暗色 (暗色比色仍 0.98), 所以不比色。
- 暫未收到新的線索: 繁中 add2 f125 (1557,518,194,27)、簡中 add1 f170 (1381,463,171,24)。
  收完、或本來就沒有線索時面板中間的字樣; 當「全部收取」的確認圖。

分岔 (簡中換掉原本第 64–69 步那個分岔; 繁中插在「線索面板」之後、「傳遞線索」之前):
  接收線索 → 點擊, 點到確認圖 (全部收取) 出現 (逾時5s→跳出)
  全部收取 → 點擊, 點到確認圖 (暫未收到新的線索) 出現 (逾時8s→跳過)
  座標點擊 上一步 (面板外的線索板空白處) → 點到確認圖 (傳遞線索) 出現 (逾時5s→跳過)
面板開著時會蓋住右側那排圖示, 傳遞線索重新出現＝面板關了。
固定矩形照票 08 (busy-pause-fixed-rect) 的做法: 影片座標的框外擴 40px 換成搜尋範圍的比例。
"""
from __future__ import annotations

import argparse
import copy
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "busy-pause-fixed-rect"))

import common as bp  # noqa: E402  (busy-pause-fixed-rect 的共用: 路徑、換算、寫檔、草稿同步)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402

BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-07-run-1007-fixes-02")
MARGIN = 40

LANGS = {
    "cn": {
        "flow": "早_簡中", "video": "add1",
        "recv": "接收线索", "all": "全部收取", "empty": "暂未收到新的线索",
        "relay": "传递线索", "after": "线索",
        "crops": {"全部收取": (100, (1378, 852, 170, 46)),
                  "暂未收到新的线索": (170, (1381, 463, 171, 24))},
        "close": (-429, -184),
        # 驗證影格: 範本 → (該找得到的, 不該找到的)
        "frames": {"接收线索": ((0, 30, 190, 220), (80, 160)),
                   "全部收取": ((80, 100, 160, 180), (0, 190)),
                   "暂未收到新的线索": ((160, 170, 180), (0, 80, 100, 190)),
                   "传递线索": ((0, 190, 220), (80, 100, 160, 180))},
    },
    "tw": {
        "flow": "早_繁中", "video": "add2",
        "recv": "接收線索", "all": "全部收取", "empty": "暫未收到新的線索",
        "relay": "傳遞線索", "after": "線索面板",
        "crops": {"接收線索": (160, (1790, 350, 58, 58)),
                  "全部收取": (80, (1554, 958, 192, 52)),
                  "暫未收到新的線索": (125, (1557, 518, 194, 27))},
        # 簡中的 (-429,-184) 換成繁中尺度 (基準距離 1868 / 1650)
        "close": (-486, -208),
        "frames": {"接收線索": ((0, 40, 160, 180), (80, 115)),
                   "全部收取": ((80, 115, 125), (0, 160)),
                   "暫未收到新的線索": ((112, 115, 125, 130), (0, 80, 95, 140)),
                   "傳遞線索": ((0, 140, 160), (80, 90, 115, 125))},
    },
}


def frame(video, i):
    cap = cv2.VideoCapture(os.path.join(bp.VIDEO_DIR, video + ".mp4"))
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, img = cap.read()
    if not ok:
        raise SystemExit(f"{video} 讀不到第 {i} 格")
    return img


def crops(cfg):
    out, boxes = {}, {}
    for name, (i, box) in cfg["crops"].items():
        x, y, w, h = box
        out[name] = bp.encode(frame(cfg["video"], i)[y:y + h, x:x + w])
        boxes[name] = box
    return out, boxes


def rect(lang, box, region):
    return bp.video_box_to_rect(box, lang, region, MARGIN)


def find_step(tgt, confirm_tgt, timeout, on_nf):
    return {"type": "find_click", "interval": 0.3, "confirm": "appear", "timeout": timeout,
            "onNotFound": on_nf, "offsetX": 0, "offsetY": 0,
            "confirmTarget": confirm_tgt, "target": tgt, "action": "click",
            "button": "left", "clicks": 1, "updateOrigin": True}


def block(cfg, recv_tgt, all_tgt, empty_tgt, relay_tgt):
    x, y = cfg["close"]
    return [
        {"type": "branch_start"},
        find_step(recv_tgt, all_tgt, 5, "break"),
        find_step(all_tgt, empty_tgt, 8, "skip"),
        {"type": "click", "mode": "prev", "x": x, "y": y, "button": "left", "clicks": 1,
         "updateOrigin": True, "confirm": "appear", "confirmTarget": copy.deepcopy(relay_tgt),
         "timeout": 5, "interval": 0.3, "onNotFound": "skip"},
        {"type": "branch_end"},
    ]


def _tmpl(s):
    return findtarget.template(s) if s.get("type") == "find_click" else ""


def rebuild(lang, data, boxes):
    """回傳 (新 steps, 被換掉/插入的位置說明)."""
    cfg = LANGS[lang]
    steps = data["steps"]
    region = data["scanRegion"]
    relay_i = next(i for i, s in enumerate(steps) if _tmpl(s) == cfg["relay"])
    relay_tgt = findtarget.target(steps[relay_i])
    all_tgt = {"template": cfg["all"], "limit": rect(lang, boxes[cfg["all"]], region)}
    empty_tgt = {"template": cfg["empty"], "limit": rect(lang, boxes[cfg["empty"]], region)}
    recv_i = next((i for i, s in enumerate(steps) if _tmpl(s) == cfg["recv"]), None)
    if recv_i is not None:
        # 簡中: 換掉原本整個分岔 (接收线索 的上一步是 branch_start)
        start = recv_i - 1
        if steps[start].get("type") != "branch_start":
            raise SystemExit(f"{cfg['flow']}: 接收线索不在分岔開頭, 不認得的寫法")
        end = next(j for j in range(recv_i, len(steps)) if steps[j].get("type") == "branch_end")
        # 傳遞線索緊接在分岔後 (繁中重跑), 或包在下一個分岔裡 (簡中)
        if _tmpl(steps[start - 1]) != cfg["after"] or end + 1 not in (relay_i - 1, relay_i):
            raise SystemExit(f"{cfg['flow']}: 接收线索分岔前後不是預期的步驟")
        recv_tgt = findtarget.target(steps[recv_i])
        new = block(cfg, recv_tgt, all_tgt, empty_tgt, relay_tgt)
        where = f"第 {start + 1}–{end + 1} 步換成第 {start + 1}–{start + len(new)} 步"
        return steps[:start] + new + steps[end + 1:], where, start
    # 繁中: 插在「線索面板」與「傳遞線索」之間
    if _tmpl(steps[relay_i - 1]) != cfg["after"]:
        raise SystemExit(f"{cfg['flow']}: 傳遞線索的上一步不是 {cfg['after']}")
    recv_tgt = {"template": cfg["recv"], "limit": rect(lang, boxes[cfg["recv"]], region)}
    new = block(cfg, recv_tgt, all_tgt, empty_tgt, relay_tgt)
    where = f"插在第 {relay_i} 步之後 (新的第 {relay_i + 1}–{relay_i + len(new)} 步)"
    return steps[:relay_i] + new + steps[relay_i:], where, relay_i


def verify(lang, steps, at, images):
    """真引擎: 新分岔裡每個找圖目標/確認圖, 在影格 (貼到實機搜尋範圍畫布) 上該找到的找到、不該的找不到."""
    cfg = LANGS[lang]
    region = None
    tgts = {}
    for s in steps[at:at + 5]:
        for t in (findtarget.target(s) if s["type"] == "find_click" else None,
                  findtarget.confirm_target(s)):
            if t:
                tgts.setdefault(t["template"], t)
    names = sorted(tgts)
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        hub = bp.make_hub(images, names, tmp)
        for name in names:
            want, nowant = cfg["frames"][name]
            for i, expect in [(i, True) for i in want] + [(i, False) for i in nowant]:
                canvas, org = PLACE[lang](frame(cfg["video"], i))
                f = findtarget.find(tgts[name], hub, canvas, org, origin=None, scale=1.0)
                ok = (f.picked is not None) == expect
                got = (f"{findtarget.fmt_box(f.picked.box)} {f.picked.score:.3f}"
                       if f.picked else f"無 ({f.failed})")
                print(f"  {'OK ' if ok else 'NG '} {name} f{i:03d} 預期{'有' if expect else '無'}: {got}")
                if not ok:
                    fails.append((name, i))
    return fails


PLACE = {}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(LANGS), action="append")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    langs = args.lang or sorted(LANGS)
    if args.apply:
        if bp.autoclick_running():
            raise SystemExit("AutoClick 正在執行: 請先關掉 (不然草稿會把改動蓋回去)")
        if not os.path.isdir(BACKUP):
            shutil.copytree(os.path.dirname(bp.PROFILE), BACKUP)
            print(f"已備份 profiles 到 {BACKUP}")
    bad = False
    for lang in langs:
        cfg = LANGS[lang]
        path = bp.flow_path(cfg["flow"])
        r = flowfile.read(path)
        data, images = copy.deepcopy(r["data"]), dict(r["images"])
        PLACE[lang] = bp.frame_region(lang, data["scanRegion"])
        new_imgs, boxes = crops(cfg)
        images.update(new_imgs)
        n0 = len(data["steps"])
        data["steps"], where, at = rebuild(lang, data, boxes)
        print(f"{cfg['flow']}: 步驟 {n0} → {len(data['steps'])}；{where}")
        err = bp.section_error(data["steps"])
        if err:
            raise SystemExit(f"{cfg['flow']}: 區段結構錯誤: {err}")
        fails = verify(lang, data["steps"], at, images)
        if fails:
            bad = True
            print(f"  驗證不符 {len(fails)} 項: 不寫回")
            continue
        if args.apply:
            back = bp.write_flow(path, data, images, r["pos"])
            refs = set(flowfile.flow_refs(back["data"]))
            print(f"  已寫回；範本 {len(set(flowfile.flow_refs(r['data'])))} → {len(refs)}"
                  f"；草稿{'已同步' if bp.sync_draft(path) else '屬於別份流程, 不動'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

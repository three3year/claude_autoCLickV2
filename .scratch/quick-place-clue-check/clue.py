"""影格一律逐幀順序讀 (示範影片跳轉讀幀不準)。"""
from __future__ import annotations

import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
TEMPLATES = os.path.join(HERE, "templates")
sys.path.insert(0, os.path.join(SCRATCH, "busy-pause-fixed-rect"))

import common as bp  # noqa: E402

from automation import findtarget  # noqa: E402

BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-09-quick-place-clue-check")
BACKUP_FLOWS = os.path.join(BACKUP, "arknights", "flows")

NUMS = range(1, 8)

OPEN_TIMEOUT = 5
COND_TIMEOUT = 2
PICK_TIMEOUT = 3
CARD_TIMEOUT = 1
CLOSE_TIMEOUT = 3
LEFTOVER_TIMEOUT = 1
INTERVAL = 0.3

LANGS = {
    "cn": {
        "flow": "早_簡中", "video": "add3",
        "steps": 247, "receive_no": 54,
        "open": "CONFIDENTIAL线索", "marker": "全部分页",
        "labels": ("相关搜集者", "来自"), "selected": "选中{}",
        "quick": "快速置入", "receive": "接收线索", "chat": "交流中",
        "unlock": "解锁线索", "entry": "线索", "send_close": "传递关闭",
        "boxes": {
            "CONFIDENTIAL线索": (0, (1574, 641, 84, 140)),
            "全部分页": (40, (1272, 48, 80, 42)),
            "相关搜集者": (285, (1386, 297, 118, 32)),
            "来自": (285, (1386, 262, 66, 30)),
        },
        "buttons": [1326 + 56 * k for k in range(7)], "button_y": 133, "button_r": 23,
        "selected_frames": {1: 90, 2: 116, 3: 146, 4: 174, 5: 204, 6: 235, 7: 288},
        "quick_box": (1512, 818, 160, 48),
        "close_at": (1095, 215),
        "panel_left": 1232,
        "closed": [0, 10, 20, 300, 330, 360],
        "all": [40, 50, 60],
        "picked": {1: (62, 92), 2: (93, 118), 3: (119, 148), 4: (149, 176),
                   5: (177, 206), 6: (207, 237), 7: (238, 290)},
        "has": {1: False, 2: False, 3: True, 4: False, 5: True, 6: True, 7: True},
    },
    "tw": {
        "flow": "早_繁中", "video": "add4",
        "steps": 212, "receive_no": 45,
        "open": "CONFIDENTIAL線索", "marker": "全部分頁",
        "labels": ("相關蒐集者", "來自"), "selected": "選中{}",
        "quick": "快速置入", "receive": "接收線索", "chat": "交流中",
        "unlock": "解鎖線索", "entry": "線索面板", "send_close": "傳遞關閉",
        "boxes": {
            "CONFIDENTIAL線索": (0, (1774, 720, 96, 154)),
            "全部分頁": (50, (1438, 52, 82, 46)),
            "相關蒐集者": (225, (1563, 331, 135, 35)),
            "來自": (225, (1563, 291, 73, 34)),
        },
        "buttons": [1495, 1558, 1621, 1685, 1748, 1811, 1874], "button_y": 146, "button_r": 25,
        "selected_frames": {1: 69, 2: 83, 3: 99, 4: 114, 5: 143, 6: 159, 7: 225},
        "quick_box": (1711, 924, 38, 38),
        "close_at": (1200, 690),
        "panel_left": 1390,
        "closed": [0, 5, 10, 240, 260, 290],
        "all": [35, 45, 55],
        "picked": {1: (57, 71), 2: (72, 85), 3: (86, 101), 4: (102, 116),
                   5: (117, 145), 6: (146, 161), 7: (162, 227)},
        "has": {1: False, 2: True, 3: True, 4: True, 5: True, 6: True, 7: True},
    },
}

LABEL = {"cn": "来自", "tw": "來自"}

MARGIN = {"open": 20, "marker": 20, "label": 24, "selected": 4}


def selected_name(lang, n):
    return LANGS[lang]["selected"].format(n)


def button_box(lang, n):
    cfg = LANGS[lang]
    x, y, r = cfg["buttons"][n - 1], cfg["button_y"], cfg["button_r"]
    return (x - r, y - r, 2 * r, 2 * r)


def crops(lang):
    cfg = LANGS[lang]
    out = dict(cfg["boxes"])
    for n in NUMS:
        out[selected_name(lang, n)] = (cfg["selected_frames"][n], button_box(lang, n))
    return out


def new_template_names(lang):
    cfg = LANGS[lang]
    return [cfg["open"], cfg["marker"], LABEL[lang]] + [selected_name(lang, n) for n in NUMS]


def center(box):
    x, y, w, h = box
    return (x + w // 2, y + h // 2)


def screen_xy(lang, xy):
    ox, oy = bp.LANGS[lang]["offset"]
    return (xy[0] + ox, xy[1] + oy)


def template_path(lang, name):
    return os.path.join(TEMPLATES, lang, name + ".png")


def load_templates(lang, names=None):
    out = {}
    for n in names or new_template_names(lang):
        p = template_path(lang, n)
        if not os.path.isfile(p):
            raise SystemExit(f"缺範本 {p}: 先跑 crop.py --lang {lang}")
        with open(p, "rb") as f:
            out[n] = f.read()
    return out


STRIDE = 3


def picked_frames(lang):
    return [(f, n) for n, (a, b) in LANGS[lang]["picked"].items()
            for f in range(a + 2, b + 1, STRIDE)]


def read_frames(video, wanted):
    import cv2
    wanted = set(wanted)
    cap = cv2.VideoCapture(os.path.join(bp.VIDEO_DIR, video + ".mp4"))
    out, n = {}, 0
    try:
        while len(out) < len(wanted):
            ok, img = cap.read()
            if not ok:
                break
            if n in wanted:
                out[n] = img
            n += 1
    finally:
        cap.release()
    miss = wanted - set(out)
    if miss:
        raise SystemExit(f"{video} 讀不到第 {sorted(miss)} 幀")
    return out


OCCLUDE_DIFF = 8.0


def occluded(frames, box, pad=6):
    import cv2
    import numpy as np
    if len(frames) < 3:
        return set()
    x, y, w, h = box
    crops = {n: cv2.cvtColor(img[y - pad:y + h + pad, x - pad:x + w + pad],
                             cv2.COLOR_BGR2GRAY).astype(np.float32)
             for n, img in frames.items()}
    med = np.median(np.stack(list(crops.values())), axis=0)
    return {n for n, c in crops.items() if float(np.abs(c - med).mean()) > OCCLUDE_DIFF}


def rect(lang, region, box, margin):
    return bp.video_box_to_rect(box, lang, region, margin)


def targets(lang, region):
    cfg = LANGS[lang]
    boxes = cfg["boxes"]
    label = LABEL[lang]
    out = {
        "open": {"template": cfg["open"],
                 "limit": rect(lang, region, boxes[cfg["open"]][1], MARGIN["open"])},
        "marker": {"template": cfg["marker"],
                   "limit": rect(lang, region, boxes[cfg["marker"]][1], MARGIN["marker"])},
        "label": {"template": label,
                  "limit": rect(lang, region, boxes[label][1], MARGIN["label"])},
    }
    for n in NUMS:
        out[n] = {"template": selected_name(lang, n),
                  "limit": rect(lang, region, button_box(lang, n), MARGIN["selected"])}
    return out


def offsets(lang):
    cfg = LANGS[lang]
    mx, my = center(cfg["boxes"][cfg["marker"]][1])
    out = {n: (cfg["buttons"][n - 1] - mx, cfg["button_y"] - my) for n in NUMS}
    out["close"] = (cfg["close_at"][0] - mx, cfg["close_at"][1] - my)
    return out


def _find(tgt, timeout, on_nf, action="click", update=True, **extra):
    s = {"type": "find_click", "interval": INTERVAL, "confirm": "none", "timeout": timeout,
         "onNotFound": on_nf, "offsetX": 0, "offsetY": 0}
    s.update(extra)
    s.update({"target": copy.deepcopy(tgt), "action": action, "button": "left", "clicks": 1,
              "updateOrigin": update})
    return s


def _rel_click(xy, timeout, on_nf, confirm, confirm_target=None):
    s = {"type": "click", "mode": "prev", "x": int(xy[0]), "y": int(xy[1]), "button": "left",
         "clicks": 1, "updateOrigin": False, "confirm": confirm}
    if confirm_target is not None:
        s["confirmTarget"] = copy.deepcopy(confirm_target)
    s.update({"timeout": timeout, "interval": INTERVAL, "onNotFound": on_nf})
    return s


def check_steps(lang, region, quick_step):
    t = targets(lang, region)
    off = offsets(lang)
    out = [_find(t["open"], OPEN_TIMEOUT, "skip", confirm="appear", confirmTarget=t["marker"]),
           {"type": "branch_start"},
           _find(t["marker"], COND_TIMEOUT, "skip", action="none")]
    for n in NUMS:
        out.append(_rel_click(off[n], PICK_TIMEOUT, "break", "appear", t[n]))
        out.append(_find(t["label"], CARD_TIMEOUT, "break", action="none", update=False))
    out += [_rel_click(off["close"], CLOSE_TIMEOUT, "break", "gone"),
            copy.deepcopy(quick_step),
            {"type": "branch_end"},
            {"type": "branch_start"},
            _find(t["marker"], LEFTOVER_TIMEOUT, "skip", action="none"),
            _rel_click(off["close"], CLOSE_TIMEOUT, "skip", "gone"),
            {"type": "branch_end"}]
    return out


def template_of(step):
    return findtarget.template(step) if step.get("type") == "find_click" else ""


def branch_of(steps, i):
    from automation.runner import branch_layout
    if i == 0 or steps[i - 1].get("type") != "branch_start":
        return None
    lay = branch_layout(steps, i - 1)
    return None if lay is None else (i - 1, lay[1])


def one_step(steps, name, flow):
    hits = [i for i, s in enumerate(steps) if template_of(s) == name]
    if len(hits) != 1:
        raise SystemExit(f"{flow}: 「{name}」的步驟有 {len(hits)} 個, 預期 1 個")
    return hits[0]


def locate(steps, lang):
    cfg = LANGS[lang]
    flow = cfg["flow"]
    get = one_step(steps, "領取", flow)
    chat = branch_of(steps, one_step(steps, cfg["chat"], flow))
    quick = one_step(steps, cfg["quick"], flow)
    unlock = branch_of(steps, one_step(steps, cfg["unlock"], flow))
    recv = branch_of(steps, one_step(steps, cfg["receive"], flow))
    if None in (chat, unlock, recv):
        raise SystemExit(f"{flow}: 交流中、解鎖線索、接收線索不是分岔的條件步驟")
    entry = unlock[1] + 1
    if template_of(steps[entry]) != cfg["entry"]:
        raise SystemExit(f"{flow}: 解鎖分岔後面不是「{cfg['entry']}」入口: {steps[entry]}")
    order = (get + 1 == chat[0] and chat[1] + 1 == unlock[0] and entry + 1 == recv[0]
             and chat[0] < quick < chat[1])
    if not order:
        raise SystemExit(f"{flow}: 會客室的步驟順序跟規格寫的不同")
    if (get + 1, len(steps)) != (cfg["receive_no"], cfg["steps"]):
        raise SystemExit(f"{flow}: 領取在第 {get + 1} 步、共 {len(steps)} 步, 跟規格寫的"
                         f"第 {cfg['receive_no']} 步、{cfg['steps']} 步不同")
    return {"get": get, "chat": chat, "quick": quick, "unlock": unlock, "entry": entry,
            "recv": recv}


def is_new(steps, lang):
    return any(template_of(s) == LANGS[lang]["open"] for s in steps)


def new_layout(steps, lang):
    cfg = LANGS[lang]
    flow = cfg["flow"]
    get = one_step(steps, "領取", flow)
    recv = branch_of(steps, one_step(steps, cfg["receive"], flow))
    opn = one_step(steps, cfg["open"], flow)
    unlock = branch_of(steps, one_step(steps, cfg["unlock"], flow))
    conds = [i for i, s in enumerate(steps) if template_of(s) == cfg["marker"]]
    if len(conds) != 2 or None in (recv, unlock):
        raise SystemExit(f"{flow}: 新版的面板標記條件有 {len(conds)} 個 (預期 2 個) 或分岔不完整")
    chk, left = branch_of(steps, conds[0]), branch_of(steps, conds[1])
    return {"get": get, "recv": recv, "open": opn, "check": chk, "leftover": left,
            "unlock": unlock, "entry": unlock[1] + 1}


def rebuild(steps, lang, region):
    a = locate(steps, lang)
    s = [copy.deepcopy(x) for x in steps]
    rb, re_ = a["recv"]
    receive = s[rb:re_ + 1]
    out = (s[:a["get"] + 1] + receive + check_steps(lang, region, s[a["quick"]])
           + s[a["unlock"][0]:rb] + s[re_ + 1:])
    return out

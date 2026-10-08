"""快速置入前先查 1–7 號線索: 裁範本、建構、驗證、報告腳本共用的設定 (見 spec.md).

路徑、流程存檔讀寫、preflight、草稿同步、引擎與影格的換算沿用 busy-pause-fixed-rect/common.py
(匯入成 bp); 影格一律逐幀順序讀 (示範影片跳轉讀幀不準)。

座標都是影片像素; 換成實機螢幕座標靠 bp.LANGS 的偏移 (簡中 (95,57)、繁中 (0,0))。
add3 跟 demo6 一樣是 1696x912 的簡中視窗錄影, 沿用同一個偏移。
"""
from __future__ import annotations

import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
TEMPLATES = os.path.join(HERE, "templates")
sys.path.insert(0, os.path.join(SCRATCH, "busy-pause-fixed-rect"))

import common as bp  # noqa: E402  (busy-pause-fixed-rect 的共用; 也把 app 放進 sys.path)

from automation import findtarget  # noqa: E402

BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-09-quick-place-clue-check")
BACKUP_FLOWS = os.path.join(BACKUP, "arknights", "flows")

NUMS = range(1, 8)

# ---- 新步驟的時限 (秒) ----
OPEN_TIMEOUT = 5        # 開面板: 點到面板標記出現
COND_TIMEOUT = 2        # 檢查區段的條件 (面板標記); 開面板那步已確認過, 正常第一輪就找到
PICK_TIMEOUT = 3        # 點 N 號篩選鈕, 點到選中的 N 號鈕出現 (補做間隔 1 秒 → 約補 2 次)
CARD_TIMEOUT = 1        # 卡片標籤: 「有」第一輪就找到, 「沒有」等滿這段就跳出
CLOSE_TIMEOUT = 3       # 關面板: 點到面板標記離開原位
LEFTOVER_TIMEOUT = 1    # 跳出後補關面板的分岔條件
INTERVAL = 0.3

# 每版的影片、範本、影片座標 (x, y, w, h) 與各種影格。
# crop: 範本名 → (幀, 框); 框外擴 margin 成固定矩形。
# 選中的 N 號鈕從「點下一號之前」那幾幀裁 (游標停在下一號上, 不壓到這一號);
# 7 號從點關面板之前裁。卡片標籤兩個候選都裁, 由 crop.py 在影格上比過分數後挑 LABEL。
LANGS = {
    "cn": {
        "flow": "早_簡中", "video": "add3",
        "steps": 247, "receive_no": 54,          # 改前步驟數、領取的編號 (只拿來核對)
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
        "quick_box": (1512, 818, 160, 48),       # 現有的快速置入範本在影片上的位置 (只拿來驗證)
        "close_at": (1095, 215),                 # 點面板外的線索板空白處 (影片裡的位置)
        "panel_left": 1232,                      # 面板左緣 (關面板的點要在它左邊)
        # 影格: 面板關著、開著選 all、選中各號 (區間 [首, 尾])、每號有沒有卡片
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

# crop.py 在 add3/add4 影格上比過兩個候選後挑的卡片標籤 (見 results/labels_<lang>.json)
LABEL = {"cn": "来自", "tw": "來自"}

# 固定矩形的外擴 (影片像素): 篩選鈕只外擴一點, 不碰到隔壁那顆
MARGIN = {"open": 20, "marker": 20, "label": 24, "selected": 4}


def selected_name(lang, n):
    return LANGS[lang]["selected"].format(n)


def button_box(lang, n):
    """N 號篩選鈕在影片上的框 (x, y, w, h)."""
    cfg = LANGS[lang]
    x, y, r = cfg["buttons"][n - 1], cfg["button_y"], cfg["button_r"]
    return (x - r, y - r, 2 * r, 2 * r)


def crops(lang):
    """要裁的範本: 名 → (幀, 影片框). 含兩個卡片標籤候選."""
    cfg = LANGS[lang]
    out = dict(cfg["boxes"])
    for n in NUMS:
        out[selected_name(lang, n)] = (cfg["selected_frames"][n], button_box(lang, n))
    return out


def new_template_names(lang):
    """新流程用到的新範本 (卡片標籤只用挑中的那個)."""
    cfg = LANGS[lang]
    return [cfg["open"], cfg["marker"], LABEL[lang]] + [selected_name(lang, n) for n in NUMS]


def center(box):
    x, y, w, h = box
    return (x + w // 2, y + h // 2)


def screen_xy(lang, xy):
    """影片座標 → 實機螢幕座標."""
    ox, oy = bp.LANGS[lang]["offset"]
    return (xy[0] + ox, xy[1] + oy)


def template_path(lang, name):
    return os.path.join(TEMPLATES, lang, name + ".png")


def load_templates(lang, names=None):
    """templates/<lang>/ 底下裁好的範本 (PNG 位元組); crop.py 產的."""
    out = {}
    for n in names or new_template_names(lang):
        p = template_path(lang, n)
        if not os.path.isfile(p):
            raise SystemExit(f"缺範本 {p}: 先跑 crop.py --lang {lang}")
        with open(p, "rb") as f:
            out[n] = f.read()
    return out


STRIDE = 3    # 驗證用的影格: 各號選中區間每幾幀取一張


def picked_frames(lang):
    """[(幀, 號碼)]: 各號選中區間每 STRIDE 幀 (前 2 幀游標還壓在剛點的鈕上, 跳過)."""
    return [(f, n) for n, (a, b) in LANGS[lang]["picked"].items()
            for f in range(a + 2, b + 1, STRIDE)]


def read_frames(video, wanted):
    """逐幀順序讀 (不跳轉), 回傳 {幀號: 影像}."""
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


OCCLUDE_DIFF = 8.0    # 框內平均灰階差 (0–255) 超過它＝游標壓在上面


def occluded(frames, box, pad=6):
    """同一個畫面狀態的一組影格裡, 游標壓在 box 上的那些幀.

    影格之間只差游標 (面板靜止), 所以取這組在框內的中位數當乾淨的底, 跟它差很多的幀
    就是游標經過。實跑前會避開游標, 這些幀不拿來驗證範本 (列出來, 不算數)。
    """
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


# ================= 新步驟 =================

def rect(lang, region, box, margin):
    return bp.video_box_to_rect(box, lang, region, margin)


def targets(lang, region):
    """新步驟用的找圖目標 (範本 + 固定矩形)."""
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
    """相對面板標記中心的座標: N 號篩選鈕與關面板的點 (影片上量; 倍率 1 時與實機相同)."""
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
    """開面板 → 檢查區段 → 跳出後補關面板 (spec「新步驟的形狀」)."""
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


# ================= 以內容定位 =================

def template_of(step):
    return findtarget.template(step) if step.get("type") == "find_click" else ""


def branch_of(steps, i):
    """steps[i] 是分岔第一個分支的條件時, 回傳 (分岔開頭, 分岔結尾) 索引."""
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
    """改前存檔各段的位置 (0 起算): 領取、交流中分岔、快速置入、解鎖分岔、線索入口、接收分岔.

    核對順序是「領取 → 交流中分岔 → 解鎖分岔 → 線索入口 → 接收分岔」緊接著,
    以及改前的編號與步驟數; 不符就中止 (存檔被別的改動動過)。
    """
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
    """已經是新版了嗎 (有開面板那步)."""
    return any(template_of(s) == LANGS[lang]["open"] for s in steps)


def new_layout(steps, lang):
    """新版存檔各段的位置 (0 起算): 領取、接收分岔、開面板、檢查區段、補關分岔、解鎖分岔."""
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
    """改前步驟 → 新步驟 (list). 其餘步驟原封不動 (同一個 dict 的深拷貝)."""
    a = locate(steps, lang)
    s = [copy.deepcopy(x) for x in steps]
    rb, re_ = a["recv"]
    receive = s[rb:re_ + 1]
    out = (s[:a["get"] + 1] + receive + check_steps(lang, region, s[a["quick"]])
           + s[a["unlock"][0]:rb] + s[re_ + 1:])
    return out

"""剩下的九宮格與全畫面換成固定矩形: 量位置、驗證、寫回、報告腳本共用的設定 (見 spec.md).

路徑、流程存檔讀寫、引擎與影格的共用沿用 busy-pause-fixed-rect/common.py (匯入成 bp)。
"""
from __future__ import annotations

import functools
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "busy-pause-fixed-rect"))

import common as bp  # noqa: E402  (busy-pause-fixed-rect 的共用)

BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-09-fixed-rect-sweep")
BACKUP_FLOWS = os.path.join(BACKUP, "arknights", "flows")
RESULTS = os.path.join(HERE, "results")
LOG = os.path.join(bp.APP, "dist", "AutoClick", "autoclick.log")

MARGIN = 40          # 外擴 (實機螢幕像素)

# 晚班兩版要加框的步驟 (2026-10-08 存檔的編號, 規格「改的範圍」)。
FIXED_STEPS = [2, 3, 6, 8, 10, 13, 16, 19, 20, 22, 23, 25, 27, 28, 29, 60, 61, 63, 64]
LIST_STEPS = [32, 34, 37, 42, 44, 47, 53, 56]
CONFIRM_STEP = 3     # 第 3 步的確認圖「待辦事項」(九宮格 7)
# 同一天兩次實機位置不同的步驟: 框＝晚班與早班實跑 (同客戶端、同一張圖、同尺寸) 位置的聯集。
# 待辦鈴鐺 10/08 簡中早班 y=179、晚班 y=232; 繁中早班 y=129、晚班 y=189 (其他步驟早晚一致)。
WIDEN_STEPS = {3}

# 每版: 早晚兩份流程、晚班參考影片、10/08 晚實跑在日誌裡的開頭 (校準那一行的時間)、
# 同一天早班實跑的開頭 (WIDEN_STEPS 用)、忙碌指示的位置 (實機螢幕座標) 與它的來源、
# 晚班的票、10/08 晚班總秒數 (報告用)。影片 → 實機的偏移照 bp.LANGS (busy-pause-fixed-rect 的量法)。
LANGS = {
    "cn": {"morning": "早_簡中", "evening": "晚_簡中", "video": "demo4",
           "run": "2026-10-08 23:19:14", "morning_run": "2026-10-08 08:48:34",
           "busy_box": (1043, 896, 237, 21),
           "busy_src": "10/08 23:19 晚_簡中實跑 9 次 busy.check gone 的位置",
           "ticket": "02-evening-cn-rects.md", "evening_secs": 103},
    "tw": {"morning": "早_繁中", "evening": "晚_繁中", "video": "demo3",
           "run": "2026-10-08 23:22:53", "morning_run": "2026-10-08 08:38:22",
           "busy_box": (1069, 944, 272, 25),
           "busy_src": "demo2 第 2000 幀，10/07 核對過實機版面一致",
           "ticket": "03-evening-tw-rects.md", "evening_secs": 108},
}
BUSY = "忙碌指示"
FIND_ROLES = ("find", "branch")


class SeqFrames:
    """影片影格, 從頭逐幀順序讀 (同 positions.py 量位置的讀法).

    bp.Frames 用跳轉 (CAP_PROP_POS_FRAMES): demo4 (變動幀率, 13.6fps) 約第 400 幀以後跳到的
    不是那一幀, demo6 也有幾格偏差——量到的幀號跟驗證讀的影格會對不上。要用的影格先
    prefetch (每支影片順序讀一次, 存成無損 PNG), get 時解回來; 沒預讀的就單獨順序讀一次。
    """

    def __init__(self):
        self._png = {}

    def prefetch(self, keys):
        import cv2
        by = {}
        for video, n in keys:
            if (video, n) not in self._png:
                by.setdefault(video, set()).add(n)
        for video, want in by.items():
            cap = cv2.VideoCapture(os.path.join(bp.VIDEO_DIR, video + ".mp4"))
            n, last = 0, max(want)
            while n <= last and cap.grab():
                if n in want:
                    ok, img = cap.retrieve()
                    if not ok:
                        raise SystemExit(f"讀不到 {video} 第 {n} 幀")
                    self._png[(video, n)] = cv2.imencode(".png", img)[1]
                n += 1
            cap.release()
            missing = sorted(want - {k for v, k in self._png if v == video})
            if missing:
                raise SystemExit(f"{video} 沒有第 {missing[:5]} 幀")

    def get(self, video, n):
        import cv2
        if (video, n) not in self._png:
            self.prefetch([(video, n)])
        return cv2.imdecode(self._png[(video, n)], cv2.IMREAD_COLOR)

    def close(self):
        self._png.clear()


def offset(lang):
    return bp.LANGS[lang]["offset"]


def grow(box, m=MARGIN):
    x, y, w, h = box
    return (x - m, y - m, w + 2 * m, h + 2 * m)


def screen_rect(box, region, m=MARGIN):
    """實機螢幕座標的框外擴 m → `固定矩形` (搜尋範圍 region 的比例; 編輯器框選的同一套換算)."""
    from automation import findtarget
    r = findtarget.ratio_rect_from_screen(grow(box, m), tuple(region))
    if r is None:
        raise SystemExit(f"框 {box} 在搜尋範圍外")
    return r


def busy_rect(lang, region):
    return screen_rect(LANGS[lang]["busy_box"], region)


def target_of(data, c):
    """改動 c 指的找圖目標 (data 裡的那個 dict): 流程層級忙碌指示、步驟的找圖目標或確認圖."""
    from automation import findtarget
    import flowfile
    if c["where"] == "busy":
        return data[flowfile.BUSY_KEY]
    key = findtarget.TARGET if c["where"] == "target" else findtarget.CONFIRM_TARGET
    return data["steps"][c["step"] - 1][key]


# ================= 10/08 晚實跑日誌 =================

_BOX = re.compile(r"\((\d+),(\d+),(\d+),(\d+)\)")
_PICKED = re.compile(r"picked=\((\d+),(\d+),(\d+),(\d+)\)")


def run_lines(lang, log=LOG, which="run"):
    """10/08 這一版實跑 (which: 晚班 "run" / 早班 "morning_run") 的日誌行: 從校準那一行起,
    到下一次校準 (或 app 重開) 為止."""
    start = LANGS[lang][which]
    out, on = [], False
    with open(log, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(start) and " calibrate " in line:
                on = True
                continue
            if on and (" calibrate " in line or " engine.load.start" in line):
                break
            if on:
                out.append(line.rstrip("\n"))
    if not out:
        raise SystemExit(f"[{lang}] 日誌裡找不到 {start} 那次實跑")
    return out


@functools.lru_cache(maxsize=None)
def run_finds(lang, log=LOG, which="run"):
    """[{step, role, template, result, picked, boxes}]: 這次實跑每一筆 find.target (唯讀, 有快取).

    boxes＝matches 與 rejected 裡所有的框 (列名「日誌所有出現位置」用)。
    """
    rows = []
    for line in run_lines(lang, log, which):
        if " find.target " not in line:
            continue
        m = re.match(r"^\S+ \S+ find\.target step=(\d+) role=(\w+) template=(\S+) result=(\w+)",
                     line)
        if not m:
            continue
        p = _PICKED.search(line)
        boxes = []
        for key in ("matches=[", "rejected=["):
            i = line.find(key)
            if i >= 0:
                j = line.index("]", i)
                boxes += [tuple(int(v) for v in b) for b in _BOX.findall(line[i:j])]
        rows.append({"step": int(m.group(1)), "role": m.group(2), "template": m.group(3),
                     "result": m.group(4),
                     "picked": tuple(int(v) for v in p.groups()) if p else None,
                     "boxes": boxes})
    return rows


def _picks(finds, step, roles, template):
    return [f["picked"] for f in finds
            if (step is None or f["step"] == step) and f["role"] in roles
            and f["template"] == template and f["result"] in ("found", "gone") and f["picked"]]


def step_positions(lang, step, template, roles=FIND_ROLES):
    """這一步在日誌裡找到的位置 (實機螢幕座標): {"晚": [...], "早": [...]}.

    "早" 只有 WIDEN_STEPS 的找圖目標才有: 同一天早班實跑同一張圖 (同尺寸) 找到的位置
    (早班步驟編號不同, 只認範本)。晚班沒有紀錄、或該有早班卻沒有就中止。
    """
    eve = sorted(set(_picks(run_finds(lang), step, roles, template)))
    if not eve:
        raise SystemExit(f"[{lang}] 日誌第 {step} 步沒有 {template} ({'/'.join(roles)}) 的位置")
    out = {"晚": eve}
    if step in WIDEN_STEPS and roles == FIND_ROLES:
        size = eve[0][2:]
        mor = sorted({b for b in _picks(run_finds(lang, which="morning_run"), None,
                                        ("find", "branch", "confirm_next"), template)
                      if b[2:] == size})
        if not mor:
            raise SystemExit(f"[{lang}] 第 {step} 步: 早班實跑沒有 {template} 同尺寸的位置")
        out["早"] = mor
    return out

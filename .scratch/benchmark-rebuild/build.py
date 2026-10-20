"""基準集候選案例建構 (benchmark-rebuild 票 02–04)。

    .venv/Scripts/python.exe .scratch/benchmark-rebuild/scan.py      # 先掃 (一次, 約 25 分鐘)
    .venv/Scripts/python.exe .scratch/benchmark-rebuild/build.py     # 挑候選 → tmp/candidates/ + tmp/cards.html

答案來源優先序: 人工判定過的資料 (quick-place 線索判定、商店標註與預期挑選、demo2／add5 轉換計畫)
→ 用現在的範本在影格上配對 (bcommon 的 OpenCV 配對工具, 不是受測的引擎)。
每個候選都過: 游標碰到答案框不收、答案框前後幾幀在變 (轉場、淡入淡出) 不收。
agent 目視審核的結論寫在 review.yaml (drop／doubt／note), 這裡讀進來。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bcommon as bc  # noqa: E402
import cases  # noqa: E402

# 每份流程主要的示範影片 (範本就是從這些截的); 跨影片案例用別支
FLOW_VIDEOS = {"早_簡中": ["demo6", "demo5", "add1", "add3", "add5"],
               "晚_簡中": ["demo4"],
               "早_繁中": ["demo2", "add2", "add4"],
               "晚_繁中": ["demo3"]}
BUSY = "忙碌指示"
# 一般正例／負樣本不挑的範本 (有專屬類型的)
SPECIAL_PREFIX = ("採購_", "选中", "選中", "标题_", "標題_")
SPECIAL = {BUSY, "来自", "來自", "CONFIDENTIAL线索", "CONFIDENTIAL線索", "全部分页", "全部分頁",
           "快速置入", "解锁线索", "解鎖線索", "線索面板", "標題列圖示", "標題列關閉鈕"}
POS = 0.93      # 一般正例: 配對分數至少
UNIQUE = 0.72   # 一般正例: 第二高 (別處) 不到它
NEG = 0.72      # 負樣本: 全畫面最高不到它

REVIEW = os.path.join(bc.HERE, "review.yaml")


_review = None


def review():
    global _review
    if _review is None:
        _review = {}
        if os.path.isfile(REVIEW):
            with open(REVIEW, encoding="utf-8") as f:
                _review = yaml.safe_load(f) or {}
    return _review


def rkey(name, video, n):
    return f"{name}@{video}f{n}"


def dropped(name, video, n):
    """agent 審過、不收的 (review.yaml 的 drop): 挑的時候跳過, 換下一個."""
    drops = review().get("drop") or {}
    # 「範本@影片f*」＝那支影片裡這張範本的幀都不收
    return rkey(name, video, n) in drops or f"{name}@{video}f*" in drops


def special(name):
    return name in SPECIAL or name.startswith(SPECIAL_PREFIX)


# ---------------------------------------------------------------- 掃描結果

class Scan:
    def __init__(self, lang):
        d = bc.load(os.path.join(bc.TMP, f"scan_{lang}.json"))
        self.lang = lang
        self.stride = d["stride"]
        self.templates = d["templates"]
        self.videos = d["videos"]
        self._tpl = bc.lang_templates(lang)

    def key_of(self, flow, name):
        return next(k for k, v in self.templates.items() if [flow, name] in v["names"])

    def names(self, flow):
        return [n for k, v in self.templates.items() for f, n in v["names"] if f == flow]

    def tpl(self, key):
        return self._tpl[key][0]

    def peaks(self, key, video, n):
        return self.videos[video]["peaks"].get(key, {}).get(str(n), [])

    def coarse_max(self, key, video):
        v = self.videos[video]
        return dict(zip(v["frames"], v["max"][key]))

    def present(self, key, video, thr=POS):
        """[(幀, 峰值們)] 最高峰 ≥ thr 的取樣幀."""
        pk = self.videos[video]["peaks"].get(key, {})
        return sorted((int(n), p) for n, p in pk.items() if p and p[0][0] >= thr)

    def runs(self, frames):
        """連續取樣幀分組 (相鄰差一個 stride)."""
        out, cur = [], []
        for n in frames:
            if cur and n - cur[-1] > self.stride:
                out.append(cur)
                cur = []
            cur.append(n)
        if cur:
            out.append(cur)
        return out


# ---------------------------------------------------------------- 共用檢查

def exact(scene, tpl, thr=0.6):
    """全解析度配對: (最高 (分數, 框), 別處第二高分數)."""
    ps = bc.peaks(scene, tpl, thr=min(thr, 0.5), top=6)
    if not ps:
        s, box = bc.best(scene, tpl)
        return (s, box), 0.0
    top = ps[0]
    return (top[0], top[1:]), (ps[1][0] if len(ps) > 1 else 0.0)


def clean(lang, video, n, boxes, allow_busy=False):
    """(乾淨嗎, 原因)——游標碰到框、框在變、畫面上有忙碌字樣都不乾淨.

    忙碌字樣: 實跑時流程會先等它消失才找別的範本 (使用者 10/20 審卡片 #15), 所以除了忙碌指示類
    (allow_busy) 都不收。"""
    img = bc.frame(video, n)
    if not allow_busy and bc.busy_on(img, lang):
        return False, "忙碌"
    if bc.cursor_touches(img, lang, boxes):
        return False, "游標"
    if bc.unstable(video, n, boxes):
        return False, "轉場"
    return True, ""


def base(kind, lang, flow, name, video, n, scene, tpl_img, **kw):
    c = {"kind": kind, "lang": lang, "flow": flow, "template": name, "video": video,
         "frame": n, "scene": scene, "tpl": tpl_img,
         "tpl_path": bc.template_path(flow, name), "doubt": None, "note": None}
    c.update(kw)
    return c


# ---------------------------------------------------------------- 一般正例

def human_frames(flow):
    """人工判定過的取材幀: {範本名: [(影片, 幀)]} (demo2 轉換計畫→早_繁中; add5 計畫→早_簡中)."""
    out = {}
    acc = os.path.join(bc.SCRATCH, "v2f-rules-agent-docs", "acceptance")
    plans = {"早_繁中": ["demo2_plan.json"], "早_簡中": ["add5_plan.json"]}.get(flow, [])
    for p in plans:
        d = bc.load(os.path.join(acc, p))
        video = os.path.splitext(os.path.basename(d["video"]))[0]
        for name, t in d["templates"].items():
            out.setdefault(name, []).append((video, int(t["frame"])))
    return out


def positive_pool(scan, flow, used):
    """這份流程每張 (非專屬) 範本最好的一個取樣: [(分數, 名, 影片, 幀, 人工?)]."""
    human = human_frames(flow)
    pool = []
    for name in scan.names(flow):
        if special(name) or name in used:
            continue
        key = scan.key_of(flow, name)
        best = None
        for video in FLOW_VIDEOS[flow]:
            for run in scan.runs([n for n, _ in scan.present(key, video)]):
                if len(run) < 3:
                    continue
                for n in run[1:-1]:
                    p = scan.peaks(key, video, n)
                    second = p[1][0] if len(p) > 1 else 0.0
                    if second >= UNIQUE:
                        continue
                    cand = (p[0][0], name, video, n, False)
                    if best is None or cand[0] > best[0]:
                        best = cand
        if name in human:
            for video, n in human[name]:
                if video in FLOW_VIDEOS[flow]:
                    best = (1.0, name, video, n, True)   # 人工判定的優先
                    break
        if best:
            pool.append(best)
    return pool


def pick_positive(scan, flow, k, used, kind="一般正例", frame_ok=None):
    """一份流程挑 k 個一般正例 (大小錯開: 照範本面積排序後平均取)."""
    lang = bc.FLOWS[flow]
    pool = positive_pool(scan, flow, used)
    pool.sort(key=lambda r: (scan.tpl(scan.key_of(flow, r[1])).size, r[1]))
    out = []
    tried = set()
    order = [pool[int(i * len(pool) / k)] for i in range(k)] + pool if pool else []
    for score, name, video, n, human in order:
        if len(out) >= k:
            break
        if name in tried:
            continue
        tried.add(name)
        tpl = scan.tpl(scan.key_of(flow, name))
        c = positive_at(scan, flow, name, video, n, tpl, kind, human)
        if c is None or (frame_ok and not frame_ok(c)):
            continue
        out.append(c)
        used.add(name)
    return out


def positive_at(scan, flow, name, video, n, tpl, kind, human=False):
    """在 (影片, 幀) 附近 (同一段出現的取樣幀) 找一個乾淨的幀做正例; 都不乾淨回 None."""
    lang = bc.FLOWS[flow]
    key = scan.key_of(flow, name)
    if human:
        tries = [n]
    else:
        run = next((r for r in scan.runs([m for m, _ in scan.present(key, video)]) if n in r), [n])
        mid = run.index(n) if n in run else 0
        tries = sorted(run, key=lambda m: abs(run.index(m) - mid))[:6]
    for m in tries:
        if dropped(name, video, m):
            continue
        scene = bc.frame(video, m)
        (s, box), second = exact(scene, tpl)
        if s < (0.85 if human else POS) or second >= UNIQUE:
            continue
        ok, why = clean(lang, video, m, [box])
        if not ok:
            continue
        c = base(kind, lang, flow, name, video, m, scene, tpl, expected="present", boxes=[box],
                 origin="人工判定 (轉換計畫取材幀)" if human else "配對工具")
        if s < 0.95:
            c["doubt"] = f"配對分數只有 {s:.2f}"
        elif second >= 0.6:
            c["doubt"] = f"畫面別處也有像的 (第二高 {second:.2f})"
        c["note"] = f"配對分數 {s:.3f}，別處最高 {second:.2f}"
        return c
    return None


# ---------------------------------------------------------------- 易誤判負樣本

def usual_box(scan, key, video):
    pres = scan.present(key, video)
    if not pres:
        return None
    n, p = pres[len(pres) // 2]
    w, h = scan.templates[key]["size"]
    return (p[0][1], p[0][2], w, h)


def negative_after(scan, flow, name):
    """同畫面的前後狀態: 範本剛消失、畫面其他地方大致沒變的幀. [(全畫面差, 影片, 幀, 框)]."""
    import numpy as np
    key = scan.key_of(flow, name)
    out = []
    for video in FLOW_VIDEOS[flow]:
        mx = scan.coarse_max(key, video)
        frames = scan.videos[video]["frames"]
        for run in scan.runs([n for n, _ in scan.present(key, video)]):
            if len(run) < 2:
                continue
            last = run[-1]
            box = (scan.peaks(key, video, last)[0][1], scan.peaks(key, video, last)[0][2],
                   *scan.templates[key]["size"])
            nxt = [n for n in frames if last < n <= last + scan.stride * 8]
            for g in nxt:
                if mx[g] >= 55:
                    continue
                a = bc.gray(bc.frame(video, last)).astype(np.float32)
                b = bc.gray(bc.frame(video, g)).astype(np.float32)
                diff = float(np.abs(a - b).mean())
                out.append((diff, video, g, box))
                break
    return sorted(out)


def negative_lookalike(scan, flow, name):
    """長得像: 範本不在、但全畫面最高分最高的取樣幀. [(-粗找分, 影片, 幀)]."""
    key = scan.key_of(flow, name)
    out = []
    for video in FLOW_VIDEOS[flow]:
        for n, m in scan.coarse_max(key, video).items():
            if 50 <= m <= 70 and not any(p[0] >= 0.75 for p in scan.peaks(key, video, n)):
                out.append((-m, video, n))
    return sorted(out)


def negative_at(scan, flow, name, video, g, box, how):
    lang = bc.FLOWS[flow]
    tpl = scan.tpl(scan.key_of(flow, name))
    if dropped(name, video, g) or not bc.calm_scene(video, g):
        return None
    scene = bc.frame(video, g)
    if bc.busy_on(scene, lang):
        return None
    s, where = bc.best(scene, tpl)
    if s >= NEG:
        return None
    if how == "前後狀態" and box is not None:
        # 原位要真的空了 (不是淡掉、變暗)
        x, y, w, h = box
        H, W = scene.shape[:2]
        win = scene[max(0, y - 8):min(H, y + h + 8), max(0, x - 8):min(W, x + w + 8)]
        if win.shape[0] >= h and win.shape[1] >= w and bc.best(win, tpl)[0] >= 0.45:
            return None
    check = [b for b in (box, where) if b is not None]
    if bc.cursor_touches(scene, lang, check):
        return None
    if how == "前後狀態" and bc.unstable(video, g, check):
        return None
    c = base("易誤判負樣本", lang, flow, name, video, g, scene, tpl, expected="absent", boxes=[],
             origin="配對工具", lookalike=where)
    c["note"] = (f"{how}：全畫面最像的地方配對分數 {s:.2f}" +
                 ("（範本剛從原位消失）" if how == "前後狀態" else ""))
    if s >= 0.65:
        c["doubt"] = f"最像的地方分數 {s:.2f}，請確認不是範本本身"
    return c


def pick_negative(scan, flow, k, used):
    out = []
    names = [n for n in scan.names(flow) if not special(n) and n not in used]
    # 前後狀態: 跟消失前比全畫面差最小的 (畫面沒換頁、只少了那個東西)
    after = []
    for name in names:
        for diff, video, g, box in negative_after(scan, flow, name)[:2]:
            after.append((diff, name, video, g, box))
    after.sort()
    for diff, name, video, g, box in after:
        if len(out) >= (k + 1) // 2:
            break
        if name in used:
            continue
        c = negative_at(scan, flow, name, video, g, box, "前後狀態")
        if c:
            out.append(c)
            used.add(name)
    look = []
    for name in names:
        if name in used:
            continue
        for negm, video, n in negative_lookalike(scan, flow, name)[:1]:
            look.append((negm, name, video, n))
    look.sort()
    for negm, name, video, n in look:
        if len(out) >= k:
            break
        if name in used:
            continue
        key = scan.key_of(flow, name)
        c = negative_at(scan, flow, name, video, n, usual_box(scan, key, video), "長得像")
        if c:
            out.append(c)
            used.add(name)
    return out


# ---------------------------------------------------------------- 商店 (人工標註)

CREDIT = os.path.join(bc.SCRATCH, "credit-store-templates")
SHOP_FLOW = {"cn": "早_簡中", "tw": "早_繁中"}


def shop_frames(lang):
    """商店標註: [(標註 id, 影片, 順序讀的幀號, 畫面, 卡片們)]; demo1 (糊) 與非影片的 pic 不用.

    標註影格當初是跳轉讀的: 在順序讀的前後 12 幀裡找跟存檔 PNG 最像的那幀當幀號
    (畫面用順序讀的那幀, 卡片位置照標註)。"""
    import numpy as np
    ann = bc.load(os.path.join(CREDIT, "annotations.json"))
    out = []
    for fr in ann["frames"]:
        src = fr.get("source", {})
        if fr["set"] != lang or "video" not in src or src["video"] == "demo1":
            continue
        png = bc.imread(os.path.join(CREDIT, "frames", fr["id"] + ".png"))
        video, n0 = src["video"], int(src["frame"])
        frames = bc.read_frames(video, range(max(0, n0 - 12), n0 + 13))
        n = min(frames, key=lambda m: float(np.abs(frames[m].astype(np.float32)
                                                   - png.astype(np.float32)).mean()))
        out.append((fr["id"], video, n, frames[n], fr["cards"]))
    return out


def card_boxes(scene, tpl, cards):
    """每張卡片附近 (卡片中心 ±160px) 範本配對到的框: [(分數, 框)] (順序同 cards)."""
    th, tw = tpl.shape[:2]
    H, W = scene.shape[:2]
    out = []
    for card in cards:
        cx, cy = card["center"]
        x0, y0 = max(0, int(cx) - 160), max(0, int(cy) - 160)
        win = scene[y0:min(H, int(cy) + 160), x0:min(W, int(cx) + 160)]
        if win.shape[0] < th or win.shape[1] < tw:
            out.append((0.0, None))
            continue
        s, (x, y, w, h) = bc.best(win, tpl)
        out.append((s, (x + x0, y + y0, w, h)))
    return out


def shop_cases(lang, want_color):
    """商店案例: 同款多個 (不開比色, 同款全部沒售罄) 與比色 (開比色: 混著售罄的、全部售罄的)."""
    flow = SHOP_FLOW[lang]
    tpls = bc.flow_templates(flow)
    out = []
    for fid, video, n, scene, cards in shop_frames(lang):
        by = {}
        for card in cards:
            by.setdefault(card["name"], []).append(card)
        for item, cs in sorted(by.items()):
            name = "採購_" + item
            if name not in tpls:
                continue
            tpl = tpls[name]
            boxes = card_boxes(scene, tpl, cs)
            real = [b for _, b in boxes if b is not None]
            if dropped(name, video, n) or not clean(lang, video, n, real)[0]:
                continue
            sold = [bool(c.get("soldOut")) for c in cs]
            unsold = [b for (s, b), so in zip(boxes, sold) if not so]
            # 售罄的卡灰掉, 灰階配對本來就低; 只看沒售罄的
            low = min((s for (s, _), so in zip(boxes, sold) if not so), default=1.0)
            sold_best = max((s for (s, _), so in zip(boxes, sold) if so), default=0.0)
            common = dict(origin="人工判定 (商店標註 annotations.json)")
            if not want_color:
                if len(cs) < 2 or any(sold):
                    continue
                c = base("同款多個", lang, flow, name, video, n, scene, tpl,
                         expected="present", boxes=[b for _, b in boxes], multi=True, **common)
                c["note"] = f"商店同款 {len(cs)} 格都沒售罄；每格配對分數最低 {low:.2f}"
            else:
                if not any(sold):
                    continue
                if unsold:
                    c = base("比色", lang, flow, name, video, n, scene, tpl, expected="present",
                             boxes=unsold, multi=True, color_check=True, **common)
                    c["note"] = (f"商店同款 {len(cs)} 格，{sum(sold)} 格售罄（灰）："
                                 f"只有沒售罄的 {len(unsold)} 格算")
                else:
                    c = base("比色", lang, flow, name, video, n, scene, tpl, expected="absent",
                             boxes=[], color_check=True, **common)
                    c["note"] = f"商店同款 {len(cs)} 格全部售罄（灰），開比色應該沒有"
            if low < 0.8:
                c["doubt"] = f"有一格配對分數只有 {low:.2f}"
            c["shop"] = fid
            c["sold_best"] = sold_best
            out.append(c)
    return out


# ---------------------------------------------------------------- 同款多個 (配對工具)

def multi_from_scan(scan, flow, k, used):
    """同一幀裡同一張範本有 ≥2 個強峰 (≥POS) 的: centers 列出每一個."""
    lang = bc.FLOWS[flow]
    pool = []
    for name in scan.names(flow):
        if name in used or name == BUSY or name.startswith("採購_"):
            continue
        key = scan.key_of(flow, name)
        for video in FLOW_VIDEOS[flow]:
            for n, p in scan.present(key, video):
                strong = [q for q in p if q[0] >= POS]
                if len(strong) >= 2:
                    pool.append((-len(strong), -min(q[0] for q in strong), name, video, n))
    pool.sort()
    out, seen = [], set()
    for _, _, name, video, n in pool:
        if len(out) >= k:
            break
        if name in seen or dropped(name, video, n):
            continue
        tpl = scan.tpl(scan.key_of(flow, name))
        scene = bc.frame(video, n)
        ps = bc.peaks(scene, tpl, thr=0.6)
        strong = [q for q in ps if q[0] >= 0.9]
        weak = [q for q in ps if 0.7 <= q[0] < 0.9]
        boxes = [tuple(q[1:]) for q in strong]
        if len(boxes) < 2:
            continue
        ok, why = clean(lang, video, n, boxes)
        if not ok:
            continue
        seen.add(name)
        used.add(name)
        c = base("同款多個", lang, flow, name, video, n, scene, tpl, expected="present",
                 boxes=boxes, multi=True, origin="配對工具")
        c["note"] = (f"{len(boxes)} 個，配對分數 {min(q[0] for q in strong):.2f}–"
                     f"{max(q[0] for q in strong):.2f}")
        if weak:
            c["doubt"] = (f"另有 {len(weak)} 處像但分數不夠 ({max(q[0] for q in weak):.2f})，"
                          f"請確認不是同款")
        out.append(c)
    return out


# ---------------------------------------------------------------- 比色 (同形不同色)

COLOR_SAME = 18.0    # 框內跟範本平均 BGR 差 ≤ 它＝同色
COLOR_OTHER = 30.0   # ≥ 它＝明顯不同色 (灰掉、變暗)


def color_states(scan, flow, name):
    """同形 (形狀配對 ≥0.8) 的取樣幀分兩群: 同色 [(影片, 幀, 框, 色差)] 與不同色.

    每段出現從中間往外排, 段內每個取樣幀都列 (中間那幀不乾淨時換旁邊的)。"""
    key = scan.key_of(flow, name)
    tpl = scan.tpl(key)
    same, other = [], []
    for video in FLOW_VIDEOS[flow]:
        for run in scan.runs([n for n, _ in scan.present(key, video, thr=0.8)]):
            mid = len(run) // 2
            for n in sorted(run, key=lambda m: abs(run.index(m) - mid)):
                p = scan.peaks(key, video, n)[0]
                box = (p[1], p[2], tpl.shape[1], tpl.shape[0])
                d = bc.color_diff(bc.frame(video, n), box, tpl)
                if d <= COLOR_SAME:
                    same.append((video, n, box, d))
                elif d >= COLOR_OTHER:
                    other.append((video, n, box, d))
    return same, other


def color_pair(scan, flow, name, label_same, label_other):
    """一張範本一正 (同色, 開比色要找到) 一負 (不同色, 開比色應該沒有)."""
    lang = bc.FLOWS[flow]
    tpl = scan.tpl(scan.key_of(flow, name))
    same, other = color_states(scan, flow, name)
    out = []
    for group, expected, label in ((same, "present", label_same), (other, "absent", label_other)):
        for video, n, box, d in group:
            if dropped(name, video, n):
                continue
            ok, _ = clean(lang, video, n, [box])
            if not ok:
                continue
            scene = bc.frame(video, n)
            c = base("比色", lang, flow, name, video, n, scene, tpl, expected=expected,
                     boxes=[box] if expected == "present" else [], color_check=True,
                     origin="配對工具＋色差",
                     lookalike=None if expected == "present" else box)
            c["note"] = f"{label}（框內跟範本平均色差 {d:.0f}）"
            if expected == "absent":
                c["note"] += "；同形狀的灰／暗版在畫面上，開比色應該沒有"
            out.append(c)
            break
    return out


# ---------------------------------------------------------------- 忙碌指示

def busy_cases(scan, lang):
    """忙碌指示: 在場 (乾淨的、疊字的、淡入淡出的) 要找到, 剛消失的要找不到.

    在場段用寬門檻 (配對 ≥0.6) 切: 段中間配對掉到 0.6–0.88、前後都還在的取樣幀＝字樣上疊著別的字;
    段頭往前、段尾往後逐幀讀 (stride 1): 配對 0.75–0.9 的是淡入／淡出中, 段尾 <0.4 的是剛消失。"""
    flows = [f for f, lg in bc.FLOWS.items() if lg == lang]
    out = []
    done_keys = set()
    for flow in flows:
        key = scan.key_of(flow, BUSY)
        if key in done_keys:
            continue   # 早晚同一張圖只做一次
        done_keys.add(key)
        tpl = scan.tpl(key)
        want = {"clean": 2, "fade": 2, "overlay": 1, "gone": 2}
        got = {k: 0 for k in want}

        def add(kind_, video, n, img, box, expected, note, doubt=None, origin="配對工具"):
            c = base("忙碌指示", lang, flow, BUSY, video, n, img, tpl, expected=expected,
                     boxes=[box] if expected == "present" else [], origin=origin,
                     lookalike=None if expected == "present" else box)
            c["note"], c["doubt"] = note, doubt
            out.append(c)
            got[kind_] += 1

        for video in bc.VIDEOS[lang]:
            for run in scan.runs([n for n, _ in scan.present(key, video, thr=0.6)]):
                if len(run) < 3:
                    continue
                score = {n: scan.peaks(key, video, n)[0][0] for n in run}
                # 乾淨的在場幀
                strong = [n for n in run if score[n] >= POS]
                if got["clean"] < want["clean"] and strong:
                    n = strong[len(strong) // 2]
                    if not dropped(BUSY, video, n):
                        img = bc.frame(video, n)
                        s_, box = bc.best(img, tpl)
                        if s_ >= POS and clean(lang, video, n, [box], allow_busy=True)[0]:
                            add("clean", video, n, img, box, "present",
                                f"忙碌字樣在場（配對 {s_:.2f}）")
                # 疊字: 段中間掉下去、前後取樣幀都還很清楚
                if got["overlay"] < want["overlay"]:
                    for a, n, b in zip(run, run[1:], run[2:]):
                        if not (0.6 <= score[n] < 0.88 and score[a] >= 0.9 and score[b] >= 0.9):
                            continue
                        if dropped(BUSY, video, n):
                            continue
                        img = bc.frame(video, n)
                        s_, box = bc.best(img, tpl)
                        if bc.cursor_touches(img, lang, [box]):
                            continue
                        add("overlay", video, n, img, box, "present",
                            f"忙碌字樣上疊著別的字或特效（配對 {s_:.2f}；前後幀都 ≥0.9）",
                            f"配對 {s_:.2f}：請確認字樣還在、只是被疊字蓋到")
                        break
                # 段頭往前逐幀: 淡入
                first, last = run[0], run[-1]
                edges = [("淡入", range(max(0, first - scan.stride), first + 1)),
                         ("淡出", range(last, last + scan.stride * 3))]
                for how, rng in edges:
                    fr = bc.read_frames(video, rng)
                    box0 = None
                    for m in sorted(fr):
                        if dropped(BUSY, video, m):
                            continue
                        s_, box = bc.best(fr[m], tpl)
                        box0 = box0 or box
                        if (0.75 <= s_ < 0.9 and got["fade"] < want["fade"]
                                and not bc.cursor_touches(fr[m], lang, [box])):
                            add("fade", video, m, fr[m], box, "present",
                                f"{how}中的忙碌字樣（配對 {s_:.2f}），還看得到就要找到",
                                f"{how}中，配對 {s_:.2f}：請確認字樣還看得出來", "配對工具 (逐幀)")
                        if (how == "淡出" and s_ < 0.4 and got["gone"] < want["gone"]
                                and not bc.unstable(video, m, [box0], k=1, thr=4.0)):
                            add("gone", video, m, fr[m], box, "absent",
                                f"忙碌字樣剛消失（第 {last} 幀還在；這幀最像 {s_:.2f}）",
                                origin="配對工具 (逐幀)")
                            break
            if all(got[k] >= want[k] for k in want):
                break
    return out


# ---------------------------------------------------------------- 線索背景 (quick-place 人工判定)

QP = os.path.join(bc.SCRATCH, "quick-place-clue-check")


def clue_cfg(lang):
    sys.path.insert(0, QP)
    import importlib.util
    spec = importlib.util.spec_from_file_location("qp_clue_cfg", os.path.join(QP, "clue.py"))
    src = open(os.path.join(QP, "clue.py"), encoding="utf-8").read()
    # clue.py 開頭會 import app 的模組; 這裡只要它的 LANGS 表
    start = src.index("LANGS = {")
    end = src.index("\n}\n", start) + 3
    ns = {}
    exec(src[start:end], ns)
    return ns["LANGS"][lang]


def near_box(scene, tpl, xy, r=40):
    """在 xy (影片座標) 附近 ±r 配對: (分數, 框)."""
    th, tw = tpl.shape[:2]
    H, W = scene.shape[:2]
    x0, y0 = max(0, int(xy[0] - tw / 2 - r)), max(0, int(xy[1] - th / 2 - r))
    win = scene[y0:min(H, int(xy[1] + th / 2 + r)), x0:min(W, int(xy[0] + tw / 2 + r))]
    s, (x, y, w, h) = bc.best(win, tpl)
    return s, (x + x0, y + y0, w, h)


def cluebg_cases(lang):
    """線索面板上的小圖 (add3／add4): 情境來自 quick-place 票的人工判定 (面板關著／選 all／選中 N 號、
    N 號有沒有卡片)."""
    cfg = clue_cfg(lang)
    flow, video = cfg["flow"], cfg["video"]
    tpls = bc.flow_templates(flow)
    sel = cfg["selected"]
    label = cfg["labels"][1]
    origin = "人工判定 (quick-place 線索情境)"
    picked = cfg["picked"]
    has = cfg["has"]
    nums_has = [n for n in sorted(has) if has[n]]
    nums_none = [n for n in sorted(has) if not has[n]]
    plan = []
    # 選中 N 號: 那顆鈕找得到
    n = nums_has[1]
    a, b = picked[n]
    plan.append(("present", sel.format(n), (a + b) // 2,
                 (cfg["buttons"][n - 1], cfg["button_y"]), f"選中 {n} 號，篩選鈕 {n} 是選中狀態"))
    # 選中 M 號時, N 號鈕是沒選中的樣子 → 選中 N 的範本應該沒有
    m = nums_has[-1]
    a, b = picked[m]
    plan.append(("absent", sel.format(n), (a + b) // 2, None,
                 f"選中的是 {m} 號；{n} 號鈕是沒選中的樣子（形狀一樣、底色不同）"))
    # 卡片標籤: 有卡片的號找得到、暂无线索的號找不到
    f_label = cfg["boxes"][label][0]   # 人工框過卡片標籤的那幀
    n_label = next(k for k, (a, b) in picked.items() if a <= f_label <= b)
    plan.append(("present", label, f_label, None, f"{n_label} 號有線索卡，卡片上有「{label}」"))
    if nums_none:
        a, b = picked[nums_none[-1]]
        plan.append(("absent", label, (a + b) // 2, None, f"{nums_none[-1]} 號暂无线索，沒有卡片"))
    out = []
    for expected, name, n0, xy, note in plan:
        tpl = tpls[name]
        # 同一情境 (選中同一號) 裡從 n0 往外找游標沒碰框、框沒在變的幀
        rng = next(((a, b) for a, b in picked.values() if a <= n0 <= b), (n0, n0))
        n = next((m for m in sorted(range(rng[0] + 1, rng[1]), key=lambda m: abs(m - n0))
                  if _clue_clean(lang, video, m, tpl, xy, cfg, name, expected)), None)
        if n is None:
            continue
        scene = bc.frame(video, n)
        if expected == "present":
            if xy is None:
                bx = cfg["boxes"][name][1]
                xy = (bx[0] + bx[2] / 2, bx[1] + bx[3] / 2)
            s, box = near_box(scene, tpl, xy, r=60)
            boxes = [box]
            # 卡片標籤每張卡都有: 同款全部列出 (centers)
            more = [tuple(q[1:]) for q in bc.peaks(scene, tpl, thr=0.9)
                    if not bc.overlaps(tuple(q[1:]), box)]
            boxes += more
        else:
            s, box = bc.best(scene, tpl)
            boxes = []
        c = base("線索背景", lang, flow, name, video, n, scene, tpl, expected=expected,
                 boxes=boxes, origin=origin, multi=len(boxes) > 1,
                 lookalike=None if boxes else box)
        c["note"] = f"{note}（配對 {s:.2f}）"
        if expected == "present" and s < 0.85:
            c["doubt"] = f"配對只有 {s:.2f}"
        if expected == "absent" and s >= 0.8:
            c["doubt"] = f"最像的地方 {s:.2f}，請確認不是範本本身"
        out.append(c)
    return out


def _clue_clean(lang, video, n, tpl, xy, cfg, name, expected):
    """線索面板情境裡這幀能不能用: 該找到的框 (與畫面最像的地方) 游標沒碰、沒在變."""
    if dropped(name, video, n):
        return False
    scene = bc.frame(video, n)
    if expected == "present":
        if xy is None:
            bx = cfg["boxes"][name][1]
            xy = (bx[0] + bx[2] / 2, bx[1] + bx[3] / 2)
        box = near_box(scene, tpl, xy, r=60)[1]
    else:
        box = bc.best(scene, tpl)[1]
    return clean(lang, video, n, [box])[0]


def cluebg_board(scan, flow, used):
    """線索板 (好友線索板／自家線索板) 上的 CONFIDENTIAL 線索: 配對工具挑一個乾淨的正例."""
    name = "CONFIDENTIAL线索" if bc.FLOWS[flow] == "cn" else "CONFIDENTIAL線索"
    key = scan.key_of(flow, name)
    tpl = scan.tpl(key)
    lang = bc.FLOWS[flow]
    for video in FLOW_VIDEOS[flow]:
        if video.startswith("add"):
            continue   # add3／add4 已經用在面板案例
        for run in scan.runs([n for n, _ in scan.present(key, video)]):
            c = positive_at(scan, flow, name, video, run[len(run) // 2], tpl, "線索背景")
            if c:
                c["note"] = "線索板背景上的 CONFIDENTIAL 線索；" + c["note"]
                return [c]
    return []


# ---------------------------------------------------------------- 混淆

def confuser_present(scan, flow, k, used, names=None):
    """範本在 (≥0.95), 畫面別處有長得像的 (0.72–0.92): 要挑對那一個."""
    lang = bc.FLOWS[flow]
    pool = []
    for name in (names or scan.names(flow)):
        if name in used or name == BUSY or name.startswith("採購_"):
            continue
        key = scan.key_of(flow, name)
        for video in FLOW_VIDEOS[flow]:
            for n, p in scan.present(key, video, thr=0.95):
                if len(p) > 1 and 0.72 <= p[1][0] < 0.92:
                    pool.append((-p[1][0], name, video, n))
    pool.sort()
    out, seen = [], set()
    for _, name, video, n in pool:
        if len(out) >= k:
            break
        if name in seen or dropped(name, video, n):
            continue
        tpl = scan.tpl(scan.key_of(flow, name))
        scene = bc.frame(video, n)
        ps = bc.peaks(scene, tpl, thr=0.6)
        if not ps or ps[0][0] < 0.95 or len(ps) < 2 or ps[1][0] >= 0.92:
            continue
        box = tuple(ps[0][1:])
        if not clean(lang, video, n, [box])[0]:
            continue
        seen.add(name)
        used.add(name)
        c = base("混淆", lang, flow, name, video, n, scene, tpl, expected="present",
                 boxes=[box], origin="配對工具")
        c["note"] = (f"本尊配對 {ps[0][0]:.2f}；畫面上另有長得像的 {len(ps) - 1} 處"
                     f"（最高 {ps[1][0]:.2f}），要挑對本尊")
        out.append(c)
    return out


def confuser_absent(scan, flow, k, used, names=None):
    """範本不在, 但畫面上有長得很像的 (配對 0.72–0.88): 應該沒有."""
    lang = bc.FLOWS[flow]
    busy_key = scan.key_of(flow, BUSY)
    pool = []
    for name in (names or scan.names(flow)):
        if name in used or name == BUSY or name.startswith("採購_"):
            continue
        key = scan.key_of(flow, name)
        for video in FLOW_VIDEOS[flow]:
            pk = scan.videos[video]["peaks"].get(key, {})
            busy_on = {int(n) for n, _ in scan.present(busy_key, video, thr=0.7)}
            for n, p in pk.items():
                # 底部忙碌字樣帶會蓋住列表最下面的標題 (半露的其實在): 那種幀不當負樣本
                if p and 0.75 <= p[0][0] < 0.88 and int(n) not in busy_on:
                    pool.append((-p[0][0], name, video, int(n)))
    pool.sort()
    out, seen = [], set()
    for negs, name, video, n in pool:
        if len(out) >= k:
            break
        if name in seen or dropped(name, video, n) or not bc.calm_scene(video, n):
            continue
        tpl = scan.tpl(scan.key_of(flow, name))
        scene = bc.frame(video, n)
        if bc.busy_on(scene, lang):
            continue
        s, box = bc.best(scene, tpl)
        if not 0.72 <= s < 0.88:
            continue
        if bc.cursor_touches(scene, lang, [box]) or bc.unstable(video, n, [box]):
            continue
        seen.add(name)
        used.add(name)
        c = base("混淆", lang, flow, name, video, n, scene, tpl, expected="absent", boxes=[],
                 origin="配對工具")
        c["note"] = f"範本不在；畫面上最像的東西配對 {s:.2f}（長得像但不是）"
        c["doubt"] = f"最像的地方 {s:.2f}：請確認那不是範本本身（例如被遮住一部分）"
        c["lookalike"] = box
        out.append(c)
    return out


# ---------------------------------------------------------------- 縮放、跨影片

SCALES = (0.85, 1.15)   # 支援倍率範圍兩端


def scaled_case(c, s):
    """真實影格等比縮 s 倍: 答案框跟著乘 s, 預期尺度寫 s; 範本不動."""
    import cv2
    scene = c["scene"]
    H, W = scene.shape[:2]
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
    c = dict(c)
    c["scene"] = cv2.resize(scene, (round(W * s), round(H * s)), interpolation=interp)
    c["boxes"] = [tuple(int(round(v * s)) for v in b) for b in c["boxes"]]
    c["expected_scale"] = s
    c["note"] = f"真實影格縮成 ×{s}（範本不動，預期尺度 {s}）；原本{c['note']}"
    return c


# 錄影日期 (跨影片＝別天錄的)
VIDEO_DAY = {"demo2": "10/03", "demo3": "10/04", "demo4": "10/04", "demo5": "10/04",
             "demo6": "10/06", "add1": "10/07", "add2": "10/07", "add3": "10/09",
             "add4": "10/09", "add5": "10/10"}


def source_video(scan, key):
    """範本取材的影片＝整支影片裡配對分數最高的那支."""
    best = (-1, None)
    for video, v in scan.videos.items():
        m = max(v["max"][key]) if v["max"][key] else 0
        if m > best[0]:
            best = (m, video)
    return best[1]


def cross_cases(scan, lang, k, used):
    """範本在取材影片以外、別天錄的影片上找 (同一客戶端、同一倍率)."""
    pool = []
    for flow in (f for f, lg in bc.FLOWS.items() if lg == lang):
        for name in scan.names(flow):
            if special(name) or name in used[flow]:
                continue
            key = scan.key_of(flow, name)
            src = source_video(scan, key)
            for video in bc.VIDEOS[lang]:
                if VIDEO_DAY[video] == VIDEO_DAY[src]:
                    continue
                for run in scan.runs([n for n, _ in scan.present(key, video, thr=0.85)]):
                    if len(run) < 3:
                        continue
                    n = run[len(run) // 2]
                    p = scan.peaks(key, video, n)
                    if len(p) > 1 and p[1][0] >= UNIQUE:
                        continue
                    pool.append((p[0][0], flow, name, src, video, n))
    # 分數低的 (畫面細節變了的) 優先, 但每張範本、每份流程平均分
    pool.sort()
    out, seen = [], set()
    flows = [f for f, lg in bc.FLOWS.items() if lg == lang]
    for i in range(len(pool) * 2):
        if len(out) >= k:
            break
        want_flow = flows[len(out) % len(flows)]
        row = next((r for r in pool if r[1] == want_flow and r[2] not in seen), None)
        if row is None:
            row = next((r for r in pool if r[2] not in seen), None)
        if row is None:
            break
        s0, flow, name, src, video, n = row
        seen.add(name)
        if dropped(name, video, n):
            continue
        tpl = scan.tpl(scan.key_of(flow, name))
        scene = bc.frame(video, n)
        (s, box), second = exact(scene, tpl)
        if s < 0.85 or second >= UNIQUE or not clean(lang, video, n, [box])[0]:
            continue
        used[flow].add(name)
        c = base("跨影片", lang, flow, name, video, n, scene, tpl, expected="present",
                 boxes=[box], template_video=src, origin="配對工具")
        c["note"] = (f"範本推定取自 {src}（{VIDEO_DAY[src]}；整支影片配對最高的那支），"
                     f"在 {video}（{VIDEO_DAY[video]}）找："
                     f"配對 {s:.2f}，別處最高 {second:.2f}")
        if s < 0.9:
            c["doubt"] = f"別天的畫面配對只有 {s:.2f}：請確認紅框是同一個東西"
        out.append(c)
    return out


# ---------------------------------------------------------------- 主程式

KINDS = {}


def kind(fn):
    KINDS[fn.__name__] = fn
    return fn


@kind
def general(scans, used):
    out = []
    for flow in bc.FLOWS:
        out += pick_positive(scans[bc.FLOWS[flow]], flow, 3, used[flow])
    return out


@kind
def negatives(scans, used):
    out = []
    for flow in bc.FLOWS:
        out += pick_negative(scans[bc.FLOWS[flow]], flow, 3, used[flow])
    return out


def _spread(cands, k):
    """平均取 k 個 (照原順序)."""
    if len(cands) <= k:
        return cands
    return [cands[int(i * len(cands) / k)] for i in range(k)]


@kind
def multi(scans, used):
    out = []
    for lang in ("cn", "tw"):
        shop = shop_cases(lang, want_color=False)
        # 不同畫面各取一個
        by_frame = {}
        for c in shop:
            by_frame.setdefault(c["shop"], c)
        # 聚酸酯 3 格那種格數多的優先, 再平均取
        shops = sorted(by_frame.values(), key=lambda c: -len(c["boxes"]))
        out += shops[:1] + _spread(shops[1:], 2)
        for flow in (f for f, lg in bc.FLOWS.items() if lg == lang):
            out += multi_from_scan(scans[lang], flow, 2, used[flow])
    return out


@kind
def color(scans, used):
    out = []
    for lang in ("cn", "tw"):
        shop = shop_cases(lang, want_color=True)
        pos = [c for c in shop if c["expected"] == "present"]
        neg = [c for c in shop if c["expected"] == "absent"]
        # 售罄那格形狀還配得上的優先 (比色才是唯一分得開的地方)
        pos.sort(key=lambda c: -c["sold_best"])
        neg.sort(key=lambda c: -c["sold_best"])
        got = pos[:1] + neg[:1]
        flow = SHOP_FLOW[lang]
        unlock = "解锁线索" if lang == "cn" else "解鎖線索"
        got += color_pair(scans[lang], flow, "全部收取", "全部收取藍色（可以收）", "全部收取暗的")
        got += color_pair(scans[lang], flow, unlock, "解鎖線索亮著（可以點）", "解鎖線索灰的")
        got += color_pair(scans[lang], flow, "快速置入", "快速置入亮著", "快速置入灰的")
        out += got[:6]   # 每個客戶端 6 個 (配額每類 6–12)
    return out


@kind
def busy(scans, used):
    return busy_cases(scans["cn"], "cn") + busy_cases(scans["tw"], "tw")


@kind
def cluebg(scans, used):
    out = cluebg_cases("cn") + cluebg_cases("tw")
    for flow in ("早_簡中", "早_繁中"):
        out += cluebg_board(scans[bc.FLOWS[flow]], flow, used[flow])
    return out


@kind
def confusers(scans, used):
    out = []
    for flow in bc.FLOWS:
        scan = scans[bc.FLOWS[flow]]
        titles = [n for n in scan.names(flow) if n.startswith(("标题_", "標題_"))]
        out += confuser_present(scan, flow, 1, used[flow], titles)
        out += confuser_absent(scan, flow, 1, used[flow], titles)
        out += confuser_present(scan, flow, 2, used[flow])
        out += confuser_absent(scan, flow, 1, used[flow])
    return out


@kind
def scale(scans, used):
    out = []
    for flow in bc.FLOWS:
        got = pick_positive(scans[bc.FLOWS[flow]], flow, 3, used[flow], kind="縮放")
        i = list(bc.FLOWS).index(flow)
        for j, c in enumerate(got):
            out.append(scaled_case(c, SCALES[(i + j) % 2]))
    return out


@kind
def cross(scans, used):
    return cross_cases(scans["cn"], "cn", 4, used) + cross_cases(scans["tw"], "tw", 4, used)


CODES = {"一般正例": "pos", "易誤判負樣本": "neg", "同款多個": "multi", "比色": "color",
         "忙碌指示": "busy", "線索背景": "cluebg", "混淆": "conf", "縮放": "scale",
         "跨影片": "cross"}


def name_cases(cands):
    seen = {}
    for c in sorted(cands, key=lambda c: (cases.KIND_ORDER.index(c["kind"]), c["lang"],
                                          c["flow"], c["template"], c["video"], c["frame"])):
        code = CODES[c["kind"]]
        seen[code] = seen.get(code, 0) + 1
        tag = f"_x{c['expected_scale']}" if c.get("expected_scale", 1.0) != 1.0 else ""
        c["name"] = (f"{code}{seen[code]:02d}_{c['lang']}_{c['template']}"
                     f"_{c['video']}f{c['frame']}{tag}")


def apply_review(cands):
    """review.yaml 的 doubt／note (鍵＝範本@影片f幀) 蓋過自動產生的; drop 的挑的時候已跳過."""
    rv = review()
    for c in cands:
        k = rkey(c["template"], c["video"], c["frame"])
        if k in (rv.get("doubt") or {}):
            c["doubt"] = rv["doubt"][k]
        if k in (rv.get("ok") or {}):
            c["doubt"] = None
        if k in (rv.get("note") or {}):
            c["note"] = rv["note"][k]
        if k in (rv.get("color_absent") or {}):
            c["color_check"] = True
            c["expected"] = "absent"
            c["lookalike"] = c["boxes"][0] if c["boxes"] else None
            c["boxes"] = []
            c["multi"] = False
            c["note"] = rv["color_absent"][k]
    return [c for c in cands if not dropped(c["template"], c["video"], c["frame"])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kinds", nargs="*", default=list(KINDS))
    ap.add_argument("--bench", action="store_true", help="寫完用基準集執行器跑一次")
    ap.add_argument("--seen", action="store_true", help="這次的候選全部記成 agent 看過")
    a = ap.parse_args()
    scans = {lang: Scan(lang) for lang in ("cn", "tw")}
    # 同一客戶端兩份流程共用: 一張範本名在整個客戶端只挑一次 (早晚同名的不重複)
    per_lang = {"cn": set(), "tw": set()}
    used = {flow: per_lang[lg] for flow, lg in bc.FLOWS.items()}
    cands = []
    for k in a.kinds:
        got = KINDS[k](scans, used)
        print(f"{k}: {len(got)}", flush=True)
        cands += got
    name_cases(cands)
    cands = apply_review(cands)
    if os.path.isdir(bc.CANDIDATES):
        shutil.rmtree(bc.CANDIDATES)
    for c in cands:
        cases.write_case(c)
    numbered = cases.card_page(cands, os.path.join(bc.TMP, "cards.html"))
    cases.review_sheets(numbered, os.path.join(bc.TMP, "review"))
    # agent 還沒看過的 (換掉、新挑的) 另外拼一份; --seen 把這次全部記成看過
    seen_path = os.path.join(bc.TMP, "seen.json")
    seen = set(bc.load(seen_path)) if os.path.isfile(seen_path) else set()
    def sig(c):
        return f"{rkey(c['template'], c['video'], c['frame'])}|{c['kind']}|{len(c['boxes'])}"
    new = [(no, c) for no, c in numbered if sig(c) not in seen]
    cases.review_sheets(new, os.path.join(bc.TMP, "review_new"))
    for no, c in numbered:
        c["card_no"] = no
    if new:
        cases.card_page([c for _, c in new], os.path.join(bc.TMP, "changes", "cards.html"),
                        title="基準集候選案例：這次換掉或改過的")
    print(f"agent 還沒看過: {len(new)} 個 → tmp/review_new/")
    if a.seen:
        bc.dump(seen_path, sorted(seen | {sig(c) for _, c in numbered}))
    bc.dump(os.path.join(bc.TMP, "candidates.json"),
            [{"no": no, "name": c["name"], "kind": c["kind"], "doubt": c["doubt"]}
             for no, c in numbered])
    print(f"候選 {len(cands)} 個 → {bc.CANDIDATES}; 卡片頁 {os.path.join(bc.TMP, 'cards.html')}")
    if a.bench:
        sys.path.insert(0, os.path.join(bc.ROOT, "src"))
        from subject_detection.bench import format_report, run_bench
        rep = run_bench(bc.CANDIDATES)
        text = format_report(rep)
        with open(os.path.join(bc.TMP, "bench.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        print(text)


if __name__ == "__main__":
    main()

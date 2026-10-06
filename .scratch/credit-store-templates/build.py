"""採購中心商品範本: 從倉庫素材圖切 PNG, 用專案引擎在商店畫面上驗證 (見 spec.md).

    .venv/Scripts/python.exe .scratch/credit-store-templates/build.py            # 全部重跑
    .venv/Scripts/python.exe .scratch/credit-store-templates/build.py --items 糖  # 只跑幾種, 輸出到 preview/
    .venv/Scripts/python.exe .scratch/credit-store-templates/build.py --overlays  # 只畫核對圖, 不跑引擎

全部重跑時清空 `oCam Video\\採購中心範本\\繁中\\`、`簡中\\` 再重新產生, 並覆寫 `報告.md`。
驗證畫面與標註在 annotations.json (影格由 extract_frames.py 抽出、圓心由
measure_centers.py 量出)。核對圖寫到本資料夾的 overlays/。

驗證走引擎公開 API, 與影片轉流程的自我驗證同一套: make_library → 逐張
Engine.register → 以整張驗證畫面 Engine.query(預期尺度 1), 門檻用 arknights
profile 的 config.yaml, 位置容許值沿用 tools/video_to_flow/verify.position_tolerance。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
from dataclasses import dataclass

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = r"C:\Users\three\我的電腦\oCam Video"
OUT = os.path.join(SRC, "採購中心範本")
PROFILE = os.path.join(ROOT, "profiles", "arknights")
sys.path.insert(0, os.path.join(ROOT, "tools"))

from video_to_flow import verify as vtf_verify  # noqa: E402
from video_to_flow.geom import center  # noqa: E402

PREFIX = "採購_"
RETAKE = "待重拍_"

# 倉庫素材圖上的 23 種商品: (遊戲繁中名, 核對圖用的 ASCII 代號, 素材圖, 圓圈中心)
# 素材圖都是繁中客戶端的倉庫 (同一尺度)。圓圈中心是霍夫圓偵測的結果; pic2 各格的
# 物品由看圖對照遊戲物品辨認 (pic2 只取一階灰圈、二階黃綠圈)。pic8 的 EXP 卡圓心
# 由外環外緣擬圓, 書本超出圓圈擬不準, 改用同欄/同列的圓心 (格距同 pic2)。
ITEMS = [
    ("源岩", "yuanyan", "pic2", (104.5, 585.5)),
    ("固源岩", "guyuanyan", "pic2", (104.5, 351.5)),
    ("代糖", "daitang", "pic2", (873.5, 586.5)),
    ("糖", "tang", "pic2", (873.5, 351.5)),
    ("酯原料", "zhiyuanliao", "pic2", (680.5, 351.5)),
    ("聚酸酯", "jusuanzhi", "pic2", (681.5, 117.5)),
    ("異鐵碎片", "yitiesuipian", "pic2", (1257.5, 117.5)),
    ("異鐵", "yitie", "pic2", (1064.5, 586.5)),
    ("雙酮", "shuangtong", "pic2", (1448.5, 352.5)),
    ("酮凝集", "tongningji", "pic2", (1448.5, 117.5)),
    ("破損裝置", "posunzhuangzhi", "pic2", (488.5, 118.5)),
    ("裝置", "zhuangzhi", "pic2", (296.5, 586.5)),
    ("招聘許可", "zhaopin", "pic4", (96.5, 115.5)),
    ("加急許可", "jiaji", "pic4", (96.5, 349.5)),
    ("碳", "tan", "pic5", (95.5, 578.5)),
    ("碳素", "tansu", "pic5", (96.5, 341.5)),
    ("碳素組", "tansuzu", "pic5", (96.5, 108.5)),
    ("龍門幣", "longmenbi", "pic6", (96.5, 96.5)),
    ("赤金", "chijin", "pic6", (96.5, 330.5)),
    ("基礎作戰記錄", "record0", "pic8", (330.4, 105.2)),
    ("初級作戰記錄", "record1", "pic8", (137.0, 572.0)),
    ("技巧概要·卷1", "skill1", "pic8", (522.5, 105.2)),
    ("技巧概要·卷2", "skill2", "pic8", (330.4, 572.0)),
]
# 有簡中客戶端倉庫圖的商品: 簡中範本改從這裡切 (不必把繁中倉庫圖縮放到簡中尺度)。
# pic7 與 pic8 同一排版, 格距 170.9 vs 192 px (比 0.89, 等於簡中/繁中的畫面比);
# 圓心取法同 pic8。
CN_SOURCES = {
    "基礎作戰記錄": ("pic7", (278.1, 88.9)),
    "初級作戰記錄": ("pic7", (107.2, 502.0)),
    "技巧概要·卷1": ("pic7", (449.0, 88.9)),
    "技巧概要·卷2": ("pic7", (278.1, 502.0)),
}
# 驗證畫面上出現、但不在這次範本裡的商品 (核對圖代號)
OTHER_CODES = {"傢俱零件": "furniture"}
# 這次沒做的商品 (使用者決定傢俱零件不判斷, 不列)
NOT_MADE = []

# 兩個候選框法: 相對圓圈中心的 (左, 上, 右, 下), 倉庫像素 (圓圈外環半徑約 78、
# 內側黑環半徑約 70)。下緣都停在中心下方 +20 以內: 倉庫右下的庫存數字框
# 從 +33 起、商店卡的販售數量框從 +40 起, 龍門幣的「3600」條從 +32 起。
# 商店卡左上的折扣標籤最低到中心上方 -66 (換成倉庫像素; 右緣到 -54), 兩者都不碰到——
# 所以上半圓的上緣只能到 -65, 頂端約 13 px 的外環弧框不進來。
FRAMINGS = {
    "inner": {"label": "圈內方塊", "box": (-50, -52, 50, 20),
              "note": "倉庫 100×72，四角落在內側黑環以內，不含圓圈外背景"},
    "ring": {"label": "含外環上半圓", "box": (-80, -65, 80, 0),
             "note": "倉庫 160×65，下緣在中心線；左右含外環 (分階顏色)，四角帶到背景；"
                     "上緣停在折扣標籤下方 (-65)，外環頂端約 13 px 的弧框不進來"},
}

TW_SCALE = 0.975          # 倉庫圖示 → 繁中商店 (spec Further Notes 實測)
# 卡片範圍 (相對圓圈中心, 繁中商店像素): demo2 / pic1 上量的卡片外框
CARD_BOX_TW = (-140, -150, 150, 140)
# 卡片格距 (欄距, 列距): 未售完卡多的畫面上連格距一起擬合的結果 (繁中 pic1、
# demo2 第 2760 幀; 簡中 demo1 第 4620 幀、demo5 第 3300 幀、demo6 第 3113 幀)
GRID = {"tw": (312.1, 313.4), "cn": (276.1, 277.1)}
# 量圓圈直徑用的已知商品: 黃綠圈的二階材料 (圖示不超出圓圈, 外環完整)
RING_ITEMS = {"糖", "聚酸酯", "裝置", "固源岩", "異鐵"}
# 外環半徑的粗估 (px): 量直徑時放射線的搜尋範圍以它為準
RING_RADIUS = {"warehouse": 78.0, "tw": 75.0, "cn": 66.0}


# ---------------------------------------------------------------- 影像 I/O

def read(path):
    img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"讀不到圖檔: {path}")
    return img


def write(path, img):
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise SystemExit(f"無法編碼 PNG: {path}")
    buf.tofile(path)


# ---------------------------------------------------------------- 切圖

def cut(src, circle, box, s, src_scale=1.0):
    """切出相對圓圈中心 box (繁中倉庫像素) 的範圍, 輸出是繁中倉庫圖示的 s 倍.

    src_scale = 素材圖本身相對繁中倉庫的尺度 (簡中客戶端的倉庫圖 < 1)。
    回傳 (範本圖, 範本中心相對圓圈中心的偏移 (縮放後像素))。
    """
    f = s / src_scale
    big = cv2.resize(src, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    cx, cy = (circle[0] + 0.5) * f - 0.5, (circle[1] + 0.5) * f - 0.5
    left, top, right, bottom = box
    x0, y0 = round(cx + left * s), round(cy + top * s)
    w, h = round((right - left) * s), round((bottom - top) * s)
    if x0 < 0 or y0 < 0 or x0 + w > big.shape[1] or y0 + h > big.shape[0]:
        raise SystemExit(f"切圖超出素材圖範圍: 中心 {circle} 框 {box}")
    return big[y0:y0 + h, x0:x0 + w].copy(), (x0 + w / 2 - cx, y0 + h / 2 - cy)


def cut_all(sources, names, framing, s, cn_src_scale=None):
    """{商品名: {"img": 範本圖, "offset": 範本中心相對圓圈中心的偏移}}.

    cn_src_scale 有值＝簡中組: CN_SOURCES 裡的商品改從簡中倉庫圖切, 該圖相對繁中
    倉庫的尺度取 cn_src_scale (同一客戶端的倉庫與商店畫面等比, 所以等於簡中/繁中
    商店的圓圈直徑比)。
    """
    out = {}
    for name, _code, pic, circle in ITEMS:
        if name in names:
            src_scale = 1.0
            if cn_src_scale is not None and name in CN_SOURCES:
                pic, circle = CN_SOURCES[name]
                src_scale = cn_src_scale
            img, off = cut(sources[pic], circle, FRAMINGS[framing]["box"], s, src_scale)
            out[name] = {"img": img, "offset": off}
    return out


# ---------------------------------------------------------------- 量圓圈直徑

def ring_radius(img, circle, r_guess):
    """沿放射線找彩色外環的外緣 (外環 → 背景) 半徑, 取各方向中位數.

    每條射線在 [0.8R, 1.25R] 內找色差 (Lab) 的梯度, 取「由內往外最後一個
    超過該射線最大梯度一半」的位置——外環內側的黑環邊緣更強, 但在更裡面。
    右下象限 (數字框) 不量。
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    rs = np.arange(0.8 * r_guess, 1.25 * r_guess, 0.25)
    radii = []
    for deg in range(100, 360, 4):
        a = np.deg2rad(deg)
        xs = (circle[0] + rs * np.cos(a)).astype(np.float32)
        ys = (circle[1] + rs * np.sin(a)).astype(np.float32)
        prof = cv2.remap(lab, xs.reshape(1, -1), ys.reshape(1, -1),
                         cv2.INTER_LINEAR)[0]
        grad = np.linalg.norm(prof[2:] - prof[:-2], axis=1)
        strong = np.nonzero(grad >= 0.5 * grad.max())[0]
        radii.append(rs[1 + strong[-1]])
    return float(np.median(radii))


@dataclass
class Scales:
    """量出來的尺度: 簡中倍率與量測依據."""
    cn_scale: float      # 倉庫圖示 → 簡中商店
    cn_over_tw: float    # 簡中/繁中 圓圈直徑比
    grid_ratio: float    # 簡中/繁中 卡片格距比 (核對用)
    d_tw: float          # 繁中商店直徑中位數
    d_cn: float          # 簡中商店直徑中位數
    d_warehouse: float   # 倉庫直徑中位數 (核對 ×0.975 用)
    per_card: dict       # {"tw"/"cn": [(畫面, 商品, 直徑)]}


def measure_scales(frames, sources):
    """簡中商店的圓圈直徑 ÷ 繁中商店的圓圈直徑 (只量未售完的已知商品卡)."""
    per_card = {"tw": [], "cn": []}
    for fr in frames:
        for card in fr["cards"]:
            if card["name"] in RING_ITEMS and not card["soldOut"]:
                r = ring_radius(fr["img"], card["center"], RING_RADIUS[fr["set"]])
                per_card[fr["set"]].append((fr["id"], card["name"], 2 * r))
    d_tw = statistics.median(d for *_, d in per_card["tw"])
    d_cn = statistics.median(d for *_, d in per_card["cn"])
    d_wh = statistics.median(2 * ring_radius(sources[pic], circle, RING_RADIUS["warehouse"])
                             for name, _code, pic, circle in ITEMS if name in RING_ITEMS)
    return Scales(TW_SCALE * d_cn / d_tw, d_cn / d_tw, GRID["cn"][0] / GRID["tw"][0],
                  d_tw, d_cn, d_wh, per_card)


# ---------------------------------------------------------------- 驗證

def card_box(card, k):
    """卡片範圍 (x0, y0, x1, y1), k = 該畫面相對繁中商店的格距比."""
    l, t, r, b = CARD_BOX_TW
    cx, cy = card["center"]
    return cx + l * k, cy + t * k, cx + r * k, cy + b * k


def _inside(pt, rect):
    return rect[0] <= pt[0] <= rect[2] and rect[1] <= pt[1] <= rect[3]


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


class Verifier:
    """一組範本 (同一尺度) 在一組驗證畫面上的驗證結果.

    results[範本名][畫面 id][比色開關] = `_judge` 的結果 dict;
    failed[範本名] = 引擎無法登錄的原因。
    """

    def __init__(self, engine, config, templates, frames, k):
        from subject_detection import make_library

        self.templates, self.frames, self.k = templates, frames, k
        self.match_threshold = float(config["match_threshold"])
        self.verify_threshold = float(config["verify_threshold"])
        self.failed = {}
        registered = []
        with tempfile.TemporaryDirectory(prefix="credit_store_") as tmp:
            paths = {}
            for i, (name, t) in enumerate(templates.items()):
                p = os.path.join(tmp, f"t{i:02d}.png")
                write(p, t["img"])
                paths[name] = p
            lib = make_library(paths, config, os.path.join(tmp, "registered"))
            for name in templates:
                try:   # 登錄產物載進記憶體, 暫存目錄刪掉後照樣能查
                    engine.register(lib, name)
                    registered.append(name)
                except Exception as e:   # 無結構的框連登錄都過不了
                    self.failed[name] = str(e)
        self.results = {n: {} for n in templates}
        for name in registered:
            for fr in frames:
                for color in (False, True):
                    r = engine.query(lib, name, fr["img"], color_check=color,
                                     expected_scale=1.0)
                    self.results[name].setdefault(fr["id"], {})[color] = \
                        self._judge(name, fr, r)

    def _judge(self, name, fr, r):
        """範本 name 在畫面 fr 上的一次查詢結果 r → 本畫面的判定與報告用分數.

        - own: 每張未售完的本尊卡 {card, hit (預期位置附近有匹配), score (那附近
          最高的深度驗證分數), color (該候選的比色分數)}; 售完的本尊卡不計
        - false: 落在別種商品卡 (含售完卡) 上的匹配
        - top_other: 別種商品卡上深度驗證分數最高的候選; 沒有候選過粗篩時
          coarse_other 記粗篩分數最高的 (分數, 卡名)
        - on_card / on_coarse: 每張卡上最高的深度驗證 / 粗篩分數 (同系列互認檢查用)
        - ok: 本畫面通過 (本尊卡都有匹配、別種卡上沒有匹配)
        """
        t = self.templates[name]
        th, tw = t["img"].shape[:2]
        tol = vtf_verify.position_tolerance((0, 0, tw, th))
        # 候選的深度驗證分數只有過粗篩門檻的才有 (與比色無關)
        cands = r.debug.get("candidates", [])
        passing = [c for c in cands if c["score"] >= self.match_threshold]
        vscores = r.debug.get("verify_scores", [c["score"] for c in passing])
        scored = [(tuple(c["box"]), v) for c, v in zip(passing, vscores)]
        colors = {tuple(m.box): m.color for m in list(r.matches) + list(r.rejected)}
        matches = [tuple(int(v) for v in m.box) for m in r.matches]

        own, others, false_hits = [], [], []
        on_card, on_coarse = {}, {}
        coarse_other = None
        for i, card in enumerate(fr["cards"]):
            rect = card_box(card, self.k)
            here = [(v, b) for b, v in scored if _inside(center(b), rect)]
            if here:
                on_card[i] = max(here)[0]
            coarse = [c["score"] for c in cands if _inside(center(c["box"]), rect)]
            if coarse:
                on_coarse[i] = max(coarse)
            if card["name"] == name:
                if card["soldOut"]:
                    continue
                want = (card["center"][0] + t["offset"][0],
                        card["center"][1] + t["offset"][1])
                near = [(v, b) for b, v in scored if _dist(center(b), want) <= tol]
                best_v, best_b = max(near, default=(None, None))
                own.append({"card": i, "score": best_v,
                            "hit": any(_dist(center(b), want) <= tol for b in matches),
                            "color": colors.get(best_b) if best_b else None})
                continue
            if here:
                v, b = max(here)
                others.append({"card": i, "name": card["name"], "score": v,
                               "color": colors.get(b), "soldOut": card["soldOut"]})
            if coarse and (coarse_other is None or max(coarse) > coarse_other[0]):
                coarse_other = (max(coarse), card["name"])
            false_hits += [{"card": i, "name": card["name"], "soldOut": card["soldOut"]}
                           for b in matches if _inside(center(b), rect)]
        return {"own": own, "has_own": bool(own), "false": false_hits,
                "top_other": max(others, key=lambda o: o["score"], default=None),
                "coarse_other": coarse_other, "on_card": on_card, "on_coarse": on_coarse,
                "ok": all(o["hit"] for o in own) and not false_hits}

    def verdict(self, name, color):
        """('pass' / 'retake' / 'unverified', 原因清單)."""
        if name in self.failed:
            return "retake", [f"引擎無法登錄這張範本（{self.failed[name]}）"]
        why, seen = [], False
        for fr in self.frames:
            res = self.results[name][fr["id"]][color]
            seen |= res["has_own"]
            why += [f"{fr['id']} 第 {o['card'] + 1} 張卡（本尊）沒有匹配"
                    for o in res["own"] if not o["hit"]]
            why += [f"{fr['id']} 第 {f['card'] + 1} 張卡（{f['name']}"
                    f"{'，售完' if f['soldOut'] else ''}）上有匹配" for f in res["false"]]
        if why:
            return "retake", why
        return ("pass" if seen else "unverified"), []

    def margin(self, name):
        """比色關: 「本尊分數 − 最高別種商品分數」在含本尊的畫面上的最小值.

        別種卡上沒有候選過粗篩時別種分數算 0 (兩種框法同一個算法)。
        """
        vals = []
        for fr in self.frames:
            res = self.results.get(name, {}).get(fr["id"], {}).get(False)
            if res is None or not res["has_own"]:
                continue
            own = min((o["score"] or 0.0) for o in res["own"])
            other = res["top_other"]["score"] if res["top_other"] else 0.0
            vals.append(own - other)
        return min(vals) if vals else None


@dataclass
class SetRun:
    """一組範本 (一種框法、一種尺度) 的驗證與判定."""
    label: str
    templates: dict
    ver: Verifier
    files: dict | None = None   # {商品名: 輸出檔名}; 寫出後才有

    def __post_init__(self):
        self.verdicts = {n: {c: self.ver.verdict(n, c) for c in (False, True)}
                         for n in self.templates}

    def verdict_of(self, name, color=False):
        return self.verdicts[name][color][0]

    def names_with(self, verdict, color=False):
        return [n for n in self.templates if self.verdict_of(n, color) == verdict]

    def min_margin(self):
        ms = [m for m in map(self.ver.margin, self.templates) if m is not None]
        return min(ms) if ms else None


# ---------------------------------------------------------------- 輸出

def write_set(run, dest):
    """清空輸出資料夾後依判定命名寫出 PNG (`待重拍_` 前綴只看比色關)."""
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    run.files = {}
    for name, t in run.templates.items():
        fn = PREFIX + name + ".png"
        if run.verdict_of(name) == "retake":
            fn = RETAKE + fn
        write(os.path.join(dest, fn), t["img"])
        run.files[name] = fn


def overlay(fr, templates, k, path):
    """核對圖: 卡片範圍 (綠＝未售完、紅＝售完)、圓圈中心、範本預期位置、商品代號."""
    img = fr["img"].copy()
    for card in fr["cards"]:
        x0, y0, x1, y1 = (round(v) for v in card_box(card, k))
        col = (0, 0, 255) if card["soldOut"] else (0, 180, 0)
        cv2.rectangle(img, (x0, y0), (x1, y1), col, 2)
        cx, cy = card["center"]
        cv2.circle(img, (round(cx), round(cy)), 4, col, -1)
        code = next((c for n, c, *_ in ITEMS if n == card["name"]),
                    OTHER_CODES.get(card["name"], "?"))
        label = code + (" SOLD" if card["soldOut"] else "")
        for color, thick in (((255, 255, 255), 4), (col, 2)):   # 白邊 + 本色
            cv2.putText(img, label, (x0 + 6, y0 + 40), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, color, thick)
        t = templates.get(card["name"])
        if t is not None:
            h, w = t["img"].shape[:2]
            ex, ey = cx + t["offset"][0] - w / 2, cy + t["offset"][1] - h / 2
            cv2.rectangle(img, (round(ex), round(ey)), (round(ex + w), round(ey + h)),
                          (255, 128, 0), 1)
    write(path, img)


def overlays(frames, templates_by_set, scales):
    k = {"tw": 1.0, "cn": scales.grid_ratio}
    for fr in frames:
        overlay(fr, templates_by_set[fr["set"]], k[fr["set"]],
                os.path.join(HERE, "overlays", fr["id"] + ".png"))


def template_sheet(sets, path):
    """各組範本並排的核對圖 (每列一種商品)."""
    rows = []
    for name, code, *_ in ITEMS:
        tiles = []
        for label, temps in sets:
            if name in temps:
                im = temps[name]["img"]
                pad = np.full((180, 200, 3), 255, np.uint8)
                pad[20:20 + im.shape[0], 10:10 + im.shape[1]] = im
                cv2.putText(pad, f"{code} {label}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX,
                            0.4, (0, 0, 0), 1)
                tiles.append(pad)
        if tiles:
            rows.append(np.hstack(tiles))
    width = max(r.shape[1] for r in rows)
    rows = [np.hstack([r, np.full((r.shape[0], width - r.shape[1], 3), 255, np.uint8)])
            for r in rows]
    write(path, np.vstack(rows))


# ---------------------------------------------------------------- 報告

V_LABEL = {"pass": "通過", "retake": "待重拍", "unverified": "未驗證"}


def _fmt(v):
    return "—" if v is None else f"{v:.3f}"


def _own_cell(res, color):
    if not res["has_own"]:
        return "（無本尊）"
    parts = []
    for o in res["own"]:
        s = _fmt(o["score"])
        if color and o["color"] is not None:
            s += f"／色 {o['color']:.3f}"
        parts.append(s + ("" if o["hit"] else " ✗"))
    return "、".join(parts)


def _other_cell(res, color):
    o = res["top_other"]
    if o is None:
        c = res["coarse_other"]
        return "—" if c is None else f"—（粗篩 {c[0]:.3f} {c[1]}）"
    s = f"{o['score']:.3f} {o['name']}{'（售完）' if o['soldOut'] else ''}"
    if color and o["color"] is not None:
        s += f"／色 {o['color']:.3f}"
    if res["false"]:
        names = "、".join(dict.fromkeys(f["name"] for f in res["false"]))
        s += f" ⚠ 匹配落在 {names}"
    return s


def score_table(lines, title, run):
    """每張範本在每張畫面上的本尊分數與最高別種分數 (比色關/開並列)."""
    lines += [f"### {title}：每張範本在每張畫面上的分數", "",
              "分數是引擎深度驗證的分數；門檻見開頭。本尊分數列出畫面上每張"
              "未售完的本尊卡（✗＝那張卡上沒有匹配）；最高別種是落在其他商品卡（含售完卡）"
              "上的最高分候選，⚠＝它過了門檻成為匹配；別種卡上沒有候選過粗篩時"
              "只有粗篩分數，寫成「—（粗篩 分數 名稱）」，差距計算時視為 0。"
              "比色開另附比色分數。", "",
              "| 範本 | 畫面 | 本尊（比色關） | 最高別種（比色關） | 本尊（比色開） | 最高別種（比色開） |",
              "|---|---|---|---|---|---|"]
    ver = run.ver
    for name in run.templates:
        if name in ver.failed:
            lines.append(f"| {name} | — | 引擎無法登錄 | | | |")
            continue
        for fr in ver.frames:
            r = ver.results[name][fr["id"]]
            lines.append(f"| {name} | {fr['id']} | {_own_cell(r[False], False)} | "
                         f"{_other_cell(r[False], False)} | {_own_cell(r[True], True)} | "
                         f"{_other_cell(r[True], True)} |")
    lines.append("")


def verdict_table(lines, title, run):
    lines += [f"### {title}：判定", "",
              "| 範本 | 檔名 | 比色關 | 比色開 | 未過原因 |", "|---|---|---|---|---|"]
    for name in run.templates:
        (off, off_why), (on, on_why) = run.verdicts[name][False], run.verdicts[name][True]
        why = "；".join(dict.fromkeys(off_why + [w + "（比色開）" for w in on_why
                                                 if w not in off_why]))
        lines.append(f"| {name} | {run.files.get(name, '')} | {V_LABEL[off]} | "
                     f"{V_LABEL[on]} | {why} |")
    lines.append("")
    for v in V_LABEL:
        names = run.names_with(v)
        lines.append(f"- **{V_LABEL[v]}**（比色關，{len(names)} 張）："
                     f"{'、'.join(names) if names else '無'}")
    on_diff = [n for n in run.templates if run.verdict_of(n, True) != run.verdict_of(n)]
    if on_diff:
        lines.append("- 比色開的判定不同：" + "、".join(
            f"{n}（{V_LABEL[run.verdict_of(n, True)]}）" for n in on_diff))
    lines.append("")


def _source_key(fr):
    return fr["source"].get("pic") or fr["source"]["video"]


def video_quality(frames):
    """各素材影片的位元率 (檔案大小 ÷ 長度), 判斷壓縮失真用."""
    out = {}
    for fr in frames:
        v = fr["source"].get("video")
        if v is None or v in out:
            continue
        path = os.path.join(SRC, v + ".mp4")
        cap = cv2.VideoCapture(path)
        secs = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        size = os.path.getsize(path)
        out[v] = (size / 1e6, secs, size * 8 / secs / 1e6)
    return out


def _by_source(groups):
    return "、".join(f"{k}（{len(v)} 幀）" for k, v in groups.items()) or "無"


def failure_sources(lines, title, run):
    """待重拍的範本: 沒過與通過的畫面各來自哪個素材 (看失敗是否集中在某支影片)."""
    rows = []
    for name in run.names_with("retake"):
        if name in run.ver.failed:
            continue
        bad, good = {}, {}
        for fr in run.ver.frames:
            res = run.ver.results[name][fr["id"]][False]
            if res["has_own"] or res["false"]:
                (good if res["ok"] else bad).setdefault(_source_key(fr), []).append(fr["id"])
        rows.append(f"| {name} | {_by_source(bad)} | {_by_source(good)} |")
    if not rows:
        return
    lines += [f"### {title}：待重拍的失敗來源", "",
              "| 範本 | 沒過的畫面 | 本尊卡有匹配、也沒誤認的畫面 |", "|---|---|---|"] + rows
    q = video_quality(run.ver.frames)
    if q:
        lines += ["", "素材影片的位元率（壓縮越重，影格越糊，分數越低）：", "",
                  "| 影片 | 大小 | 長度 | 位元率 |", "|---|---|---|---|"]
        lines += [f"| {v} | {mb:.0f} MB | {s:.0f} 秒 | {br:.1f} Mbps |"
                  for v, (mb, s, br) in q.items()]
    lines.append("")


SERIES = [("源岩", "固源岩"), ("代糖", "糖"), ("酯原料", "聚酸酯"), ("異鐵碎片", "異鐵"),
          ("雙酮", "酮凝集"), ("破損裝置", "裝置"), ("碳", "碳素"), ("碳", "碳素組"),
          ("碳素", "碳素組"), ("招聘許可", "加急許可"), ("基礎作戰記錄", "初級作戰記錄"),
          ("技巧概要·卷1", "技巧概要·卷2")]


def cross_table(lines, title, run):
    """同系列不同階: A 範本在 B 卡上、B 範本在 A 卡上的最高分."""
    ver = run.ver
    lines += [f"### {title}：同系列不同階互相認錯的檢查", "",
              "每一對列出「A 範本在 B 卡上」與「B 範本在 A 卡上」所有畫面的最高深度驗證分數"
              "（比色關；沒有候選過粗篩時列粗篩最高分）。深度驗證分數過門檻＝認錯。", "",
              "| A | B | A 範本在 B 卡 | B 範本在 A 卡 |", "|---|---|---|---|"]

    def best(tpl, card_name):
        if tpl in ver.failed:
            return "（無法登錄）"
        vals, coarse, seen = [], [], False
        for fr in ver.frames:
            res = ver.results[tpl][fr["id"]][False]
            idxs = {i for i, c in enumerate(fr["cards"]) if c["name"] == card_name}
            seen |= bool(idxs)
            vals += [s for i, s in res["on_card"].items() if i in idxs]
            coarse += [s for i, s in res["on_coarse"].items() if i in idxs]
        if not seen:
            return "—（畫面上沒有）"
        if not vals:
            return f"—（粗篩最高 {max(coarse):.3f}）" if coarse else "—（沒有候選）"
        v = max(vals)
        return f"{v:.3f}" + (" ⚠ 過門檻" if v >= ver.verify_threshold else "")

    for a, b in SERIES:
        if a in run.templates and b in run.templates:
            lines.append(f"| {a} | {b} | {best(a, b)} | {best(b, a)} |")
    lines.append("")


def _frame_source(fr):
    s = fr["source"]
    return s["pic"] if "pic" in s else f"{s['video']} 第 {s['frame']} 幀（{s['frame'] / 20:.1f} 秒）"


def _counts(run):
    parts = []
    for v in V_LABEL:
        names = run.names_with(v)
        parts.append(f"{V_LABEL[v]} {len(names)}" + (f"（{'、'.join(names)}）" if names else ""))
    return "；".join(parts)


def build_report(config, tw_runs, chosen, cn_run, scales):
    tw_run = tw_runs[chosen]
    frames = tw_run.ver.frames + cn_run.ver.frames
    lines = ["# 採購中心範本：交付報告", "",
             "由 `.scratch/credit-store-templates/build.py` 產生（重跑會清空 `繁中\\`、`簡中\\` "
             "並重寫本報告）。規格見同資料夾的 `spec.md`。", "",
             "## 摘要", "",
             f"- 框法：**{FRAMINGS[chosen]['label']}**（比較見「框法比較」）。",
             f"- 簡中倍率：倉庫圖示 × {scales.cn_scale:.4f}。",
             f"- 繁中：{_counts(tw_run)}。",
             f"- 簡中：{_counts(cn_run)}。",
             "", "## 驗證方式", "",
             f"- 引擎公開 API：逐張登錄 → 以整張驗證畫面查詢、預期尺度 1。門檻用 arknights profile："
             f"匹配門檻（粗篩 {config['match_threshold']}、深度驗證 {config['verify_threshold']}）、"
             f"比色門檻 {config['color_threshold']}。",
             "- 通過＝畫面上每張未售完的本尊卡都有匹配落在預期位置附近（位置容許值同影片轉流程："
             "max(6, 範本短邊 × 0.25) px），且沒有任何匹配落在別種商品的卡上（含售完卡）。",
             "- 範本整體：所有含本尊的畫面都通過＝通過；任一畫面不通過或無法登錄＝待重拍；"
             "沒有畫面出現它的未售完卡＝未驗證。沒出現的範本照樣在每張畫面上查，"
             "若落到別種商品卡上同樣判待重拍（測過且失敗）——這是對 spec「未驗證」的詮釋，"
             "讓 `待重拍_` 只代表真的測過而失敗。",
             "- 檔名的 `待重拍_` 前綴只看比色關（找圖目標的預設）。", "",
             "驗證畫面（影格存於 `.scratch/credit-store-templates/frames/`，標註在 `annotations.json`，"
             "疊框核對圖在 `overlays/`）：", ""]
    for fr in frames:
        sold = sum(c["soldOut"] for c in fr["cards"])
        lines.append(f"- `{fr['id']}`：{_frame_source(fr)}，10 張卡、售完 {sold} 張")
    lines += ["", "## 框法比較（繁中）", "",
              "| 框法 | 範本大小（繁中） | 通過（比色關） | 通過（比色開） | 本尊 − 最高別種 的最小值 | |",
              "|---|---|---|---|---|---|"]
    for f, run in tw_runs.items():
        h, w = next(iter(run.templates.values()))["img"].shape[:2]
        lines.append(f"| {FRAMINGS[f]['label']}（{FRAMINGS[f]['note']}） | {w}×{h} | "
                     f"{len(run.names_with('pass'))} | {len(run.names_with('pass', True))} | "
                     f"{_fmt(run.min_margin())} | {'**選中**' if f == chosen else ''} |")
    lines += ["", "判斷順序：通過張數（比色關）多的勝；一樣時比最小差距，大的勝。"
              "未選中框法的逐畫面分數在報告最後的附錄。", "",
              "各範本在兩種框法下的摘要（比色關；本尊取最差的一張、別種取最高的一張）：", "",
              "| 範本 | " + " | ".join(f"{FRAMINGS[f]['label']}：判定／最小差距" for f in tw_runs)
              + " |", "|---|" + "---|" * len(tw_runs)]
    for name in tw_run.templates:
        cells = [f"{V_LABEL[run.verdict_of(name)]}／{_fmt(run.ver.margin(name))}"
                 for run in tw_runs.values()]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "## 尺度", "",
              f"- 繁中：倉庫圖示 × {TW_SCALE}（spec 實測：商店黃圈直徑 151.2、倉庫 155.2）。"
              f"本腳本同一量法核對：倉庫 {scales.d_warehouse:.1f} px、繁中商店 {scales.d_tw:.1f} px，"
              f"比 {scales.d_tw / scales.d_warehouse:.4f}。",
              f"- 簡中：倉庫圖示 × {scales.cn_scale:.4f}（＝ {TW_SCALE} × 簡中/繁中 "
              f"{scales.cn_over_tw:.4f}）。",
              f"  - 例外：{'、'.join(CN_SOURCES)} 有簡中客戶端的倉庫圖"
              f"（{'、'.join(sorted({p for p, _c in CN_SOURCES.values()}))}），簡中範本直接從它切："
              f"簡中倉庫 × {TW_SCALE}（同一客戶端內倉庫→商店的比例），不經繁中倉庫圖縮放。"
              f"簡中倉庫相對繁中倉庫的尺度取簡中/繁中 {scales.cn_over_tw:.4f}"
              "（pic7 與 pic8 的格距比 170.9/192 ≈ 0.89 吻合）。",
              "  - 量法：在每張驗證畫面上、未售完的黃綠圈二階材料卡（"
              + "、".join(sorted(RING_ITEMS)) + "）沿放射線找彩色外環的外緣（右下數字框象限不量），"
              "取各方向中位數為半徑；兩組各取所有卡的中位數相比。",
              f"  - 繁中商店直徑中位數 {scales.d_tw:.1f} px（{len(scales.per_card['tw'])} 張卡）、"
              f"簡中商店 {scales.d_cn:.1f} px（{len(scales.per_card['cn'])} 張卡）。",
              f"  - 核對：卡片格距比 {GRID['cn'][0]} / {GRID['tw'][0]} = {scales.grid_ratio:.4f}。",
              "  - 各卡量值：" + "；".join(f"{i} {n} {d:.1f}" for i, n, d in scales.per_card["cn"]),
              ""]
    for title, run in (("繁中", tw_run), ("簡中", cn_run)):
        lines += [f"## {title}", ""]
        score_table(lines, title, run)
        verdict_table(lines, title, run)
        failure_sources(lines, title, run)
        cross_table(lines, title, run)
    lines += ["## 這次沒做的商品", "",
              "採購中心會賣、但倉庫素材圖裡沒有的商品（之後補截倉庫圖示再重跑）：", ""]
    lines += [f"- {n}" for n in NOT_MADE]
    lines += ["- 其他偶爾上架的商品", "",
              "傢俱零件：使用者決定不判斷，不做範本。", ""]
    for f, run in tw_runs.items():
        if f != chosen:
            lines += [f"## 附錄：未選中的框法（{FRAMINGS[f]['label']}）", ""]
            score_table(lines, f"繁中・{FRAMINGS[f]['label']}", run)
    return lines


# ---------------------------------------------------------------- 主程式

def load_frames(set_keys):
    with open(os.path.join(HERE, "annotations.json"), encoding="utf-8") as f:
        ann = json.load(f)
    frames = [fr for fr in ann["frames"] if fr["set"] in set_keys]
    for fr in frames:
        fr["img"] = read(os.path.join(HERE, "frames", fr["id"] + ".png"))
    return frames


def make_engine():
    engine = vtf_verify.make_engine()
    if engine.coarse_only:
        raise SystemExit("深度驗證模型載不起來 (coarse-only): 驗證結果不等於實際執行, 中止")
    return engine


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", nargs="*", help="只跑這幾種 (輸出到 preview/, 不動正式輸出)")
    ap.add_argument("--overlays", action="store_true", help="只畫核對圖")
    args = ap.parse_args(argv)

    from subject_detection.library import load_config

    names = set(args.items) if args.items else {n for n, *_ in ITEMS}
    unknown = names - {n for n, *_ in ITEMS}
    if unknown:
        raise SystemExit(f"不認得的商品: {'、'.join(unknown)}")
    pics = {p for *_, p, _c in ITEMS} | {p for p, _c in CN_SOURCES.values()}
    sources = {p: read(os.path.join(SRC, p + ".png")) for p in sorted(pics)}
    frames = load_frames({"tw", "cn"})
    tw_frames = [fr for fr in frames if fr["set"] == "tw"]
    cn_frames = [fr for fr in frames if fr["set"] == "cn"]

    scales = measure_scales(frames, sources)
    print(f"圓圈直徑中位數: 繁中商店 {scales.d_tw:.1f}、簡中商店 {scales.d_cn:.1f} → "
          f"簡中/繁中 {scales.cn_over_tw:.4f} (格距比 {scales.grid_ratio:.4f}); "
          f"倉庫 {scales.d_warehouse:.1f}")

    tw_sets = {fw: cut_all(sources, names, fw, TW_SCALE) for fw in FRAMINGS}
    cn_sets = {fw: cut_all(sources, names, fw, scales.cn_scale, scales.cn_over_tw)
               for fw in FRAMINGS}
    os.makedirs(os.path.join(HERE, "overlays"), exist_ok=True)
    template_sheet([(f"tw-{fw}", tw_sets[fw]) for fw in FRAMINGS]
                   + [(f"cn-{fw}", cn_sets[fw]) for fw in FRAMINGS],
                   os.path.join(HERE, "overlays", "templates.png"))
    if args.overlays:
        overlays(frames, {"tw": tw_sets["inner"], "cn": cn_sets["inner"]}, scales)
        return 0

    engine = make_engine()
    config = load_config(PROFILE)

    # 繁中: 兩種框法都驗, 依通過張數 → 最小差距定案
    tw_runs = {}
    for fw in FRAMINGS:
        print(f"繁中 {FRAMINGS[fw]['label']} 驗證中…", flush=True)
        tw_runs[fw] = SetRun("繁中", tw_sets[fw],
                             Verifier(engine, config, tw_sets[fw], tw_frames, 1.0))

    def rank(fw):
        m = tw_runs[fw].min_margin()
        return len(tw_runs[fw].names_with("pass")), float("-inf") if m is None else m

    chosen = max(FRAMINGS, key=rank)
    print("框法:", {fw: rank(fw) for fw in FRAMINGS}, "→", chosen)

    print(f"簡中 (×{scales.cn_scale:.4f}) 驗證中…", flush=True)
    cn_run = SetRun("簡中", cn_sets[chosen],
                    Verifier(engine, config, cn_sets[chosen], cn_frames, scales.grid_ratio))

    base = os.path.join(HERE, "preview") if args.items else OUT
    write_set(tw_runs[chosen], os.path.join(base, "繁中"))
    write_set(cn_run, os.path.join(base, "簡中"))
    overlays(frames, {"tw": tw_sets[chosen], "cn": cn_sets[chosen]}, scales)

    lines = build_report(config, tw_runs, chosen, cn_run, scales)
    with open(os.path.join(base, "報告.md"), "w", encoding="utf-8") as out:
        out.write("\n".join(lines))
    for run in (tw_runs[chosen], cn_run):
        print(run.label, {V_LABEL[v]: len(run.names_with(v)) for v in V_LABEL})
    print("輸出:", base)
    return 0


if __name__ == "__main__":
    sys.exit(main())

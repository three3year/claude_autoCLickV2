"""票 09: 挑主校準對——從主畫面影格裁兩張遊戲內固定圖, 以拾取檢查驗唯一與縮放餘裕, 看五個倍率的中心抖動.

    .venv/Scripts/python .scratch/scale-range/pick_pair.py

產物: templates/<lang>/<名>.png、results/pick_pair.json。
"""
from __future__ import annotations

import os
import shutil
import tempfile

import srcommon as sr
from srcommon import bp

from automation import findtarget, pickcheck  # noqa: E402

# 候選 (影片座標的框): 設定齒輪 (左上) × 倉庫圖示 (右下), 兩版都是主畫面固定元件
PAIRS = {
    "tw": {"names": ("主畫面設定鈕", "主畫面倉庫"),
           "boxes": {"主畫面設定鈕": (30, 58, 60, 56), "主畫面倉庫": (1770, 858, 100, 104)}},
    "cn": {"names": ("主画面设置钮", "主画面仓库"),
           "boxes": {"主画面设置钮": (24, 52, 58, 56), "主画面仓库": (1578, 756, 76, 82)}},
}


def crop_templates(lang):
    video, n = sr.LANGS[lang]["menu"]
    img = sr.frame(video, n)
    d = os.path.join(sr.TEMPLATES, lang)
    os.makedirs(d, exist_ok=True)
    out = {}
    for name, box in PAIRS[lang]["boxes"].items():
        c = sr.crop(img, box)
        bp.write_img(os.path.join(d, name + ".png"), c)
        out[name] = bp.encode(c)
    return out, img


def check(lang):
    names = list(PAIRS[lang]["names"])
    images, img = crop_templates(lang)
    flow = sr.read_flow(sr.LANGS[lang]["evening"])
    region = flow["data"]["scanRegion"]
    canvas, org = sr.place(lang, region)(img)
    tmp = tempfile.mkdtemp(prefix="sr_pair_")
    res = {"names": names, "boxes": PAIRS[lang]["boxes"], "menu": sr.LANGS[lang]["menu"],
           "region": region, "checks": {}, "jitter": {}, "ok": True}
    try:
        hub = bp.make_hub(images, names, tmp)
        # 拾取檢查: 唯一 + 縮放餘裕 (×1 畫布上以倍率 1 查; 縮放餘裕內部再縮 0.85/1.15)
        for name in names:
            warns = pickcheck.check(hub, canvas, org, {"template": name}, anchor=None,
                                    scale=1.0, kinds=(pickcheck.SCALE, pickcheck.UNIQUE))
            res["checks"][name] = [str(w) for w in warns]
            if warns:
                res["ok"] = False
        # 五個倍率的中心抖動: 縮放後找到的中心 ÷ s 與 ×1 的中心差幾 px
        for name in names:
            base = None
            rows = []
            for s in sr.SCALES:
                f = sr.find_scaled(hub, {"template": name}, canvas, org, None, s)
                if f.picked is None:
                    rows.append({"scale": s, "found": False})
                    res["ok"] = False
                    continue
                c = sr.center(f.picked.box)
                c1 = (c[0] / s, c[1] / s)
                if s == 1.0:
                    base = c1
                rows.append({"scale": s, "found": True, "center": c, "center_x1": c1,
                             "score": round(float(f.picked.score), 3),
                             "matches": len(f.matches)})
            for r in rows:
                if r.get("found") and base is not None:
                    r["jitter"] = round(max(abs(r["center_x1"][0] - base[0]),
                                            abs(r["center_x1"][1] - base[1])), 1)
                    if r["jitter"] > 3:
                        res["ok"] = False
            res["jitter"][name] = rows
        # 距離 (螢幕座標, 倍率 1) ＝ 新基準距離
        f1 = sr.find_scaled(hub, {"template": names[0]}, canvas, org, None, 1.0)
        f2 = sr.find_scaled(hub, {"template": names[1]}, canvas, org, None, 1.0)
        if f1.picked and f2.picked:
            (x1, y1), (x2, y2) = sr.center(f1.picked.box), sr.center(f2.picked.box)
            res["centers"] = [(x1, y1), (x2, y2)]
            res["distance"] = round(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return res


def main():
    out = {}
    for lang in ("tw", "cn"):
        out[lang] = check(lang)
        r = out[lang]
        print(f"[{lang}] ok={r['ok']} distance={r.get('distance')} centers={r.get('centers')}")
        for name, ws in r["checks"].items():
            print(f"   {name}: {'通過' if not ws else ws}")
        for name, rows in r["jitter"].items():
            print(f"   {name}: " + ", ".join(
                f"×{x['scale']}:{'找不到' if not x.get('found') else str(x.get('jitter', 0)) + 'px/' + str(x['score']) + '/' + str(x['matches']) + '個'}"
                for x in rows))
    sr.dump(os.path.join(sr.RESULTS, "pick_pair.json"), out)


if __name__ == "__main__":
    main()

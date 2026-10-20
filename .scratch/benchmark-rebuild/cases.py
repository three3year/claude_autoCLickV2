"""候選案例: 寫成案例資料夾 (新格式)、卡片頁、agent 審核用的拼圖。

一個候選 (dict):
  name        案例資料夾名
  kind        案例類型 (一般正例、易誤判負樣本、同款多個、比色、忙碌指示、線索背景、混淆、縮放、跨影片)
  lang, flow, template, video, frame    來源
  template_video   (跨影片) 範本取材的影片
  expected    present | absent
  boxes       答案框 [(x, y, w, h)] (畫面座標, 已套用縮放); present 至少一個
  multi       True＝centers (同款多個要全中且不能多); 否則 center
  color_check, expected_scale, tolerance
  scene       畫面 (BGR)
  tpl         範本圖 (BGR); tpl_path 有給就直接複製那個檔
  doubt       agent 有疑問的原因 (None＝沒疑問)
  note        卡片上給人看的一句說明
"""
from __future__ import annotations

import html
import os
import shutil

import cv2
import numpy as np
import yaml

import bcommon as bc

KIND_ORDER = ["一般正例", "易誤判負樣本", "同款多個", "比色", "忙碌指示", "線索背景",
              "混淆", "縮放", "跨影片"]
CLIENT = {"cn": "簡中", "tw": "繁中"}


def expect_of(c):
    e = {"expected": c["expected"]}
    if c["expected"] == "present":
        cs = [[int(round(v)) for v in bc.center(b)] for b in c["boxes"]]
        if c.get("multi"):
            e["centers"] = cs
        else:
            e["center"] = cs[0]
    e["tolerance"] = int(c.get("tolerance", 15))
    if c.get("color_check"):
        e["color_check"] = True
    if c.get("expected_scale", 1.0) != 1.0:
        e["expected_scale"] = float(c["expected_scale"])
    src = {"flow": c["flow"], "template": c["template"], "video": c["video"],
           "frame": int(c["frame"]) if c.get("frame") is not None else None,
           "kind": c["kind"], "client": CLIENT[c["lang"]]}
    if c.get("template_video"):
        src["template_video"] = c["template_video"]
    if c.get("origin"):
        src["answer_from"] = c["origin"]
    e["source"] = src
    return e


def write_case(c, root=None):
    root = root or bc.CANDIDATES
    d = os.path.join(root, c["name"])
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    bc.imwrite(os.path.join(d, "screenshot.png"), c["scene"])
    if c.get("tpl_path"):
        shutil.copyfile(c["tpl_path"], os.path.join(d, "template.png"))
    else:
        bc.imwrite(os.path.join(d, "template.png"), c["tpl"])
    with open(os.path.join(d, "expect.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(expect_of(c), f, allow_unicode=True, sort_keys=False)
    return d


# ---------------------------------------------------------------- 圖

def _fit(img, w):
    s = w / img.shape[1]
    return cv2.resize(img, (w, max(1, round(img.shape[0] * s))),
                      interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_NEAREST), s


def annotated(c, width=900):
    """縮到 width 寬的畫面, present 畫紅框 (同款多個每個都畫)."""
    img, s = _fit(c["scene"], width)
    if c.get("lookalike") is not None:
        x, y, w, h = c["lookalike"]
        cv2.rectangle(img, (int(x * s) - 2, int(y * s) - 2),
                      (int((x + w) * s) + 2, int((y + h) * s) + 2), (0, 200, 255), 1)
    if c["expected"] == "present":
        for x, y, w, h in c["boxes"]:
            cv2.rectangle(img, (int(x * s) - 2, int(y * s) - 2),
                          (int((x + w) * s) + 2, int((y + h) * s) + 2), (0, 0, 255), 2)
    return img


def zoom_crop(c, size=220):
    """答案框 (第一個) 附近放大: 紅框對到哪裡一眼看得到; absent 回 None."""
    if c["expected"] == "present":
        box, color = c["boxes"][0], (0, 0, 255)
    elif c.get("lookalike") is not None:
        box, color = c["lookalike"], (0, 200, 255)
    else:
        return None
    x, y, w, h = box
    m = max(w, h) // 2 + 10
    H, W = c["scene"].shape[:2]
    x0, y0 = max(0, x - m), max(0, y - m)
    x1, y1 = min(W, x + w + m), min(H, y + h + m)
    crop = c["scene"][y0:y1, x0:x1].copy()
    cv2.rectangle(crop, (x - x0 - 1, y - y0 - 1), (x - x0 + w, y - y0 + h), color, 1)
    s = size / max(crop.shape[:2])
    return cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)


def tpl_view(c, size=220):
    t = c["tpl"]
    s = min(size / max(t.shape[:2]), 4.0)
    return cv2.resize(t, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)


# ---------------------------------------------------------------- 卡片頁

def order(cands):
    """有疑問的排前面, 其餘照類型、名字."""
    return sorted(cands, key=lambda c: (c.get("doubt") is None,
                                        KIND_ORDER.index(c["kind"]), c["name"]))


def card_page(cands, path, title="基準集候選案例"):
    """本機 HTML 卡片頁 (圖檔放旁邊的 cards/, 不上傳). 回傳 [(編號, 候選)]."""
    out_dir = os.path.dirname(path)
    img_dir = os.path.join(out_dir, "cards")
    if os.path.isdir(img_dir):
        shutil.rmtree(img_dir)
    os.makedirs(img_dir)
    numbered = list(enumerate(order(cands), 1))
    counts = {}
    for _, c in numbered:
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
    rows = []
    for no, c in numbered:
        base = f"{no:03d}"
        bc.imwrite(os.path.join(img_dir, base + "_scene.jpg"), annotated(c))
        bc.imwrite(os.path.join(img_dir, base + "_tpl.png"), tpl_view(c))
        z = zoom_crop(c)
        if z is not None:
            bc.imwrite(os.path.join(img_dir, base + "_zoom.png"), z)
        e = expect_of(c)
        src = e["source"]
        where = f"{src['client']} · {src['flow']} · {src['video']} 第 {src['frame']} 幀"
        if src.get("template_video"):
            where += f" · 範本取自 {src['template_video']}"
        if c["expected"] == "present":
            n = len(c["boxes"])
            verdict = f"應該找到{f' {n} 個（全部都要、不能多）' if c.get('multi') else ''}"
        else:
            verdict = "應該沒有"
        tags = []
        if c.get("color_check"):
            tags.append("開比色")
        if c.get("expected_scale", 1.0) != 1.0:
            tags.append(f"縮放 ×{c['expected_scale']}")
        doubt = (f'<p class="doubt">agent 有疑問：{html.escape(c["doubt"])}</p>'
                 if c.get("doubt") else "")
        note = f'<p class="note">{html.escape(c["note"])}</p>' if c.get("note") else ""
        zcap = "答案框放大" if c["expected"] == "present" else "畫面上最像的地方（黃框，不是答案）"
        zoom = (f'<figure><img src="cards/{base}_zoom.png"><figcaption>{zcap}</figcaption></figure>'
                if z is not None else "")
        rows.append(f"""
<section class="card {'neg' if c['expected'] == 'absent' else 'pos'}{' has-doubt' if c.get('doubt') else ''}" id="c{no}">
  <header><span class="no">#{no}</span> <span class="kind">{html.escape(c['kind'])}</span>
    <span class="verdict {'neg' if c['expected'] == 'absent' else 'pos'}">{verdict}</span>
    {''.join(f'<span class="tag">{t}</span>' for t in tags)}
    <span class="tpl-name">範本：{html.escape(c['template'])}</span></header>
  {doubt}{note}
  <div class="row">
    <figure><img src="cards/{base}_tpl.png"><figcaption>範本</figcaption></figure>
    {zoom}
  </div>
  <img class="scene" src="cards/{base}_scene.jpg">
  <p class="src">{html.escape(where)} · {html.escape(c['name'])}</p>
</section>""")
    summary = "、".join(f"{k} {counts[k]}" for k in KIND_ORDER if k in counts)
    n_doubt = sum(1 for _, c in numbered if c.get("doubt"))
    page = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --bg:#f6f6f4; --card:#fff; --ink:#1d1d1f; --muted:#666; --line:#ddd;
  --doubt:#b45309; --doubt-bg:#fff7e6; --pos:#0a7d32; --neg:#b42318;
  --pos-bg:#e6f6ea; --neg-bg:#fdeaea; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#18181a; --card:#232326; --ink:#eee;
  --muted:#aaa; --line:#3a3a3d; --doubt:#f5a524; --doubt-bg:#3a2d12; --pos:#4ade80; --neg:#f87171;
  --pos-bg:#16301f; --neg-bg:#3a1a1a; }} }}
body {{ background:var(--bg); color:var(--ink); font:15px/1.5 system-ui, "Microsoft JhengHei", sans-serif;
  margin:0 auto; max-width:960px; padding:16px; }}
h1 {{ font-size:22px; margin:8px 0; }}
.intro {{ color:var(--muted); }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:8px;
  padding:12px 14px; margin:14px 0; }}
.card.pos {{ background:var(--pos-bg); }}
.card.neg {{ background:var(--neg-bg); }}
.card.has-doubt {{ border-color:var(--doubt); border-width:3px; }}
header {{ display:flex; flex-wrap:wrap; gap:8px; align-items:baseline; }}
.no {{ font-weight:700; font-size:20px; }}
.kind {{ font-weight:600; }}
.verdict.pos {{ color:var(--pos); font-weight:600; }}
.verdict.neg {{ color:var(--neg); font-weight:600; }}
.tag {{ border:1px solid var(--line); border-radius:4px; padding:0 6px; font-size:13px; }}
.tpl-name {{ color:var(--muted); }}
.doubt {{ background:var(--doubt-bg); color:var(--doubt); padding:4px 8px; border-radius:4px; margin:6px 0; }}
.note {{ margin:6px 0; }}
.row {{ display:flex; gap:16px; flex-wrap:wrap; margin:8px 0; }}
figure {{ margin:0; }}
figcaption {{ color:var(--muted); font-size:13px; }}
img {{ max-width:100%; image-rendering:pixelated; }}
img.scene {{ width:100%; image-rendering:auto; border:1px solid var(--line); }}
.src {{ color:var(--muted); font-size:13px; margin:4px 0 0; word-break:break-all; }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="intro">共 {len(numbered)} 張：{summary}。agent 有疑問的 {n_doubt} 張排在最前面（橘框）。
綠底＝應該找到（紅框＝答案），紅底＝應該沒有（不畫框，請確認畫面裡真的沒有那張範本）。看完把<strong>錯的編號</strong>回報就好。</p>
{''.join(rows)}
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return numbered


def review_sheets(numbered, out_dir, per=4):
    """agent 審核用的拼圖: 每張 per 個案例 (範本、放大、縮小的畫面)."""
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, f))
    paths = []
    for i in range(0, len(numbered), per):
        tiles = []
        for no, c in numbered[i:i + per]:
            scene = annotated(c, 760)
            t = tpl_view(c, 160)
            z = zoom_crop(c, 200)
            left_h = t.shape[0] + (z.shape[0] + 10 if z is not None else 0) + 30
            h = max(scene.shape[0], left_h) + 30
            tile = np.full((h, 980, 3), 255, np.uint8)
            tile[30:30 + t.shape[0], 0:t.shape[1]] = t
            if z is not None:
                y = 40 + t.shape[0]
                tile[y:y + z.shape[0], 0:z.shape[1]] = z
            tile[30:30 + scene.shape[0], 215:215 + scene.shape[1]] = scene
            label = f"#{no} {c['expected']}{' multi' if c.get('multi') else ''}" \
                    f"{' color' if c.get('color_check') else ''}" \
                    f"{' x' + str(c['expected_scale']) if c.get('expected_scale', 1) != 1 else ''}"
            cv2.putText(tile, label, (4, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 200), 2)
            tiles.append(tile)
        sheet = np.vstack(tiles)
        p = os.path.join(out_dir, f"sheet_{i // per + 1:02d}.jpg")
        bc.imwrite(p, sheet)
        paths.append(p)
    return paths

"""票 02 重放: 晚_簡中改過的框 (新/舊) 套到影格上, 看目標找不找得到。

影格先用 extract.py 抽到 tmp/frames/<影片>/。流程讀本 worktree 的 flows/晚_簡中。
用法: python check02.py <影片> <倍率,倍率,...> [基準點x,y]
沒給基準點時, 在影格裡找`主画面设置钮` (分數最高的那格) 當`座標基準點`。
"""
import os, sys, glob, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "app")); sys.path.insert(0, os.path.join(ROOT, "src"))
import cv2, numpy as np
import applog, enginehub, flowfile
from automation import findtarget

TMP = os.path.join(HERE, "tmp"); os.makedirs(TMP, exist_ok=True)
applog.set_path(os.path.join(TMP, "check02.log"))
FLOW = "晚_簡中"
# 票 02 改動前的框 (calibration-settle 6a9a339)
OLD = {"待辦事項": [-64, 738, 214, 102], "可收获": [85, 732, 220, 108],
       "订单交付": [88, 732, 225, 108], "干员信赖": [84, 732, 228, 108],
       "忙碌指示": [847, 719, 333, 101]}

video = sys.argv[1]
ks = [float(v) for v in sys.argv[2].split(",")]
fixed_anchor = tuple(int(v) for v in sys.argv[3].split(",")) if len(sys.argv) > 3 else None

folder = os.path.join(ROOT, "flows", FLOW)
f = flowfile.read_flow(folder)
imgs = {os.path.splitext(os.path.basename(p))[0]: p
        for p in glob.glob(os.path.join(folder, "templates", "*.png"))}
from subject_detection.library import load_default_config
cfg = load_default_config(); cfg.update(f.get("engine") or {})
hub = enginehub.EngineHub(); hub.load()
assert hub.ready and not hub.coarse_only, hub.error
reg = os.path.join(TMP, "reg_" + FLOW); os.makedirs(reg, exist_ok=True)
hub.bind(imgs, cfg, reg); hub.preload(sorted(imgs))


def changed_targets():
    out, seen = [], set()
    def walk(steps):
        for i, s in enumerate(steps):
            for key, t in findtarget.step_targets(s):
                n = t.get("template")
                if n in OLD and n not in seen:
                    seen.add(n); out.append((i + 1, key, t))
    walk(f["steps"])
    out.append((0, "busy", f["busy"]))
    return out


paths = sorted(glob.glob(os.path.join(TMP, "frames", video, "f*.png")))
frames = {int(os.path.basename(p)[1:-4]): p for p in paths}
def frame(i):
    return cv2.imdecode(np.fromfile(frames[i], np.uint8), cv2.IMREAD_COLOR)

grays = {i: cv2.cvtColor(frame(i), cv2.COLOR_BGR2GRAY) for i in frames}
H, W = next(iter(grays.values())).shape
print(f"{video}: {len(frames)} frames {W}x{H}", flush=True)

tg = changed_targets()
k0 = ks[len(ks) // 2]
tmpl = {t["template"]: cv2.imdecode(np.fromfile(imgs[t["template"]], np.uint8), 0) for _, _, t in tg}
tmpl["主画面设置钮"] = cv2.imdecode(np.fromfile(imgs["主画面设置钮"], np.uint8), 0)


def ncc_top(name, n):
    tw = cv2.resize(tmpl[name], None, fx=k0, fy=k0, interpolation=cv2.INTER_AREA)
    rows = []
    for i, g in grays.items():
        _, mv, _, ml = cv2.minMaxLoc(cv2.matchTemplate(g, tw, cv2.TM_CCOEFF_NORMED))
        rows.append((float(mv), i, ml))
    rows.sort(reverse=True)
    picked = []
    for r in rows:   # 隔開至少 20 格, 取不同時段
        if all(abs(r[1] - p[1]) >= 20 for p in picked):
            picked.append(r)
        if len(picked) == n:
            break
    return picked


if fixed_anchor:
    anchor = fixed_anchor
else:
    sc, fi, _ = ncc_top("主画面设置钮", 1)[0]
    r = hub.query("主画面设置钮", frame(fi), expected_scale=k0)
    m = max(r.matches, key=lambda m: m.score)
    anchor = (m.box[0] + m.box[2] // 2, m.box[1] + m.box[3] // 2)
    print(f"anchor from f{fi} ncc={sc:.3f} engine={m.score:.3f} -> {anchor}")


def margin(box, lim):
    """目標框到限定矩形各邊的餘裕 (左, 上, 右, 下); 負的＝超出。"""
    x, y, w, h = box; lx, ly, lw, lh = lim
    return (x - lx, y - ly, (lx + lw) - (x + w), (ly + lh) - (y + h))


summary = []
for sn, key, t in tg:
    n = t["template"]
    for sc, fi, _ in ncc_top(n, 3):
        fr = frame(fi)
        wh = hub.query(n, fr, color_check=bool(t.get("color")), expected_scale=k0)
        good = [m for m in wh.matches if m.score >= 0.8]
        if not good:
            print(f"#{sn:<3}{n:6} f{fi:<5} ncc={sc:.3f} 整張找不到 (best={wh.score:.3f}) -> 跳過")
            continue
        for k in ks:
            res = {}
            for tag, within in (("新", t["within"]), ("舊", OLD[n])):
                tt = dict(t, within=within)
                fd = findtarget.find(tt, hub, fr, (0, 0), origin=None, scale=k, anchor=anchor)
                lim = findtarget.limit_rect(tt, (0, 0, W, H), None, k, anchor)
                tgt_box = min(good, key=lambda m: abs(m.box[0] + m.box[2] / 2 - (lim[0] + lim[2] / 2))
                              + abs(m.box[1] + m.box[3] / 2 - (lim[1] + lim[3] / 2))).box
                res[tag] = (fd.picked is not None, lim, margin(tgt_box, lim), tgt_box)
            row = dict(video=video, step=sn, t=n, f=fi, k=k, anchor=anchor,
                       new=res["新"][0], old=res["舊"][0], target=list(res["新"][3]),
                       new_lim=list(res["新"][1]), new_margin=res["新"][2],
                       old_lim=list(res["舊"][1]), old_margin=res["舊"][2])
            summary.append(row)
            print(f"#{sn:<3}{n:6} f{fi:<5} k={k:.3f} target={row['target']} "
                  f"新={'Y' if row['new'] else 'N'} lim={row['new_lim']} 餘裕(左上右下)={row['new_margin']} | "
                  f"舊={'Y' if row['old'] else 'N'} 餘裕={row['old_margin']}", flush=True)

json.dump(summary, open(os.path.join(TMP, f"check02_{video}.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("done")

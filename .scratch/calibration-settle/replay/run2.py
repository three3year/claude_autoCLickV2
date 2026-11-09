from common import *
name = sys.argv[1]
only = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
f, hub, imgs = load(name)
fr0 = frame(0); H, W = fr0.shape[:2]
cal = f["calibration"]
print("jitter:")
for fi in range(0, 101, 10):
    c = calibration.calibrate(hub.query, frame(fi), (0, 0), cal)
    print(f"  f{fi} used={c.used} k={c.scale:.4f} anchor={c.anchor} centers={c.measurement.centers}")
c = calibration.calibrate(hub.query, fr0, (0, 0), cal)
k, anc = c.scale, c.anchor
print("CAL f0", c.used, c.pair, round(k, 4), anc, flush=True)
tg = [x for x in targets(f) if x[2]["template"] in imgs and (only is None or x[2]["template"] in only)]
names = sorted({t["template"] for _, _, t in tg})
tmpl = {n: cv2.imdecode(np.fromfile(imgs[n], np.uint8), cv2.IMREAD_GRAYSCALE) for n in names}
ncc = {n: [] for n in names}
for fi in range(0, 1441, 10):
    g = cv2.cvtColor(frame(fi), cv2.COLOR_BGR2GRAY)
    for n in names:
        tw = cv2.resize(tmpl[n], None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        mm = cv2.matchTemplate(g, tw, cv2.TM_CCOEFF_NORMED)
        _, mv, _, ml = cv2.minMaxLoc(mm)
        ncc[n].append((round(float(mv), 3), fi, ml[0] + tw.shape[1] // 2, ml[1] + tw.shape[0] // 2))
print("ncc done", flush=True)
out = {"cal": [c.used, k, anc], "rows": []}
for (sn, key, t) in tg:
    n = t["template"]
    top = sorted(ncc[n], reverse=True)[:3]
    lim = findtarget.limit_rect(t, (0, 0, W, H), None, k, anc)
    for sc, fi, cx, cy in top:
        fr = frame(fi)
        fd = findtarget.find(t, hub, fr, (0, 0), origin=None, scale=k, anchor=anc)
        r = hub.query(n, fr, color_check=bool(t.get("color")), expected_scale=k)
        row = dict(step=sn, key=key, t=n, within=t.get("within"), limit=lim, f=fi, ncc=[sc, cx, cy],
                   in_found=fd.picked is not None,
                   in_pick=[*fd.picked.box, round(fd.picked.score, 3)] if fd.picked else None,
                   in_best=round(float(fd.query.score), 3) if fd.query is not None else None,
                   in_failed=fd.failed,
                   wh_score=round(float(r.score), 3), wh_failed=r.failed,
                   wh=[[*(int(v) for v in m.box), round(float(m.score), 3)] for m in r.matches][:3])
        out["rows"].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
json.dump(out, open(f"res2_{name}.json", "w", encoding="utf-8"), ensure_ascii=False)
print("done")

from common import *
f = flowfile.read_flow(os.path.join(ROOT, "flows", "晚_簡中"))
d = json.load(open("res2_晚_簡中.json", encoding="utf-8"))
tp = f["template_pos"]; k, anc = 1.1298, (60, 86)
seen = set(); xs = []
for r in d["rows"]:
    if r["t"] in tp and r["in_pick"] and r["t"] not in seen:
        seen.add(r["t"]); b = r["in_pick"]; c = (b[0] + b[2] // 2, b[1] + b[3] // 2)
        p = tp[r["t"]]; e = (anc[0] + p[0] * k, anc[1] + p[1] * k)
        xs.append((r["t"], p, c, round(c[0] - e[0]), round(c[1] - e[1]), round((c[0]-anc[0])/p[0],3) if p[0] else None, round((c[1]-anc[1])/p[1],3) if p[1] else None))
for x in xs: print(x)
# true scale via ncc multiscale
for n in ["无人机加速", "收取", "进驻总览", "干员休整", "基建图标"]:
    r = next(r for r in d["rows"] if r["t"] == n and r["in_pick"])
    g = cv2.cvtColor(frame(r["f"]), cv2.COLOR_BGR2GRAY)
    t = cv2.imdecode(np.fromfile(os.path.join(ROOT, "flows", "晚_簡中", "templates", n + ".png"), np.uint8), 0)
    best = max((cv2.minMaxLoc(cv2.matchTemplate(g, cv2.resize(t, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.TM_CCOEFF_NORMED))[1], s) for s in np.arange(1.05, 1.20, 0.005))
    print(n, "best ncc scale", round(best[1], 3), round(best[0], 3))

import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
print("cal", d["cal"])
groups = {}
for r in d["rows"]:
    groups.setdefault((r["step"], r["key"], r["t"], str(r["within"])), []).append(r)
def off(box, lim):
    if lim is None: return 0, 0
    x, y, w, h = box[:4]; lx, ly, lw, lh = lim
    dx = max(lx - x, 0) + max((x + w) - (lx + lw), 0)
    dy = max(ly - y, 0) + max((y + h) - (ly + lh), 0)
    return dx, dy
for (sn, key, t, w), rs in groups.items():
    best = max(rs, key=lambda r: (r["in_found"], (r["wh"][0][4] if r["wh"] else 0), r["wh_score"]))
    wh = best["wh"][0] if best["wh"] else None
    o = off(wh, best["limit"]) if wh else None
    if best["in_found"]: v = "OK"
    elif wh and wh[4] >= 0.8: v = "rect-off"
    elif wh: v = "weak?"
    else: v = "not-found"
    print(f"#{sn:<3}{key[:7]:8}{t:10} f{best['f']:<5} lim={best['limit']} in={'Y' if best['in_found'] else 'N'}/{best['in_best']}/{best['in_failed']} whole={wh} wh_best={best['wh_score']} out_by={o} ncc={best['ncc']} -> {v}")

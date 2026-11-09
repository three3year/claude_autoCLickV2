from common import *
name = sys.argv[1]; anc = tuple(int(v) for v in sys.argv[2].split(","))
ks = [1.058, 1.075, 1.09, 1.105, 1.115, 1.121, 1.13, 1.14]
d = json.load(open(f"res2_{name}.json", encoding="utf-8"))
f, hub, imgs = load(name)
best = {}
for r in d["rows"]:
    key = (r["step"], r["key"], r["t"])
    if r["in_found"] and key not in best: best[key] = r
tg = {(sn, key, t["template"]): t for sn, key, t in targets(f)}
print("k:", ks)
for key, r in best.items():
    t = tg[key]
    if t.get("within") is None: continue
    fr = frame(r["f"])
    res = []
    for k in ks:
        fd = findtarget.find(t, hub, fr, (0, 0), origin=None, scale=k, anchor=anc)
        res.append("Y" if fd.picked else "-")
    print(f"#{key[0]:<3} {key[2]:8} f{r['f']:<5} {' '.join(res)}", flush=True)

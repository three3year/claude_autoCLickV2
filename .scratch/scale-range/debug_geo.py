"""除錯: 繁中進駐總覽幾幀上 標題_貿易站 的匹配、⇌ 位置、貿易站1列 的找法."""
import os, shutil, tempfile, sys
import srcommon as sr
from srcommon import bp
from rebuild_shift import HEADERS
from shift_build import Geometry, CATEGORY
from automation import findtarget

lang = sys.argv[1] if len(sys.argv) > 1 else "tw"
conv = sr.load(os.path.join(sr.RESULTS, f"convert_{lang}.json"))
ev = sr.LANGS[lang]["evening"]
r = sr.read_flow(ev, sr.CONVERTED)
region = r["data"]["scanRegion"]
anchor = tuple(conv[ev]["pair"]["new_anchor"])
images = {}
for n in [*HEADERS[lang]["crops"], "_swap"]:
    with open(os.path.join(sr.TEMPLATES, lang, n + ".png"), "rb") as f:
        images[n] = f.read()
old = {n: b for n, b in r["images"].items() if n in CATEGORY[lang]}
tmp = tempfile.mkdtemp()
hub = bp.make_hub({**old, **images}, [*old, *images], tmp)
geo = Geometry(lang, hub, sr.place(lang, region), anchor, region)
hdr = {"tw": "標題_貿易站", "cn": "标题_贸易站"}[lang]
row = {"tw": "貿易站1列", "cn": "贸易站1列"}[lang]
old_tgt = next(findtarget.target(s) for s in r["data"]["steps"] if findtarget.template(s) == row)
frames = {"tw": [540, 550, 560, 580, 600, 610], "cn": [450, 470, 500, 520, 540]}[lang]
for fn in frames:
    f = geo.find(fn, {"template": hdr, "limit": geo.col_rect()})
    sw = geo.swaps(fn)
    f2 = geo.find(fn, old_tgt)
    print(f"f{fn} scroll={geo.scroll[fn]} 標題匹配={[ (sr.center(m.box), round(m.score,3)) for m in f.matches]} ⇌={sw}")
    print(f"      header_center={geo.header_center(fn, hdr)}  {row}={(sr.center(f2.picked.box), round(f2.picked.score,3), f2.picked.color) if f2.picked else (f2.failed, f2.query.score if f2.query else None, [ (sr.center(m.box), m.color) for m in f2.rejected])}")
shutil.rmtree(tmp, ignore_errors=True)

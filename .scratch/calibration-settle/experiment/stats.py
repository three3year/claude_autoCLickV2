"""規格裡實驗數字的出處: python stats.py (在本資料夾執行)."""
import json, statistics as st
for f in ("result_windowed.json", "result_maximized.json"):
    rows = json.load(open(f, encoding="utf-8"))["rows"]
    for t in (0.05, 1.0, 1.5):
        g = [x for x in rows if x["t"] == t and "k" in x["main"]]
        k = [x["main"]["k"] for x in g]; d = [x["main"]["dist"] for x in g]
        print(f"{f} t={t}: n={len(g)} main_k {min(k)}–{max(k)} mean {st.mean(k):.4f} "
              f"dist {min(d)}–{max(d)} mean {st.mean(d):.2f}")
    tk = sorted({x["title"]["k"] for x in rows if "k" in x["title"]})
    print(f"{f} title_k values: {tk} (n={sum('k' in x['title'] for x in rows)})")

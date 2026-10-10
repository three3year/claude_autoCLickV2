"""穩健性: 把整張截圖縮放 (模擬不同視窗大小/非同張截圖), 看本尊粗篩/驗證剩多少、他者爬到多少."""
import io, json, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SP = Path(sys.argv[1]); OUT = SP / "scratchpad" / "recruit_tags"
PROJ = Path(r"C:\Users\three\我的電腦\AiProject\claude_autoClickV2")
import cv2
from subject_detection import Engine, make_library, load_config
NAMES = ["guard", "novice", "cost", "dps", "surv"]
LABEL = {"guard": "近衛幹員", "novice": "新手", "cost": "費用回復", "dps": "輸出", "surv": "生存"}
crops = json.load(open(OUT / "crops.json", encoding="utf-8"))
cfg = load_config(PROJ / "profiles" / "arknights")
MT, VT = float(cfg["match_threshold"]), float(cfg["verify_threshold"])
scene0 = cv2.imread(str(SP / "images" / "1.png"))
engine = Engine()
SCALES = [0.75, 0.886, 1.0, 1.15, 1.3]
lines = []
for setname, prefix in (("A_按鈕含深色底框", "btn"), ("B_只含文字", "txt")):
    lib = make_library({n: str(OUT / f"{prefix}_{n}.png") for n in NAMES}, cfg, str(OUT / f"artifacts_{prefix}"))
    for n in NAMES: engine.register(lib, n)
    lines.append(f"\n===== 裁切組 {setname} =====")
    lines.append(f"{'模板':>6} {'場景縮放':>6} | {'本尊粗篩':>8} {'本尊驗證':>8} | 他者最高粗篩 (位置) | 他者過粗篩門檻者的驗證分數 | 結果")
    for s in SCALES:
        scene = scene0 if s == 1.0 else cv2.resize(scene0, None, fx=s, fy=s,
                 interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        def locate(box):
            x, y, w, h = box; cx, cy = (x + w / 2) / s, (y + h / 2) / s
            for m in NAMES:
                bx1, by1, bx2, by2 = crops[m]["button"]
                if bx1 - 4 <= cx <= bx2 + 4 and by1 - 4 <= cy <= by2 + 4: return m
            return None
        for n in NAMES:
            r = engine.query(lib, n, scene)
            cands = r.debug["candidates"]; vs = r.debug.get("verify_scores") or []
            vi = 0; self_c = self_v = None; other = (None, None); other_v = []
            for c in cands:
                v = None
                if c["score"] >= MT and vi < len(vs): v = vs[vi]; vi += 1
                w = locate(c["box"])
                if w == n:
                    if self_c is None or c["score"] > self_c: self_c, self_v = c["score"], v
                elif w is not None:
                    if other[0] is None or c["score"] > other[0]: other = (c["score"], LABEL[w])
                    if v is not None: other_v.append(f"{LABEL[w]}={v:.3f}")
            # 引擎最終答案落在哪
            final = locate(r.box) if r.found else None
            verdict = ("本尊" if final == n else (f"誤認→{LABEL[final]}" if final else ("找到其他處" if r.found else f"沒找到 (failed={r.failed})")))
            if r.found and len(r.matches) > 1:
                verdict += f"; 共 {len(r.matches)} 個匹配: " + ",".join(LABEL.get(locate(m.box), "其他處") for m in r.matches)
            fc = lambda x: "—" if x is None else f"{x:.3f}"
            lines.append(f"{LABEL[n]:>6} {s:>6} | {fc(self_c):>8} {fc(self_v):>8} | {fc(other[0]):>6} ({other[1] or '—'}) | {' '.join(other_v) or '—'} | {verdict}")
text = "\n".join(lines); print(text)
(OUT / "result_scaled.txt").write_text(text, encoding="utf-8")

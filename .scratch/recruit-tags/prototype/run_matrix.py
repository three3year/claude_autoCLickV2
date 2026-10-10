"""五個公開招募標籤: 各登錄為模板、對整張截圖 query, 產 5x5 交叉分數矩陣.

用法: python run_matrix.py <session_dir>
輸出: result.txt (可讀報告) 與 result.json (原始分數) 於 scratchpad/recruit_tags/
"""
import io, json, sys, os
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
scene = cv2.imread(str(SP / "images" / "1.png"))
engine = Engine()
assert not engine.coarse_only, "驗證模型沒載入"

def locate(box):
    """候選框中心落在哪個按鈕 (按鈕外框座標); 無則 None."""
    x, y, w, h = box; cx, cy = x + w / 2, y + h / 2
    for n in NAMES:
        bx1, by1, bx2, by2 = crops[n]["button"]
        if bx1 - 4 <= cx <= bx2 + 4 and by1 - 4 <= cy <= by2 + 4:
            return n
    return None

report, raw = [], {"config": {"match_threshold": MT, "verify_threshold": VT,
                               "scale_range": cfg["scale_range"], "aspect_jitter": cfg["aspect_jitter"]},
                   "crops": crops, "sets": {}}
for setname, prefix in (("A_按鈕含深色底框", "btn"), ("B_只含文字", "txt")):
    paths = {n: str(OUT / f"{prefix}_{n}.png") for n in NAMES}
    lib = make_library(paths, cfg, str(OUT / f"artifacts_{prefix}"))
    for n in NAMES:
        engine.register(lib, n)
    report.append(f"\n{'=' * 78}\n裁切組 {setname}\n{'=' * 78}")
    setraw = {"queries": {}, "coarse": {}, "verify": {}, "direct_verify": {}}
    for n in NAMES:
        r = engine.query(lib, n, scene)
        setraw["queries"][n] = {"found": r.found, "box": r.box, "score": r.score,
                                "failed": r.failed, "debug": r.debug}
        report.append(f"\n--- 模板 {LABEL[n]} ({n}) 範本 {crops[n][prefix if prefix=='text' else ('button' if prefix=='btn' else 'text')]}"
                      f"  found={r.found} failed={r.failed} best={r.score:.4f}")
        cands = r.debug["candidates"]
        vs = r.debug.get("verify_scores")
        passing = [c for c in cands if c["score"] >= MT]
        vi = 0
        coarse_row, verify_row = {}, {}
        for c in cands:
            v = None
            if c["score"] >= MT and vs is not None:
                v = vs[vi]; vi += 1
            where = locate(c["box"])
            tag = ("本尊" if where == n else (LABEL[where] if where else "其他處"))
            report.append(f"   cand box={c['box']} scale={c['scale']} coarse={c['score']:.4f}"
                          f" verify={'—' if v is None else f'{v:.4f}'}  → {tag}")
            if where:
                if c["score"] > coarse_row.get(where, -1): coarse_row[where] = c["score"]
                if v is not None and v > verify_row.get(where, -1): verify_row[where] = v
        setraw["coarse"][n], setraw["verify"][n] = coarse_row, verify_row
        # 補充: 繞過粗篩, 直接把五個按鈕位置 (以本模板尺寸) 餵驗證模型, 看驗證階段本身分不分得開
        from subject_detection.verification import masked_fill
        art = lib.templates[n].artifacts
        key = "button" if prefix == "btn" else "text"
        crops_img = []
        for m in NAMES:
            x1, y1, x2, y2 = crops[m][key]
            crops_img.append(masked_fill(scene[y1:y2, x1:x2], art.mask))
        embs = engine._verifier.embed(crops_img)
        setraw["direct_verify"][n] = {m: float(s) for m, s in zip(NAMES, embs @ art.embedding)}

    def matrix(title, data, thr, fmt="{:.3f}"):
        lines = [f"\n{title}  (列=模板, 欄=畫面上的按鈕; [ ]=本尊, *=過門檻 {thr})",
                 "        " + "".join(f"{LABEL[m]:>10}" for m in NAMES)]
        for n in NAMES:
            cells = []
            for m in NAMES:
                v = data[n].get(m)
                s = "—" if v is None else fmt.format(v)
                if v is not None and v >= thr: s += "*"
                cells.append(f"[{s}]" if m == n else s)
            lines.append(f"{LABEL[n]:>6}  " + "".join(f"{c:>10}" for c in cells))
        return lines
    report += matrix("粗篩分數 (梯度域 NCC, match_threshold)", setraw["coarse"], MT)
    report += matrix("驗證分數 (engine query 內, 只有粗篩過門檻的候選才有; verify_threshold)", setraw["verify"], VT)
    report += matrix("補充: 直接餵驗證模型的五個位置 (繞過粗篩)", setraw["direct_verify"], VT)
    # 誤認判定
    report.append("\n誤認判定 (他者分數也過門檻, 或與本尊差 < 0.05):")
    for n in NAMES:
        self_v = setraw["verify"][n].get(n)
        self_c = setraw["coarse"][n].get(n)
        for m in NAMES:
            if m == n: continue
            c, v = setraw["coarse"][n].get(m), setraw["verify"][n].get(m)
            issues = []
            if c is not None and c >= MT: issues.append(f"粗篩過門檻 {c:.3f}")
            if v is not None and v >= VT: issues.append(f"驗證過門檻 {v:.3f} (會被引擎當成匹配)")
            if v is not None and self_v is not None and abs(self_v - v) < 0.05: issues.append(f"驗證與本尊差 {self_v - v:+.3f}")
            if c is not None and self_c is not None and abs(self_c - c) < 0.05: issues.append(f"粗篩與本尊差 {self_c - c:+.3f}")
            if issues:
                report.append(f"   模板 {LABEL[n]} → 位置 {LABEL[m]}: " + "; ".join(issues))
    raw["sets"][setname] = setraw

text = "\n".join(report)
print(text)
(OUT / "result.txt").write_text(text, encoding="utf-8")
json.dump(raw, open(OUT / "result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)

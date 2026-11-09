"""停點實驗: 遊戲停在主畫面, 從不同出發點用三種方式把游標移開, 量主畫面視差.

用法: python park_exp.py <label> [px py]
  label: 例如 windowed / maximized (結果檔名用)
  px py: 遊戲視窗內任一螢幕點 (預設主螢幕中央 960 500), 用來找遊戲視窗
只移動游標, 不按任何鍵。開始前先校準一次確認真的是簡中主畫面, 否則中止。
"""
import ctypes, ctypes.wintypes as W, json, math, os, sys, time

ROOT = r"C:\Users\three\我的電腦\AiProject\claude_autoClickV2"
sys.path.insert(0, os.path.join(ROOT, "app")); sys.path.insert(0, os.path.join(ROOT, "src"))
HERE = os.path.dirname(os.path.abspath(__file__))
REPLAY = HERE  # common.py 與本檔同資料夾
sys.path.insert(0, REPLAY)

import cv2, numpy as np
from common import load  # 載入 晚_簡中 範本與引擎 (同 app)
import calibration
from automation import capture, win

label = sys.argv[1]
px, py = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (960, 500)
win.set_dpi_aware()
u = ctypes.windll.user32

f, hub, _ = load("晚_簡中")
cal = f["calibration"]
MAIN, BASE_MAIN = cal["pair"], float(cal["baseline"])
TITLE, BASE_TITLE = cal["fallback"]["pair"], float(cal["fallback"]["baseline"])

hwnd = win.top_window_at(px, py)
n = u.GetWindowTextLengthW(hwnd); b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(hwnd, b, n + 1)
wr = W.RECT(); u.GetWindowRect(hwnd, ctypes.byref(wr))
cr = W.RECT(); u.GetClientRect(hwnd, ctypes.byref(cr))
p0 = W.POINT(0, 0); u.ClientToScreen(hwnd, ctypes.byref(p0))
CL, CT, CW, CH = p0.x, p0.y, cr.right, cr.bottom
WREG = (max(wr.left, 0), max(wr.top, 0), wr.right - max(wr.left, 0), wr.bottom - max(wr.top, 0))
print("window", hwnd, repr(b.value), "zoomed", u.IsZoomed(hwnd), "client", (CL, CT, CW, CH), "wreg", WREG)


def meas(img, org):
    out = {}
    for tag, pair, base in (("main", MAIN, BASE_MAIN), ("title", TITLE, BASE_TITLE)):
        m = calibration.measure(hub.query, img, pair, org)
        if m.ok:
            out[tag] = {"centers": {k: list(v) for k, v in m.centers.items()},
                        "dist": round(m.distance, 1), "k": round(m.distance / base, 4)}
        else:
            out[tag] = {"missing": m.missing, "scores": m.scores}
    return out


img, org = capture.grab(WREG)
first = meas(img, org)
print("precheck", json.dumps(first, ensure_ascii=False))
if "dist" not in first["main"]:
    sys.exit("主畫面校準對找不到 → 不是簡中主畫面, 中止 (沒有移動游標)")

x1, y1, x2, y2 = win.monitor_rect_at(CL + CW / 2, CT + CH / 2)
OUT = (min(max(CL - 2, x1), x2 - 1), min(max(CT + CH + 1, y1), y2 - 1))  # 同 app: 範圍左下角外 1-2px
IN = (CL + 4, CT + CH - 4)
print("outside corner", OUT, "inside corner", IN)


def smooth(x, y, ms=250):
    sx, sy = win.cursor_pos()
    n = max(2, int(ms / 15))
    for i in range(1, n + 1):
        win.move(sx + (x - sx) * i / n, sy + (y - sy) * i / n)
        win._send_hover()
        time.sleep(ms / 1000.0 / n)


METHODS = {
    "A_jump(現在)": lambda: win.park(*OUT),
    "B_smooth_out": lambda: smooth(*OUT),
    "C_in_then_out": lambda: (smooth(*IN), time.sleep(0.1), smooth(*OUT, ms=60)),
}
STARTS = [(0.85, 0.15), (0.5, 0.5), (0.85, 0.85), (0.2, 0.2)]
TIMES = [0.05, 0.2, 0.4, 0.7, 1.0, 1.5]

shots = []  # (method, start, t, img, org)
t_all = time.time()
for mname, fn in METHODS.items():
    for fx, fy in STARTS:
        sx, sy = int(CL + CW * fx), int(CT + CH * fy)
        smooth(sx, sy, ms=300)
        time.sleep(1.2)
        im, og = capture.grab(WREG); shots.append((mname, (fx, fy), "start", im, og))
        fn()
        t0 = time.time()
        for t in TIMES:
            time.sleep(max(0, t0 + t - time.time()))
            im, og = capture.grab(WREG); shots.append((mname, (fx, fy), t, im, og))
print("moves done in %.1fs, measuring %d shots" % (time.time() - t_all, len(shots)))

rows = []
for mname, st, t, im, og in shots:
    r = meas(im, og); r.update(method=mname, start=st, t=t); rows.append(r)
    mm = r["main"]
    wh = mm.get("centers", {}).get(MAIN[1])
    print(f"{mname:15s} start={st} t={t!s:5s} main_k={mm.get('k')} 仓库={wh} title_k={r['title'].get('k')}")
for mname, st, t, im, og in shots:
    if t == TIMES[-1]:
        crop = im[max(0, CT + CH - og[1] - 160):CT + CH - og[1], max(0, CL - og[0]):CL - og[0] + 200]
        cv2.imencode(".png", crop)[1].tofile(os.path.join(HERE, f"{label}_{mname[:1]}_{st[0]}_{st[1]}_bl.png"))
with open(os.path.join(HERE, f"result_{label}.json"), "w", encoding="utf-8") as fp:
    json.dump({"client": [CL, CT, CW, CH], "out": OUT, "in": IN, "rows": rows}, fp, ensure_ascii=False, indent=1)
print("saved", os.path.join(HERE, f"result_{label}.json"))

"""忙碌暫停、固定矩形: 建構與驗證腳本共用的路徑與流程存檔存取 (見 spec.md).

流程存檔只經 app 的流程存檔模組 (app/flowfile.py) 讀寫。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
APP = os.path.join(ROOT, "app")
PROFILE = os.path.join(APP, "dist", "AutoClick", "profiles", "arknights")
FLOWS = os.path.join(PROFILE, "flows")
BACKUP = os.path.join(APP, "dist", "profiles-backup-2026-10-07-busy-pause-fixed-rect")
RESULTS = os.path.join(HERE, "results")

for p in (APP, os.path.join(APP, "tests"), os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

MORNING = ["早_簡中", "早_繁中"]
EVENING = ["晚_簡中", "晚_繁中"]
FLOW_NAMES = MORNING + EVENING


def flow_path(name, flows=FLOWS):
    import flowfile
    return os.path.join(flows, name + flowfile.EXT)


def autoclick_running():
    """AutoClick (含 noUAC 版) 正在執行嗎: 開著時它的草稿會把改動蓋回去."""
    import subprocess
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                         text=True, errors="replace").stdout.lower()
    return '"autoclick.exe"' in out or '"autoclick-nouac.exe"' in out


def ticket_backup(ticket):
    """票 06 起每張票改流程前各自的備份目錄 (票 05 用 BACKUP)."""
    return f"{BACKUP}-{ticket}"


def preflight(flows, backup=BACKUP):
    """改正式流程前的檢查與備份: AutoClick 已關、備份已在. 改的是別的目錄 (試跑) 就只查前者.

    backup 不存在時: 票 05 的 BACKUP 要人工先做; 票 06 起的 (ticket_backup) 由這裡
    把當下的 profiles 整個複製過去——重跑時備份已在, 不會被改過的版本蓋掉。
    """
    import shutil
    if autoclick_running():
        raise SystemExit("AutoClick 正在執行: 請先關掉 (不然草稿會把改動蓋回去)")
    if os.path.normcase(os.path.abspath(flows)) != os.path.normcase(FLOWS):
        return
    if not os.path.isdir(backup):
        if backup == BACKUP:
            raise SystemExit(f"還沒備份: 先把 profiles 複製到 {BACKUP}")
        shutil.copytree(os.path.dirname(PROFILE), backup)
        print(f"已備份 profiles 到 {backup}")


def is_busy_wait(step, busy):
    """「忙碌指示 → 等待消失」步驟: 等待消失, 範本就是流程層級的忙碌指示."""
    from automation import findtarget
    return (busy is not None and step.get("type") == "find_click"
            and step.get("action") == "wait_gone"
            and findtarget.template(step) == busy.get("template"))


def write_flow(path, data, images, pos):
    """寫存檔並讀回驗證: 每個被引用的範本都在存檔裡; 回傳讀回的結果."""
    import flowfile
    missing = flowfile.write(path, data, images, pos)
    if missing:
        raise SystemExit(f"存檔引用了不存在的範本: {'、'.join(missing)}")
    back = flowfile.read(path)
    lost = set(flowfile.flow_refs(back["data"])) - set(back["images"])
    if lost:
        raise SystemExit(f"讀回後缺範本: {'、'.join(sorted(lost))}")
    return back


def current_flow(profile=PROFILE):
    """草稿 (_autosave.json) 屬於哪一份存檔 (工作區的 state.json)."""
    import flowfile
    p = flowfile.Workspace(profile).flow_path()
    return os.path.normcase(os.path.abspath(p)) if p else None


def sync_draft(path, profile=PROFILE):
    """草稿屬於 path 這份存檔時, 改寫成存檔讀回的內容 (同 App._flow_data 的形狀).

    回傳是否改寫。草稿屬於別份存檔時不動。
    """
    import flowfile
    cur = current_flow(profile)
    if cur != os.path.normcase(os.path.abspath(path)):
        return False
    r = flowfile.read(path)
    # app 啟動時讀草稿＋工作區裡的圖 (不重解存檔): 範本有增減或換圖時工作區也要跟上
    ws = flowfile.Workspace(profile)
    have = {}
    for n, p in ws.images().items():
        with open(p, "rb") as f:
            have[n] = f.read()
    if have != r["images"]:
        ws.load_flow(path)
    data = dict(r["data"])
    data.pop("flowFormat", None)
    data[flowfile.RETRY_KEY] = flowfile.retry_interval_ms(data)
    flowfile.write_draft(profile, data)
    return True


# ================= 真引擎 (接縫三) =================

def read_img(path):
    """讀圖 (中文路徑, 經 app 的 imgio); 讀不到就中止."""
    from automation import imgio
    img = imgio.imread(path)
    if img is None:
        raise SystemExit(f"讀不到圖: {path}")
    return img


def write_img(path, img):
    from automation import imgio
    imgio.imwrite(path, img)


def decode(blob):
    """存檔裡的範本位元組 → 影像 (經 app 的 imgio)."""
    from automation import imgio
    return imgio.imdecode(blob)


def encode(img):
    """影像 → 範本的 PNG 位元組 (經 app 的 imgio, 與編輯器存範本同一套編碼)."""
    from automation import imgio
    return imgio.encode_png(img)


def make_hub(images, names, tmp):
    """臨時 profile 目錄 tmp: 範本寫進它的工作區, 引擎照 app 的方式載入 (arknights 門檻).

    同 credit-store-switch/frames.py: 深度驗證模型載不起來就中止 (結果不等於實際執行)。
    """
    import applog
    import enginehub
    import flowfile
    ws = flowfile.Workspace(tmp)
    for n in names:
        ws.add(n, images[n])
    applog.set_path(os.path.join(tmp, "autoclick.log"))
    hub = enginehub.EngineHub()
    hub.load(ws.root, config_dir=PROFILE)
    if not hub.ready:
        raise SystemExit(f"引擎載入失敗: {hub.error!r}")
    if hub.coarse_only:
        raise SystemExit("深度驗證模型載不起來 (coarse-only): 驗證結果不等於實際執行, 中止")
    hub.preload(names)
    return hub


VIDEO_DIR = r"C:\Users\three\我的電腦\oCam Video"

# 兩版的參考影片與「影片座標 → 實機螢幕座標」的偏移 (畫面倍率兩版實跑都是 1.000)。
# 偏移由 10/07 實跑日誌的 picked 框對影片上同一張範本的位置量出:
# 簡中 快速置入 影片 (1512,818) ↔ 實機 (1607,875); 繁中 進駐總覽 (206,150) ↔ (206,150)。
LANGS = {
    "cn": {"flow": "早_簡中", "offset": (95, 57), "videos": ["demo6", "demo5", "demo1"]},
    "tw": {"flow": "早_繁中", "offset": (0, 0), "videos": ["demo2", "demo3"]},
}


def video_box_to_rect(box, lang, region, margin=0):
    """影片座標的框 (x, y, w, h) 外擴 margin → `固定矩形` (搜尋範圍 region 的比例).

    同編輯器框選的換算 (findtarget.ratio_rect_from_screen): 先換成實機螢幕座標再算比例。
    """
    from automation import findtarget
    ox, oy = LANGS[lang]["offset"]
    x, y, w, h = box
    scr = (x + ox - margin, y + oy - margin, w + 2 * margin, h + 2 * margin)
    r = findtarget.ratio_rect_from_screen(scr, tuple(region))
    if r is None:
        raise SystemExit(f"框 {box} 在搜尋範圍外")
    return r


def frame_region(lang, region):
    """影格當成「實機截到的搜尋範圍」時的 (影像, 左上螢幕座標) 換算: 回傳一個函式.

    影格貼到搜尋範圍大小的黑底畫布上 (位置照偏移), 找圖目標就照實機的搜尋範圍算限定範圍。
    """
    import numpy as np
    ox, oy = LANGS[lang]["offset"]
    rx, ry, rw, rh = region
    if ox < rx or oy < ry:
        raise SystemExit(f"影片左上 ({ox},{oy}) 在搜尋範圍左上 ({rx},{ry}) 之外: 不認得的配置")

    def place(img):
        canvas = np.zeros((rh, rw, 3), np.uint8)
        dx, dy = ox - rx, oy - ry
        h = min(img.shape[0], rh - dy)
        w = min(img.shape[1], rw - dx)
        canvas[dy:dy + h, dx:dx + w] = img[:h, :w]
        return canvas, (rx, ry)
    return place


class Frames:
    """影片影格讀取 (1:1 遊戲畫面); 同一支影片共用一個 VideoCapture."""

    def __init__(self):
        self._caps = {}

    def get(self, video, n):
        import cv2
        cap = self._caps.get(video)
        if cap is None:
            cap = self._caps[video] = cv2.VideoCapture(
                os.path.join(VIDEO_DIR, video + ".mp4"))
        cap.set(cv2.CAP_PROP_POS_FRAMES, n)
        ok, img = cap.read()
        if not ok:
            raise SystemExit(f"讀不到 {video} 第 {n} 幀")
        return img

    def close(self):
        for cap in self._caps.values():
            cap.release()


def section_error(steps):
    """區段完整性 (同 App._flow_error 的堆疊掃描): 錯誤訊息或 None."""
    from automation.runner import branch_layout
    stack = []
    for i, s in enumerate(steps):
        t = s["type"]
        if t in ("loop_start", "branch_start"):
            if t == "branch_start":
                lay = branch_layout(steps, i)
                if lay is None:
                    return f"第 {i + 1} 步: 分岔標記不成對"
                segs, end = lay
                for st in segs:
                    if st >= end or steps[st]["type"] != "find_click":
                        return f"第 {i + 1} 步: 分支開頭不是找圖步驟"
            stack.append(t)
        elif t in ("loop_end", "branch_end"):
            need = "loop_start" if t == "loop_end" else "branch_start"
            if not stack or stack[-1] != need:
                return f"第 {i + 1} 步: {t} 沒有對應的開始標記 (或區段交錯)"
            stack.pop()
        elif t == "branch_or" and (not stack or stack[-1] != "branch_start"):
            return f"第 {i + 1} 步: 分岔（或）不在分岔區段內"
    return f"{stack[-1]} 缺少結束標記" if stack else None

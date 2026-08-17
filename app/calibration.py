"""`校準`與`畫面倍率`: 純邏輯集中地, 純檔案/純計算 (GUI 無關).

詞彙見 app/CONTEXT.md「校準與畫面倍率」。UI 與 runner 只呼叫這個模組,
不各自實作: 校準資料的載入/儲存、倍率計算、`機器指紋`、`未校準`判定、
`重定基準`的流程存檔改寫、`來源基準`標記。(存檔攜帶校準資料與`匯入換算`
三分支落在 flowfile——那是存檔格式的事。)

校準資料存在 profile 內 (calibration.json, 隨 profile 資料夾搬遷)::

    pair          `校準對`: 兩個範本名稱
    baseline      `基準距離`: 校準對匹配框中心在基準機器上的直線距離 (px)
    scale         `畫面倍率`: 本機相對基準的單一等比倍數; null = 從未校準
    fingerprint   `機器指紋`: 量得倍率當下的螢幕配置; 與當下不符 = 視同未校準

校準對的兩張圖由 profile 自存一份 (`flowfile.calibration_images`), 與流程存檔
解耦——刪掉任何一份流程都不會弄壞校準。

缺檔 = 沒有校準對 = profile 完全不受校準影響 (不警告、不換算)。
"""
import json
import math
import os

from automation import flowfmt

FILE_NAME = "calibration.json"

# flow 資料的`來源基準`標記鍵 (票 06): 以不同校準對的 pack 匯入、尚未歸位的
# 流程帶著 {"pair": [...], "baseline": N}; 存檔前必須先換算或明確確認
SOURCE_BASELINE = "sourceBaseline"

# `重定基準`/匯入換算要改寫的步驟偏移欄位 (三類偏移, 拖曳含兩端點)。
# 相對與絕對座標都是偏移量、都要換算; 搜尋範圍等螢幕座標不在流程步驟裡。
_SCALE_KEYS = {
    "click": ("x", "y"),
    "drag": ("x1", "y1", "x2", "y2"),
    "find_click": ("offsetX", "offsetY"),
}


def path(profile_dir):
    return os.path.join(profile_dir, FILE_NAME)


def valid(cal):
    """校準資料是否成形: 兩個範本名的校準對 + 正的基準距離."""
    if not isinstance(cal, dict):
        return False
    pair = cal.get("pair")
    if (not isinstance(pair, list) or len(pair) != 2
            or not all(isinstance(n, str) and n for n in pair)):
        return False
    try:
        return float(cal.get("baseline", 0)) > 0
    except (TypeError, ValueError):
        return False


def load(profile_dir):
    """讀 profile 的校準資料; 缺檔/壞檔 = 沒有校準對, 回傳 None."""
    try:
        with open(path(profile_dir), encoding="utf-8") as f:
            cal = json.load(f)
    except (OSError, ValueError):
        return None
    return cal if valid(cal) else None


def save(profile_dir, cal):
    with open(path(profile_dir), "w", encoding="utf-8") as f:
        json.dump(cal, f, ensure_ascii=False, indent=2)


def current_fingerprint():
    """`機器指紋`: 當下的螢幕配置快照 (虛擬桌面幾何).

    整包 profile 複製到別台電腦時, 靠它認出「倍率是別台機器量的」。
    """
    from automation import win
    return win.virtual_screen()


def is_uncalibrated(cal, fingerprint):
    """`未校準`判定: 有校準對、但本機沒有有效倍率.

    從未校準 (scale 為 null)、或機器指紋與當下螢幕配置不符都算。
    呼叫端保證 cal 不是 None (沒有校準對的 profile 談不上未校準)。
    """
    return cal.get("scale") is None or cal.get("fingerprint") != fingerprint


def effective_scale(cal, fingerprint):
    """執行期代入的`畫面倍率`: 沒有校準對或未校準 = 1 (恆等換算)."""
    if cal is None or is_uncalibrated(cal, fingerprint):
        return 1.0
    return float(cal["scale"])


def run_warning(cal, fingerprint):
    """執行流程前的警告訊息; None = 不必警告 (票 03).

    未校準 = 警告後照跑 (以倍率 1 代入); 沒有校準對 = 完全不警告。
    """
    if cal is None or not is_uncalibrated(cal, fingerprint):
        return None
    return ("此 profile 已設定校準對，但本機尚未校準，座標可能偏移。\n"
            "將以倍率 1 執行；建議先按主視窗的「校準」按鈕量測本機倍率。")


def pick_gate_message(cal, fingerprint):
    """拾取座標前的守門訊息; None = 放行 (票 04).

    未校準時拾取到的本機像素無法歸一到基準尺度 (倍率未知), 事後救不回來,
    所以擋下要求先校準。沒有校準對的 profile 不擋。
    """
    if cal is None or not is_uncalibrated(cal, fingerprint):
        return None
    return ("此 profile 已設定校準對，但本機尚未校準。\n"
            "未校準時拾取的座標無法換算回基準尺度，"
            "請先按主視窗的「校準」按鈕完成校準。")


# 同機重校的量測抖動 (匹配框 1-2px 級) 視同倍率 1 的容差;
# 沒有它, 同一台機器重校量到 0.997 之類的值後, 每次存檔都會觸發
# 全 profile 重定改寫+彈窗, 基準距離也會漂移
IDENTITY_EPS = 0.005


def snap_identity(scale):
    """量測抖動內的`畫面倍率`貼齊為 1 (校準完成後原機器行為不變)."""
    return 1.0 if abs(scale - 1.0) < IDENTITY_EPS else scale


def measure(query, screen, pair):
    """量`校準對`兩張圖的匹配框中心直線距離.

    query: runner 同款偵測接縫 (query(範本名, 搜尋區域) → QueryResult);
    screen: 已截好的搜尋區域影像 (找圖語意與一般找圖一致, 由呼叫端決定
    範圍內或全螢幕)。回傳 (距離, 找不到的範本名 list); 任一張找不到時
    距離為 None——失敗結果指明缺哪一張, 呼叫端不得寫入任何校準資料。
    """
    centers = []
    missing = []
    for name in pair:
        r = query(name, screen)
        if not r.found:
            missing.append(name)
            continue
        x, y, w, h = r.box
        centers.append((x + w // 2, y + h // 2))
    if missing:
        return None, missing
    (x1, y1), (x2, y2) = centers
    return math.hypot(x2 - x1, y2 - y1), []


def scale_steps(steps, k):
    """就地把步驟偏移 ×k 四捨五入: 找圖偏移、座標點擊/拖曳 (abs 與 prev).

    `重定基準`與匯入換算共用; 標記/等待/按鍵步驟沒有偏移欄位, 自然不動。
    """
    for s in steps:
        for key in _SCALE_KEYS.get(s.get("type"), ()):
            if key in s:
                s[key] = flowfmt.scale_px(s[key], k)


def source_baseline(data):
    """flow 資料上的`來源基準`標記; 無標記回傳 None."""
    marker = data.get(SOURCE_BASELINE)
    return marker if valid(marker) else None


def foreign_ratio(measured_distance, source_baseline_px, current_scale):
    """`來源基準`流程歸位的換算比值 (票 06).

    流程座標是來源基準機器的尺度; 對來源校準對量得本機距離後:
    本機實體像素 = 座標 × (本機距離 ÷ 來源基準距離), 再反除現行倍率
    歸一到本 profile 的基準尺度 (與拾取歸一同一套語意)。
    """
    return (measured_distance / float(source_baseline_px)) / float(current_scale)


def rebase(profile_dir, fingerprint):
    """`重定基準`: profile 內**每一份**流程存檔 (含步驟草稿) 的座標乘上現行
    倍率改寫、基準距離改為本機量值、倍率歸 1、指紋更新——本機成為新基準.

    存檔內的範本圖一個 byte 都不動, 只改 flow.json 的步驟座標。
    帶`來源基準`標記的流程不改寫: 它的尺度由標記定義、與 profile 基準無關,
    存檔守門會要求先歸位。壞檔 (讀不出來) 跳過——它本來就載入不了, 不存在
    混尺度的問題。漏改任何一份就是混尺度, 所以草稿也算一份。
    回傳改寫的檔名 list。
    """
    import flowfile  # 延後匯入: flowfile 也 import 本模組 (存檔攜帶校準資料)
    cal = load(profile_dir)
    k = float(cal["scale"])

    def rewrite(data):
        if source_baseline(data):
            return False   # 不改寫: 尺度由標記定義
        scale_steps(data.get("steps") or [], k)

    rewritten = []
    for p in flowfile.list_flows(profile_dir):
        try:
            if flowfile.update_flow_data(p, rewrite) is not None:
                rewritten.append(os.path.basename(p))
        except (OSError, ValueError, KeyError):
            continue
    draft = flowfile.read_draft(profile_dir)
    if draft is not None and rewrite(draft) is not False:
        flowfile.write_draft(profile_dir, draft)
        rewritten.append(flowfile.DRAFT_NAME)
    # 新基準距離 = 本機量值 = 舊基準 × 倍率 (倍率就是這樣量出來的)
    cal["baseline"] = float(cal["baseline"]) * k
    cal["scale"] = 1.0
    cal["fingerprint"] = fingerprint
    save(profile_dir, cal)
    return sorted(rewritten)

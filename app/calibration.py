"""`校準`與`畫面倍率`、`座標基準點`: 純邏輯集中地 (GUI 無關; 詞彙見 app/CONTEXT.md
「尺度與畫面倍率」「座標與原點」).

一份流程一個尺度 (ADR 0009): `校準對`與`基準距離`住在流程裡 (flow.yaml 的
`calibration` 段), 別處不存任何校準資料。一次`校準`量出兩個值 (ADR 0012):
中心距離 ÷ 基準距離＝`畫面倍率`, 第一張圖的中心＝`座標基準點`的螢幕位置。兩者都只屬於
一次執行 (執行器開頭自動量) 或一次拾取 (編輯器每次拾取當下量), 不落地::

    calibration   {"pair": [兩個範本名], "baseline": 基準距離 (流程尺度, px)}

`備用校準對` (可不設): 主對任一張找不到 (彈窗蓋住、不在主畫面) 時改量的第二組, 住在
校準資料的 `fallback` 鍵::

    calibration   {"pair": [...], "baseline": ...,
                   "fallback": {"pair": [兩個範本名], "baseline": 它自己的基準距離,
                                "offset": [dx, dy]}}   備用第一張中心 → 座標基準點 (流程尺度)

用備用對量時基準點＝備用第一張的中心 + 偏移×倍率, 所以存下的座標一律仍相對同一個
`座標基準點`, 不因用了哪一組而改變; 倍率是備用對量出來的 (同樣貼齊 1)。

執行器、編輯器、影片轉流程三處量測都走這裡的 `measure` / `calibrate`, 行為一致由此保證。
"""
import math

from automation import flowfmt


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


# 量測抖動 (匹配框 1-2px 級) 視同倍率 1 的容差: 在建立流程時的視窗大小下執行,
# 倍率要剛好是 1——座標原樣使用沒有捨入誤差, 引擎的預期尺度網格也對準 1.0
IDENTITY_EPS = 0.005


def snap_identity(scale):
    """量測抖動內的`畫面倍率`貼齊為 1."""
    return 1.0 if abs(scale - 1.0) < IDENTITY_EPS else scale


# 兩張圖中心距離小於這個值 (px) 就不能當比例尺 (重疊在同一處)
MIN_DISTANCE = 1.0

# 流程層級的校準資料鍵 (flow.json, flowFormat 4 起; ADR 0009):
# {"pair": [兩個範本名], "baseline": 基準距離}——兩張都是這份流程自己的範本
FLOW_KEY = "calibration"


def flow_pair(data):
    """流程資料上的校準資料 {pair, baseline}; 沒有或不成形回傳 None."""
    cal = (data or {}).get(FLOW_KEY)
    return cal if valid(cal) else None


def make(pair, baseline):
    """組一份流程層級的校準資料."""
    return {"pair": [str(pair[0]), str(pair[1])], "baseline": float(baseline)}


# ---------- `備用校準對` ----------

FALLBACK_KEY = "fallback"


def make_fallback(pair, baseline, offset):
    """組備用組: 兩個範本名、它自己的基準距離、「備用第一張中心 → 座標基準點」的偏移 (流程尺度整數)."""
    return {"pair": [str(pair[0]), str(pair[1])], "baseline": float(baseline),
            "offset": [int(offset[0]), int(offset[1])]}


def _fallback_valid(fb):
    if not valid(fb):
        return False
    off = fb.get("offset")
    return (isinstance(off, list) and len(off) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in off))


def fallback_pair(cal):
    """校準資料上的備用組 {pair, baseline, offset}; 沒有或不成形回傳 None."""
    fb = (cal or {}).get(FALLBACK_KEY) if isinstance(cal, dict) else None
    return fb if _fallback_valid(fb) else None


def fallback_problem(cal):
    """備用組不成形時的說明 (讀檔時警告用); 沒設或成形回傳 None."""
    if not isinstance(cal, dict) or FALLBACK_KEY not in cal:
        return None
    if _fallback_valid(cal[FALLBACK_KEY]):
        return None
    return "備用校準對的設定不成形（範本名缺、基準距離非正、或偏移缺），當作沒有備用對"


def fallback_offset(anchor, fb_first, k):
    """設定備用對時算偏移: (座標基準點 − 備用第一張中心) ÷ 倍率, 流程尺度整數."""
    return flowfmt.from_screen(anchor, fb_first, k)


def fallback_anchor(fb_first, offset, k):
    """用備用對量時的`座標基準點`: 備用第一張中心 + 偏移×倍率 (螢幕座標)."""
    return flowfmt.to_screen(offset, fb_first, k)


def fallback_first(anchor, offset, k):
    """反過來: 由座標基準點與偏移推回備用第一張的中心 (換主校準對時重算偏移用)."""
    return flowfmt.to_screen((-int(offset[0]), -int(offset[1])), anchor, k)


class Measurement:
    """一次`校準`量測: 校準對兩張圖的匹配框中心 (螢幕座標) 與分數.

    centers: {範本名: (x, y)} (螢幕座標, 找到的才有); scores: {範本名:
    查詢的最高分}; missing: 找不到的範本名 (依校準對順序)。
    """

    def __init__(self, pair, centers, scores, missing):
        self.pair = list(pair)
        self.centers = centers
        self.scores = scores
        self.missing = missing

    @property
    def distance(self):
        """兩張圖中心的直線距離; 任一張找不到時 None."""
        if self.missing:
            return None
        (x1, y1), (x2, y2) = (self.centers[n] for n in self.pair)
        return math.hypot(x2 - x1, y2 - y1)

    @property
    def anchor(self):
        """`座標基準點`的螢幕位置＝第一張圖的中心; 第一張找不到時 None."""
        return self.centers.get(self.pair[0])

    @property
    def too_close(self):
        """兩張都找到、但中心幾乎重疊 (不能當比例尺)."""
        d = self.distance
        return d is not None and d < MIN_DISTANCE

    @property
    def problem(self):
        """量不到的原因: "missing" 找不到 / "too_close" 兩張重疊 / None＝量到了."""
        return ("missing" if self.missing else
                "too_close" if self.too_close else None)

    @property
    def ok(self):
        return self.problem is None

    def describe(self):
        """量不到的原因一句話 (執行紀錄、對話框、影片工具共用); 量到了＝空字串."""
        if self.problem == "missing":
            names = "、".join(f"「{n}」（最高分數 {self.scores[n]:.3f}）" for n in self.missing)
            return f"搜尋範圍內找不到校準圖{names}"
        if self.problem == "too_close":
            return "兩張校準圖重疊在同一處，不能當比例尺"
        return ""

    def scale(self, baseline):
        """這次量到的`畫面倍率` (量測抖動內貼齊 1)."""
        return snap_identity(self.distance / float(baseline))


def measure(query, screen, pair, origin=(0, 0)):
    """量`校準對`兩張圖的匹配框中心 (回傳 `Measurement`).

    query: 偵測接縫 (query(範本名, 搜尋區域) → QueryResult)——**不帶預期
    尺度**: 校準就是為了得出倍率, 倍率差很多 (視窗縮到一半) 也要量得到;
    screen: 已截好的`搜尋範圍`影像 (校準只在搜尋範圍內找, ADR 0012; 範圍未設＝
    全螢幕, 沿用呼叫端語意), origin 是它左上角的螢幕座標 (中心換回螢幕座標用;
    影片影格給 (0, 0))。任一張找不到時 distance 為 None——結果指明缺哪一張,
    呼叫端不得寫入任何校準資料。
    """
    centers, scores, missing = {}, {}, []
    for name in pair:
        r = query(name, screen)
        scores[name] = float(r.score)
        if not r.found:
            missing.append(name)
            continue
        x, y, w, h = r.box
        centers[name] = (int(origin[0]) + x + w // 2, int(origin[1]) + y + h // 2)
    return Measurement(pair, centers, scores, missing)


class Calibrated:
    """一次`校準`的結論: 量測 + 這份流程的基準距離 → 成功時有`座標基準點` (螢幕座標)
    與`畫面倍率`; 失敗時 problem / describe() 說明原因, 不得寫入任何座標。

    used: 用的是哪一組 ("main" 主對 / "fallback" 備用對); main: 主對的量測;
    fallback: 備用對的量測 (主對找得到或沒設備用對時 None); measurement: 用的那一組的
    量測; pair / baseline: 用的那一組的校準對與基準距離。
    """

    def __init__(self, main, baseline, pair, fallback=None, fb=None):
        self.main = main
        self.fallback = fallback
        if fallback is not None:
            self.used, self.measurement = "fallback", fallback
            self.pair, self.baseline = list(fb["pair"]), float(fb["baseline"])
        else:
            self.used, self.measurement = "main", main
            self.pair, self.baseline = list(pair), float(baseline)
        self.problem = self.measurement.problem
        self.anchor = self.scale = None
        if self.ok:
            self.scale = self.measurement.scale(self.baseline)
            if self.used == "fallback":
                self.anchor = fallback_anchor(fallback.anchor, fb["offset"],
                                              self.scale)
            else:
                self.anchor = main.anchor

    @property
    def ok(self):
        return self.problem is None

    def describe(self):
        """量不到的原因一句話; 用到備用對仍失敗時兩組各說一遍."""
        if self.fallback is None:
            return self.main.describe()
        if self.ok:
            return ""
        return (f"主校準對：{self.main.describe()}；"
                f"備用校準對：{self.fallback.describe()}")


def calibrate(query, screen, origin, cal):
    """用流程的校準資料 cal ({pair, baseline[, fallback]}) 在一張`搜尋範圍`截圖上量一次
    (回傳 `Calibrated`).

    先量主對; 主對任一張找不到、且有設`備用校準對`, 才量備用對 (主對兩張重疊不算
    找不到, 不退備用)。執行開頭與編輯器每次拾取都走這裡: 各處的座標基準點與倍率
    才會是同一個量法。
    """
    main = measure(query, screen, cal["pair"], origin)
    fb = fallback_pair(cal)
    if main.problem == "missing" and fb is not None:
        return Calibrated(main, cal["baseline"], cal["pair"],
                          measure(query, screen, fb["pair"], origin), fb)
    return Calibrated(main, cal["baseline"], cal["pair"])

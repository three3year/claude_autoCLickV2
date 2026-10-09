"""`校準`與`畫面倍率`、`座標基準點`: 純邏輯集中地 (GUI 無關; 詞彙見 app/CONTEXT.md
「尺度與畫面倍率」「座標與原點」).

一份流程一個尺度 (ADR 0009): `校準對`與`基準距離`住在流程存檔裡 (flow.json 的
`calibration` 鍵), profile 不存任何校準資料。一次`校準`量出兩個值 (ADR 0012):
中心距離 ÷ 基準距離＝`畫面倍率`, 第一張圖的中心＝`座標基準點`的螢幕位置。兩者都只屬於
一次執行 (執行器開頭自動量) 或一次拾取 (編輯器每次拾取當下量), 不落地::

    calibration   {"pair": [兩個範本名], "baseline": 基準距離 (流程尺度, px)}

執行器、編輯器、影片轉流程三處量測都走這裡的 `measure` / `calibrate`, 行為一致由此保證。
"""
import math


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
    與`畫面倍率`; 失敗時 problem / describe() 說明原因 (同 Measurement), 不得寫入任何座標。"""

    def __init__(self, measurement, baseline):
        self.measurement = measurement
        self.problem = measurement.problem
        self.anchor = measurement.anchor if self.ok else None
        self.scale = measurement.scale(baseline) if self.ok else None

    @property
    def ok(self):
        return self.problem is None

    def describe(self):
        return self.measurement.describe()


def calibrate(query, screen, origin, cal):
    """用流程的校準資料 cal ({pair, baseline}) 在一張`搜尋範圍`截圖上量一次 (回傳 `Calibrated`).

    執行開頭與編輯器每次拾取都走這裡: 兩邊的座標基準點與倍率才會是同一個量法。
    """
    return Calibrated(measure(query, screen, cal["pair"], origin), cal["baseline"])

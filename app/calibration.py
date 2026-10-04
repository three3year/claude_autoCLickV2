"""`校準`與`畫面倍率`: 純邏輯集中地 (GUI 無關; 詞彙見 app/CONTEXT.md「尺度與畫面倍率」).

一份流程一個尺度 (ADR 0009): `校準對`與`基準距離`住在流程存檔裡 (flow.json 的
`calibration` 鍵), profile 不存任何校準資料。`畫面倍率`只屬於一次執行 (執行器
開頭自動量) 或一次編輯 (編輯器按「校準」量), 不落地::

    calibration   {"pair": [兩個範本名], "baseline": 基準距離 (流程尺度, px)}

執行器、編輯器、影片轉流程三處量測都走這裡的 `measure`, 行為一致由此保證。
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
    """一次`校準`量測: 校準對兩張圖在截圖上的匹配框中心與分數.

    centers: {範本名: (x, y)} (截圖內座標, 找到的才有); scores: {範本名:
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
    def too_close(self):
        """兩張都找到、但中心幾乎重疊 (不能當比例尺)."""
        d = self.distance
        return d is not None and d < MIN_DISTANCE

    def scale(self, baseline):
        """這次量到的`畫面倍率` (量測抖動內貼齊 1)."""
        return snap_identity(self.distance / float(baseline))


def measure(query, screen, pair):
    """量`校準對`兩張圖的匹配框中心 (回傳 `Measurement`).

    query: 偵測接縫 (query(範本名, 搜尋區域) → QueryResult)——**不帶預期
    尺度**: 校準就是為了得出倍率, 倍率差很多 (視窗縮到一半) 也要量得到;
    screen: 已截好的搜尋區域影像 (呼叫端決定範圍內或全螢幕)。任一張找不到
    時 distance 為 None——結果指明缺哪一張, 呼叫端不得寫入任何校準資料。
    """
    centers, scores, missing = {}, {}, []
    for name in pair:
        r = query(name, screen)
        scores[name] = float(r.score)
        if not r.found:
            missing.append(name)
            continue
        x, y, w, h = r.box
        centers[name] = (x + w // 2, y + h // 2)
    return Measurement(pair, centers, scores, missing)

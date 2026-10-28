"""`拾取檢查` (詞彙見 app/GLOSSARY.md「尺度與畫面倍率」; 常數的由來見 ADR 0013).

編輯器在拾取當下立刻做、**只警告不擋存檔**的三項檢查, 讓範本與限定範圍在`支援倍率範圍`
×0.85–1.15 兩端都還找得到、挑得對; `影片轉流程`的自我驗證套同一套。判斷只實作在這裡
(偵測器注入, 回警告清單), 編輯器與影片工具都只呼叫它, 兩邊的標準才不會各自漂移。

- `縮放餘裕` (scale_margin): 同一張截圖等比縮到 (當下倍率×0.85) 與 (當下倍率×1.15),
  各以對應的`預期尺度`查一次; 找不到、粗篩最高分 < MATCH_MIN、或驗證最高分 < VERIFY_MIN
  就警告, 寫明哪一關、分數與倍率——範本該重截, 不是降門檻。
- `矩形餘裕` (rect_margin): `固定矩形`每邊至少比該找圖目標的範本多 RECT_MARGIN (流程
  尺度); 不足就警告並給「至少 W×H」。用百分比不用像素: 像素餘裕會隨倍率縮小。不需要偵測器。
- `唯一` (unique): 照找圖目標的限定範圍以當下倍率查一次, 引擎回報的`匹配`多於一個就不唯一;
  設了「第 N 個」「最接近」這類`挑選規則`的目標已宣告會有多個, 不查; 0 個不警告。
"""
import math

from calibration import SCALE_HIGH, SCALE_LOW

from . import findtarget

MATCH_MIN = 0.7
VERIFY_MIN = 0.85
RECT_MARGIN = 0.20

SCALE, RECT, UNIQUE = "scale", "rect", "unique"
KIND_ZH = {SCALE: "縮放餘裕", RECT: "矩形餘裕", UNIQUE: "唯一"}
GATE_ZH = findtarget.GATE_ZH


class PickWarning:
    """一則拾取檢查的警告: 種類、一句人看的話、關鍵分數 (供報告與測試)."""
    __slots__ = ("kind", "template", "text", "scores")

    def __init__(self, kind, template, text, **scores):
        self.kind = kind
        self.template = template
        self.text = text
        self.scores = scores

    def __repr__(self):
        return f"PickWarning({self.kind}, {self.template!r}, {self.scores})"

    def __str__(self):
        return f"〔{KIND_ZH[self.kind]}〕{self.text}"


def margin_px(size):
    """範本一邊的長度 → 那一邊兩側各至少要多的像素."""
    return math.ceil(round(size * RECT_MARGIN, 6))


def min_rect(template_size):
    """範本 (w, h) → 固定矩形至少要的 (W, H) (流程尺度)."""
    w, h = int(template_size[0]), int(template_size[1])
    return w + 2 * margin_px(w), h + 2 * margin_px(h)


def rect_margin(tgt, template_size):
    """`矩形餘裕`: 限定範圍是固定矩形且已知範本大小時, 矩形每邊是否至少比範本多 20%.

    找圖目標還沒選範本 (template_size None) 就跳過——流程順序不受限制。
    """
    lim = tgt.get("within")
    if lim is None or template_size is None:
        return []
    if not findtarget.valid_fixed_rect(lim):
        return []
    w, h = int(template_size[0]), int(template_size[1])
    need_w, need_h = min_rect((w, h))
    lw, lh = int(lim[2]), int(lim[3])
    if lw >= need_w and lh >= need_h:
        return []
    name = tgt.get("template", "")
    text = (f"固定矩形 {lw}×{lh} 對範本「{name}」{w}×{h} 的餘裕不足"
            f"（每邊至少多 {int(RECT_MARGIN * 100)}%：左右各 {margin_px(w)}px、"
            f"上下各 {margin_px(h)}px），至少要框 {need_w}×{need_h}；"
            "餘裕太小時視窗縮放、基準點量測誤差就會把圖切掉")
    return [PickWarning(RECT, name, text, rect=(lw, lh), size=(w, h),
                    min=(need_w, need_h))]


def resize_image(screen, s):
    """整張截圖等比縮 s 倍 (縮小 INTER_AREA、放大 INTER_LINEAR)."""
    import cv2
    h, w = screen.shape[:2]
    size = (max(1, round(w * s)), max(1, round(h * s)))
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
    return cv2.resize(screen, size, interpolation=interp)


def _scaled(screen, screen_origin, anchor, origin, s):
    img = resize_image(screen, s)

    def pt(p):
        return None if p is None else (round(p[0] * s), round(p[1] * s))
    return img, pt(screen_origin), pt(anchor), pt(origin)


def _gate_scores(f):
    q = f.query
    if q is None:
        return None, None
    d = getattr(q, "debug", None) or {}
    return d.get("match_score"), d.get("verify_score")


def scale_margin(detector, screen, screen_origin, tgt, anchor=None, scale=1.0,
                 origin=None):
    """`縮放餘裕`: 截圖縮到 (scale×0.85) 與 (scale×1.15) 各查一次.

    限定範圍照目標的設定裁 (沒有就整個截圖); 挑選規則不看 (只問找不找得到)。
    以原點為基準卻沒有原點、固定矩形卻沒有基準點＝無法查, 不警告。
    """
    name = tgt.get("template", "")
    probe = {k: v for k, v in tgt.items() if k != "pick"}
    if (origin is None and findtarget.needs_origin(probe)) or \
            (anchor is None and findtarget.needs_anchor(probe)):
        return []
    out = []
    for s in (SCALE_LOW, SCALE_HIGH):
        img, org, anc, ori = _scaled(screen, screen_origin, anchor, origin, s)
        k = scale * s
        f = findtarget.find(probe, detector, img, org, origin=ori, scale=k,
                            anchor=anc)
        if f.query is None:
            continue
        match, verify = _gate_scores(f)
        where = f"縮到 ×{s:.2f}（畫面倍率 ×{k:.3f}）時"
        if not f.matches:
            gate = GATE_ZH.get(f.query.failed, "")
            text = (f"{where}找不到範本「{name}」（{gate}最高 {f.query.score:.3f}）"
                    "：範本在縮放後找不到，建議重截（裁小、框按鈕本體或換一幀）")
            out.append(PickWarning(SCALE, name, text, scale=s, gate=f.query.failed,
                               score=float(f.query.score)))
        elif match is not None and match < MATCH_MIN:
            text = (f"{where}範本「{name}」粗篩最高 {match:.3f} 貼近門檻"
                    f"（要 ≥ {MATCH_MIN}）：縮放後可能找不到，建議重截（裁小或換一幀）")
            out.append(PickWarning(SCALE, name, text, scale=s, gate="match",
                               score=float(match)))
        elif verify is not None and verify < VERIFY_MIN:
            text = (f"{where}範本「{name}」驗證最高 {verify:.3f} 貼近門檻"
                    f"（要 ≥ {VERIFY_MIN}）：縮放後可能找不到，建議重截（框按鈕本體或換一幀）")
            out.append(PickWarning(SCALE, name, text, scale=s, gate="verify",
                               score=float(verify)))
    return out


def exempt_from_unique(tgt):
    """設了「第 N 個」「最接近」這類挑選規則的找圖目標已宣告會有多個匹配, 不查唯一."""
    return findtarget.pick_rule(tgt)[0] in ("top", "left", "near")


def unique(detector, screen, screen_origin, tgt, anchor=None, scale=1.0,
           origin=None):
    """`唯一`: 照找圖目標的限定範圍以當下倍率查一次, 匹配多於一個就警告並列出位置.

    比色照目標設定帶進查詢 (比色不符的不算匹配)。畫面上根本找不到＝沉默
    (不在那個畫面上編輯也不該被誤報)。
    """
    if exempt_from_unique(tgt):
        return []
    if (origin is None and findtarget.needs_origin(tgt)) or \
            (anchor is None and findtarget.needs_anchor(tgt)):
        return []
    f = findtarget.find(tgt, detector, screen, screen_origin, origin=origin,
                        scale=scale, anchor=anchor)
    if len(f.matches) <= 1:
        return []
    name = tgt.get("template", "")
    centers = [m.center for m in f.matches]
    where = "限定範圍內" if f.limit is not None else "搜尋範圍內"
    text = (f"{where}有 {len(f.matches)} 個匹配："
            + "、".join(f"({x},{y})" for x, y in centers)
            + f"——範本「{name}」不唯一，不能當參考點；換一張、加限定範圍或設挑選規則")
    return [PickWarning(UNIQUE, name, text, matches=centers)]


ALL = (RECT, SCALE, UNIQUE)


def check(detector, screen, screen_origin, tgt, anchor=None, scale=1.0,
          origin=None, template_size=None, kinds=ALL):
    """三項一次跑 (kinds 指定哪幾項; 矩形餘裕不需要偵測器, 要有 template_size)."""
    out = []
    if RECT in kinds:
        out += rect_margin(tgt, template_size)
    if SCALE in kinds and detector is not None and screen is not None:
        out += scale_margin(detector, screen, screen_origin, tgt, anchor, scale,
                            origin)
    if UNIQUE in kinds and detector is not None and screen is not None:
        out += unique(detector, screen, screen_origin, tgt, anchor, scale, origin)
    return out

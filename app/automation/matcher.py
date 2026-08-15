"""模板比對 (OpenCV matchTemplate).

- 不透明範本: TM_CCOEFF_NORMED 灰階 (原行為).
- 含 alpha 的去背範本: TM_CCORR_NORMED + mask, 只比對不透明區域,
  非方形物件不會被背景干擾.

(過渡模組: 辨識接縫將改走主體偵測引擎, 見 ADR 0002; 屆時本模組移除。)
"""
import cv2
import numpy as np


def _not_found(tw, th):
    return {"found": False, "score": 0.0, "x": 0, "y": 0,
            "w": int(tw), "h": int(th), "cx": 0, "cy": 0}


def _split_mask(tmpl):
    """拆出灰階範本與遮罩 (無 alpha 回傳 mask=None)."""
    if tmpl.ndim == 3 and tmpl.shape[2] == 4:
        gray = cv2.cvtColor(tmpl[:, :, :3], cv2.COLOR_BGR2GRAY)
        mask = np.where(tmpl[:, :, 3] > 127, 255, 0).astype(np.uint8)
        return gray, mask
    gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY) if tmpl.ndim == 3 else tmpl
    return gray, None


def _match_once(screen_gray, tmpl_gray, mask):
    """單次比對, 回傳 (score, x, y); 範本比畫面大回傳 None."""
    th, tw = tmpl_gray.shape[:2]
    sh, sw = screen_gray.shape[:2]
    if th > sh or tw > sw:
        return None
    if mask is not None:
        if int(mask.sum()) == 0:
            return None
        res = cv2.matchTemplate(screen_gray, tmpl_gray,
                                cv2.TM_CCORR_NORMED, mask=mask)
        res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
    else:
        res = cv2.matchTemplate(screen_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    return float(min(max_val, 1.0)), int(max_loc[0]), int(max_loc[1])


def find_template(screen_bgr, tmpl, threshold=0.85):
    """在 screen 中尋找 tmpl (BGR 或含去背 alpha 的 BGRA).

    回傳 dict: found, score, x, y, w, h, cx, cy
    (座標為 screen 圖內像素座標).
    """
    sg = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
    tg, mask = _split_mask(tmpl)
    th, tw = tg.shape[:2]

    r = _match_once(sg, tg, mask)
    if r is None:
        return _not_found(tw, th)
    score, x, y = r
    return {
        "found": bool(score >= threshold), "score": score,
        "x": x, "y": y, "w": int(tw), "h": int(th),
        "cx": int(x + tw // 2), "cy": int(y + th // 2),
    }


def annotate(screen_bgr, result, threshold):
    """在畫面上框出最佳比對位置 (綠=達門檻, 紅=未達), 回傳新影像."""
    img = screen_bgr.copy()
    color = (0, 200, 60) if result["found"] else (40, 40, 230)
    x, y, w, h = result["x"], result["y"], result["w"], result["h"]
    cv2.rectangle(img, (x, y), (x + w, y + h), color, 3)
    label = f"{result['score']:.3f} / {threshold:.2f}"
    cv2.putText(img, label, (x, max(20, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
    return img

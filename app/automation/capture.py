"""螢幕截圖 (mss). 每次呼叫建立新 mss 實例以確保執行緒安全.

cv2/mss/numpy 延後到首次擷取才 import: 本模組在開窗關鍵路徑上被載入
(runner/對話框都引用), 重量級套件不得跟著進來 (ADR 0004, 票 06)。
"""


def grab(region=None):
    """截取螢幕畫面.

    region: (x, y, w, h) 虛擬桌面座標; None = 整個虛擬桌面(所有螢幕).
    回傳 (bgr_image, (origin_x, origin_y)) — origin 為截圖左上角的螢幕座標.
    """
    import cv2
    import mss
    import numpy as np
    with mss.mss() as sct:
        if region:
            mon = {"left": int(region[0]), "top": int(region[1]),
                   "width": int(region[2]), "height": int(region[3])}
        else:
            mon = sct.monitors[0]  # 整個虛擬桌面
        raw = np.array(sct.grab(mon))  # BGRA
        bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
        return bgr, (mon["left"], mon["top"])

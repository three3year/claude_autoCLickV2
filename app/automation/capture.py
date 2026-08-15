"""螢幕截圖 (mss). 每次呼叫建立新 mss 實例以確保執行緒安全."""
import cv2
import mss
import numpy as np


def grab(region=None):
    """截取螢幕畫面.

    region: (x, y, w, h) 虛擬桌面座標; None = 整個虛擬桌面(所有螢幕).
    回傳 (bgr_image, (origin_x, origin_y)) — origin 為截圖左上角的螢幕座標.
    """
    with mss.mss() as sct:
        if region:
            mon = {"left": int(region[0]), "top": int(region[1]),
                   "width": int(region[2]), "height": int(region[3])}
        else:
            mon = sct.monitors[0]  # 整個虛擬桌面
        raw = np.array(sct.grab(mon))  # BGRA
        bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
        return bgr, (mon["left"], mon["top"])

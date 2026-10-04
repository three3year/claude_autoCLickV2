"""圖片讀寫 (支援中文/非 ASCII 路徑; cv2.imread 在 Windows 對此會失敗).

cv2/numpy 延後到首次讀寫才 import: 本模組在開窗關鍵路徑上被載入,
重量級套件不得跟著進來 (ADR 0004, 票 06)。
"""
import os


def imread(path):
    """讀取圖片為 BGR 或 BGRA (保留去背 alpha), 失敗回傳 None."""
    import cv2
    import numpy as np
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.ndim == 3 and img.shape[2] == 2:  # 灰階+alpha (LA) → BGRA, 保留透明度
        gray, a = img[:, :, 0], img[:, :, 1]
        img = np.dstack([cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), a])
    return img


def imdecode(blob):
    """把圖檔位元組解成 BGR/BGRA (供直接從流程存檔裡讀出來的圖預覽用)."""
    import cv2
    import numpy as np
    if not blob:
        return None
    img = cv2.imdecode(np.frombuffer(blob, dtype=np.uint8),
                       cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.ndim == 3 and img.shape[2] == 2:
        gray, a = img[:, :, 0], img[:, :, 1]
        img = np.dstack([cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), a])
    return img


def to_flow_scale(img, k):
    """螢幕上截下的圖 → `流程尺度` (除以`畫面倍率` k, ADR 0009).

    k＝1 時原物件照回 (一個像素都不動); 其餘以 1/k 等比縮放, 縮小用 INTER_AREA。
    """
    if k == 1:
        return img
    import cv2
    h, w = img.shape[:2]
    size = (max(1, round(w / k)), max(1, round(h / k)))
    interp = cv2.INTER_AREA if k > 1 else cv2.INTER_LINEAR
    return cv2.resize(img, size, interpolation=interp)


def encode_png(img):
    """把影像編成 PNG 位元組 (現場截圖在按下確定前只存在記憶體裡)."""
    import cv2
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("無法編碼圖片")
    return buf.tobytes()


def imwrite(path, img):
    import cv2
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise RuntimeError(f"無法編碼圖片: {path}")
    buf.tofile(path)

"""流程存檔的格式版本與遷移.

`絕對座標`的基準從「螢幕左上角」改成「`搜尋範圍`左上角」之後, 同一組數字在
新舊格式下意思不同, 所以存檔要帶標記, 讀檔時把舊格式換算過來——不能靠猜。
"""

COORD_SPACE = "coordSpace"
REGION = "region"   # 絕對座標＝相對`搜尋範圍`左上角的偏移 (現行)
SCREEN = "screen"   # 絕對座標＝螢幕座標 (舊格式, 沒有標記時視為此)

_ABS_KEYS = {"click": (("x", "y"),), "drag": (("x1", "y1"), ("x2", "y2"))}


def abs_steps(steps):
    """流程中使用`絕對座標`的步驟 (1-based 序號, 步驟)."""
    return [(i + 1, s) for i, s in enumerate(steps)
            if s.get("type") in _ABS_KEYS and s.get("mode", "abs") == "abs"]


def to_region_space(data):
    """把舊格式 (螢幕座標) 的流程換算成範圍座標; 回傳說明訊息或 None.

    直接就地修改 data。已經是新格式、或沒有`絕對座標`步驟時不動它。
    有`絕對座標`步驟卻沒有`搜尋範圍`時無從換算, 回報訊息讓呼叫端提醒使用者。
    """
    if data.get(COORD_SPACE) == REGION:
        return None
    steps = data.get("steps") or []
    olds = abs_steps(steps)
    if not olds:
        data[COORD_SPACE] = REGION  # 沒有絕對座標步驟, 直接標記為新格式
        return None

    region = data.get("scanRegion")
    if not region:
        return (f"這份流程有 {len(olds)} 個絕對座標步驟，但沒有搜尋範圍可當基準，"
                f"無法自動換算成範圍座標——請框選搜尋範圍後重新拾取這些座標")

    ox, oy = int(region[0]), int(region[1])
    for _, s in olds:
        for kx, ky in _ABS_KEYS[s["type"]]:
            s[kx] = int(s[kx]) - ox
            s[ky] = int(s[ky]) - oy
    data[COORD_SPACE] = REGION
    return (f"已把 {len(olds)} 個絕對座標步驟換算成範圍座標"
            f"（原點 {ox},{oy}）")

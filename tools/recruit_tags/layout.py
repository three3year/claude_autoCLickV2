"""五個`標籤格`的版面模型 (1.0 尺度 = 1920 寬客戶區).

從 grill 截圖 (繁中視窗, 1700×868, ×0.8854) 量五個標籤按鈕的外框換算而來;
第六格是灰色空位, 不在五格之內。截圖的尺度 = 截圖寬 ÷ 1920, 格子座標按尺度換算。
版面是相對整個客戶區量的, 所以截圖長寬比要與基準相同 (遊戲在不同長寬比下會重排)。
"""
from __future__ import annotations

from .errors import ToolError

BASE = (1920, 980)            # 1.0 尺度的客戶區 (grill 截圖 1700×868 ÷ 0.8854)
# 長寬比與基準相差超過 1% 就拒絕: 真的最大化客戶區 (約 1920×1000–1009) 沒量過,
# 遊戲在別的比例下可能重排, 寧可拒絕要 --cells 也不在錯的位置上得出結論
ASPECT_TOLERANCE = 0.01

# (x, y, w, h), 1.0 尺度; 由左到右、由上到下
CELLS = [
    (636, 490, 177, 58),
    (840, 490, 177, 58),
    (1045, 490, 177, 58),
    (636, 578, 177, 58),
    (840, 578, 177, 58),
]

SEARCH_PAD = 6                # 搜尋區域 = 格子外擴這麼多 (1.0 尺度 px)
# 匹配中心離格子中心的容許偏離 (1.0 尺度 px)。標籤字面在格子裡置中, 所以只有
# 置中的匹配算數: 「支援」在「支援機械」格裡、「資深幹員」在「高級資深幹員」格裡
# 會完全吻合, 但偏離中心一個字寬 (約 24px)。
CENTER_TOLERANCE = (10, 8)


def scale_of(width, height):
    """截圖大小 → 尺度; 長寬比不對時丟 ToolError."""
    want = BASE[0] / BASE[1]
    got = width / height
    if abs(got / want - 1) > ASPECT_TOLERANCE:
        raise ToolError(
            f"截圖長寬比 {got:.3f}（{width}×{height}）與版面基準 {want:.3f}"
            f"（{BASE[0]}×{BASE[1]}）相差超過 {ASPECT_TOLERANCE:.0%}：截圖要是整個遊戲客戶區"
            "（不含標題列與視窗邊框）；客戶區比例不同時用 --cells 指定格子位置")
    return width / BASE[0]


def scaled_cells(scale, cells=None):
    """1.0 尺度的格子 → 截圖像素 (x, y, w, h)."""
    cells = CELLS if cells is None else cells
    if len(cells) != 5:
        raise ToolError(f"標籤格要剛好 5 個（拿到 {len(cells)} 個）")
    return [tuple(round(v * scale) for v in c) for c in cells]


def search_box(cell, scale, width, height):
    """格子 (截圖像素) → 搜尋區域 (x0, y0, x1, y1), 外擴 SEARCH_PAD 並裁在截圖內."""
    pad = round(SEARCH_PAD * scale)
    x, y, w, h = cell
    return (max(0, x - pad), max(0, y - pad), min(width, x + w + pad), min(height, y + h + pad))


def centered(box, cell, scale):
    """匹配框 (截圖像素) 的中心是否在格子中心容許範圍內."""
    bx, by, bw, bh = box
    x, y, w, h = cell
    return (abs(bx + bw / 2 - (x + w / 2)) <= CENTER_TOLERANCE[0] * scale
            and abs(by + bh / 2 - (y + h / 2)) <= CENTER_TOLERANCE[1] * scale)

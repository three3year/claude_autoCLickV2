"""範本渲染: 用近似遊戲的字型把`招募標籤`字面畫成只含文字的圖 (白字深底).

範本以 1.0 尺度 (最大化、1920 寬客戶區) 渲染一次, 其他尺度交給引擎的 expected_scale。
緊貼字形外框 (墨跡) 再留 `margin` px, 不含按鈕底框——grill 實測含底框時他者
粗篩分數最高 0.52、只含文字 0.36。渲染設定集中在 `Settings`, 隨結果一起輸出。
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from .errors import ToolError

_FONT_DIRS = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
              Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"]

# 客戶端 → 預設字型檔 (依序找第一個存在的)
DEFAULT_FONTS = {
    "tw": ["NotoSansTC-VF.ttf", "msjh.ttc"],
    "cn": ["msyh.ttc", "NotoSansSC-VF.ttf"],
}

# 1.0 尺度的字級 (em, px): grill 截圖 (×0.886) 四字標籤寬約 86px → 每字約 24.3px
DEFAULT_SIZE = 24
DEFAULT_WEIGHT = 500
GAME_BG = (49, 49, 49)        # 標籤按鈕底色 (grill 截圖量)
GAME_FG = (255, 255, 255)


@dataclass(frozen=True)
class Settings:
    font: str                 # 字型檔完整路徑
    size: int = DEFAULT_SIZE  # 1.0 尺度的字級 (px)
    weight: int | None = DEFAULT_WEIGHT   # 可變字型的字重軸; 非可變字型忽略
    fg: tuple = GAME_FG       # 文字顏色 (RGB)
    bg: tuple = GAME_BG       # 底色 (RGB)
    margin: int = 3           # 墨跡外框外留的邊 (px)

    def describe(self):
        d = asdict(self)
        d["font"] = Path(self.font).name
        return d


def find_font(name):
    """字型檔名或路徑 → 存在的完整路徑."""
    p = Path(name)
    if p.is_file():
        return str(p)
    for d in _FONT_DIRS:
        if (d / name).is_file():
            return str(d / name)
    raise ToolError(f"找不到字型「{name}」（找過 {', '.join(str(d) for d in _FONT_DIRS)}）")


def default_settings(client="tw", **overrides):
    """客戶端的預設渲染設定; overrides 可給 font/size/weight/... (None 的不覆寫)."""
    font = overrides.pop("font", None)
    if font is None:
        for name in DEFAULT_FONTS[client]:
            try:
                font = find_font(name)
                break
            except ToolError:
                continue
        else:
            raise ToolError(f"本機沒有{client}客戶端的預設字型（{'、'.join(DEFAULT_FONTS[client])}）")
    else:
        font = find_font(font)
    return replace(Settings(font=font), **{k: v for k, v in overrides.items() if v is not None})


def _font(settings, size):
    from PIL import ImageFont
    f = ImageFont.truetype(settings.font, size)
    if settings.weight is not None:
        try:
            axes = f.get_variation_axes()
        except OSError:          # 不是可變字型
            axes = []
        if axes:   # 只動字重軸, 其他軸用預設
            f.set_variation_by_axes([settings.weight if a["name"] in (b"Weight", "Weight")
                                     else a["default"] for a in axes])
    return f


def text_image(text, settings, scale=1.0, pad=None):
    """把字面畫成 BGR 影像 (緊貼墨跡外框 + pad px 邊; pad 預設 settings.margin×scale).

    scale: 字級倍率 (測試畫假截圖時用; 範本一律 1.0)。
    """
    from PIL import Image, ImageDraw
    size = max(4, round(settings.size * scale))
    font = _font(settings, size)
    w = size * (len(text) + 2)
    h = size * 3
    img = Image.new("RGB", (w, h), tuple(settings.bg))
    ImageDraw.Draw(img).text((size, size), text, font=font, fill=tuple(settings.fg))
    arr = np.asarray(img)[:, :, ::-1].copy()
    ink = np.abs(arr.astype(int) - np.array(settings.bg[::-1])).sum(2) > 60
    ys, xs = np.where(ink)
    if not len(xs):
        raise ToolError(f"字型 {Path(settings.font).name} 畫不出「{text}」")
    m = round(settings.margin * scale) if pad is None else pad
    y0, y1 = max(0, ys.min() - m), min(h, ys.max() + 1 + m)
    x0, x1 = max(0, xs.min() - m), min(w, xs.max() + 1 + m)
    return arr[y0:y1, x0:x1]


def templates(pool, settings):
    """快照的 29 個標籤 → {範本名: BGR 影像}; 範本名 = tag<id> (避開檔名裡的中文)."""
    return {template_name(t["id"]): text_image(t["name"], settings) for t in pool["tags"]}


def template_name(tag_id):
    return f"tag{int(tag_id):02d}"

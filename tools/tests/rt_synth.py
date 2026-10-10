"""公開招募辨識工具測試用的合成輸入: 迷你資料表與迷你快照.

(名稱刻意加前綴: tests/ 的引擎測試已有 synth.py, 同名模組會互相遮蔽。)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "tools", ROOT / "app", ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# 29 個招募標籤的台服 / 國服字面 (tagId 1-29, 與 gacha_table 的 gachaTags 同)
TAGS_TW = ["近衛幹員", "狙擊幹員", "重裝幹員", "醫療幹員", "輔助幹員", "術師幹員",
           "特種幹員", "先鋒幹員", "近戰位", "遠程位", "高級資深幹員", "控場", "爆發",
           "資深幹員", "治療", "支援", "新手", "費用回復", "輸出", "生存", "群攻",
           "防護", "減速", "削弱", "快速復活", "位移", "召喚", "支援機械", "元素"]
TAGS_CN = ["近卫干员", "狙击干员", "重装干员", "医疗干员", "辅助干员", "术师干员",
           "特种干员", "先锋干员", "近战位", "远程位", "高级资深干员", "控场", "爆发",
           "资深干员", "治疗", "支援", "新手", "费用回复", "输出", "生存", "群攻",
           "防护", "减速", "削弱", "快速复活", "位移", "召唤", "支援机械", "元素"]
TAG_ID = {name: i + 1 for i, name in enumerate(TAGS_TW)}


def gacha_table(tags, rows, header="※全部可能出現的幹員※", newline="\n"):
    """迷你 gacha_table: rows = [(星數, [名字, ...]), ...]; 名字可帶 <@rc.eml> 標記.

    newline: 國服的 recruitDetail 用字面的反斜線 n 換行 (傳 "\\\\n")。
    """
    parts = ["<@rc.title>公開招募說明</>", "", header, ""]
    for stars, names in rows:
        parts.append("★" * stars + newline + " / ".join(names))
        parts.append("--------------------")
    return {"gachaTags": [{"tagId": i + 1, "tagName": n, "tagGroup": i + 1}
                          for i, n in enumerate(tags)],
            "recruitDetail": "\n".join(parts)}


def char(name, rarity, profession, position, tag_list, key=None):
    """character_table 的一筆 (只放建池會讀的欄位)."""
    return key or f"char_{name}", {
        "name": name, "rarity": f"TIER_{rarity}", "profession": profession,
        "position": position, "tagList": list(tag_list)}


def character_table(*entries):
    return dict(entries)


def pool(operators, server="tw", rename=None):
    """迷你快照 (與建池產出同格式): operators = [(名字, 星數, [標籤字面...]), ...].

    職業 / 位置 / 資質標籤要自己寫進標籤字面 (快照裡的標籤集合本來就已含它們)。
    rename: {原字面: 換成的字面}——標籤的 tagId 不變, 只換畫面上的字。
    """
    names = list(TAGS_TW if server == "tw" else TAGS_CN)
    ids = {n: i + 1 for i, n in enumerate(names)}
    for old, new in (rename or {}).items():
        names[ids[old] - 1] = new
    return {"server": server, "source": {}, "tags": [{"id": i + 1, "name": n}
                                                     for i, n in enumerate(names)],
            "operators": [{"name": n, "rarity": r, "tags": sorted(ids[t] for t in tags)}
                          for n, r, tags in operators]}


# ---- 假招募畫面 (辨識入口用) -------------------------------------------------

def fake_screen(labels, scale=1.0, cells=None, distractor=True, size=None, settings=None):
    """畫一張假招募畫面: 淺灰底、五個深色標籤格 (白字置中)、格外一段含「幹員」的干擾文字.

    labels: 五格的字面 (None = 空格只畫底框); cells: 1.0 尺度的格子 (預設工具版面);
    size: 1.0 尺度的畫面大小 (預設工具基準)。
    """
    import numpy as np
    from recruit_tags import layout, render

    settings = settings or render.default_settings("tw")
    bw, bh = size or layout.BASE
    w, h = round(bw * scale), round(bh * scale)
    img = np.full((h, w, 3), 205, np.uint8)
    for label, (x, y, cw, ch) in zip(labels, cells or layout.CELLS):
        x0, y0 = round(x * scale), round(y * scale)
        x1, y1 = round((x + cw) * scale), round((y + ch) * scale)
        img[y0:y1, x0:x1] = settings.bg[::-1]
        if label:
            _paste_center(img, render.text_image(label, settings, scale=scale, pad=0),
                          (x0 + x1) / 2, (y0 + y1) / 2)
    if distractor:   # 原畫面上方的「可獲得的幹員」: 同款字形, 在格子外
        x, y, cw, ch = (cells or layout.CELLS)[0]
        box_y = round((y - 150) * scale)
        band = np.full((round(50 * scale), round(400 * scale), 3), settings.bg[::-1], np.uint8)
        _paste_center(band, render.text_image("可獲得的幹員", settings, scale=scale, pad=0),
                      band.shape[1] / 2, band.shape[0] / 2)
        x0 = round(x * scale)
        img[box_y:box_y + band.shape[0], x0:x0 + band.shape[1]] = band
    return img


def _paste_center(img, patch, cx, cy):
    ph, pw = patch.shape[:2]
    x0, y0 = round(cx - pw / 2), round(cy - ph / 2)
    img[y0:y0 + ph, x0:x0 + pw] = patch

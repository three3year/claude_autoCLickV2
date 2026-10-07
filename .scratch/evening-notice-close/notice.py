"""晚班開頭關公告: 建構、驗證、報告腳本共用的設定 (見 spec.md).

路徑、流程存檔讀寫、引擎與影格的共用沿用 busy-pause-fixed-rect/common.py (匯入成 bp)。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "busy-pause-fixed-rect"))

import common as bp  # noqa: E402,F401  (busy-pause-fixed-rect 的共用)

BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-07-evening-notice-close")
BACKUP_FLOWS = os.path.join(BACKUP, "arknights", "flows")
RESULTS = os.path.join(HERE, "results")

TIMEOUT = 2          # 新的第 1 步的逾時 (秒); 其餘設定照早班那一步
BUSY = "忙碌指示"

# 每版: 晚班存檔、搬來源的早班存檔、公告 X 的範本、規格寫定的固定矩形、要不要換忙碌指示。
# frames: 真引擎驗證的影格——有公告的 (影片, 幀, 影片座標的框) 與晚班示範影片 (找主畫面影格)。
# 簡中有公告的影格只在 demo5 (demo6 上沒有公告; 票 08 驗證固定矩形用的也是 demo5 這三格),
# demo1 是低位元率, 照實列出、不算數 (同票 08)。
# 繁中 demo2 的圓形叉叉出現在四個彈窗上, 第 186–216 幀那個是公告 (活動公告／系統公告／資訊速報)。
LANGS = {
    "cn": {
        "flow": "晚_簡中", "src": "早_簡中", "template": "公告关闭",
        "rect": {"kind": "rect", "x": 0.8597, "y": 0.0598, "w": 0.0792, "h": 0.1478},
        "swap_busy": False,
        "positive": [("demo5", n, (1509, 95, 56, 56)) for n in (285, 288, 291)],
        "low_bitrate": [("demo1", n, (1509, 95, 56, 56)) for n in (378, 393, 420)],
        "evening_video": "demo4",
    },
    "tw": {
        "flow": "晚_繁中", "src": "早_繁中", "template": "圓形叉叉",
        "rect": {"kind": "rect", "x": 0.6917, "y": 0.0674, "w": 0.2453, "h": 0.2344},
        "swap_busy": True,
        "positive": [("demo2", n, (1712, 110, 46, 46)) for n in (186, 192, 198, 204, 210, 216)],
        "low_bitrate": [],
        "evening_video": "demo3",
    },
}


def expected_first_step(lang):
    """規格寫定的新第 1 步 (Implementation Decisions); 讀回檢查拿它比, 不從早班推."""
    return {"type": "find_click", "interval": 0.3, "confirm": "gone", "onNotFound": "skip",
            "timeout": TIMEOUT, "offsetX": 0, "offsetY": 0,
            "target": {"template": LANGS[lang]["template"], "limit": dict(LANGS[lang]["rect"])},
            "action": "click", "button": "left", "clicks": 1, "updateOrigin": True}


def is_notice_step(step, lang):
    from automation import findtarget
    return (step.get("type") == "find_click"
            and findtarget.template(step) == LANGS[lang]["template"])


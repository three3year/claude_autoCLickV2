from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "busy-pause-fixed-rect"))

import common as bp  # noqa: E402,F401

BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-07-evening-notice-close")
BACKUP_FLOWS = os.path.join(BACKUP, "arknights", "flows")
RESULTS = os.path.join(HERE, "results")

TIMEOUT = 2
BUSY = "忙碌指示"

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
    return {"type": "find_click", "interval": 0.3, "confirm": "gone", "onNotFound": "skip",
            "timeout": TIMEOUT, "offsetX": 0, "offsetY": 0,
            "target": {"template": LANGS[lang]["template"], "limit": dict(LANGS[lang]["rect"])},
            "action": "click", "button": "left", "clicks": 1, "updateOrigin": True}


def is_notice_step(step, lang):
    from automation import findtarget
    return (step.get("type") == "find_click"
            and findtarget.template(step) == LANGS[lang]["template"])


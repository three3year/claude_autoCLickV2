"""`找圖目標`: 「找一張圖」的通用單位 (詞彙見 app/CONTEXT.md「找圖語意」).

存檔裡的找圖目標是步驟上的巢狀物件 (flowFormat 3)::

    {"template": "範本名",
     "limit":      {"kind": "origin", "x", "y", "w", "h"}   以原點為基準的矩形
                 | {"kind": "grid", "cells": [1..9]}         搜尋範圍九宮格 (由左上起依列編號)
     "pick":       {"kind": "top" | "left", "n": N}          由上到下 / 由左到右第 N 個
                 | {"kind": "near", "base": "origin" | "region", "x", "y"}  最接近指定點
     "colorCheck": true}

缺欄位＝不限定 / 分數最高 / 不比色。找圖步驟的找圖目標在 `target`, `確認圖`在
`confirmTarget`; 「點到下一步的圖出現」沿用下一步的 `target`。像素欄位 (原點
矩形、指定點) 與步驟偏移一樣存「當前基準機器」的尺度, 執行期 ×`畫面倍率`。

本模組維持輕量 (不 import cv2/numpy): 存檔格式、編輯器、執行器、影片轉流程
都從這裡讀寫找圖目標, 解析並執行一個找圖目標的邏輯也在這裡 (三處行為一致)。
"""

TARGET = "target"
CONFIRM_TARGET = "confirmTarget"

# flowFormat 2 的步驟欄位: 範本名直接掛在步驟上 (讀檔時單向遷移)
_V2_KEYS = (("template", TARGET), ("confirmTemplate", CONFIRM_TARGET))


# ================= 步驟上的找圖目標 =================

def target(step):
    """找圖步驟自己的找圖目標 (沒有＝空目標)."""
    return step.get(TARGET) or {}


def confirm_target(step):
    """`確認圖`的找圖目標 (沒有＝空目標)."""
    return step.get(CONFIRM_TARGET) or {}


def template(step):
    """找圖步驟的範本名 (未選＝空字串)."""
    return target(step).get("template", "")


def confirm_template(step):
    return confirm_target(step).get("template", "")


def uses_confirm_target(step):
    """`確認圖`是否生效: 只有動作為點擊、點擊後確認選「確認圖出現」時才有意義."""
    return (step.get("type") == "find_click"
            and step.get("action", "click") == "click"
            and step.get("confirm") == "appear")


def step_targets(step):
    """步驟上存在的找圖目標 [(鍵, 目標), ...] (改名/換算時走訪用)."""
    if step.get("type") != "find_click":
        return []
    return [(k, step[k]) for k in (TARGET, CONFIRM_TARGET)
            if isinstance(step.get(k), dict)]


def migrate_step(step):
    """flowFormat 2 → 3: 範本名與確認圖範本名搬進對應的找圖目標 (就地, 冪等).

    空的確認圖範本名不留空目標。回傳是否有改動。
    """
    changed = False
    for old, new in _V2_KEYS:
        if old not in step:
            continue
        name = step.pop(old)
        changed = True
        if isinstance(name, str) and name and not isinstance(step.get(new), dict):
            step[new] = {"template": name}
    return changed

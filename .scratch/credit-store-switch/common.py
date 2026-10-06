"""採購中心改成一個分岔: 建構與驗證腳本共用的路徑、優先順序與區塊定位 (見 spec.md).

流程存檔只經 app 的流程存檔模組 (app/flowfile.py) 讀寫。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
APP = os.path.join(ROOT, "app")
PROFILE = os.path.join(APP, "dist", "AutoClick", "profiles", "arknights")
FLOWS = os.path.join(PROFILE, "flows")
TEMPLATE_SRC = r"C:\Users\three\我的電腦\oCam Video\採購中心範本"
BACKUP = "app/dist/profiles-backup-2026-10-07-credit-store-switch/"

for p in (APP, os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

PREFIX = "採購_"
RETAKE = "待重拍_"
ROUNDS = 10            # 重複區段次數 (一頁 10 張卡)
NO_COLOR = {"技巧概要·卷2"}   # 比色例外: demo6 上比色 0.94, 差門檻一點

# 購買優先順序 = 分支順序 (兩版相同, 繁體名)
PRIORITY = [
    "加急許可", "招聘許可", "技巧概要·卷2", "技巧概要·卷1", "赤金", "龍門幣",
    "固源岩", "糖", "聚酸酯", "異鐵", "裝置", "酮凝集",
    "源岩", "代糖", "酯原料", "異鐵碎片", "破損裝置", "雙酮",
    "初級作戰記錄", "基礎作戰記錄", "碳素組", "碳素", "碳",
]
assert len(PRIORITY) == len(set(PRIORITY)) == 23

LANGS = {
    "tw": {"label": "繁中", "folder": "繁中", "flows": ["早_繁中"]},
    # 簡中: 改名前是 早_簡中_demo6, 改名後 (票 02) 它就是 早_簡中
    "cn": {"label": "簡中", "folder": "簡中", "flows": ["早_簡中_demo6", "早_簡中"]},
}

CREDIT = "收取信用"
RECRUIT = ("公開招募", "公开招募")
NAV = ("導航", "导航")
BUY = ("購買物品", "购买物品")


def flow_path(lang, name=None):
    """這個語系要改的流程存檔路徑 (name 給了就用它; 也可以直接給檔案路徑)."""
    import flowfile
    if name and os.path.isfile(name):
        return name
    names = [name] if name else LANGS[lang]["flows"]
    for n in names:
        p = os.path.join(FLOWS, n + flowfile.EXT)
        if os.path.isfile(p):
            return p
    raise SystemExit(f"找不到流程存檔: {'、'.join(names)}")


def template_name(item):
    return PREFIX + item


def _tmpl(step):
    from automation import findtarget
    return findtarget.template(step) if step.get("type") == "find_click" else ""


def _end_at_depth0(steps, i, end_type):
    """steps[i] 之後第一個同層的 end_type 標記索引 (區段巢狀以深度略過)."""
    depth = 0
    for j in range(i + 1, len(steps)):
        t = steps[j].get("type")
        if t in ("loop_start", "branch_start"):
            depth += 1
        elif t in ("loop_end", "branch_end"):
            if depth == 0:
                if t != end_type:
                    raise SystemExit(f"第 {j + 1} 步: 預期 {end_type}, 遇到 {t}")
                return j
            depth -= 1
    raise SystemExit(f"第 {i + 1} 步之後找不到 {end_type}")


def purchase_span(steps):
    """採購區塊的位置: (起, 迄) 使得 steps[起:迄] 是收取信用分岔之後、導航之前的步驟.

    迄 = 「導航 → 公開招募」的導航那一步; 收取信用分岔原樣不動。
    """
    credit = next((i for i, s in enumerate(steps) if _tmpl(s) == CREDIT), None)
    if credit is None:
        raise SystemExit("流程裡找不到收取信用")
    start = _end_at_depth0(steps, credit, "branch_end") + 1
    recruit = next((i for i in range(start, len(steps)) if _tmpl(steps[i]) in RECRUIT),
                   None)
    if recruit is None or not _tmpl(steps[recruit - 1]).startswith(NAV):
        raise SystemExit("收取信用之後找不到「導航 → 公開招募」")
    return start, recruit - 1


def buy_tail(section):
    """一件商品的買法: (條件步驟, 條件步驟之後到分支結尾的步驟).

    條件步驟＝區塊裡第一個「點到確認圖出現、確認圖是購買物品」的找圖步驟。
    """
    from automation import findtarget
    for i, s in enumerate(section):
        if (s.get("type") == "find_click" and s.get("confirm") == "appear"
                and findtarget.confirm_template(s) in BUY):
            tail = []
            for t in section[i + 1:]:
                if t.get("type") in ("branch_or", "branch_end"):
                    return s, tail
                if t.get("type") in ("branch_start", "loop_start", "loop_end"):
                    raise SystemExit("商品分支裡有巢狀區段, 不認得的寫法")
                tail.append(t)
    raise SystemExit("採購區塊裡找不到商品的條件步驟 (確認圖＝購買物品)")

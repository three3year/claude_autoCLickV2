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
ROUNDS = 10
NO_COLOR = {"技巧概要·卷2"}

PRIORITY = [
    "加急許可", "招聘許可", "技巧概要·卷2", "技巧概要·卷1", "赤金", "龍門幣",
    "固源岩", "糖", "聚酸酯", "異鐵", "裝置", "酮凝集",
    "源岩", "代糖", "酯原料", "異鐵碎片", "破損裝置", "雙酮",
    "初級作戰記錄", "基礎作戰記錄", "碳素組", "碳素", "碳",
]
assert len(PRIORITY) == len(set(PRIORITY)) == 23

LANGS = {
    "tw": {"label": "繁中", "folder": "繁中", "flows": ["早_繁中"]},
    "cn": {"label": "簡中", "folder": "簡中", "flows": ["早_簡中_demo6", "早_簡中"]},
}

CREDIT = "收取信用"
RECRUIT = ("公開招募", "公开招募")
NAV = ("導航", "导航")
BUY = ("購買物品", "购买物品")
GOT = ("獲得物資", "获得物资")


def flow_path(lang, name=None):
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


def item_of(template):
    return template[len(PREFIX):]


def _tmpl(step):
    from automation import findtarget
    return findtarget.template(step) if step.get("type") == "find_click" else ""


def _end_at_depth0(steps, i, end_type):
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

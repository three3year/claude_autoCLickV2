"""早班收取信用改成等物資彈窗出現: 建構、驗證、報告腳本共用的設定 (見 spec.md).

路徑、流程存檔讀寫、preflight、草稿同步沿用 busy-pause-fixed-rect/common.py (匯入成 bp);
商店模擬器沿用 credit-store-switch/sim.py (匯入成 css_sim)。兩個資料夾的共用模組都叫
`common`, 所以用 importlib 各自載成不同名字, 不靠 sys.path 順序。
"""
from __future__ import annotations

import copy
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")


def load_module(alias, path, common=None):
    """把 path 載成模組 alias; common 給了就在載入期間讓 `import common` 拿到它."""
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    saved = sys.modules.get("common")
    if common is not None:
        sys.modules["common"] = common
    try:
        sys.modules[alias] = mod
        spec.loader.exec_module(mod)
    finally:
        if common is not None:
            if saved is None:
                sys.modules.pop("common", None)
            else:
                sys.modules["common"] = saved
    return mod


bp = load_module("bp_common", os.path.join(SCRATCH, "busy-pause-fixed-rect", "common.py"))

from automation import findtarget  # noqa: E402  (bp 已把 app 放進 sys.path)


def css_sim():
    """credit-store-switch 的商店模擬器 (sim.py, 連它的 common)."""
    d = os.path.join(SCRATCH, "credit-store-switch")
    css_common = load_module("css_common", os.path.join(d, "common.py"))
    return load_module("css_sim", os.path.join(d, "sim.py"), common=css_common)


BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-08-credit-collect-confirm")
BACKUP_FLOWS = os.path.join(BACKUP, "arknights", "flows")


CREDIT = "收取信用"
GOT = ("獲得物資", "获得物资")
RECRUIT = ("公開招募", "公开招募")

# 每版: 流程存檔、現行編號 (1 起算) 的收取信用與緊接的物資彈窗那步、步驟數 (改前改後相同)。
# 編號只拿來核對 (存檔被別的改動挪過就中止), 定位一律靠內容。
LANGS = {
    "tw": {"flow": "早_繁中", "credit_no": 113, "got_no": 114, "steps": 212, "ticket": "01"},
    "cn": {"flow": "早_簡中", "credit_no": 124, "got_no": 125, "steps": 247, "ticket": "02"},
}

CHANGED = ("confirm", "confirmTarget", "onNotFound")   # 收取信用那一步只改這三個欄位


def ticket_backup(lang):
    """備份之後存檔又被別的改動動過時, 這張票另備的目錄."""
    return f"{BACKUP}-{LANGS[lang]['ticket']}"


def orig_flows(lang):
    """這一版改動前的流程資料夾: 另備的那份在就用它, 不然用本功能的備份."""
    extra = os.path.join(ticket_backup(lang), "arknights", "flows")
    return extra if os.path.isdir(extra) else BACKUP_FLOWS


def _tmpl(step):
    return findtarget.template(step) if step.get("type") == "find_click" else ""


def credit_index(steps, lang):
    """收取信用那一步的索引 (0 起算), 並核對它是收取信用分岔的條件、下一步是物資彈窗."""
    cfg = LANGS[lang]
    hits = [i for i, s in enumerate(steps) if _tmpl(s) == CREDIT]
    if len(hits) != 1:
        raise SystemExit(f"{cfg['flow']}: 收取信用的步驟有 {len(hits)} 個, 預期 1 個")
    i = hits[0]
    if i == 0 or steps[i - 1].get("type") != "branch_start":
        raise SystemExit(f"{cfg['flow']}: 第 {i + 1} 步收取信用不是分岔的條件步驟")
    if _tmpl(steps[i + 1]) not in GOT:
        raise SystemExit(f"{cfg['flow']}: 收取信用的下一步不是物資彈窗: {steps[i + 1]}")
    if (i + 1, i + 2, len(steps)) != (cfg["credit_no"], cfg["got_no"], cfg["steps"]):
        raise SystemExit(f"{cfg['flow']}: 收取信用在第 {i + 1} 步、共 {len(steps)} 步, "
                         f"跟規格寫的第 {cfg['credit_no']} 步、{cfg['steps']} 步不同")
    return i


def changed_step(step, got_step):
    """收取信用的新設定: 確認圖出現 (照抄下一步的找圖目標)、找不到時跳出; 其餘不動."""
    new = copy.deepcopy(step)
    new["confirm"] = "appear"
    new["confirmTarget"] = copy.deepcopy(findtarget.target(got_step))
    new["onNotFound"] = "break"
    return new


def recruit_index(steps, start):
    """start 之後第一個公開招募 (採購段最後的「導航 → 公開招募」)."""
    i = next((k for k in range(start, len(steps)) if _tmpl(steps[k]) in RECRUIT), None)
    if i is None:
        raise SystemExit("收取信用之後找不到公開招募")
    return i

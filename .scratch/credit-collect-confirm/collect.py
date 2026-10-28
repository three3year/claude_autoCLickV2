from __future__ import annotations

import copy
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")


def load_module(alias, path, common=None):
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

from automation import findtarget  # noqa: E402


def css_sim():
    d = os.path.join(SCRATCH, "credit-store-switch")
    css_common = load_module("css_common", os.path.join(d, "common.py"))
    return load_module("css_sim", os.path.join(d, "sim.py"), common=css_common)


BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-08-credit-collect-confirm")
BACKUP_FLOWS = os.path.join(BACKUP, "arknights", "flows")


CREDIT = "收取信用"
GOT = ("獲得物資", "获得物资")
RECRUIT = ("公開招募", "公开招募")

LANGS = {
    "tw": {"flow": "早_繁中", "credit_no": 113, "got_no": 114, "steps": 212, "ticket": "01"},
    "cn": {"flow": "早_簡中", "credit_no": 124, "got_no": 125, "steps": 247, "ticket": "02"},
}

CHANGED = ("confirm", "confirmTarget", "onNotFound")


def ticket_backup(lang):
    return f"{BACKUP}-{LANGS[lang]['ticket']}"


def orig_flows(lang):
    extra = os.path.join(ticket_backup(lang), "arknights", "flows")
    return extra if os.path.isdir(extra) else BACKUP_FLOWS


def _tmpl(step):
    return findtarget.template(step) if step.get("type") == "find_click" else ""


def credit_index(steps, lang):
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
    new = copy.deepcopy(step)
    new["confirm"] = "appear"
    new["confirmTarget"] = copy.deepcopy(findtarget.target(got_step))
    new["onNotFound"] = "break"
    return new


def recruit_index(steps, start):
    i = next((k for k in range(start, len(steps)) if _tmpl(steps[k]) in RECRUIT), None)
    if i is None:
        raise SystemExit("收取信用之後找不到公開招募")
    return i

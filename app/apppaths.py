"""app 用到的固定位置 (詞彙見 app/GLOSSARY.md「存檔與快取」; 佈局見 ADR 0015、0017 與
.scratch/project-cleanup/issues/09-packaged-layout-and-flow-location.md).

    流程存放區                         流程資料夾的預設位置 (開檔與新流程第一次存檔的對話框從這裡開)
        原始碼執行:        <repo>\\flows\\  (gitignore)
        打包版 (frozen):   exe 往上找得到本專案就是 <repo>\\flows\\, 找不到 %USERPROFILE%\\AutoClick\\
    本機狀態資料夾                     state.json (只記上次開的流程)、autoclick.log、「未存檔」快取
        打包版 (frozen):   %LOCALAPPDATA%\\AutoClick\\
        原始碼執行:        <repo>\\.local\\  (agent 冒煙開過的流程不會變成打包版下次自動開的那份)

打包版資料夾 (dist\\AutoClick\\) 裡沒有任何使用者資料: 部署＝整個換掉。
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_REPO_MARKER = os.path.join("app", "apppaths.py")


def _repo_above(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, _REPO_MARKER)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def flows_root():
    """`流程存放區`: 原始碼執行在 repo 的 flows; 打包版從 exe 往上找 repo, 找不到
    (整包拿到沒有 repo 的電腦) 退回 %USERPROFILE%\\AutoClick (ADR 0017)."""
    if getattr(sys, "frozen", False):
        repo = _repo_above(os.path.dirname(sys.executable))
        if repo is None:
            return os.path.join(os.path.expanduser("~"), "AutoClick")
        return os.path.join(repo, "flows")
    return os.path.join(REPO_ROOT, "flows")


def state_dir():
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "AutoClick")
    return os.path.join(REPO_ROOT, ".local")


def log_path():
    return os.path.join(state_dir(), "autoclick.log")


def unsaved_dir():
    return os.path.join(state_dir(), "unsaved")


def _state_path():
    return os.path.join(state_dir(), "state.json")


def load_state():
    try:
        with open(_state_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except OSError:
        pass


def last_flow():
    return load_state().get("last_flow")


def remember_last_flow(folder):
    save_state(dict(load_state(), last_flow=os.path.abspath(str(folder))))

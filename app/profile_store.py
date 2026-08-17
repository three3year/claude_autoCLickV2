"""Profile 目錄結構: 列舉/建立/應用狀態, 純檔案邏輯 (GUI 無關).

`profiles/<game>/` 是遊戲設定檔, 自帶:

    config.yaml       引擎參數 (覆蓋引擎預設; match/verify 門檻都在這)
    flows/            該 profile 的流程存檔 (含步驟草稿 _autosave.json)
    calibration.json  校準資料 (校準對名稱、基準距離、本機倍率與機器指紋)
    calibration/      `校準對`的兩張圖 (profile 自存, 與流程存檔解耦)
    workspace/        當前流程的可重建快取 (範本圖 + 登錄產物; 不進版控)

**沒有範本庫**: 範本圖住在流程存檔裡 (ADR 0006), profile 只負責上面這些。
一個資料夾算不算 profile, 看的是引擎參數設定檔在不在。

應用一次連一個 profile; UI 只提供切換與建立, 改名/刪除交給檔案總管。
部署後 (frozen) 使用者資料放 exe 旁, 原始碼執行用 repo 根目錄。
"""
import json
import os
import re
import shutil
import sys


def data_root():
    """使用者資料根目錄: frozen = exe 旁; 原始碼執行 = repo 根目錄."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def profiles_root(root=None):
    return os.path.join(root if root is not None else data_root(), "profiles")


CONFIG_NAME = "config.yaml"


def list_profiles(profiles_dir):
    """profiles_dir 下的 profile 名稱 (有引擎參數設定檔的資料夾才算).

    判定依據是設定檔而不是範本庫目錄——範本庫已經不存在了 (ADR 0006)。
    """
    try:
        entries = sorted(os.listdir(profiles_dir))
    except OSError:
        return []
    return [n for n in entries
            if os.path.isfile(os.path.join(profiles_dir, n, CONFIG_NAME))]


def default_config_path():
    """引擎預設 config 檔 (含註解), 建立新 profile 時整份複製."""
    from subject_detection import library as sd_library
    return os.path.join(os.path.dirname(os.path.abspath(sd_library.__file__)),
                        "default_config.yaml")


_BAD_NAME = re.compile(r'[\\/:*?"<>|]')


def create_profile(profiles_dir, name):
    """建立 `<profiles_dir>/<name>/` 目錄結構並帶入預設 config.

    回傳 profile 路徑; 名稱非法或已存在時丟 ValueError。
    """
    name = name.strip()
    if not name or name in (".", "..") or _BAD_NAME.search(name):
        raise ValueError(f"無效的 profile 名稱: {name!r}")
    dest = os.path.join(profiles_dir, name)
    if os.path.exists(dest):
        raise ValueError(f"profile「{name}」已存在")
    os.makedirs(os.path.join(dest, "flows"))
    shutil.copyfile(default_config_path(), os.path.join(dest, CONFIG_NAME))
    return dest


# ---- 應用狀態 (目前選用的 profile 等, 存在 profiles 根目錄下) ----

def _state_path(profiles_dir):
    return os.path.join(profiles_dir, "app_state.json")


def load_state(profiles_dir):
    try:
        with open(_state_path(profiles_dir), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(profiles_dir, state):
    try:
        os.makedirs(profiles_dir, exist_ok=True)
        with open(_state_path(profiles_dir), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except OSError:
        pass

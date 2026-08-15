"""Profile 目錄結構: 列舉/建立/應用狀態, 純檔案邏輯 (GUI 無關).

`profiles/<game>/` 是遊戲設定檔, 自帶:

    templates/    範本庫 (單檔範本或多截圖範本目錄; 引擎據此登錄)
    flows/        該 profile 的流程存檔 (含 _autosave.json)
    config.yaml   引擎參數 (覆蓋引擎預設; match/verify 門檻都在這)
    registered/   引擎登錄產物 (可重建, 不進版控)

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


def list_profiles(profiles_dir):
    """profiles_dir 下的 profile 名稱 (有 templates/ 子目錄的資料夾才算)."""
    try:
        entries = sorted(os.listdir(profiles_dir))
    except OSError:
        return []
    return [n for n in entries
            if os.path.isdir(os.path.join(profiles_dir, n, "templates"))]


def default_config_path():
    """引擎預設 config 檔 (含註解), 建立新 profile 時整份複製."""
    from subject_detection import profile as sd_profile
    return os.path.join(os.path.dirname(os.path.abspath(sd_profile.__file__)),
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
    os.makedirs(os.path.join(dest, "templates"))
    os.makedirs(os.path.join(dest, "flows"))
    shutil.copyfile(default_config_path(), os.path.join(dest, "config.yaml"))
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

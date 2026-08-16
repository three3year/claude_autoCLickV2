"""主體偵測引擎公開 API.

頂層符號以 PEP 562 惰性再匯出: `from subject_detection import Engine` 照常
可用, 但單獨 import 輕量子模組 (如 profile) 不會連帶載入 cv2/numpy——
應用層的開窗關鍵路徑依賴這一點 (ADR 0004)。
"""
__all__ = ["Engine", "QueryResult", "Profile"]


def __getattr__(name):
    if name in ("Engine", "QueryResult"):
        from . import engine
        return getattr(engine, name)
    if name == "Profile":
        from .profile import Profile
        return Profile
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

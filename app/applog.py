"""輕量檔案日誌: 偶發 UI 問題的事後蒐證.

清場進出、還原驗證重試、grab 轉移、保險絲觸發、未攔截例外都落地到
固定位置的日誌檔 (exe／repo 旁), 主視窗隱藏時錯誤不再無聲消失。
寫入失敗一律吞掉——日誌絕不能反過來影響主流程。
"""
import os
import threading
import time
import traceback

_LOCK = threading.Lock()
_MAX_BYTES = 1_000_000  # 超過即輪替一份 .1 (從簡, 最多保留兩份)
_path = None


def log_path():
    global _path
    if _path is None:
        import profile_store
        _path = os.path.join(profile_store.data_root(), "autoclick.log")
    return _path


def set_path(path):
    """覆寫日誌位置 (測試用)."""
    global _path
    _path = path


def log(event, **fields):
    """寫一行帶時間戳的事件紀錄: `時間 事件 k=v k=v ...`."""
    parts = [time.strftime("%Y-%m-%d %H:%M:%S"), event]
    parts += [f"{k}={v}" for k, v in fields.items()]
    _write(" ".join(parts))


def exception(event, etype, value, tb):
    """未攔截例外: 事件行 + 完整 traceback 一併落地."""
    text = "".join(traceback.format_exception(etype, value, tb)).rstrip()
    log(event, error=f"{etype.__name__}: {value}")
    _write(text)


def _write(text):
    try:
        with _LOCK:
            p = log_path()
            try:
                if os.path.getsize(p) > _MAX_BYTES:
                    os.replace(p, p + ".1")
            except OSError:
                pass  # 檔案不存在 (首次寫入) 或輪替失敗都直接續寫
            with open(p, "a", encoding="utf-8") as f:
                f.write(text + "\n")
    except Exception:
        pass

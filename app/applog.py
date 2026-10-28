import os
import threading
import time
import traceback

_LOCK = threading.Lock()
_MAX_BYTES = 1_000_000
_path = None


def log_path():
    global _path
    if _path is None:
        import apppaths
        _path = apppaths.log_path()
    return _path


def set_path(path):
    global _path
    _path = path


def log(event, **fields):
    """寫一行帶時間戳的事件紀錄: `時間 事件 k=v k=v ...`."""
    parts = [time.strftime("%Y-%m-%d %H:%M:%S"), event]
    parts += [f"{k}={v}" for k, v in fields.items()]
    _write(" ".join(parts))


def exception(event, etype, value, tb):
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
                pass
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(text + "\n")
    except Exception:
        pass

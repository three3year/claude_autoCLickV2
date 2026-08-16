"""applog: 單行事件、例外落地、大小輪替."""
import os

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import applog


def _use_tmp_log(tmp_path, monkeypatch):
    p = str(tmp_path / "autoclick.log")
    monkeypatch.setattr(applog, "_path", p)
    return p


def test_事件寫成帶時間戳的單行(tmp_path, monkeypatch):
    p = _use_tmp_log(tmp_path, monkeypatch)
    applog.log("clear.enter", windows=3, depth=1)
    lines = open(p, encoding="utf-8").read().splitlines()
    assert len(lines) == 1
    assert "clear.enter" in lines[0]
    assert "windows=3" in lines[0] and "depth=1" in lines[0]
    assert lines[0][:4].isdigit()  # 年份開頭的時間戳


def test_例外含完整traceback(tmp_path, monkeypatch):
    p = _use_tmp_log(tmp_path, monkeypatch)
    try:
        raise ValueError("boom")
    except ValueError as e:
        import sys
        applog.exception("callback.error", *sys.exc_info())
        del e
    text = open(p, encoding="utf-8").read()
    assert "callback.error" in text
    assert "ValueError: boom" in text
    assert "Traceback" in text


def test_超過大小上限即輪替(tmp_path, monkeypatch):
    p = _use_tmp_log(tmp_path, monkeypatch)
    monkeypatch.setattr(applog, "_MAX_BYTES", 100)
    for _ in range(10):
        applog.log("x", data="y" * 40)
    assert os.path.exists(p + ".1")  # 舊檔輪替保留
    assert os.path.getsize(p) < 500  # 現行檔已重新開始


def test_預設路徑在資料根目錄(monkeypatch):
    monkeypatch.setattr(applog, "_path", None)
    import profile_store
    assert applog.log_path() == os.path.join(profile_store.data_root(),
                                             "autoclick.log")


def test_寫入失敗不炸(tmp_path, monkeypatch):
    monkeypatch.setattr(applog, "_path", str(tmp_path / "no_dir" / "x.log"))
    applog.log("evt")  # 目錄不存在 → 安靜吞掉

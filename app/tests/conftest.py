import tkinter as tk

import pytest

from harness import Harness

import applog


@pytest.fixture(autouse=True, scope="session")
def _applog_to_tmp(tmp_path_factory):
    """整個測試 session 的檔案日誌改寫進暫存目錄.

    個別測試的 monkeypatch 還原後, 殘留視窗的 <Destroy> 事件仍可能觸發
    applog——沒有這層兜底就會把測試雜訊寫進 repo 根目錄的 autoclick.log。
    """
    applog._path = str(tmp_path_factory.mktemp("applog") / "autoclick.log")


@pytest.fixture
def harness(monkeypatch):
    return Harness(monkeypatch)


@pytest.fixture(scope="session")
def tkroot():
    """整個測試 session 共用一個 Tk 例項.

    同一程序內反覆建立/銷毀 Tk, 第二次 tk.Tk() 會偶發
    「couldn't read init.tcl」初始化失敗——共用一個就穩定。
    各測試自行設定需要的狀態 (withdraw/deiconify/geometry)。
    """
    r = tk.Tk()
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass

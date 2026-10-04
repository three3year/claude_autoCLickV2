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
    applog.set_path(str(tmp_path_factory.mktemp("applog") / "autoclick.log"))


@pytest.fixture(autouse=True)
def no_real_dialogs(monkeypatch):
    """任何測試都不准彈出真的 modal 對話框.

    測試跑在使用者的桌面上: 真的彈出來會卡住測試程序 (modal 等人來按), 還會
    蓋在使用者畫面上——這種打擾等同於測試失敗。全部換成記錄; 詢問類一律回
    「否」(最保守的那條路), 需要「是」的測試自己在測試裡 monkeypatch 覆蓋
    (測試本體的 setattr 比 autouse fixture 晚套用, 會贏)。實作在 `nodialogs.py`,
    一次性 GUI 冒煙腳本也用同一個。

    回傳 {"warning": [...], "info": [...], "error": [...]}, 想斷言就拿去用。
    """
    from nodialogs import stub_dialogs

    return stub_dialogs(monkeypatch.setattr)


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

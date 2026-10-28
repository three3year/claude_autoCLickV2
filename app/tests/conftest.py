import tkinter as tk

import pytest

from harness import Harness

import applog


@pytest.fixture(autouse=True, scope="session")
def _applog_to_tmp(tmp_path_factory):
    applog.set_path(str(tmp_path_factory.mktemp("applog") / "autoclick.log"))


@pytest.fixture(autouse=True)
def local_paths(tmp_path_factory, monkeypatch):
    import apppaths
    base = tmp_path_factory.mktemp("local")
    monkeypatch.setattr(apppaths, "state_dir", lambda: str(base / "state"))
    monkeypatch.setattr(apppaths, "flows_root", lambda: str(base / "flows"))
    return base


@pytest.fixture(autouse=True)
def no_real_dialogs(monkeypatch):
    from nodialogs import stub_dialogs

    return stub_dialogs(monkeypatch.setattr)


@pytest.fixture(autouse=True)
def inline_recognition(monkeypatch):
    """背景辨識預設當場做完 (同步): 不在意`辨識中`的測試照舊寫, 斷言緊接在操作後面.

    要看辨識中當下的樣子就換成 `harness.Held()` (扣住／放行); 真的開執行緒的
    `recognition.Threaded` 另有測試。
    """
    import recognition
    from harness import Inline
    monkeypatch.setattr(recognition, "DEFAULT_EXECUTOR", Inline)


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


@pytest.fixture
def main_app(tkroot, monkeypatch):
    """真的主視窗 (App) 建在 tkroot 底下的一個 Toplevel 上, 測完關掉.

    只換掉碰作業系統或背景的邊界: 引擎不載入 (維持載入中)、不掛 F12 與視窗事件鉤子、
    不跑 300ms 輪詢與保險絲 (要看輪詢結果的測試自己呼叫一次 `run_poll`)。
    視窗真的映射出來: 虛擬事件與 <Enter>/<Leave> 要映射後才派送。
    """
    import app as app_mod
    import enginehub

    poll = app_mod.App._poll

    def _no_loop(self):
        """取代輪詢與保險絲. 不能用 lambda: App 會用 after 排它, Tkinter 以「id＋函式名」
        當 Tcl 命令名, 視窗關掉後名字釋出, 下一個 App 的選單 lambda 可能拿到同一個名字,
        留著的 after 一到就誤觸那個選單項目 (2026-10-13 測試偶發多一步、卡在步驟對話框)."""

    monkeypatch.setattr(enginehub.EngineHub, "load", lambda self: None)
    monkeypatch.setattr(app_mod.hotkey, "start_stop_hotkey", lambda cb: None)
    monkeypatch.setattr(app_mod.win, "watch_window_changes", lambda cb: None)
    monkeypatch.setattr(app_mod.App, "_poll", _no_loop)
    monkeypatch.setattr(app_mod.App, "_fuse_check", _no_loop)
    top = tk.Toplevel(tkroot)
    a = app_mod.App(top)
    a.run_poll = lambda: poll(a)
    top.geometry("+40+40")
    top.update()
    yield a
    a.hub.state = enginehub.FAILED
    # 還沒到期的 after 一起取消: 它們的命令名跟著視窗釋出後可能被下一個測試重用 (見上)
    for pending in tkroot.tk.splitlist(tkroot.tk.call("after", "info")):
        tkroot.after_cancel(pending)
    try:
        top.destroy()
    except tk.TclError:
        pass

"""清場驗證式還原 + modal 堆疊的 GUI 整合測試 (真 Tk, 無真實輸入).

驗證「隱藏→還原→可見」一輪與 grab 歸屬; 可見性同時看 Tk (winfo_viewable)
與 win32 (IsWindowVisible), 不只做語法檢查。grab/modal 的「點擊被導走」
行為合成事件測不出 (繞過 grab 路由), 那部分靠打包版真實輸入冒煙。
"""
import ctypes
import tkinter as tk

import harness  # noqa: F401  # 先把 app/ 加進 sys.path
import pytest

import applog
import ui_grab
import ui_overlay
from window_coord import WindowCoordinator

user32 = ctypes.windll.user32
GA_ROOT = 2


def _os_visible(w):
    return bool(user32.IsWindowVisible(user32.GetAncestor(w.winfo_id(), GA_ROOT)))


@pytest.fixture
def fresh(monkeypatch, tmp_path):
    """日誌寫進暫存目錄、堆疊與清場狀態每個測試重來."""
    monkeypatch.setattr(applog, "_path", str(tmp_path / "autoclick.log"))
    monkeypatch.setattr(ui_grab, "coord", WindowCoordinator())
    monkeypatch.setattr(ui_overlay, "_hide_state",
                        {"depth": 0, "saved": [], "stale_tops": []})
    return tmp_path


@pytest.fixture
def root(tkroot, fresh):
    r = tkroot
    for c in list(r.winfo_children()):
        c.destroy()
    try:
        r.grab_release()
    except tk.TclError:
        pass
    r.state("normal")
    r.geometry("240x140+80+80")
    r.deiconify()
    r.update()
    yield r
    for c in list(r.winfo_children()):
        try:
            c.destroy()
        except tk.TclError:
            pass
    try:
        r.grab_release()
        r.withdraw()  # 不留視窗打擾後續非 GUI 測試
    except tk.TclError:
        pass


def test_清場一輪_隱藏還原皆確認可見(root, fresh):
    dlg = tk.Toplevel(root)
    dlg.geometry("180x100+140+140")
    root.update()
    assert root.winfo_viewable() and dlg.winfo_viewable()

    with ui_overlay.screen_clear(root):
        root.update()
        assert not root.winfo_viewable() and not _os_visible(root)
        assert not dlg.winfo_viewable() and not _os_visible(dlg)

    # 離場即已完成 map 驗證, 不需要再「等一下」
    assert root.winfo_viewable() and _os_visible(root)
    assert dlg.winfo_viewable() and _os_visible(dlg)
    log = open(str(fresh / "autoclick.log"), encoding="utf-8").read()
    assert "clear.enter" in log and "clear.exit" in log


def test_巢狀清場只有最外層還原(root, fresh):
    with ui_overlay.screen_clear(root):
        with ui_overlay.screen_clear(root):
            root.update()
            assert not root.winfo_viewable()
        root.update()
        assert not root.winfo_viewable()  # 內層離場不還原
    assert root.winfo_viewable()


def test_zoomed快照還原(root, fresh):
    root.state("zoomed")
    root.update()
    with ui_overlay.screen_clear(root):
        root.update()
    assert root.state() == "zoomed"


def test_迷你視窗類刻意隱藏不被還原誤觸(root, fresh):
    hidden = tk.Toplevel(root)
    hidden.geometry("100x60+300+300")
    hidden.withdraw()  # 刻意隱藏 (執行流程迷你視窗顯隱)
    root.update()
    with ui_overlay.screen_clear(root):
        root.update()
    assert not hidden.winfo_viewable()  # 不在清單上的視窗一律不碰


def test_清場中對話框被銷毀_跳過還原不炸(root, fresh):
    dlg = tk.Toplevel(root)
    dlg.geometry("120x80+150+150")
    root.update()
    with ui_overlay.screen_clear(root):
        root.update()
        dlg.destroy()
    assert root.winfo_viewable()


def test_modal堆疊_關閉上層grab回下層(root, fresh):
    a = tk.Toplevel(root)
    a.geometry("140x90+130+130")
    root.update()
    ui_grab.register_modal(a)
    root.update()
    assert root.grab_current() is a

    b = tk.Toplevel(root)
    b.geometry("120x70+160+160")
    root.update()
    ui_grab.register_modal(b)
    root.update()
    assert root.grab_current() is b  # grab 永遠在堆頂

    b.destroy()
    root.update()
    assert root.grab_current() is a  # 關掉上層, grab 回到下層

    a.destroy()
    root.update()
    assert root.grab_current() is None  # 堆空: 主視窗正常互動, 不設 grab


def test_中途關閉非堆頂_grab歸屬仍正確(root, fresh):
    a, b = tk.Toplevel(root), tk.Toplevel(root)
    a.geometry("140x90+130+130")
    b.geometry("120x70+160+160")
    root.update()
    ui_grab.register_modal(a)
    ui_grab.register_modal(b)
    root.update()
    a.destroy()  # 中途關閉非堆頂
    root.update()
    assert root.grab_current() is b
    b.destroy()


def test_清場後grab交還堆頂(root, fresh):
    dlg = tk.Toplevel(root)
    dlg.geometry("140x90+130+130")
    root.update()
    ui_grab.register_modal(dlg)
    root.update()
    assert root.grab_current() is dlg

    with ui_overlay.screen_clear(root, extra=(dlg,)):
        root.update()
        # 清場中: 隱形視窗不得持有 grab (握著 grab 的隱形視窗＝整個 App 卡死)
        assert ui_grab.ui_theme.safe_grab_current(root) is None

    assert dlg.winfo_viewable()
    assert root.grab_current() is dlg  # 離場後 grab 歸堆頂 (非快照持有者)

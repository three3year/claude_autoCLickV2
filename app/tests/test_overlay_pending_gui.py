import time
import tkinter as tk

import numpy as np
import pytest

import harness

import ui_overlay
from test_screen_clear_gui import fresh, root  # noqa: F401

SHOT = (np.full((300, 400, 3), 60, np.uint8), (0, 0))


class _Pending:
    def __init__(self, state="pending", mark=None):
        self.state, self.mark = state, mark

    def status(self):
        return self.state


@pytest.fixture
def no_grab(monkeypatch):
    def grab(*a, **k):
        raise AssertionError("給了預先截好的圖就不該自己截")
    monkeypatch.setattr(ui_overlay.capture, "grab", grab)


def _drive(root, *steps, ms=120):
    errors = []
    deadline = time.monotonic() + 10

    def run(i):
        def go():
            top = getattr(root, "_pick_top", None)
            if i == 0 and (top is None or not top.winfo_viewable()):
                if time.monotonic() < deadline:
                    root.after(30, go)
                else:
                    errors.append(AssertionError("覆蓋層沒出現"))
                    if top is not None:
                        top._done_var.set(1)
                return
            try:
                cv = next(c for c in top.winfo_children() if isinstance(c, tk.Canvas))
                steps[i](cv)
            except BaseException as e:
                errors.append(e)
                if top is not None and top.winfo_exists():
                    top._done_var.set(1)
                return
            if i + 1 < len(steps):
                run(i + 1)
        root.after(ms, go)
    run(0)
    return errors


def _hint(cv):
    first = next(i for i in cv.find_all() if cv.type(i) == "text")
    return cv.itemcget(first, "text")


def _click(cv, x, y):
    cv.event_generate("<Motion>", x=x, y=y)
    cv.event_generate("<ButtonPress-1>", x=x, y=y)
    cv.event_generate("<ButtonRelease-1>", x=x, y=y)


def test_顯示預先截好的圖_待定時提示辨識中_好了換回原說明(root, no_grab):
    p = _Pending()
    seen = {}

    def busy(cv):
        seen["busy"] = _hint(cv)
        seen["size"] = (cv.winfo_toplevel().winfo_width(), cv.winfo_toplevel().winfo_height())
        p.state = "ready"

    def ready(cv):
        seen["ready"] = _hint(cv)
        cv.event_generate("<Escape>")
    errors = _drive(root, busy, ready)
    r = ui_overlay.pick(root, "region", "框一塊", shot=SHOT, pending=p)
    assert not errors, errors
    assert r is None
    assert seen["size"] == (400, 300), "覆蓋層就是那張截圖的大小"
    assert seen["busy"].startswith(ui_overlay.BUSY_HINT)
    assert seen["ready"] == "框一塊　（直接點選＝取用高亮框，拖曳＝自訂範圍，Esc 取消）"


def test_待定結果失敗_覆蓋層立刻結束回中止(root, no_grab):
    p = _Pending()

    def fail(cv):
        p.state = "failed"
    errors = _drive(root, fail)
    r = ui_overlay.pick(root, "region", "框一塊", shot=SHOT, pending=p)
    assert not errors, errors
    assert r is ui_overlay.ABORT


def test_原點晚到才畫_待定時點擊照收_結果標記先點(root, no_grab):
    p = _Pending()
    seen = {}

    def pending(cv):
        seen["marks"] = cv.find_withtag("mark")
        seen["hint"] = _hint(cv)
        _click(cv, 50, 60)
    errors = _drive(root, pending)
    r = ui_overlay.pick(root, "point", "點一下指定點", shot=SHOT, pending=p, late="mark")
    assert not errors, errors
    assert seen["marks"] == () and "◎ 原點還在算" in seen["hint"]
    assert r == {"screenX": 50, "screenY": 60, "early": True}


def test_原點算好後畫出_點擊不再標先點(root, no_grab):
    p = _Pending()
    seen = {}

    def arrive(cv):
        p.state, p.mark = "ready", (100, 100)

    def look(cv):
        seen["marks"] = len(cv.find_withtag("mark"))
        seen["hint"] = _hint(cv)
        _click(cv, 130, 90)
    errors = _drive(root, arrive, look)
    r = ui_overlay.pick(root, "point", "點一下指定點", shot=SHOT, pending=p, late="mark")
    assert not errors, errors
    assert seen["marks"] == 2 and seen["hint"] == "點一下指定點　（◎＝原點，Esc 取消）"
    assert r == {"screenX": 130, "screenY": 90}


def test_拾取座標待定時只收點一下_原點到了以後照原點算(root, no_grab):
    p = _Pending()

    def early(cv):
        _click(cv, 70, 80)
    errors = _drive(root, early)
    r = ui_overlay.pick(root, "line", "點一下", shot=SHOT, pending=p, late="base")
    assert not errors, errors
    assert r == {"endX": 70, "endY": 80, "early": True}

    p = _Pending()

    def arrive(cv):
        p.state, p.mark = "ready", (20, 30)

    def click(cv):
        _click(cv, 70, 80)
    errors = _drive(root, arrive, click)
    r = ui_overlay.pick(root, "line", "點一下", shot=SHOT, pending=p, late="base")
    assert not errors, errors
    assert (r["dx"], r["dy"], r["startX"], r["startY"]) == (50, 50, 20, 30)


def test_原點確定推不出且還沒點_回NO_MARK(root, no_grab):
    p = _Pending()

    def none(cv):
        p.state = "ready"
    errors = _drive(root, none)
    r = ui_overlay.pick(root, "point", "點一下", shot=SHOT, pending=p, late="mark")
    assert not errors, errors
    assert r is ui_overlay.NO_MARK


def test_點原點模式_原點算好就自己結束_推不出就等使用者點(root, no_grab):
    p = _Pending()
    seen = {}

    def busy(cv):
        seen["busy"] = _hint(cv)
        p.state, p.mark = "ready", (120, 80)
    errors = _drive(root, busy)
    r = ui_overlay.pick(root, "point", "先點一下原點", shot=SHOT, pending=p, late="origin")
    assert not errors, errors
    assert seen["busy"].startswith(ui_overlay.BUSY_HINT)
    assert r == {"screenX": 120, "screenY": 80, "auto": True}

    p = _Pending()

    def none(cv):
        p.state = "ready"

    def click(cv):
        seen["hint"] = _hint(cv)
        _click(cv, 33, 44)
    errors = _drive(root, none, click)
    r = ui_overlay.pick(root, "point", "先點一下原點", shot=SHOT, pending=p, late="origin")
    assert not errors, errors
    assert seen["hint"] == "先點一下原點　（Esc 取消）"
    assert r == {"screenX": 33, "screenY": 44}

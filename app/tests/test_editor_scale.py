"""編輯器的拾取與截範本用編輯器倍率 (flow-scale 票 04, ADR 0009).

編輯器從螢幕取得的東西都換回`流程尺度`再存: 座標類拾取 (座標點擊、拖曳、
限定範圍、指定點) 除以編輯器倍率; 截下的範本圖以 1/倍率縮放 (倍率 1 原圖照存);
上傳的圖照原樣。預設原點推算與比對測試也用編輯器倍率。
拾取覆蓋層與清場以樁取代, 對話框照常用 `_Driver` 真的按按鈕。
"""
import contextlib
import os

import numpy as np
import pytest

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import app as app_mod
import enginehub
import flowfile
import ui_dialogs
from automation import findtarget, imgio
from test_template_picker import TITLE, _Driver, _open, _PickApp

REGION = [100, 200, 800, 600]


class _EditApp(_PickApp):
    """步驟對話框需要的欄位 (沿用選範本對話框的最小 App)."""

    def __init__(self, root, profile_dir, scale):
        super().__init__(root, profile_dir)
        self.editor_scale = scale
        self.scan_region = REGION


@pytest.fixture
def make_app(tkroot, tmp_path, monkeypatch):
    tkroot.deiconify()
    tkroot.geometry("+40+40")
    tkroot.update()
    monkeypatch.setattr(ui_dialogs.ui_overlay, "screen_clear",
                        lambda root, extra=(): contextlib.nullcontext())
    yield lambda scale: _EditApp(tkroot, tmp_path, scale)
    tkroot.withdraw()


def _overlay(monkeypatch, result):
    calls = []

    def pick(root, mode, prompt, **kw):
        calls.append((mode, kw))
        return result
    monkeypatch.setattr(ui_dialogs.ui_overlay, "pick", pick)
    return calls


def _edit(app, step, *actions, title):
    """開步驟對話框, 依序做 actions, 回傳對話框的結果 step."""
    d = _Driver(app.root, title)
    d.run(*actions)
    got = ui_dialogs.edit_step(app, step)
    if d.error is not None:
        raise d.error
    return got


def _press(text):
    return lambda dr: dr.press(text)


# ---------- 座標類拾取 ----------

def test_絕對座標點擊_拾取值除以編輯器倍率(make_app, monkeypatch):
    app = make_app(2.0)
    _overlay(monkeypatch, {"screenX": 300, "screenY": 400})
    got = _edit(app, {"type": "click", "mode": "abs", "x": 0, "y": 0},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert (got["x"], got["y"]) == (100, 100), "(300-100)/2, (400-200)/2"


def test_拖曳兩端點_拾取值除以編輯器倍率(make_app, monkeypatch):
    app = make_app(0.5)
    _overlay(monkeypatch, {"startX": 110, "startY": 210,
                           "endX": 130, "endY": 260})
    got = _edit(app, {"type": "drag", "mode": "abs", "x1": 0, "y1": 0,
                      "x2": 0, "y2": 0},
                _press("截圖拾取"), _press("確定"), title="新增：滑鼠拖曳")
    assert (got["x1"], got["y1"], got["x2"], got["y2"]) == (20, 20, 60, 120)


def test_相對座標_預設原點推算用編輯器倍率_拾取值也除以它(make_app, monkeypatch):
    app = make_app(2.0)
    app.steps = [{"type": "click", "mode": "abs", "x": 30, "y": 40}]
    calls = _overlay(monkeypatch, {"dx": 50, "dy": -30})
    got = _edit(app, {"type": "click", "mode": "prev", "x": 0, "y": 0,
                      "_index": 1},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    mode, kw = calls[0]
    assert kw["base"] == (100 + 60, 200 + 80), "原點＝範圍原點＋偏移×倍率"
    assert (got["x"], got["y"]) == (25, -15)


def test_倍率1時拾取值原樣(make_app, monkeypatch):
    app = make_app(1.0)
    _overlay(monkeypatch, {"screenX": 333, "screenY": 444})
    got = _edit(app, {"type": "click", "mode": "abs", "x": 0, "y": 0},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert (got["x"], got["y"]) == (233, 244)


def _target_dialog(app, monkeypatch, tgt, *actions):
    d = _Driver(app.root, "找圖設定")
    d.run(*actions)
    got = ui_dialogs.edit_target_opts(app, app.root, tgt, "找圖設定",
                                      origin_fn=lambda k: (500, 500))
    if d.error is not None:
        raise d.error
    return got


def test_限定範圍框選_除以編輯器倍率(make_app, monkeypatch):
    app = make_app(2.0)
    _overlay(monkeypatch, {"screenX": 400, "screenY": 520, "w": 300,
                           "h": 100})
    tgt = {"template": "a", "limit": {"kind": "origin", "x": 0, "y": 0,
                                      "w": 10, "h": 10}}
    got = _target_dialog(app, monkeypatch, tgt, _press("框選"), _press("確定"))
    assert got["limit"] == {"kind": "origin", "x": -50, "y": 10,
                            "w": 150, "h": 50}


def test_指定點_除以編輯器倍率(make_app, monkeypatch):
    app = make_app(2.0)
    _overlay(monkeypatch, {"screenX": 560, "screenY": 440})
    tgt = {"template": "a", "pick": {"kind": "near", "base": "origin",
                                     "x": 0, "y": 0}}
    got = _target_dialog(app, monkeypatch, tgt, _press("點選"), _press("確定"))
    assert got["pick"] == {"kind": "near", "base": "origin", "x": 30, "y": -30}


def test_拾取不因校準狀態被擋(make_app, monkeypatch):
    """舊模型的「未校準擋拾取」已退場: 有沒有校準對都直接拾取."""
    app = make_app(1.0)
    app.flow_cal = None
    _overlay(monkeypatch, {"screenX": 300, "screenY": 400})
    got = _edit(app, {"type": "click", "mode": "abs", "x": 0, "y": 0},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert got is not None and (got["x"], got["y"]) == (200, 200)


# ---------- 截範本 ----------

def _shot(w=40, h=20):
    img = np.zeros((h, w, 3), np.uint8)
    img[:, : w // 2] = (10, 200, 30)
    return {"img": img, "screenX": 10, "screenY": 20, "w": w, "h": h}


def test_主視窗截圖_倍率k時以1除k縮放後存(make_app):
    app = make_app(2.0)
    name = app.save_captured(_shot(40, 20))
    assert imgio.imread(app.ws.path_of(name)).shape[:2] == (10, 20)
    assert app.ws.pos_of(name) == [30, 30], "pos 是截圖當下的螢幕座標, 不換算"


def test_主視窗截圖_倍率1時與原圖逐位元相同(make_app, tmp_path):
    app = make_app(1.0)
    shot = _shot(41, 23)
    name = app.save_captured(shot)
    ref = str(tmp_path / "ref.png")
    imgio.imwrite(ref, shot["img"])
    with open(app.ws.path_of(name), "rb") as a, open(ref, "rb") as b:
        assert a.read() == b.read()


def test_選範本對話框現場截圖_也換回流程尺度(make_app):
    app = make_app(0.5)
    app.shot = _shot(40, 20)
    d = _Driver(app.root, TITLE)
    got = _open(app, d, lambda dr: (dr.press("截圖新增"), dr.press("確定")))
    assert imgio.imread(app.ws.path_of(got)).shape[:2] == (40, 80)


def test_上傳的範本不縮放(make_app, monkeypatch, tmp_path):
    app = make_app(2.0)
    src = str(tmp_path / "up.png")
    imgio.imwrite(src, _shot(40, 20)["img"])
    monkeypatch.setattr(app_mod.filedialog, "askopenfilenames",
                        lambda **kw: [src])
    app._select_tmpl_row = lambda name: None   # 面板不在這個最小 App 裡
    app.upload_template()
    [name] = app.ws.names()
    assert imgio.imread(app.ws.path_of(name)).shape[:2] == (20, 40)


# ---------- 比對測試 ----------

def test_比對測試用編輯器倍率當畫面倍率與預期尺度(make_app, monkeypatch):
    app = make_app(0.9)
    app.hub.state = enginehub.READY
    app.profile = type("P", (), {"templates": {"a": object()},
                                 "config": {"match_threshold": 0.6,
                                            "verify_threshold": 0.8}})()
    app.hub.ensure_template = lambda name: None
    app.ensure_registered = lambda: None
    app.detector = None
    screen = np.zeros((60, 80, 3), np.uint8)
    monkeypatch.setattr(ui_dialogs.capture, "grab",
                        lambda region=None: (screen, (100, 200)))
    monkeypatch.setattr(ui_dialogs.time, "sleep", lambda s: None)
    seen = []

    def fake_find(tgt, detector, scr, org, origin=None, scale=1.0):
        seen.append(scale)
        return findtarget.Found(tgt, reason="none")
    monkeypatch.setattr(ui_dialogs.findtarget, "find", fake_find)
    ui_dialogs.show_match_test(app, {"template": "a"})
    for w in app.root.winfo_children():
        if getattr(w, "title", None) and w.title() == "比對測試結果":
            w.destroy()
    assert seen == [0.9]

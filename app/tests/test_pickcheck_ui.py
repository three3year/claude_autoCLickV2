"""`拾取檢查`的編輯器接線 (scale-range 票 03/04/05): 只警告不擋存檔.

- 矩形餘裕: 找圖設定子對話框框完固定矩形, 對話框內出現警告字樣 (通過則清除), 確定照存。
- 縮放餘裕 / 唯一: 見下方各節 (票 04/05)。
拾取覆蓋層以樁取代, 校準用的截圖走假偵測器, 對話框照常用 `_Driver` 真的按按鈕。
"""
import contextlib

import numpy as np

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import ui_dialogs
from automation import imgio
from test_editor_scale import _press, make_app  # noqa: F401
from test_fixed_rect_ui import FIXED_ZH, _choose, _labels, _target_dialog


def _overlay(monkeypatch, w, h):
    """拾取樁: 框選回傳 (300,350) w×h 的矩形."""
    @contextlib.contextmanager
    def screen_clear(root, extra=()):
        yield

    monkeypatch.setattr(ui_dialogs.ui_overlay, "screen_clear", screen_clear)
    monkeypatch.setattr(ui_dialogs.ui_overlay, "pick",
                        lambda root, mode, prompt, **kw: {
                            "screenX": 300, "screenY": 350, "w": w, "h": h})


def _template(app, name, w, h):
    imgio.imwrite(app.ws.path_of(name), np.zeros((h, w, 3), np.uint8))


def _warn_labels(dlg):
    return [t for t in _labels(dlg) if t.startswith("⚠")]


# ---------- 矩形餘裕 ----------

def test_框出不足的矩形_對話框出現矩形餘裕警告_確定照存(make_app, monkeypatch):
    app = make_app(1.0)
    _template(app, "a", 50, 50)
    _overlay(monkeypatch, 58, 58)
    seen = {}

    def look(dr):
        seen["warn"] = _warn_labels(dr.dlg)
    got = _target_dialog(app, {"template": "a"}, _choose(FIXED_ZH),
                         _press("在畫面上框選"), look, _press("確定"))
    assert len(seen["warn"]) == 1
    assert "至少要框 70×70" in seen["warn"][0] and "58×58" in seen["warn"][0]
    assert got["limit"] == {"kind": "rect", "x": 150, "y": 120, "w": 58, "h": 58}, \
        "只警告不擋存檔"


def test_餘裕足夠_沒有警告(make_app, monkeypatch):
    app = make_app(1.0)
    _template(app, "a", 50, 50)
    _overlay(monkeypatch, 80, 72)
    seen = {}

    def look(dr):
        seen["warn"] = _warn_labels(dr.dlg)
    _target_dialog(app, {"template": "a"}, _choose(FIXED_ZH),
                   _press("在畫面上框選"), look, _press("確定"))
    assert seen["warn"] == []


def test_餘裕以流程尺度算_倍率不是1時框選值先換回(make_app, monkeypatch):
    """倍率 2: 螢幕上框 120×120 → 流程尺度 60×60, 對 50×50 的範本仍不足."""
    app = make_app(2.0)
    _template(app, "a", 50, 50)
    _overlay(monkeypatch, 120, 120)
    seen = {}

    def look(dr):
        seen["warn"] = _warn_labels(dr.dlg)
    got = _target_dialog(app, {"template": "a"}, _choose(FIXED_ZH),
                         _press("在畫面上框選"), look, _press("確定"))
    assert got["limit"]["w"] == 60
    assert any("60×60" in t and "70×70" in t for t in seen["warn"])


def test_還沒選範本就框矩形_不誤報(make_app, monkeypatch):
    app = make_app(1.0)
    _overlay(monkeypatch, 10, 10)
    seen = {}

    def look(dr):
        seen["warn"] = _warn_labels(dr.dlg)
    _target_dialog(app, {"template": ""}, _choose(FIXED_ZH),
                   _press("在畫面上框選"), look, _press("確定"))
    assert seen["warn"] == []


def test_重新打開既有的不足矩形_也看得到警告_重拖夠大就清除(make_app, monkeypatch):
    app = make_app(1.0)
    _template(app, "a", 50, 50)
    _overlay(monkeypatch, 90, 90)
    seen = {}

    def before(dr):
        seen["before"] = _warn_labels(dr.dlg)

    def after(dr):
        seen["after"] = _warn_labels(dr.dlg)
    old = {"kind": "rect", "x": 0, "y": 0, "w": 58, "h": 58}
    _target_dialog(app, {"template": "a", "limit": old}, before,
                   _press("在畫面上框選"), after, _press("確定"))
    assert len(seen["before"]) == 1 and "70×70" in seen["before"][0]
    assert seen["after"] == []

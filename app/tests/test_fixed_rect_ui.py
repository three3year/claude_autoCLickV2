"""`固定矩形`的編輯器拖框 (busy-pause-fixed-rect 票 04).

找圖設定子對話框 (找圖步驟與確認圖共用) 的限定範圍選「固定矩形」, 按「在畫面上
框選」拖一個框, 存成搜尋範圍的比例。拾取覆蓋層以樁取代 (記下是不是在清場裡
叫的), 對話框照常用 `_Driver` 真的按按鈕、真的發 <<ComboboxSelected>>。
"""
import contextlib

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import ui_dialogs
from test_editor_scale import REGION, _edit, _press, make_app  # noqa: F401
from test_template_picker import _all, _btn, _Driver

FIXED_ZH = ui_dialogs.LIMIT_ZH["rect"]
# REGION＝[100, 200, 800, 600]: 框 (300,350) 400×150 ＝ (25%,25%) 50%×25%
BOX = {"screenX": 300, "screenY": 350, "w": 400, "h": 150}
RATIO = {"kind": "rect", "x": 0.25, "y": 0.25, "w": 0.5, "h": 0.25}


def _overlay(monkeypatch):
    """拾取樁: 回傳 BOX, 並記下 (模式, 當下是否在清場裡)."""
    state = {"clearing": 0}
    calls = []

    @contextlib.contextmanager
    def screen_clear(root, extra=()):
        state["clearing"] += 1
        try:
            yield
        finally:
            state["clearing"] -= 1

    def pick(root, mode, prompt, **kw):
        calls.append((mode, state["clearing"] > 0))
        return dict(BOX)
    monkeypatch.setattr(ui_dialogs.ui_overlay, "screen_clear", screen_clear)
    monkeypatch.setattr(ui_dialogs.ui_overlay, "pick", pick)
    return calls


def _choose(text):
    """限定範圍下拉選 text (真的發選取事件)."""
    def act(dr):
        cb = next(w for w in _all(dr.dlg) if w.winfo_class() == "TCombobox"
                  and text in w.cget("values"))
        cb.set(text)
        cb.event_generate("<<ComboboxSelected>>")
        dr._update()
    return act


def _labels(dlg):
    return [str(w.cget("text")) for w in _all(dlg)
            if w.winfo_class() == "TLabel"]


def _target_dialog(app, tgt, *actions):
    d = _Driver(app.root, "找圖設定")
    d.run(*actions)
    got = ui_dialogs.edit_target_opts(app, app.root, tgt, "找圖設定")
    if d.error is not None:
        raise d.error
    return got


def test_選固定矩形_框選_確定_存成搜尋範圍的比例(make_app, monkeypatch):
    app = make_app(2.0)    # 比例與編輯器倍率無關
    calls = _overlay(monkeypatch)
    got = _target_dialog(app, {"template": "a"}, _choose(FIXED_ZH),
                         _press("在畫面上框選"), _press("確定"))
    assert got["limit"] == RATIO
    assert calls == [("region", True)], "region 模式, 在清場裡框選"


def test_重新打開顯示原值_確定不變(make_app, monkeypatch):
    app = make_app(1.0)
    _overlay(monkeypatch)
    seen = {}

    def look(dr):
        seen["labels"] = _labels(dr.dlg)
        seen["combo"] = [w.get() for w in _all(dr.dlg)
                         if w.winfo_class() == "TCombobox"]
    got = _target_dialog(app, {"template": "a", "limit": dict(RATIO)},
                         look, _press("確定"))
    assert FIXED_ZH in seen["combo"]
    assert "固定矩形 (25.0%,25.0%) 50.0%×25.0%" in seen["labels"]
    assert got["limit"] == RATIO


def test_可以重拖(make_app, monkeypatch):
    app = make_app(1.0)
    _overlay(monkeypatch)
    old = {"kind": "rect", "x": 0.0, "y": 0.0, "w": 0.1, "h": 0.1}
    got = _target_dialog(app, {"template": "a", "limit": old},
                         _press("在畫面上框選"), _press("確定"))
    assert got["limit"] == RATIO


def test_沒設搜尋範圍時按鈕不可用_並說明原因(make_app, monkeypatch):
    app = make_app(1.0)
    app.scan_region = None
    calls = _overlay(monkeypatch)
    seen = {}

    def look(dr):
        btn = _btn(dr.dlg, "在畫面上框選")
        seen["disabled"] = btn.instate(["disabled"])
        seen["labels"] = _labels(dr.dlg)
        btn.invoke()      # 停用的按鈕按了也沒事
        dr.close()
    _target_dialog(app, {"template": "a"}, _choose(FIXED_ZH), look)
    assert seen["disabled"]
    assert any("要先在主視窗框選搜尋範圍" in t for t in seen["labels"])
    assert calls == [], "不進清場、不叫拾取層"


def test_選了固定矩形卻沒框過_確定時提示_不存空的限定範圍(
        make_app, monkeypatch, no_real_dialogs):
    app = make_app(1.0)
    _overlay(monkeypatch)
    seen = {}

    def still_open(dr):
        seen["open"] = dr.dlg.winfo_exists()
        dr.close()
    got = _target_dialog(app, {"template": "a"}, _choose(FIXED_ZH),
                         _press("確定"), still_open)
    assert got is None and seen["open"]
    assert any("固定矩形還沒框選" in m for m in no_real_dialogs["warning"])


def test_找圖步驟對話框_設定固定矩形後存進步驟(make_app, monkeypatch):
    """步驟對話框 →「設定…」開子對話框 → 選固定矩形、框選、確定 → 步驟確定."""
    app = make_app(1.0)
    app.ws.add("a", b"A")
    _overlay(monkeypatch)
    sub = _Driver(app.root, "找圖設定")

    def open_sub(dr):
        # 子對話框是 modal: 它的動作排在打開之後, 由巢狀事件迴圈執行;
        # 「設定…」要等子對話框關掉、摘要更新完才返回, 之後才按步驟的確定
        sub.run(_choose(FIXED_ZH), _press("在畫面上框選"), _press("確定"))
        _btn(dr.dlg, "設定…").invoke()
        _btn(dr.dlg, "確定").invoke()
    step = {"type": "find_click", "target": {"template": "a"}, "timeout": 5,
            "interval": 0.5, "action": "click", "onNotFound": "skip",
            "_edit": True}
    got = _edit(app, step, open_sub, title="編輯：找圖點擊")
    if sub.error is not None:
        raise sub.error
    assert got["target"]["limit"] == RATIO

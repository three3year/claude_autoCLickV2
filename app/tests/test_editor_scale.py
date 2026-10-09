"""編輯器每次拾取當下量`座標基準點`與`畫面倍率` (coord-anchor 票 02–06, ADR 0012).

編輯器從螢幕取得的東西都在拾取的那張截圖上校準後再存: 絕對座標、固定矩形相對當下
的基準點; 相對座標、限定範圍、指定點除以當下倍率; 截下的範本圖以 1/倍率縮放、拍攝
位置相對基準點。量不到＝不存並提示; 沒有校準對＝需要基準點的拾取擋下、只依原點的照常。
拾取覆蓋層與清場以樁取代, 校準用的截圖走假偵測器 (harness.Vision), 對話框照常用
`_Driver` 真的按按鈕。
"""
import contextlib
import os

import numpy as np
import pytest

import harness  # noqa: F401  # 先把 app/ 加進 sys.path
from harness import CAL_PAIR, Screen, Vision

import app as app_mod
import enginehub
import flowfile
import ui_dialogs
from automation import findtarget, imgio
from test_template_picker import TITLE, _Driver, _open, _PickApp

REGION = [100, 200, 800, 600]
ANCHOR = (150, 230)     # 校準對第一張的中心 (搜尋範圍內)


class _EditApp(_PickApp):
    """步驟對話框需要的欄位 (沿用選範本對話框的最小 App).

    scale: 校準對擺出來的`畫面倍率`; pair=False＝流程沒有校準對。
    """

    def __init__(self, root, profile_dir, scale=1.0, anchor=ANCHOR, pair=True):
        super().__init__(root, profile_dir)
        self.scan_region = REGION
        self.vision = Vision()
        self.detector = self.vision
        self.flow_cal = harness.cal() if pair else None
        if pair:
            for n in CAL_PAIR:
                self.ws.add(n, b"P")
            self.place_pair(scale, anchor)

    def place_pair(self, scale, anchor):
        self.vision.plan(CAL_PAIR[0], [anchor])
        self.vision.plan(CAL_PAIR[1],
                         [(anchor[0] + round(harness.CAL_BASELINE * scale), anchor[1])])

    def calibration_ready(self, title, names=None, parent=None):
        return True

    # 選範本對話框的最小 App 把它換成直接回假截圖; 這裡要走真的 (量校準那段)
    pick_region_measured = app_mod.App.pick_region_measured


@pytest.fixture
def make_app(tkroot, tmp_path, monkeypatch):
    tkroot.deiconify()
    tkroot.geometry("+40+40")
    tkroot.update()
    monkeypatch.setattr(ui_dialogs.ui_overlay, "screen_clear",
                        lambda root, extra=(): contextlib.nullcontext())
    monkeypatch.setattr(app_mod.capture, "grab",
                        lambda region=None: (Screen((region[0], region[1]),
                                                    (region[2], region[3])),
                                             (region[0], region[1])))
    monkeypatch.setattr(app_mod.time, "sleep", lambda s: None)
    yield lambda scale=1.0, **kw: _EditApp(tkroot, tmp_path, scale, **kw)
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

def test_絕對座標點擊_相對當下基準點_除以當下倍率(make_app, monkeypatch):
    app = make_app(2.0)
    _overlay(monkeypatch, {"screenX": 300, "screenY": 400})
    got = _edit(app, {"type": "click", "mode": "abs", "x": 0, "y": 0},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert (got["x"], got["y"]) == (75, 85), "(300-150)/2, (400-230)/2"
    assert app.vision.lookups == list(CAL_PAIR), "拾取當下量了一次校準對"


def test_拖曳兩端點_相對當下基準點(make_app, monkeypatch):
    app = make_app(0.5)
    _overlay(monkeypatch, {"startX": 160, "startY": 240,
                           "endX": 180, "endY": 290})
    got = _edit(app, {"type": "drag", "mode": "abs", "x1": 0, "y1": 0,
                      "x2": 0, "y2": 0},
                _press("截圖拾取"), _press("確定"), title="新增：滑鼠拖曳")
    assert (got["x1"], got["y1"], got["x2"], got["y2"]) == (20, 20, 60, 120)


def test_視窗挪位置後拾取同一點_存下的值不變(make_app, monkeypatch):
    """同一個遊戲畫面位置, 視窗 (與基準點) 整個挪了 (+400,+100): 偏移一樣."""
    app = make_app(1.0, anchor=(550, 330))
    _overlay(monkeypatch, {"screenX": 700, "screenY": 500})
    got = _edit(app, {"type": "click", "mode": "abs", "x": 0, "y": 0},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert (got["x"], got["y"]) == (150, 170)


def test_相對座標_預設原點推算用當下基準點與倍率_拾取值除以倍率(make_app, monkeypatch):
    app = make_app(2.0)
    app.steps = [{"type": "click", "mode": "abs", "x": 30, "y": 40}]
    calls = _overlay(monkeypatch, {"dx": 50, "dy": -30})
    got = _edit(app, {"type": "click", "mode": "prev", "x": 0, "y": 0,
                      "_index": 1},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    mode, kw = calls[0]
    assert kw["base"] == (150 + 60, 230 + 80), "原點＝基準點＋偏移×倍率"
    assert (got["x"], got["y"]) == (25, -15)


def test_倍率1時拾取值原樣(make_app, monkeypatch):
    app = make_app(1.0)
    _overlay(monkeypatch, {"screenX": 333, "screenY": 444})
    got = _edit(app, {"type": "click", "mode": "abs", "x": 0, "y": 0},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert (got["x"], got["y"]) == (183, 214)


def test_沒有校準對_絕對座標拾取擋下並提示先設校準對(make_app, monkeypatch,
                                             no_real_dialogs):
    app = make_app(pair=False)
    calls = _overlay(monkeypatch, {"screenX": 300, "screenY": 400})
    got = _edit(app, {"type": "click", "mode": "abs", "x": 7, "y": 8},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert calls == [], "沒進拾取"
    assert (got["x"], got["y"]) == (7, 8), "值沒被動到"
    assert any("校準對" in m for m in no_real_dialogs["warning"])


def test_沒有校準對_相對座標照常拾取_倍率1(make_app, monkeypatch):
    app = make_app(pair=False)
    _overlay(monkeypatch, {"dx": 50, "dy": -30})
    got = _edit(app, {"type": "click", "mode": "prev", "x": 0, "y": 0,
                      "_index": 0},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert (got["x"], got["y"]) == (50, -30)
    assert app.vision.lookups == []


def test_拾取當下找不到校準對_不存並提示重框搜尋範圍(make_app, monkeypatch,
                                             no_real_dialogs):
    app = make_app(1.0)
    app.vision.plan(CAL_PAIR[1], [None])
    calls = _overlay(monkeypatch, {"screenX": 300, "screenY": 400})
    got = _edit(app, {"type": "click", "mode": "abs", "x": 7, "y": 8},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert calls == [], "量不到就不進拾取"
    assert (got["x"], got["y"]) == (7, 8)
    assert any("搜尋範圍" in m and CAL_PAIR[1] in m
               for m in no_real_dialogs["warning"])


def test_拾取當下找不到校準對_相對座標也不存(make_app, monkeypatch, no_real_dialogs):
    app = make_app(1.0)
    app.vision.plan(CAL_PAIR[0], [None])
    _overlay(monkeypatch, {"dx": 50, "dy": -30})
    got = _edit(app, {"type": "click", "mode": "prev", "x": 1, "y": 2,
                      "_index": 0},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert (got["x"], got["y"]) == (1, 2)
    assert no_real_dialogs["warning"]


def _target_dialog(app, monkeypatch, tgt, *actions):
    d = _Driver(app.root, "找圖設定")
    d.run(*actions)
    got = ui_dialogs.edit_target_opts(app, app.root, tgt, "找圖設定",
                                      origin_fn=lambda anchor, k: (500, 500))
    if d.error is not None:
        raise d.error
    return got


def test_限定範圍框選_除以當下倍率(make_app, monkeypatch):
    app = make_app(2.0)
    _overlay(monkeypatch, {"screenX": 400, "screenY": 520, "w": 300,
                           "h": 100})
    tgt = {"template": "a", "limit": {"kind": "origin", "x": 0, "y": 0,
                                      "w": 10, "h": 10}}
    got = _target_dialog(app, monkeypatch, tgt, _press("框選"), _press("確定"))
    assert got["limit"] == {"kind": "origin", "x": -50, "y": 10,
                            "w": 150, "h": 50}


def test_指定點_只存相對原點的偏移_除以當下倍率(make_app, monkeypatch):
    app = make_app(2.0)
    _overlay(monkeypatch, {"screenX": 560, "screenY": 440})
    tgt = {"template": "a", "pick": {"kind": "near", "x": 0, "y": 0}}
    got = _target_dialog(app, monkeypatch, tgt, _press("點選"), _press("確定"))
    assert got["pick"] == {"kind": "near", "x": 30, "y": -30}


def test_指定點沒有基準下拉_限定範圍沒有九宮格(make_app):
    app = make_app(1.0)
    seen = {}

    def look(dr):
        from test_template_picker import _all
        seen["combos"] = [list(w.cget("values")) for w in _all(dr.dlg)
                          if w.winfo_class() == "TCombobox"]
        dr.close()
    _target_dialog(app, None, {"template": "a"}, look)
    values = [v for vs in seen["combos"] for v in vs]
    assert not any("九宮格" in v for v in values)
    assert not any("搜尋範圍左上" in v for v in values)
    assert ui_dialogs.LIMIT_ZH.keys() == {"none", "origin", "rect"}


# ---------- 截範本 ----------

def _shot(w=40, h=20, x=10, y=20):
    img = np.zeros((h, w, 3), np.uint8)
    img[:, : w // 2] = (10, 200, 30)
    return {"img": img, "screenX": x, "screenY": y, "w": w, "h": h}


def test_主視窗截圖_倍率k時以1除k縮放_拍攝位置相對基準點(make_app):
    app = make_app(2.0)
    name = app.save_captured(_shot(40, 20, 210, 250), ANCHOR, 2.0)
    assert imgio.imread(app.ws.path_of(name)).shape[:2] == (10, 20)
    assert app.ws.pos_of(name) == [40, 15], "((230-150)/2, (260-230)/2)"


def test_主視窗截圖_倍率1時與原圖逐位元相同(make_app, tmp_path):
    app = make_app(1.0)
    shot = _shot(41, 23)
    name = app.save_captured(shot, ANCHOR, 1.0)
    ref = str(tmp_path / "ref.png")
    imgio.imwrite(ref, shot["img"])
    with open(app.ws.path_of(name), "rb") as a, open(ref, "rb") as b:
        assert a.read() == b.read()


def test_截圖框選走拾取當下的校準(make_app, monkeypatch):
    app = make_app(2.0)
    shot = _shot(40, 20, 210, 250)
    monkeypatch.setattr(app, "pick_region_raw", lambda hide=(): shot)
    name = app.capture_template()
    assert imgio.imread(app.ws.path_of(name)).shape[:2] == (10, 20)
    assert app.ws.pos_of(name) == [40, 15]
    assert app.vision.lookups == list(CAL_PAIR)


def test_沒有校準對時截圖不縮放_不記拍攝位置(make_app, monkeypatch):
    app = make_app(pair=False)
    monkeypatch.setattr(app, "pick_region_raw", lambda hide=(): _shot(40, 20))
    name = app.capture_template()
    assert imgio.imread(app.ws.path_of(name)).shape[:2] == (20, 40)
    assert app.ws.pos_of(name) is None


def test_截圖當下找不到校準對_不存範本並提示(make_app, monkeypatch, no_real_dialogs):
    app = make_app(1.0)
    app.vision.plan(CAL_PAIR[0], [None])
    monkeypatch.setattr(app, "pick_region_raw", lambda hide=(): _shot(40, 20))
    assert app.capture_template() is None
    assert app.ws.names() == list(sorted(CAL_PAIR))
    assert no_real_dialogs["warning"]


def test_選範本對話框現場截圖_也換回流程尺度與相對基準點(make_app):
    app = make_app(0.5)
    app.shot = _shot(40, 20, 170, 240)
    d = _Driver(app.root, TITLE)
    got = _open(app, d, lambda dr: (dr.press("截圖新增"), dr.press("確定")))
    assert imgio.imread(app.ws.path_of(got)).shape[:2] == (40, 80)
    assert app.ws.pos_of(got) == [80, 40], "((190-150)/0.5, (250-230)/0.5)"


def test_上傳的範本不縮放(make_app, monkeypatch, tmp_path):
    app = make_app(2.0)
    src = str(tmp_path / "up.png")
    imgio.imwrite(src, _shot(40, 20)["img"])
    monkeypatch.setattr(app_mod.filedialog, "askopenfilenames",
                        lambda **kw: [src])
    app._select_tmpl_row = lambda name: None   # 面板不在這個最小 App 裡
    app.upload_template()
    [name] = [n for n in app.ws.names() if n not in CAL_PAIR]
    assert imgio.imread(app.ws.path_of(name)).shape[:2] == (20, 40)


# ---------- 預設原點: ◎ 退用拍攝位置 ----------

def test_預設原點退用拍攝位置_依當下基準點換到螢幕(make_app, monkeypatch):
    app = make_app(1.0, anchor=(550, 330))    # 視窗挪過了
    app.ws.add("a", b"A", pos=[100, 50])      # 拍的時候相對基準點 (+100,+50)
    app.steps = [{"type": "find_click", "target": {"template": "a"},
                  "offsetX": 0, "offsetY": 0},
                 {"type": "click", "mode": "prev", "x": 0, "y": 0}]
    monkeypatch.setattr(ui_dialogs, "_find_template_now",
                        lambda *a, **k: None)   # 圖此刻不在畫面上
    calls = _overlay(monkeypatch, {"dx": 5, "dy": 5})
    _edit(app, {"type": "click", "mode": "prev", "x": 0, "y": 0, "_index": 2},
          _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert calls[0][1]["base"] == (650, 380), "◎ 標在圖實際的位置 (基準點 + 偏移)"


def test_預設原點推算_絕對點擊_基準點加偏移乘倍率():
    app = type("A", (), {"steps": [{"type": "click", "x": 30, "y": 40}],
                         "template_pos": lambda self, n: None})()
    got = ui_dialogs._resolve_prev_origin(app, {"_index": 1}, None, 1.5, (100, 200))
    assert got == (100 + 45, 200 + 60)
    assert ui_dialogs._resolve_prev_origin(app, {"_index": 1}, None, 1.5, None) \
        is None, "沒有基準點無從推算"


# ---------- 比對測試 ----------

def _match_test_app(make_app, monkeypatch, scale, **kw):
    app = make_app(scale, **kw)
    app.hub.state = enginehub.READY
    app.profile = type("P", (), {"templates": {"a": object()},
                                 "config": {"match_threshold": 0.6,
                                            "verify_threshold": 0.8}})()
    app.hub.ensure_template = lambda name: None
    app.ensure_registered = lambda: None
    seen = []

    def fake_find(tgt, detector, scr, org, origin=None, scale=1.0, anchor=None):
        seen.append((scale, anchor, org))
        return findtarget.Found(tgt, reason="none")
    monkeypatch.setattr(ui_dialogs.findtarget, "find", fake_find)
    monkeypatch.setattr(ui_dialogs, "_annotate_find",
                        lambda screen, org, f, origin=None, anchor=None:
                        np.zeros((60, 80, 3), np.uint8))
    return app, seen


def _close_result(app):
    for w in app.root.winfo_children():
        if getattr(w, "title", None) and w.title() == "比對測試結果":
            w.destroy()


def test_比對測試用當下量到的基準點與倍率(make_app, monkeypatch):
    app, seen = _match_test_app(make_app, monkeypatch, 0.9)
    ui_dialogs.show_match_test(app, {"template": "a"})
    _close_result(app)
    assert seen == [(0.9, ANCHOR, (100, 200))]


def test_比對測試_固定矩形但沒有校準對_擋下(make_app, monkeypatch, no_real_dialogs):
    app, seen = _match_test_app(make_app, monkeypatch, 1.0, pair=False)
    ui_dialogs.show_match_test(app, {"template": "a", "limit": {
        "kind": "rect", "x": 0, "y": 0, "w": 10, "h": 10}})
    assert seen == []
    assert any("校準對" in m for m in no_real_dialogs["warning"])


def test_比對測試補記的拍攝位置相對基準點(make_app, monkeypatch):
    app, seen = _match_test_app(make_app, monkeypatch, 2.0)
    app.ws.add("a", b"A")

    def fake_find(tgt, detector, scr, org, origin=None, scale=1.0, anchor=None):
        m = findtarget.Match((230, 290, 40, 20), 0.99)
        return findtarget.Found(tgt, [m], m, None, type("Q", (), {"debug": {},
                                                                  "score": 0.99})())
    monkeypatch.setattr(ui_dialogs.findtarget, "find", fake_find)
    ui_dialogs.show_match_test(app, {"template": "a"})
    _close_result(app)
    assert app.ws.pos_of("a") == [50, 35], "((250-150)/2, (300-230)/2)"

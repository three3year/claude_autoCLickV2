"""`備用校準對`的編輯器接線 (scale-range 票 08): 設定備用對、校準鈕顯示用的是哪一組、
換主對時偏移重算、拾取當下主對找不到改用備用對、讀檔不成形的警告.

量測純邏輯在 test_fallback_calibration.py; 這裡沿用 test_calibration_ui 的最小 App。
"""
from types import SimpleNamespace

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import app as app_mod
import calibration
import ui_dialogs
from test_calibration_ui import OLD, _Btn, _editor, _flow_with_coords, _warnings
from test_editor_scale import make_app  # noqa: F401  (拾取當下的量測用它的最小 App)

MAIN = OLD                       # {"pair": ["舊圖示", "舊關閉"], "baseline": 1000.0}
FB = ("標題列圖示", "關閉鈕")


def _place(vision, names, a, b):
    vision.plan(names[0], [a])
    vision.plan(names[1], [b])


def _fb_editor(tkroot, monkeypatch, tmp_path, cal=None, pick=FB):
    """最小編輯器: 挑備用對的對話框直接回 pick (接受 fallback= 參數)."""
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=cal)
    monkeypatch.setattr(ui_dialogs, "pick_cal_pair", lambda app, **kw: pick)
    for n in (pick or ()):
        a.ws.add(n, b"F")
    return a, vision


def test_設定備用校準對_量兩組_存基準距離與偏移(tkroot, monkeypatch, tmp_path):
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=dict(MAIN))
    _place(vision, MAIN["pair"], (300, 200), (1200, 200))   # 900 ÷ 1000 → ×0.9
    _place(vision, FB, (30, 20), (1710, 20))                 # 距離 1680 → 基準 1866.7
    a.designate_fallback_pair()
    fb = calibration.fallback_pair(a.flow_cal)
    assert fb["pair"] == list(FB)
    assert abs(fb["baseline"] - 1680 / 0.9) < 0.1
    assert fb["offset"] == [300, 200], "(主基準點 − 備用第一張中心) ÷ 0.9"
    assert a.flow_cal["pair"] == MAIN["pair"] and a.flow_cal["baseline"] == 1000.0
    assert a.autosaved == 1
    assert any("備用校準對" in m and "標題列圖示" in m for m in a.logged)
    # 用備用對量回來是同一個基準點
    assert calibration.fallback_anchor((30, 20), fb["offset"], 0.9) == (300, 200)


def test_主對找不到_拒絕設定備用對_資料不變(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=dict(MAIN))
    _place(vision, MAIN["pair"], None, (1200, 200))
    _place(vision, FB, (30, 20), (1710, 20))
    a.designate_fallback_pair()
    assert calibration.fallback_pair(a.flow_cal) is None
    assert a.flow_cal == MAIN
    assert any("舊圖示" in m for m in rec) and a.autosaved == 0


def test_備用對找不到_拒絕(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=dict(MAIN))
    _place(vision, MAIN["pair"], (300, 200), (1200, 200))
    _place(vision, FB, (30, 20), None)
    a.designate_fallback_pair()
    assert calibration.fallback_pair(a.flow_cal) is None
    assert any("關閉鈕" in m for m in rec)


def test_備用對與主對相同_拒絕(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=dict(MAIN),
                           pick=tuple(MAIN["pair"]))
    a.designate_fallback_pair()
    assert calibration.fallback_pair(a.flow_cal) is None
    assert any("相同" in m for m in rec)


def test_還沒有主對_先提示設定校準對(tkroot, monkeypatch, tmp_path):
    rec = []
    monkeypatch.setattr(app_mod.messagebox, "showinfo",
                        lambda title, msg, **kw: rec.append(msg))
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path)
    a.designate_fallback_pair()
    assert any("校準對" in m for m in rec)
    assert vision.lookups == []


def _with_fb(offset=(100, 50)):
    c = dict(MAIN)
    c[calibration.FALLBACK_KEY] = calibration.make_fallback(FB, 1868.0, offset)
    return c


def test_介面顯示備用對(tkroot, monkeypatch, tmp_path):
    a, _ = _fb_editor(tkroot, monkeypatch, tmp_path, cal=_with_fb())
    a._update_cal_ui()
    assert "備用" in a.cal_info.text and "標題列圖示" in a.cal_info.text


def test_校準鈕_主對找不到時顯示用的是備用對(tkroot, monkeypatch, tmp_path):
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=_with_fb())
    _place(vision, MAIN["pair"], None, (1200, 200))
    _place(vision, FB, (20, 20), (1514, 20))     # ×0.8 → 基準點 (100,60)
    a.calibrate_now()
    assert "備用" in a.cal_btn.text and "×0.80" in a.cal_btn.text
    assert any("備用校準對" in m and "(100, 60)" in m for m in a.logged)


def test_校準鈕_主對找得到時不提備用(tkroot, monkeypatch, tmp_path):
    a, vision = _fb_editor(tkroot, monkeypatch, tmp_path, cal=_with_fb())
    _place(vision, MAIN["pair"], (100, 50), (1300, 50))
    a.calibrate_now()
    assert "備用" not in a.cal_btn.text and "×1.20" in a.cal_btn.text


def test_換主校準對_備用對的偏移跟著重算(tkroot, monkeypatch, tmp_path):
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=_with_fb((100, 50)),
                        pick=("圖示", "關閉"))
    _flow_with_coords(a)
    _place(vision, MAIN["pair"], (100, 50), (1000, 50))   # ×0.9, 舊基準點 (100,50)
    _place(vision, ("圖示", "關閉"), (190, 95), (640, 95))  # 新基準點差 (90,45) → 流程尺度 (100,50)
    a.designate_pair()
    assert a.flow_cal["pair"] == ["圖示", "關閉"]
    fb = calibration.fallback_pair(a.flow_cal)
    assert fb["pair"] == list(FB) and fb["baseline"] == 1868.0
    assert fb["offset"] == [200, 100], "舊偏移 (100,50) + 新舊基準點差 (100,50)"
    # 備用第一張中心不動 (舊基準點 − 舊偏移×0.9 = (10,5)), 用新偏移量回來＝新基準點
    assert calibration.fallback_anchor((10, 5), fb["offset"], 0.9) == (190, 95)


def test_換成與備用對相同的主對_拒絕(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a, vision = _editor(tkroot, monkeypatch, tmp_path, cal=_with_fb(), pick=FB)
    a.designate_pair()
    assert a.flow_cal["pair"] == MAIN["pair"]
    assert any("相同" in m for m in rec)


def test_拾取當下主對找不到_改用備用對並提示(make_app, monkeypatch):
    """沿用 test_editor_scale 的步驟對話框: 絕對座標拾取相對備用對換回的基準點."""
    from harness import CAL_PAIR
    from test_editor_scale import _edit, _overlay, _press
    app = make_app(1.0)                      # 主對本來擺在基準點 (150,230)
    app.flow_cal[calibration.FALLBACK_KEY] = calibration.make_fallback(FB, 100.0, (50, 30))
    for n in FB:
        app.ws.add(n, b"F")
    app.vision.plan(CAL_PAIR[0], [None])     # 主對第一張被蓋住
    app.vision.plan(FB[0], [(100, 200)])     # 備用: 距離 100 → ×1.0, 基準點 (100,200)+(50,30)
    app.vision.plan(FB[1], [(200, 200)])
    _overlay(monkeypatch, {"screenX": 300, "screenY": 400})
    got = _edit(app, {"type": "click", "mode": "abs", "x": 0, "y": 0},
                _press("截圖拾取"), _press("確定"), title="新增：座標點擊")
    assert (got["x"], got["y"]) == (150, 170), "基準點仍是 (150,230) (備用對換回)"
    assert any("備用校準對" in m for _, m in app.logged)


def test_讀檔時備用組不成形_當沒有並警告(tkroot, monkeypatch, tmp_path):
    a, _ = _fb_editor(tkroot, monkeypatch, tmp_path)
    for attr in ("run_mode", "run_count", "avoid_hover"):
        setattr(a, attr, SimpleNamespace(set=lambda v: None, get=lambda: 1))
    a.scan_lbl = _Btn()
    a._mode_ui = lambda: None
    a._update_region_preview = lambda: None
    bad = dict(MAIN)
    bad[calibration.FALLBACK_KEY] = {"pair": ["x"], "baseline": 0}
    a._apply_flow({"steps": [], "coordSpace": "anchor", "calibration": bad})
    assert calibration.fallback_pair(a.flow_cal) is None
    assert any("備用校準對" in m and "不成形" in m for m in a.logged)

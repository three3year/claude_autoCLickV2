"""`忙碌檢查`與`忙碌出現等候`的存檔、對話框、步驟摘要、主視窗設定與執行前檢查
(busy-check 票 02/03, ADR 0011).

存檔照 test_flowfile 的手法真檔案測; 對話框沿用 test_editor_scale 的最小 App ＋
`_Driver` 真的按按鈕、真的點勾選框; 主視窗設定與執行前檢查沿用 test_retry_settings /
test_calibration_ui 的最小 App 子類。
"""
import tkinter as tk
from types import SimpleNamespace

import harness  # noqa: F401  # 先把 app/ 加進 sys.path
from harness import click, drag, find, key, tgt

import app as app_mod
import flowfile
from test_calibration_ui import _CalApp, _warnings
from test_editor_scale import _edit, _press, make_app  # noqa: F401 (fixture)
from test_pointer_confirm_ui import _pick
from test_retry_settings import BUSY, _SetApp
from test_template_picker import _all


# ---------- 存檔 ----------

def test_忙碌檢查與忙碌出現等候存檔往返(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    steps = [click(1, 2, busyCheck=True), find("a"), key("esc", busyCheck=True)]
    flowfile.write(path, {"steps": steps, "coordSpace": "anchor",
                          "busyAppearMs": 800}, {"a": b"A"})
    data = flowfile.read(path)["data"]
    assert [s.get("busyCheck") for s in data["steps"]] == [True, None, True]
    assert flowfile.busy_appear_ms(data) == 800


def test_舊存檔讀進來沒勾_出現等候是預設(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    flowfile.write(path, {"steps": [click(1, 2), find("a")],
                          "coordSpace": "anchor"}, {"a": b"A"})
    data = flowfile.read(path)["data"]
    assert all("busyCheck" not in s for s in data["steps"])
    assert flowfile.busy_appear_ms(data) == 1000
    assert flowfile.busy_appear_ms({"busyAppearMs": "壞"}) == 1000


# ---------- 對話框 ----------

def _busy_label(dlg):
    """對話框裡的忙碌檢查勾選框 (Label ☑/☐ 實作)."""
    for w in _all(dlg):
        if w.winfo_class() == "Label" and "忙碌指示消失" in str(w.cget("text")):
            return w
    raise AssertionError("找不到忙碌檢查勾選框")


def _toggle(dr):
    dr._update()   # 事件要發到已映射的視窗上才會派送
    w = _busy_label(dr.dlg)
    assert w.winfo_ismapped(), "勾選框沒顯示在畫面上"
    w.event_generate("<Button-1>")
    dr._update()


def _see(seen):
    """記下勾選框當下的文字與是否顯示在畫面上."""
    def act(dr):
        dr._update()
        w = _busy_label(dr.dlg)
        seen["text"] = str(w.cget("text"))
        seen["shown"] = bool(w.winfo_ismapped())
    return act


def test_座標點擊對話框勾忙碌檢查_存回步驟(make_app):
    a = make_app(1.0)
    got = _edit(a, click(10, 10, _edit=True), _toggle, _press("確定"),
                title="編輯：座標點擊")
    assert got["busyCheck"] is True


def test_拖曳與按鍵對話框也有勾選(make_app):
    a = make_app(1.0)
    got = _edit(a, drag(1, 2, 3, 4, _edit=True), _toggle, _press("確定"),
                title="編輯：滑鼠拖曳")
    assert got["busyCheck"] is True
    got = _edit(a, key("esc", _edit=True), _toggle, _press("確定"),
                title="編輯：按鍵")
    assert got["busyCheck"] is True


def test_重開顯示原本的勾選_取消勾選就不留鍵(make_app):
    a = make_app(1.0)
    seen = {}
    got = _edit(a, click(10, 10, busyCheck=True, _edit=True), _see(seen),
                _toggle, _press("確定"), title="編輯：座標點擊")
    assert seen["text"].startswith("☑") and seen["shown"]
    assert "busyCheck" not in got


def test_找圖點擊對話框_動作為點擊時有勾選(make_app):
    a = make_app(1.0)
    a.ws.add("a", b"A")
    seen = {}
    got = _edit(a, find("a", _edit=True), _see(seen), _toggle, _press("確定"),
                title="編輯：找圖點擊")
    assert seen["shown"] and got["busyCheck"] is True


def test_找圖切到不點擊_勾選隱藏並存為沒勾(make_app):
    a = make_app(1.0)
    a.ws.add("a", b"A")
    seen = {}
    got = _edit(a, find("a", busyCheck=True, _edit=True),
                _pick("不點擊", "僅等待出現"), _see(seen), _press("確定"),
                title="編輯：找圖點擊")
    assert not seen["shown"]
    assert got["action"] == "none" and "busyCheck" not in got
    seen = {}
    got = _edit(a, find("a", busyCheck=True, _edit=True),
                _pick("不點擊", "等待消失"), _see(seen), _press("確定"),
                title="編輯：找圖點擊")
    assert not seen["shown"]
    assert got["action"] == "wait_gone" and "busyCheck" not in got


# ---------- 步驟摘要 ----------

def test_步驟摘要顯示忙碌檢查():
    for s in (click(1, 2, busyCheck=True), drag(1, 2, 3, 4, busyCheck=True),
              key("esc", busyCheck=True), find("a", busyCheck=True)):
        assert app_mod.step_desc(s).endswith("〔忙碌檢查〕"), s["type"]
    for s in (click(1, 2), find("a"), find("a", action="none", busyCheck=True),
              find("a", action="wait_gone", busyCheck=True)):
        assert "忙碌檢查" not in app_mod.step_desc(s), s


# ---------- 主視窗設定 ----------

def test_流程資料帶忙碌出現等候_開流程時讀回_沒有就是預設(tkroot, tmp_path):
    a = _SetApp(tkroot, tmp_path)
    a.busy_appear_ms = 700
    a.run_count = SimpleNamespace(get=lambda: 1)
    assert a._flow_data()["busyAppearMs"] == 700
    for attr in ("run_mode", "run_count", "avoid_hover"):
        setattr(a, attr, SimpleNamespace(set=lambda v: None, get=lambda: 1))
    a.scan_lbl = SimpleNamespace(configure=lambda **kw: None)
    a._mode_ui = lambda: None
    a.render_steps = lambda keep=None: None
    a._update_region_preview = lambda: None
    # 流程設定列的元件 (開舊流程要顯示 1000)
    a.busy_lbl = SimpleNamespace(configure=lambda **kw: None)
    a.retry_var = tk.StringVar(master=tkroot, value="")
    a.busy_appear_var = tk.StringVar(master=tkroot, value="")
    a._apply_flow({"steps": [], "coordSpace": "anchor"})
    assert a.busy_appear_ms == 1000 and a.busy_appear_var.get() == "1000"
    a._apply_flow({"steps": [], "coordSpace": "anchor", "busyAppearMs": 1500})
    assert a.busy_appear_ms == 1500 and a.busy_appear_var.get() == "1500"


def test_改忙碌出現等候欄位_寫進草稿(tkroot, tmp_path):
    a = _SetApp(tkroot, tmp_path)
    a.busy_appear_var = tk.StringVar(master=tkroot, value="1000")
    a.busy_appear_var.set("2500")
    a._on_busy_appear_change()
    assert a.busy_appear_ms == 2500 and a.autosaved == 1
    a.busy_appear_var.set("x")
    a._on_busy_appear_change()
    assert a.busy_appear_ms == 2500 and a.autosaved == 1, "不合法的輸入先不理"


def test_執行時把忙碌出現等候交給執行器(tkroot, monkeypatch, tmp_path):
    _warnings(monkeypatch)
    a = _SetApp(tkroot, tmp_path)
    a.busy_target = dict(BUSY)
    a.busy_appear_ms = 1500
    a.steps = [click(1, 2, busyCheck=True)]
    a.scan_region = [0, 0, 100, 100]
    a.start_run()
    kw = a.runner.started[0][1]
    assert kw["busy_appear"] == 1.5 and kw["busy"] == BUSY


# ---------- 執行前檢查 ----------

def test_有步驟勾了忙碌檢查但沒設忙碌指示_整份執行與測試選取都擋下(
        tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path, cal={"pair": ["p", "q"], "baseline": 100.0})
    a.steps = [key("esc"), key("enter", busyCheck=True), find("p"),
               find("q", busyCheck=True)]
    a.start_run()
    assert a.runner.started == []
    assert any("忙碌指示" in m and "步驟 2, 4" in m for m in rec)
    rec.clear()
    a.start_run(steps=a.steps[1:2], test=True)
    assert a.runner.started == []
    assert any("忙碌指示" in m and "步驟 1" in m for m in rec)
    # 沒勾的片段照常執行
    a.start_run(steps=a.steps[0:1], test=True)
    assert len(a.runner.started) == 1


def test_設了忙碌指示就不擋(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a = _CalApp(tkroot, tmp_path, cal={"pair": ["p", "q"], "baseline": 100.0},
                names=["p", "q", "busy"])
    a.busy_target = tgt("busy")
    a.steps = [key("enter", busyCheck=True)]
    a.start_run()
    assert rec == [] and len(a.runner.started) == 1

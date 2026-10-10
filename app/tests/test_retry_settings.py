"""流程層級的`忙碌指示` (effect-confirm 票 01): 存檔往返、被引用的範本、編輯器設定、
執行時交給執行器。`補做間隔`與`忙碌出現等候`是固定行為 (不進存檔、主視窗沒有欄位).

存檔照 test_flowfile 的手法真檔案測; 編輯器沿用最小 App 子類 + 對話框樁。
"""
from types import SimpleNamespace

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import app as app_mod
import flowfile
import ui_dialogs
from test_calibration_ui import _CalApp, _warnings

BUSY = {"template": "提交中", "limit": {"kind": "rect", "x": 600, "y": 800,
                                        "w": 300, "h": 100}}


def _flow(**extra):
    data = {"steps": [{"type": "find_click", "target": {"template": "a"}}],
            "coordSpace": "anchor"}
    data.update(extra)
    return data


# ---------- 存檔 ----------

def test_忙碌指示存檔往返(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    flowfile.write(path, _flow(busyTarget=dict(BUSY)), {"a": b"A", "提交中": b"B"})
    data = flowfile.read(path)["data"]
    assert flowfile.busy_target(data) == BUSY


def test_沒設忙碌指示讀進來是沒有(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    flowfile.write(path, _flow(), {"a": b"A"})
    data = flowfile.read(path)["data"]
    assert flowfile.busy_target(data) is None


def test_忙碌指示的範本是被引用的範本_存檔帶著它(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    data = _flow(busyTarget=dict(BUSY))
    flowfile.write(path, data, {"a": b"A", "提交中": b"B", "沒人用": b"U"})
    assert flowfile.template_names(path) == sorted(["a", "提交中"])


def test_改名跟著改忙碌指示():
    data = _flow(busyTarget=dict(BUSY))
    assert flowfile.rename_flow_refs(data, "提交中", "忙碌") == 1
    assert data["busyTarget"]["template"] == "忙碌"


# ---------- 編輯器 ----------

class _SetApp(_CalApp):
    def __init__(self, root, profile_dir, names=("a", "提交中")):
        super().__init__(root, profile_dir,
                         cal={"pair": ["a", "提交中"], "baseline": 100.0},
                         names=list(names))
        self.autosaved = 0
        self.logged = []

    def _autosave(self):
        self.autosaved += 1

    def log_ui(self, msg, level="info"):
        self.logged.append(msg)

    def referenced_templates(self):
        return flowfile.flow_refs(self._ref_data())

    def reload_profile(self):
        pass

    def refresh_templates(self):
        pass


def test_設定忙碌指示_限定範圍由作者在找圖設定裡框(tkroot, monkeypatch, tmp_path):
    a = _SetApp(tkroot, tmp_path)
    monkeypatch.setattr(ui_dialogs, "pick_template",
                        lambda app, title, initial=None: "提交中")
    seen = {}

    def opts(app, parent, tgt, title, origin_fn=None, test_fn=None):
        seen["tgt"] = tgt
        return {"limit": dict(BUSY["limit"]), "pick": None, "color": False}
    monkeypatch.setattr(ui_dialogs, "edit_target_opts", opts)
    a.edit_busy_indicator()
    assert "limit" not in seen["tgt"], "沒有九宮格預設 (九宮格已退場)"
    assert a.busy_target == BUSY
    assert a.autosaved == 1


def test_清除忙碌指示(tkroot, monkeypatch, tmp_path):
    a = _SetApp(tkroot, tmp_path)
    a.busy_target = dict(BUSY)
    monkeypatch.setattr(app_mod.messagebox, "askyesno", lambda *a_, **k: True)
    a.edit_busy_indicator()
    assert a.busy_target is None


def test_流程資料帶忙碌指示_不帶固定行為_開流程時讀回(tkroot, tmp_path):
    a = _SetApp(tkroot, tmp_path)
    a.busy_target = dict(BUSY)
    a.run_count = SimpleNamespace(get=lambda: 1)
    data = a._flow_data()
    assert data["busyTarget"] == BUSY
    for key in ("retryIntervalMs", "busyAppearMs", "avoidHover"):
        assert key not in data, key
    for attr in ("run_mode", "run_count"):
        setattr(a, attr, SimpleNamespace(set=lambda v: None, get=lambda: 1))
    a.scan_lbl = SimpleNamespace(configure=lambda **kw: None)
    a._mode_ui = lambda: None
    a.render_steps = lambda keep=None: None
    a._update_region_preview = lambda: None
    a._apply_flow({"steps": [], "coordSpace": "anchor"})
    assert a.busy_target is None


def test_執行時把忙碌指示交給執行器_固定行為不傳(tkroot, monkeypatch, tmp_path):
    _warnings(monkeypatch)
    a = _SetApp(tkroot, tmp_path)
    a.busy_target = dict(BUSY)
    a.start_run()
    kw = a.runner.started[0][1]
    assert kw["busy"] == BUSY
    for key in ("retry_interval", "busy_appear", "start_delay", "avoid_hover"):
        assert key not in kw, key


def test_忙碌指示的範本不在本流程_不執行(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a = _SetApp(tkroot, tmp_path, names=("a", "提交中"))
    a.busy_target = {"template": "不見了"}
    a.start_run()
    assert a.runner.started == []
    assert any("不見了（忙碌指示）" in m for m in rec)


def test_範本預載也載忙碌指示(harness):
    """執行器的範本預載名單含忙碌指示 (補做判斷要查)."""
    from harness import find
    harness.run([find("a")], busy=dict(BUSY))
    assert "提交中" in harness.vision.preloads[0]


def test_忙碌指示不能以原點為基準(tkroot, monkeypatch, tmp_path):
    rec = _warnings(monkeypatch)
    a = _SetApp(tkroot, tmp_path)
    monkeypatch.setattr(ui_dialogs, "pick_template",
                        lambda app, title, initial=None: "提交中")
    monkeypatch.setattr(ui_dialogs, "edit_target_opts", lambda *a_, **k: {
        "limit": None, "pick": {"kind": "near", "x": 0, "y": 0}, "color": False})
    a.edit_busy_indicator()
    assert a.busy_target is None
    assert any("原點" in m for m in rec)

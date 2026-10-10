"""流程的開啟與儲存 (flow-folder-format 08/09/10): 一份流程＝一個資料夾.

對外行為＝流程資料夾在各操作之後的檔案狀態、開啟後得到的流程、執行紀錄與彈窗。
App 的重量級 __init__ 以子類跳過; 檔案對話框以樁取代 (使用者選了哪個檔);
本機狀態資料夾與流程預設位置由 conftest 換到暫存目錄。
"""
import os
from types import SimpleNamespace

import numpy as np

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import app as app_mod
import apppaths
import enginehub
import flowfile
from automation import flowdefaults, imgio


class _Var:
    def __init__(self, value=None):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


class _FlowApp(app_mod.App):
    """只建存檔/讀檔需要的欄位 (假引擎: 狀態直接設就緒, 不載入模型)."""

    def __init__(self, root):
        self.root = root
        self.hub = enginehub.EngineHub()
        self.hub.state = enginehub.READY
        self.store = flowfile.FlowTemplates.new(apppaths.unsaved_dir())
        self.flow_engine = {}
        self.dirty = False
        self.steps = []
        self.flow_cal = None
        self.busy_target = None
        self.scan_region = None
        self._pending_templates = set()
        self._rereg_after = None
        self._collapsed = set()
        self.run_mode = _Var("執行次數")
        self.run_count = _Var(1)
        self.scan_lbl = SimpleNamespace(configure=lambda **kw: None)
        self.logged = []
        self.rendered = 0
        self.rebind_templates()

    # ---- 以樁取代的 UI ----
    def refresh_templates(self):
        pass

    def render_steps(self, keep=None):
        self.rendered += 1

    def _mode_ui(self):
        pass

    def _update_region_preview(self):
        pass

    def _update_cal_ui(self):
        pass

    def _update_busy_ui(self):
        pass

    def ensure_registered(self):
        pass

    def log_ui(self, msg, level="info"):
        self.logged.append(msg)

    def _run_count(self):
        return int(self.run_count.get())


def _img(fill=200, w=12, h=8):
    a = np.zeros((h, w, 3), np.uint8)
    a[:] = fill
    return a


def _png(fill=200):
    import cv2
    return cv2.imencode(".png", _img(fill))[1].tobytes()


def _find(template, **extra):
    """完整的找圖步驟 (記憶體裡的步驟一律照「沒寫＝」表補齊)."""
    s = {"type": "find_click", "target": {"template": template}}
    s.update(extra)
    return flowdefaults.complete(s)


def _flow(steps, **extra):
    f = flowfile.new_flow()
    f["steps"] = steps
    f.update(extra)
    return f


def _write(folder, steps, images, **extra):
    flowfile.write_flow(folder, _flow(steps, **extra), images)
    return str(folder)


def _shot(a, name, fill=90):
    """在 app 裡截一張範本 (落在快取, 還沒進 templates/)."""
    return a.add_template_image(name, _png(fill))


def _ls(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _stub_save(monkeypatch, path):
    monkeypatch.setattr(app_mod.filedialog, "asksaveasfilename",
                        lambda **kw: str(path) if path else "")


def _stub_open(monkeypatch, path):
    monkeypatch.setattr(app_mod.filedialog, "askopenfilename",
                        lambda **kw: str(path) if path else "")


def _app(tkroot, monkeypatch):
    a = _FlowApp(tkroot)
    monkeypatch.setattr(a, "_schedule_reregister", lambda: None)
    return a


def _opened(a, monkeypatch, folder):
    _stub_open(monkeypatch, os.path.join(folder, flowfile.FLOW_YAML))
    a.open_flow()
    assert a.current_flow_path() == os.path.abspath(folder)


# ---------- 開檔 ----------

def test_開檔對話框篩選flow_yaml_從流程預設位置開(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    seen = {}
    monkeypatch.setattr(app_mod.filedialog, "askopenfilename",
                        lambda **kw: seen.update(kw) or "")
    a.open_flow()
    assert ("AutoClick 流程", "flow.yaml") in seen["filetypes"]
    assert seen["initialdir"] == apppaths.flows_root()


def test_開檔_讀流程資料夾_範本是templates裡的圖(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "晚班", [_find("gear")], {"gear": b"GEAR"},
                    scan_region=[5, 6, 700, 500], run=3, engine={"scale_range": [0.6, 1.5]})
    _opened(a, monkeypatch, folder)
    assert a.list_template_names() == ["gear"]
    assert a.template_bytes("gear") == b"GEAR"
    assert a.steps == [_find("gear")]
    assert a.scan_region == [5, 6, 700, 500]
    assert a.run_count.get() == 3
    assert a.flow_name() == "晚班"
    assert a.engine_config()["scale_range"] == [0.6, 1.5]
    assert a.dirty is False


def test_開檔讀不進來_說明原因_目前流程不動(tkroot, tmp_path, monkeypatch,
                                no_real_dialogs):
    a = _app(tkroot, monkeypatch)
    good = _write(tmp_path / "好的", [_find("gear")], {"gear": b"GEAR"})
    _opened(a, monkeypatch, good)
    bad = tmp_path / "壞的"
    bad.mkdir()
    (bad / "flow.yaml").write_text("format: 1\nsteps:\n- {type: 飛走}\n", encoding="utf-8")
    _stub_open(monkeypatch, bad / "flow.yaml")

    a.open_flow()

    assert [m for m in no_real_dialogs["warning"] if "壞的" in m]
    assert a.steps == [_find("gear")], "目前的流程原封不動"
    assert a.current_flow_path() == os.path.abspath(good)
    assert any("無法開啟" in m for m in a.logged)


def test_被引用卻缺圖_照樣開_彈窗與紀錄列出缺圖(tkroot, tmp_path, monkeypatch,
                                no_real_dialogs):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [_find("有"), _find("沒有")], {"有": b"A"})
    _opened(a, monkeypatch, folder)
    assert len(a.steps) == 2
    assert [m for m in no_real_dialogs["warning"] if "沒有" in m]
    assert any("沒有" in m and "templates" in m for m in a.logged)


def test_上次沒存的截圖在讀取流程時清掉(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [_find("a")], {"a": b"A"})
    _opened(a, monkeypatch, folder)
    _shot(a, "沒存")
    assert "沒存" in a.list_template_names()
    monkeypatch.setattr(app_mod.messagebox, "askyesnocancel", lambda *x, **kw: False)

    _opened(a, monkeypatch, folder)   # 不存檔直接重讀

    assert a.list_template_names() == ["a"]
    assert _ls(os.path.join(folder, ".cache", "shots")) == []


# ---------- 存檔 ----------

def test_存檔只寫引用集合_刪掉引用的步驟再存那張圖離開templates(tkroot, tmp_path,
                                                     monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [_find("a"), _find("b")], {"a": b"A", "b": b"B"})
    _opened(a, monkeypatch, folder)
    del a.steps[1]

    assert a.save_flow()

    assert _ls(os.path.join(folder, "templates")) == ["a.png"]
    assert [s["target"]["template"] for s in flowfile.read_flow(folder)["steps"]] == ["a"]


def test_存檔保留校準對與忙碌指示的圖(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [_find("btn"), _find("沒用")],
                    {"btn": b"X", "沒用": b"X"})
    for n in ("c1", "c2", "忙"):   # 使用者自己丟進 templates/ 的圖
        (tmp_path / "f" / "templates" / (n + ".png")).write_bytes(b"X")
    _opened(a, monkeypatch, folder)
    a.steps = [_find("btn")]
    a.flow_cal = {"pair": ["c1", "c2"], "baseline": 150.0}
    a.busy_target = {"template": "忙"}

    a.save_flow()

    assert _ls(os.path.join(folder, "templates")) == sorted(
        ["btn.png", "c1.png", "c2.png", "忙.png"])
    back = flowfile.read_flow(folder)
    assert back["calibration"] == {"pair": ["c1", "c2"], "baseline": 150.0}
    assert back["busy"] == {"template": "忙"}


def test_未存檔截圖存檔前不在templates_存檔後才進去(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [_find("a")], {"a": b"A"})
    _opened(a, monkeypatch, folder)
    name = _shot(a, "新圖")
    a.steps.append(_find(name))
    assert _ls(os.path.join(folder, "templates")) == ["a.png"]

    a.save_flow()

    assert _ls(os.path.join(folder, "templates")) == ["a.png", "新圖.png"]
    assert a.dirty is False


def test_範本改名連動所有引用_存檔後檔名跟著改(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [_find("a"), _find("b", confirm="appear",
                                                       confirm_target={"template": "a"})],
                    {"a": b"A", "b": b"B"}, busy={"template": "a"})
    _opened(a, monkeypatch, folder)
    monkeypatch.setattr(a, "_sel_template", lambda: "a")
    monkeypatch.setattr(app_mod.ui_dialogs, "ask_string", lambda *x, **kw: "新名")

    a.rename_template()
    a.save_flow()

    back = flowfile.read_flow(folder)
    assert back["steps"][0]["target"]["template"] == "新名"
    assert back["steps"][1]["confirm_target"]["template"] == "新名"
    assert back["busy"]["template"] == "新名"
    assert _ls(os.path.join(folder, "templates")) == ["b.png", "新名.png"]
    assert (tmp_path / "f" / "templates" / "新名.png").read_bytes() == b"A"


def test_被引用卻缺圖的範本在紀錄裡如實回報(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [], {})
    _opened(a, monkeypatch, folder)
    a.steps = [_find("gone")]
    a.save_flow()
    assert any("gone" in m and "沒有帶到" in m for m in a.logged)


def test_存檔不動流程預設位置裡的其他流程(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    other = _write(os.path.join(apppaths.flows_root(), "別的"), [_find("x")], {"x": b"X"})
    before = open(os.path.join(other, "flow.yaml"), "rb").read()
    folder = _write(tmp_path / "f", [_find("a")], {"a": b"A"})
    _opened(a, monkeypatch, folder)
    a.save_flow()
    assert open(os.path.join(other, "flow.yaml"), "rb").read() == before
    assert a.other_flow_folders() == [other]


# ---------- 新流程第一次存檔 ----------

def test_新流程第一次存檔_建流程名資料夾_未存檔快取的登錄產物搬進去(tkroot, tmp_path,
                                                       monkeypatch):
    a = _app(tkroot, monkeypatch)
    name = _shot(a, "btn")
    reg = os.path.join(a.store.registered_dir, name)
    os.makedirs(reg)
    a.steps = [_find(name)]
    dest = os.path.join(apppaths.flows_root(), "早班")
    _stub_save(monkeypatch, dest)

    assert a.save_flow()

    assert _ls(dest) == sorted([".cache", "flow.yaml", "templates"])
    assert _ls(os.path.join(dest, "templates")) == ["btn.png"]
    assert _ls(os.path.join(dest, ".cache", "registered")) == ["btn"]
    assert _ls(apppaths.unsaved_dir()) == []
    assert a.flow_name() == "早班"
    assert apppaths.load_state()["last_flow"] == os.path.abspath(dest)


def test_新流程存檔撞到同名資料夾_拒絕說明_什麼都不寫(tkroot, tmp_path, monkeypatch,
                                      no_real_dialogs):
    a = _app(tkroot, monkeypatch)
    dest = tmp_path / "早班"
    dest.mkdir()
    (dest / "別人的檔.txt").write_text("x", encoding="utf-8")
    _shot(a, "btn")
    a.steps = [_find("btn")]
    _stub_save(monkeypatch, dest)

    assert a.save_flow() is False

    assert _ls(dest) == ["別人的檔.txt"]
    assert [m for m in no_real_dialogs["warning"] if "早班" in m]
    assert a.current_flow_path() is None and a.dirty


def test_取消存檔對話框不寫任何檔(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    a.steps = [_find("btn")]
    _stub_save(monkeypatch, None)
    assert a.save_flow() is False
    assert _ls(apppaths.flows_root()) == []


# ---------- 本機狀態: 上次開的流程 ----------

def test_開app自動開上次的流程(tkroot, tmp_path, monkeypatch):
    folder = _write(tmp_path / "f", [_find("a")], {"a": b"A"})
    apppaths.save_state({"last_flow": folder})
    a = _app(tkroot, monkeypatch)
    a._open_last_flow()
    assert a.current_flow_path() == os.path.abspath(folder)
    assert a.steps == [_find("a")]


def test_上次的流程不在了_開空白並記一行(tkroot, tmp_path, monkeypatch):
    apppaths.save_state({"last_flow": str(tmp_path / "不見了")})
    a = _app(tkroot, monkeypatch)
    a._open_last_flow()
    assert a.current_flow_path() is None and a.steps == []
    assert any("不在" in m for m in a.logged)


def test_開過的流程記成上次開的(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [], {})
    _opened(a, monkeypatch, folder)
    assert apppaths.load_state() == {"last_flow": os.path.abspath(folder)}


# ---------- 新流程 ----------

def test_新流程清空步驟與範本_未存檔快取清空(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [_find("old")], {"old": b"O"})
    _opened(a, monkeypatch, folder)

    a.new_flow()

    assert a.steps == [] and a.list_template_names() == []
    assert a.current_flow_path() is None
    assert a.flow_name() == "新流程"


def test_沒有改動時三個入口都不問(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    asked = []
    monkeypatch.setattr(app_mod.messagebox, "askyesnocancel",
                        lambda *x, **kw: asked.append(1))
    folder = _write(tmp_path / "f", [], {})
    _opened(a, monkeypatch, folder)
    a.new_flow()
    assert asked == []
    assert a.confirm_discard("離開") is True


# ---------- 未存檔提示: 存檔／不存／取消 ----------

def _dirty_app(tkroot, tmp_path, monkeypatch, answer):
    """開著一份流程、改了一步還沒存; 提示一律回 answer (True＝存檔, False＝不存, None＝取消)."""
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [_find("a")], {"a": b"A"})
    _opened(a, monkeypatch, folder)
    a.steps.append({"type": "wait", "wait": 1.0})
    a._mark_dirty()
    asked = []
    monkeypatch.setattr(app_mod.messagebox, "askyesnocancel",
                        lambda title, msg, **kw: (asked.append(msg), answer)[1])
    return a, folder, asked


def _saved_steps(folder):
    return len(flowfile.read_flow(folder)["steps"])


def test_每種改動都標成未存檔_存檔後清除(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [_find("a")], {"a": b"A"})
    _opened(a, monkeypatch, folder)
    for change in (lambda: _shot(a, "新圖"),
                   lambda: a.drop_template("新圖"),
                   lambda: a.record_template_pos("a", [1, 2]),
                   lambda: a.set_scan_region([1, 2, 30, 40]),
                   lambda: a._on_run_setting()):
        a.dirty = False
        change()
        assert a.dirty
    a.save_flow()
    assert a.dirty is False


def test_新流程_有改動_回答存檔_存完才開新的(tkroot, tmp_path, monkeypatch):
    a, folder, asked = _dirty_app(tkroot, tmp_path, monkeypatch, True)
    a.new_flow()
    assert asked and "f" in asked[0]
    assert _saved_steps(folder) == 2, "先存檔"
    assert a.current_flow_path() is None and a.steps == []


def test_新流程_有改動_回答不存_丟掉改動(tkroot, tmp_path, monkeypatch):
    a, folder, asked = _dirty_app(tkroot, tmp_path, monkeypatch, False)
    a.new_flow()
    assert asked
    assert _saved_steps(folder) == 1, "沒寫檔"
    assert a.current_flow_path() is None and a.steps == []


def test_新流程_有改動_回答取消_什麼都不變(tkroot, tmp_path, monkeypatch):
    a, folder, asked = _dirty_app(tkroot, tmp_path, monkeypatch, None)
    a.new_flow()
    assert asked
    assert _saved_steps(folder) == 1
    assert a.current_flow_path() == os.path.abspath(folder)
    assert len(a.steps) == 2 and a.dirty


def test_開檔_有改動_回答取消_不跳開檔視窗_什麼都不變(tkroot, tmp_path, monkeypatch):
    a, folder, asked = _dirty_app(tkroot, tmp_path, monkeypatch, None)
    opened = []
    monkeypatch.setattr(app_mod.filedialog, "askopenfilename",
                        lambda **kw: opened.append(1) or "")
    a.open_flow()
    assert asked and opened == []
    assert len(a.steps) == 2 and a.dirty


def test_開檔_有改動_回答不存_開別的流程(tkroot, tmp_path, monkeypatch):
    a, folder, asked = _dirty_app(tkroot, tmp_path, monkeypatch, False)
    other = _write(tmp_path / "別的", [], {})
    _stub_open(monkeypatch, os.path.join(other, "flow.yaml"))
    a.open_flow()
    assert asked
    assert a.current_flow_path() == os.path.abspath(other)
    assert _saved_steps(folder) == 1


def test_開檔_有改動_回答存檔_存完再開(tkroot, tmp_path, monkeypatch):
    a, folder, asked = _dirty_app(tkroot, tmp_path, monkeypatch, True)
    other = _write(tmp_path / "別的", [], {})
    _stub_open(monkeypatch, os.path.join(other, "flow.yaml"))
    a.open_flow()
    assert _saved_steps(folder) == 2
    assert a.current_flow_path() == os.path.abspath(other)


def _closing(a, monkeypatch):
    closed = []
    a.runner = SimpleNamespace(status=lambda: {"running": False})
    monkeypatch.setattr(a.root, "destroy", lambda: closed.append(1))
    return closed


def test_關閉_有改動_三種回答(tkroot, tmp_path, monkeypatch):
    for answer, saved, closes in ((True, 2, True), (False, 1, True), (None, 1, False)):
        a, folder, asked = _dirty_app(tkroot, tmp_path / str(answer), monkeypatch,
                                      answer)
        closed = _closing(a, monkeypatch)
        a.on_close()
        assert asked, answer
        assert _saved_steps(folder) == saved, answer
        assert bool(closed) is closes, answer


def test_回答存檔但新流程存檔被取消_不往下走(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    a.steps = [_find("x")]
    a._mark_dirty()
    monkeypatch.setattr(app_mod.messagebox, "askyesnocancel", lambda *x, **kw: True)
    _stub_save(monkeypatch, None)   # 第一次存檔的對話框按取消
    closed = _closing(a, monkeypatch)
    a.on_close()
    assert closed == [] and a.steps == [_find("x")]


# ---------- 引擎參數覆蓋 ----------

def test_引擎參數_沒寫用內建預設_流程engine段覆蓋(tkroot, monkeypatch):
    from subject_detection.library import load_default_config
    a = _app(tkroot, monkeypatch)
    assert a.engine_config() == load_default_config()
    a.flow_engine = {"scale_range": [0.6, 1.5]}
    cfg = a.engine_config()
    assert cfg["scale_range"] == [0.6, 1.5]
    assert {k: v for k, v in cfg.items() if k != "scale_range"} == {
        k: v for k, v in load_default_config().items() if k != "scale_range"}


def test_存檔原樣保留流程的engine段(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [], {}, engine={"scale_range": [0.6, 1.5]})
    _opened(a, monkeypatch, folder)
    a.save_flow()
    assert flowfile.read_flow(folder)["engine"] == {"scale_range": [0.6, 1.5]}


# ---------- 退場的東西 ----------

def test_匯出與profile入口都不存在(tkroot, monkeypatch):
    a = _app(tkroot, monkeypatch)
    for gone in ("export_pack", "switch_profile", "open_profile_dir", "_autosave",
                 "_load_autosave", "profile_dir"):
        assert not hasattr(a, gone), gone
    assert not hasattr(flowfile, "Workspace")

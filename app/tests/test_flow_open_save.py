import os
import tkinter as tk
from types import SimpleNamespace

import numpy as np

import harness

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

    def refresh_templates(self):
        pass

    def render_steps(self, keep=None):
        self.rendered += 1

    def _mode_ui(self):
        pass

    def _update_region_preview(self):
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


def test_開檔對話框篩選flow_yaml_從流程存放區開(tkroot, tmp_path, monkeypatch):
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

    _opened(a, monkeypatch, folder)

    assert a.list_template_names() == ["a"]
    assert _ls(os.path.join(folder, ".cache", "shots")) == []


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
    for n in ("c1", "c2", "忙"):
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


def test_存檔不動流程存放區裡的其他流程(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    other = _write(os.path.join(apppaths.flows_root(), "別的"), [_find("x")], {"x": b"X"})
    before = open(os.path.join(other, "flow.yaml"), "rb").read()
    folder = _write(tmp_path / "f", [_find("a")], {"a": b"A"})
    _opened(a, monkeypatch, folder)
    a.save_flow()
    assert open(os.path.join(other, "flow.yaml"), "rb").read() == before
    assert a.other_flow_folders() == [other]


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
    assert apppaths.last_flow() == os.path.abspath(dest)


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


def test_開app自動開上次的流程(tkroot, tmp_path, monkeypatch):
    folder = _write(tmp_path / "f", [_find("a")], {"a": b"A"})
    apppaths.remember_last_flow(folder)
    a = _app(tkroot, monkeypatch)
    a._open_last_flow()
    assert a.current_flow_path() == os.path.abspath(folder)
    assert a.steps == [_find("a")]


def test_上次的流程不在了_開空白並記一行(tkroot, tmp_path, monkeypatch):
    apppaths.remember_last_flow(tmp_path / "不見了")
    a = _app(tkroot, monkeypatch)
    a._open_last_flow()
    assert a.current_flow_path() is None and a.steps == []
    assert any("不在" in m for m in a.logged)


def test_開過的流程記成上次開的(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [], {})
    _opened(a, monkeypatch, folder)
    assert apppaths.last_flow() == os.path.abspath(folder)
    assert apppaths.load_state() == {"last_flow": os.path.abspath(folder)}, "只記上次開的流程"


def test_新流程清空步驟與範本_未存檔快取清空(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    folder = _write(tmp_path / "f", [_find("old")], {"old": b"O"})
    _opened(a, monkeypatch, folder)

    a.new_flow()

    assert a.steps == [] and a.list_template_names() == []
    assert a.current_flow_path() is None
    assert a.flow_name() == "未命名"


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


def _dirty_app(tkroot, tmp_path, monkeypatch, answer):
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
                   lambda: (a.run_count.set(3), a._on_run_setting())):
        a._set_dirty(False)
        assert a.root.title() == "f — AutoClick"
        change()
        assert a.dirty
        assert a.root.title() == "*f — AutoClick", "未存檔時標題前加 *"
    a.save_flow()
    assert a.dirty is False
    assert a.root.title() == "f — AutoClick", "存檔後 * 消失"


def test_標題_開檔與新流程後沒有星號_新流程是未命名(tkroot, tmp_path, monkeypatch):
    a, folder, asked = _dirty_app(tkroot, tmp_path, monkeypatch, False)
    assert a.root.title() == "*f — AutoClick"
    other = _write(tmp_path / "別的", [], {})
    _stub_open(monkeypatch, os.path.join(other, "flow.yaml"))
    a.open_flow()
    assert a.root.title() == "別的 — AutoClick"
    a.steps.append({"type": "wait", "wait": 1.0})
    a._mark_dirty()
    a.new_flow()
    assert a.root.title() == "未命名 — AutoClick"


def test_標題_新流程第一次存檔後換成流程名(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, monkeypatch)
    a.steps = [_find("x")]
    a._mark_dirty()
    assert a.root.title() == "*未命名 — AutoClick"
    _stub_save(monkeypatch, os.path.join(apppaths.flows_root(), "早班"))
    assert a.save_flow()
    assert a.root.title() == "早班 — AutoClick"


def test_執行設定的元件動過但值沒變_不算改動(tkroot, tmp_path, monkeypatch):
    win = tk.Toplevel(tkroot)
    try:
        a = _FlowApp(win)
        monkeypatch.setattr(a, "_schedule_reregister", lambda: None)
        a._build_toolbar()
        win.deiconify()
        win.update()         # 事件要發到已映射的視窗上才會派送
        folder = _write(tmp_path / "f", [_find("a")], {"a": b"A"})
        _opened(a, monkeypatch, folder)
        a.run_count.focus_force()
        win.update()

        def fire(widget, seq, **kw):
            a.dirty = False
            widget.event_generate(seq, **kw)
            win.update()
            return a.dirty

        assert not fire(a.run_count, "<KeyRelease>", keysym="Alt_L")
        assert not fire(a.run_count, "<MouseWheel>", delta=-120)
        assert a.run_count.get() == "1"
        assert fire(a.run_count, "<MouseWheel>", delta=120)
        assert a.run_count.get() == "2"
        assert fire(a.run_mode, "<MouseWheel>", delta=-120)
        assert a.run_mode.get() == "直到停止"
    finally:
        win.destroy()


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
    _stub_save(monkeypatch, None)
    closed = _closing(a, monkeypatch)
    a.on_close()
    assert closed == [] and a.steps == [_find("x")]


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


def test_匯出與profile入口都不存在(tkroot, monkeypatch):
    a = _app(tkroot, monkeypatch)
    for gone in ("export_pack", "switch_profile", "open_profile_dir", "_autosave",
                 "_load_autosave", "profile_dir"):
        assert not hasattr(a, gone), gone
    assert not hasattr(flowfile, "Workspace")


def _engine_app(tkroot, monkeypatch, engine, load=True):
    from test_enginehub import RegEngine
    a = _app(tkroot, monkeypatch)
    a.hub = enginehub.EngineHub(engine_factory=lambda: engine)
    if load:
        a.hub.load()
    a.rebind_templates()
    return a


def _settle(a):
    a._preload_thread.join(5)
    a.drain_preload()


def _preload_logs(a):
    return [m for m in a.logged if "準備範本" in m or "範本就緒" in m or "載入失敗" in m]


def test_讀取流程後不按執行_紀錄出現開始準備範本與範本就緒(tkroot, tmp_path, monkeypatch):
    from test_enginehub import RegEngine
    engine = RegEngine()
    a = _engine_app(tkroot, monkeypatch, engine)
    folder = _write(tmp_path / "f", [_find("a"), _find("b")], {"a": b"A", "b": b"B"},
                    busy={"template": "b"})
    _opened(a, monkeypatch, folder)
    _settle(a)
    assert sorted(engine.registered) == ["a", "b"]
    assert _preload_logs(a) == ["開始準備範本（2 張）", "範本就緒"]


def test_啟動自動開的上次流程_引擎就緒後才開始預載(tkroot, tmp_path, monkeypatch):
    import threading
    from test_enginehub import RegEngine
    engine = RegEngine()
    a = _engine_app(tkroot, monkeypatch, engine, load=False)
    folder = _write(tmp_path / "f", [_find("a")], {"a": b"A"})
    apppaths.remember_last_flow(folder)
    a._open_last_flow()
    a._preload_thread.join(0.3)
    a.drain_preload()
    assert engine.registered == [] and _preload_logs(a) == []
    threading.Thread(target=a.hub.load).start()
    _settle(a)
    assert engine.registered == ["a"]
    assert _preload_logs(a) == ["開始準備範本（1 張）", "範本就緒"]


def test_預載中換流程_舊的丟掉新的開始_紀錄不混(tkroot, tmp_path, monkeypatch):
    import threading
    import time
    from test_enginehub import RegEngine
    gate = threading.Event()
    engine = RegEngine(gate=gate)
    a = _engine_app(tkroot, monkeypatch, engine)
    first = _write(tmp_path / "甲", [_find("a"), _find("b"), _find("c")],
                   {"a": b"A", "b": b"B", "c": b"C"})
    second = _write(tmp_path / "乙", [_find("x")], {"x": b"X"})
    _opened(a, monkeypatch, first)
    old = a._preload_thread
    time.sleep(0.1)
    threading.Timer(0.2, gate.set).start()
    _opened(a, monkeypatch, second)
    old.join(5)
    _settle(a)
    assert "b" not in engine.registered and "c" not in engine.registered
    assert "x" in engine.registered
    assert _preload_logs(a) == ["開始準備範本（1 張）", "範本就緒"], "只有乙的兩行"


def test_預載發現壞圖_當下警告(tkroot, tmp_path, monkeypatch):
    from test_enginehub import RegEngine
    a = _engine_app(tkroot, monkeypatch, RegEngine(bad={"a"}))
    folder = _write(tmp_path / "f", [_find("a"), _find("b")], {"a": b"A", "b": b"B"})
    _opened(a, monkeypatch, folder)
    _settle(a)
    logs = _preload_logs(a)
    assert any("「a」載入失敗" in m and "停下" in m for m in logs)
    assert logs[-1] == "範本就緒"


def test_新增範本後只有那張要重新登錄_其他留在記憶體(tkroot, tmp_path, monkeypatch):
    from test_enginehub import RegEngine
    engine = RegEngine()
    a = _engine_app(tkroot, monkeypatch, engine)
    folder = _write(tmp_path / "f", [_find("a"), _find("b")], {"a": b"A", "b": b"B"})
    _opened(a, monkeypatch, folder)
    _settle(a)
    before = {n: t.artifacts for n, t in a.library.templates.items()}

    name = _shot(a, "新圖")
    app_mod.App.ensure_registered(a)

    arts = {n: t.artifacts for n, t in a.library.templates.items()}
    assert arts["a"] is before["a"] and arts["b"] is before["b"]
    assert arts[name] is None, "新的那張用到時才登錄"

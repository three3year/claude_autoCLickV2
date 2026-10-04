"""流程存檔的開啟與儲存 (票 04/08): 一份流程＝一個自包自足的檔.

對外行為＝存檔檔案的內容、開啟後得到的流程資料、工作區在各操作之後的狀態。
App 的重量級 __init__ 以子類跳過; 檔案對話框以樁取代 (使用者選了哪個檔)。
"""
import json
import os
from types import SimpleNamespace

import numpy as np

import harness  # noqa: F401  # 先把 app/ 加進 sys.path

import app as app_mod
import calibration
import enginehub
import flowfile
from automation import imgio


class _Var:
    def __init__(self, value=None):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


class _FlowApp(app_mod.App):
    """只建存檔/讀檔需要的欄位."""

    def __init__(self, root, profile_dir):
        self.root = root
        self.profile_dir = str(profile_dir)
        os.makedirs(self.flows_dir, exist_ok=True)
        self.ws = flowfile.Workspace(self.profile_dir)
        self.ws.ensure()
        self.hub = enginehub.EngineHub()
        self.hub.state = enginehub.READY
        self.profile = None
        self.steps = []
        self.scan_region = None
        self._pending_templates = set()
        self._rereg_after = None
        self._collapsed = set()
        self.run_mode = _Var("執行次數")
        self.run_count = _Var(1)
        self.avoid_hover = _Var(False)
        self.scan_lbl = SimpleNamespace(configure=lambda **kw: None)
        self.logged = []
        self.rendered = 0

    # ---- 以樁取代的 UI ----
    def reload_profile(self):
        pass

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


def _find(template, **extra):
    s = {"type": "find_click", "target": {"template": template},
         "action": "click"}
    s.update(extra)
    return s


def _app(tkroot, tmp_path, name="p"):
    return _FlowApp(tkroot, tmp_path / name)


def _stub_save(monkeypatch, path):
    monkeypatch.setattr(app_mod.filedialog, "asksaveasfilename",
                        lambda **kw: str(path) if path else "")


def _stub_open(monkeypatch, path):
    monkeypatch.setattr(app_mod.filedialog, "askopenfilename",
                        lambda **kw: str(path) if path else "")


# ---------- 存檔 ----------

def test_存檔產出自包自足的存檔_只帶被引用的範本(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    imgio.imwrite(a.ws.path_of("btn"), _img(90))
    imgio.imwrite(a.ws.path_of("junk"), _img(10))
    a.steps = [_find("btn"), {"type": "wait", "ms": 500}]
    dest = tmp_path / "p" / "flows" / ("morning" + flowfile.EXT)
    _stub_save(monkeypatch, dest)

    a.save_flow()

    assert flowfile.template_names(str(dest)) == ["btn"]
    r = flowfile.read(str(dest))
    assert r["data"]["steps"] == a.steps
    assert a.ws.flow_path() == str(dest)
    assert any("morning" in m for m in a.logged)


def test_刪掉引用它的步驟後再存檔_那張圖離開存檔(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    imgio.imwrite(a.ws.path_of("a"), _img(90))
    imgio.imwrite(a.ws.path_of("b"), _img(10))
    dest = tmp_path / "p" / "flows" / ("f" + flowfile.EXT)
    _stub_save(monkeypatch, dest)
    a.steps = [_find("a"), _find("b")]
    a.save_flow()
    assert flowfile.template_names(str(dest)) == ["a", "b"]

    del a.steps[1]
    a.save_flow()
    assert flowfile.template_names(str(dest)) == ["a"]


def test_存檔帶著流程的校準對與那兩張範本(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    for n in ("btn", "c1", "c2"):
        imgio.imwrite(a.ws.path_of(n), _img(90))
    a.steps = [_find("btn")]
    a.flow_cal = {"pair": ["c1", "c2"], "baseline": 150.0}
    dest = tmp_path / "p" / "flows" / ("f" + flowfile.EXT)
    _stub_save(monkeypatch, dest)

    a.save_flow()

    r = flowfile.read(str(dest))
    assert calibration.flow_pair(r["data"]) == {"pair": ["c1", "c2"],
                                                "baseline": 150.0}
    assert sorted(r["images"]) == ["btn", "c1", "c2"]
    assert sorted(os.listdir(a.profile_dir)) == ["flows", "workspace"], \
        "存檔不在 profile 留下校準資料"


def test_存檔不改寫profile裡的其他流程(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    other = os.path.join(a.flows_dir, "other" + flowfile.EXT)
    flowfile.write(other, {"steps": [{"type": "click", "x": 30, "y": 40}],
                           "coordSpace": "region"}, {})
    before = open(other, "rb").read()
    imgio.imwrite(a.ws.path_of("btn"), _img(90))
    a.steps = [_find("btn")]
    a.flow_cal = {"pair": ["btn", "btn2"], "baseline": 150.0}
    a.editor_scale = 0.8
    dest = tmp_path / "p" / "flows" / ("f" + flowfile.EXT)
    _stub_save(monkeypatch, dest)

    a.save_flow()

    assert open(other, "rb").read() == before


def test_被引用卻缺圖的範本在紀錄裡如實回報(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    a.steps = [_find("gone")]
    dest = tmp_path / "p" / "flows" / ("f" + flowfile.EXT)
    _stub_save(monkeypatch, dest)
    a.save_flow()
    assert any("gone" in m and "沒有帶到" in m for m in a.logged)


def test_取消存檔對話框不寫任何檔(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    a.steps = [_find("btn")]
    _stub_save(monkeypatch, None)
    a.save_flow()
    assert flowfile.list_flows(a.profile_dir) == []


# ---------- 讀檔: 本 profile 內的存檔 ----------

def test_載入本profile的存檔_解到工作區(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    src = os.path.join(a.flows_dir, "night" + flowfile.EXT)
    flowfile.write(src, {"steps": [_find("gear")], "coordSpace": "region",
                         "scanRegion": [5, 6, 700, 500], "runCount": 3},
                   {"gear": b"GEAR"})
    _stub_open(monkeypatch, src)

    a.open_flow()

    assert a.ws.names() == ["gear"]
    assert open(a.ws.path_of("gear"), "rb").read() == b"GEAR"
    assert a.steps == [_find("gear")]
    assert a.scan_region == [5, 6, 700, 500]
    assert a.ws.flow_path() == src


def test_切換流程時工作區整個清空(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    imgio.imwrite(a.ws.path_of("old"), _img(10))
    os.makedirs(os.path.join(a.ws.registered_dir, "old"), exist_ok=True)
    src = os.path.join(a.flows_dir, "other" + flowfile.EXT)
    flowfile.write(src, {"steps": [_find("new")], "coordSpace": "region"},
                   {"new": b"N"})
    _stub_open(monkeypatch, src)

    a.open_flow()

    assert a.ws.names() == ["new"], "上一份流程的圖不留在磁碟上"
    assert not os.path.exists(os.path.join(a.ws.registered_dir, "old")), \
        "登錄產物也一起清"


def test_工作區被手動刪掉後重新載入能自動重建(tkroot, tmp_path, monkeypatch):
    import shutil
    a = _app(tkroot, tmp_path)
    src = os.path.join(a.flows_dir, "f" + flowfile.EXT)
    flowfile.write(src, {"steps": [_find("gear")], "coordSpace": "region"},
                   {"gear": b"GEAR"})
    _stub_open(monkeypatch, src)
    a.open_flow()
    shutil.rmtree(a.ws.root)
    assert a.ws.names() == []          # 快取不見了

    a.open_flow()                      # 真相來源是存檔
    assert a.ws.names() == ["gear"]


# ---------- 讀檔: 外來存檔 ----------

def _foreign(tmp_path, steps, images, cal=None, stem="foreign"):
    path = tmp_path / (stem + flowfile.EXT)
    data = {"steps": steps, "coordSpace": "region"}
    if cal:
        data["calibration"] = cal
    flowfile.write(str(path), data, images)
    return path


def test_開啟外來存檔_複製副本進profile_原始檔不被動到(tkroot, tmp_path,
                                                monkeypatch):
    a = _app(tkroot, tmp_path)
    src = _foreign(tmp_path, [_find("gear")], {"gear": b"GEAR"})
    before = src.read_bytes()
    _stub_open(monkeypatch, src)

    a.open_flow()

    copies = flowfile.list_flows(a.profile_dir)
    assert len(copies) == 1
    assert os.path.basename(copies[0]) == "foreign" + flowfile.EXT
    assert src.read_bytes() == before, "原始檔一個 byte 都不動"
    assert a.ws.flow_path() == copies[0], "之後的存檔寫進副本"
    assert a.ws.names() == ["gear"]
    assert any("原始檔未被修改" in m for m in a.logged)


def test_開啟外來存檔_原樣使用不換算_校準對跟著走(tkroot, tmp_path, monkeypatch):
    cal = {"pair": ["c1", "c2"], "baseline": 100.0}
    a = _app(tkroot, tmp_path)
    src = _foreign(tmp_path, [{"type": "click", "x": 30, "y": 40}],
                   {"c1": b"1", "c2": b"2"}, cal=cal)
    _stub_open(monkeypatch, src)
    a.open_flow()
    assert a.steps[0]["x"] == 30 and a.steps[0]["y"] == 40
    assert a.flow_cal == cal
    assert a.ws.names() == ["c1", "c2"]


def test_舊格式流程可以開可以看_沒有校準對(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    src = _foreign(tmp_path, [_find("gear")], {"gear": b"GEAR"})
    _stub_open(monkeypatch, src)
    a.open_flow()
    assert len(a.steps) == 1 and a.flow_cal is None


# ---------- 讀檔: 舊格式單向轉換 ----------

def _legacy_library(profile_dir, templates):
    for name, caps in templates.items():
        d = os.path.join(profile_dir, "templates", *name.split("/"))
        os.makedirs(d, exist_ok=True)
        for cap, blob in caps.items():
            with open(os.path.join(d, cap + ".png"), "wb") as f:
                f.write(blob)


def test_匯入舊flow_json_轉成新存檔並套用既有規則(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    _legacy_library(a.profile_dir, {"cn/V": {"cn": b"V1", "翻新": b"V2"}})
    src = tmp_path / "old.json"
    src.write_text(json.dumps({
        "steps": [{"type": "find_click", "template": "cn/V.png",
                   "threshold": 0.85},
                  {"type": "click", "x": 300, "y": 250}],
        "scanRegion": [100, 50, 800, 600]}), encoding="utf-8")
    _stub_open(monkeypatch, src)

    a.open_flow()

    assert a.steps[0]["target"]["template"] == "V", "範本名去副檔名並拉平"
    assert "threshold" not in a.steps[0], "每步 threshold 安靜丟棄"
    assert (a.steps[1]["x"], a.steps[1]["y"]) == (200, 200), "座標空間遷移"
    assert a.ws.names() == ["V"]
    assert open(a.ws.path_of("V"), "rb").read() == b"V1", "多截圖取登錄基準張"
    assert any("降為單張" in m for m in a.logged)
    assert any("拉平" in m for m in a.logged)


def test_匯入舊流程包_多截圖取登錄基準張(tkroot, tmp_path, monkeypatch):
    import zipfile
    a = _app(tkroot, tmp_path)
    pack = tmp_path / ("legacy" + flowfile.EXT)
    with zipfile.ZipFile(pack, "w") as z:
        z.writestr("flow.json", json.dumps({
            "steps": [{"type": "find_click", "template": "cn/V.png"}],
            "coordSpace": "region"}))
        z.writestr("templates/cn/V/a.png", b"A")
        z.writestr("templates/cn/V/b.png", b"B")
    _stub_open(monkeypatch, pack)

    a.open_flow()

    assert a.steps[0]["target"]["template"] == "V"
    assert open(a.ws.path_of("V"), "rb").read() == b"A"
    saved = flowfile.list_flows(a.profile_dir)
    assert len(saved) == 1 and flowfile.template_names(saved[0]) == ["V"]


def test_匯入同名不覆蓋既有存檔(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    _legacy_library(a.profile_dir, {"cn/V": {"cn": b"V1"}})
    src = tmp_path / "dup.json"
    src.write_text(json.dumps({
        "steps": [{"type": "find_click", "template": "cn/V"}],
        "coordSpace": "region"}), encoding="utf-8")
    _stub_open(monkeypatch, src)
    a.open_flow()
    a.open_flow()
    assert len(flowfile.list_flows(a.profile_dir)) == 2


# ---------- 新流程 / 草稿 ----------

def test_新流程清空步驟與工作區(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    imgio.imwrite(a.ws.path_of("old"), _img(10))
    a.steps = [_find("old")]
    monkeypatch.setattr(app_mod.messagebox, "askyesno", lambda *a_, **kw: True)

    a.new_flow()

    assert a.steps == []
    assert a.ws.names() == []
    assert a.ws.flow_path() is None


def test_自動存檔只寫步驟草稿_不重壓zip(tkroot, tmp_path):
    a = _app(tkroot, tmp_path)
    imgio.imwrite(a.ws.path_of("btn"), _img(90))
    a.steps = [_find("btn")]

    a._autosave()

    draft = flowfile.draft_path(a.profile_dir)
    assert os.path.isfile(draft)
    assert json.loads(open(draft, encoding="utf-8").read())["steps"] == a.steps
    assert flowfile.list_flows(a.profile_dir) == [], "沒有壓出任何 zip"


def test_當機重開_草稿與工作區的圖一起復原(tkroot, tmp_path):
    a = _app(tkroot, tmp_path)
    imgio.imwrite(a.ws.path_of("btn"), _img(90))
    a.steps = [_find("btn")]
    a.scan_region = [1, 2, 300, 200]
    a._autosave()

    b = _FlowApp(tkroot, tmp_path / "p")   # 重開 app
    b._load_autosave()

    assert b.steps == [_find("btn")]
    assert b.scan_region == [1, 2, 300, 200]
    assert b.ws.names() == ["btn"], "還沒存檔的圖也在"


# ---------- 匯出動作已移除 ----------

def test_匯出動作不存在(tkroot, tmp_path):
    a = _app(tkroot, tmp_path)
    assert not hasattr(a, "export_pack")
    src = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(app_mod.__file__))), "app", "app.py")
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "匯出" not in text.replace("(「匯出」已移除", ""), \
        "存檔本身就是可搬移的檔, 不該再有匯出入口"

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
    """完整的找圖步驟 (記憶體裡的步驟一律照「沒寫＝」表補齊)."""
    from automation import flowdefaults
    s = {"type": "find_click", "target": {"template": template}}
    s.update(extra)
    return flowdefaults.complete(s)


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
    a.steps = [_find("btn"), {"type": "wait", "wait": 0.5}]
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
    flowfile.write(other, {"steps": [{"type": "click", "click": [30, 40]}],
                           "coordSpace": "anchor"}, {})
    before = open(other, "rb").read()
    imgio.imwrite(a.ws.path_of("btn"), _img(90))
    a.steps = [_find("btn")]
    a.flow_cal = {"pair": ["btn", "btn2"], "baseline": 150.0}
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
    flowfile.write(src, {"steps": [_find("gear")], "coordSpace": "anchor",
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
    flowfile.write(src, {"steps": [_find("new")], "coordSpace": "anchor"},
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
    flowfile.write(src, {"steps": [_find("gear")], "coordSpace": "anchor"},
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
    data = {"steps": steps, "coordSpace": "anchor"}
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
    src = _foreign(tmp_path, [{"type": "click", "click": [30, 40]}],
                   {"c1": b"1", "c2": b"2"}, cal=cal)
    _stub_open(monkeypatch, src)
    a.open_flow()
    assert a.steps[0]["click"] == [30, 40]
    assert a.flow_cal == cal
    assert a.ws.names() == ["c1", "c2"]


def test_沒有校準對的新格式流程可以開可以看(tkroot, tmp_path, monkeypatch):
    a = _app(tkroot, tmp_path)
    src = _foreign(tmp_path, [_find("gear")], {"gear": b"GEAR"})
    _stub_open(monkeypatch, src)
    a.open_flow()
    assert len(a.steps) == 1 and a.flow_cal is None


# ---------- 讀檔: 舊格式一律拒絕 (ADR 0012) ----------

def _old_pack(path, data, images):
    import zipfile
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("flow.json", json.dumps(data, ensure_ascii=False))
        for n, blob in images.items():
            z.writestr(f"templates/{n}.png", blob)


def _loaded(a, tkroot, tmp_path, monkeypatch):
    """先開著一份好的流程 (之後開舊檔要拒絕, 這份不能被動到)."""
    src = os.path.join(a.flows_dir, "good" + flowfile.EXT)
    flowfile.write(src, {"steps": [_find("gear")], "coordSpace": "anchor",
                         "scanRegion": [5, 6, 700, 500]}, {"gear": b"GEAR"})
    _stub_open(monkeypatch, src)
    a.open_flow()
    assert a.ws.names() == ["gear"]
    return src


def test_開啟座標相對搜尋範圍的舊存檔_拒絕並說明_目前流程不動(tkroot, tmp_path,
                                                 monkeypatch, no_real_dialogs):
    a = _app(tkroot, tmp_path)
    good = _loaded(a, tkroot, tmp_path, monkeypatch)
    old = os.path.join(a.flows_dir, "old" + flowfile.EXT)
    _old_pack(old, {"steps": [_find("btn"), {"type": "click", "click": [30, 40]}],
                    "coordSpace": "region", "flowFormat": 4,
                    "calibration": {"pair": ["btn", "x"], "baseline": 100.0}},
              {"btn": b"B"})
    _stub_open(monkeypatch, old)

    a.open_flow()

    assert [m for m in no_real_dialogs["warning"] if "舊格式" in m and "座標基準不同" in m]
    assert a.steps == [_find("gear")], "目前的流程原封不動"
    assert a.ws.names() == ["gear"] and a.ws.flow_path() == good
    assert any("舊格式" in m for m in a.logged)


def test_開啟舊flow_json與舊流程包_同樣拒絕_profile不多出存檔(tkroot, tmp_path,
                                                      monkeypatch, no_real_dialogs):
    a = _app(tkroot, tmp_path)
    before = flowfile.list_flows(a.profile_dir)
    src = tmp_path / "old.json"
    src.write_text(json.dumps({
        "steps": [{"type": "find_click", "template": "cn/V.png"},
                  {"type": "click", "click": [300, 250]}],
        "scanRegion": [100, 50, 800, 600]}), encoding="utf-8")
    _stub_open(monkeypatch, src)
    a.open_flow()
    pack = tmp_path / ("legacy" + flowfile.EXT)
    _old_pack(str(pack), {"steps": [{"type": "find_click", "template": "cn/V.png"}],
                          "coordSpace": "region"}, {"cn/V/a": b"A"})
    _stub_open(monkeypatch, pack)
    a.open_flow()

    assert len([m for m in no_real_dialogs["warning"] if "舊格式" in m]) == 2
    assert flowfile.list_flows(a.profile_dir) == before
    assert a.steps == [] and a.ws.names() == []


def test_舊格式匯入已退場(tkroot, tmp_path):
    a = _app(tkroot, tmp_path)
    assert not hasattr(a, "_log_conversion")
    assert not hasattr(flowfile, "import_legacy")


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
    assert flowfile.read_draft(a.profile_dir)["steps"] == a.steps
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
    draft = json.loads(open(flowfile.draft_path(a.profile_dir), encoding="utf-8").read())
    assert draft["coordSpace"] == "anchor", "草稿與存檔同一套座標空間"


def test_舊格式的草稿不復原_開空白並提示一次(tkroot, tmp_path, no_real_dialogs):
    a = _app(tkroot, tmp_path)
    os.makedirs(a.flows_dir, exist_ok=True)
    with open(flowfile.draft_path(a.profile_dir), "w", encoding="utf-8") as f:
        json.dump({"steps": [_find("btn"), {"type": "click", "click": [30, 40]}],
                   "coordSpace": "region", "scanRegion": [1, 2, 300, 200]}, f)

    a._load_autosave()
    a.root.update()   # 提示排在事件迴圈 (主視窗先開)

    assert a.steps == [] and a.scan_region is None
    assert len([m for m in no_real_dialogs["warning"] if "草稿" in m]) == 1
    assert any("座標基準不同" in m for m in a.logged)


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

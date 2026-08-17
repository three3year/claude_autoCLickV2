"""流程存檔 (自包自足的 zip) 與工作區: 資料進資料出 (暫存目錄真測, 不 mock).

對外行為＝存檔檔案的內容 (裡面有哪些範本、步驟引用指向誰)、開啟後得到的流程
資料、工作區在各操作之後的狀態。不斷言內部欄位、不斷言私有函式被呼叫。

舊格式匯入的既有規則 (座標空間遷移、每步 threshold 安靜丟棄、範本引用去副檔名、
多截圖取`登錄基準張`) 全部保留為回歸線。
"""
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calibration  # noqa: E402
import flowfile  # noqa: E402


def make_profile(tmp_path, name="p"):
    d = tmp_path / name
    (d / "flows").mkdir(parents=True)
    return d


def legacy_flow(steps=None, **extra):
    data = {
        "steps": steps if steps is not None else [
            {"type": "find_click", "template": "cn/V.png", "threshold": 0.85,
             "timeout": 10, "action": "click"},
            {"type": "click", "x": 300, "y": 250},
        ],
        "runMode": "count", "runCount": 1,
        "scanRegion": [100, 50, 800, 600], "avoidHover": False,
    }
    data.update(extra)
    return data


def find_step(template, **extra):
    s = {"type": "find_click", "template": template, "action": "click"}
    s.update(extra)
    return s


def flow(steps, **extra):
    data = {"steps": steps, "coordSpace": "region"}
    data.update(extra)
    return data


# ---------- 遷移規則 (回歸線) ----------

def test_範本引用去副檔名():
    data = legacy_flow()
    flowfile.migrate_flow(data)
    assert data["steps"][0]["template"] == "cn/V"


def test_每步threshold安靜丟棄():
    data = legacy_flow()
    flowfile.migrate_flow(data)
    assert all("threshold" not in s for s in data["steps"])


def test_legacy螢幕座標換算為範圍座標():
    data = legacy_flow()
    flowfile.migrate_flow(data)
    assert data["steps"][1]["x"] == 300 - 100
    assert data["steps"][1]["y"] == 250 - 50


def test_確認圖引用同樣去副檔名():
    data = legacy_flow(steps=[{"type": "find_click", "template": "a.png",
                               "confirm": "appear",
                               "confirmTemplate": "ok.png"}])
    flowfile.migrate_flow(data)
    s = data["steps"][0]
    assert (s["template"], s["confirmTemplate"]) == ("a", "ok")


def test_新格式資料再遷移是no_op():
    data = {"steps": [{"type": "find_click", "template": "V"},
                      {"type": "click", "x": 30, "y": 40}],
            "scanRegion": [100, 50, 800, 600], "coordSpace": "region"}
    assert flowfile.migrate_flow(data) == []
    assert data["steps"][0]["template"] == "V"
    assert data["steps"][1]["x"] == 30


# ---------- 名稱規則 ----------

def test_撞名加序號():
    assert flowfile.free_name("btn", []) == "btn"
    assert flowfile.free_name("btn", ["btn"]) == "btn_2"
    assert flowfile.free_name("btn", ["btn", "btn_2"]) == "btn_3"
    # 末端已是 _數字 → 從該數字往上找, 不疊字
    assert flowfile.free_name("btn_2", ["btn_2"]) == "btn_3"
    assert flowfile.free_name("btn_002", ["btn_002"]) == "btn_003"


def test_範本名拉平掉子路徑前綴():
    assert flowfile.flatten_name("cn/返回") == "返回"
    assert flowfile.flatten_name("a/b/c") == "c"
    assert flowfile.flatten_name("plain") == "plain"


def test_使用者輸入的名稱沒有資料夾層級():
    assert flowfile.clean_name("zh/按鈕") == "zh_按鈕"
    assert flowfile.clean_name("a:b?c") == "a_b_c"


def test_改寫引用含確認圖():
    steps = [find_step("old"), find_step("x", confirm="appear",
                                         confirmTemplate="old"),
             {"type": "wait", "ms": 10}]
    assert flowfile.rename_refs(steps, "old", "new") == 2
    assert steps[0]["template"] == "new"
    assert steps[1]["confirmTemplate"] == "new"


# ---------- 存檔內容 ----------

def test_存檔只寫入被步驟引用的範本(tmp_path):
    path = tmp_path / ("f" + flowfile.EXT)
    images = {"used": b"U", "cfm": b"C", "junk": b"J"}
    data = flow([find_step("used", confirm="appear", confirmTemplate="cfm")])
    missing = flowfile.write(str(path), data, images)
    assert missing == []
    assert flowfile.template_names(str(path)) == ["cfm", "used"]
    with zipfile.ZipFile(path) as z:
        assert "templates/junk.png" not in z.namelist()


def test_刪掉引用它的步驟後再存檔_那張圖離開存檔(tmp_path):
    path = tmp_path / ("f" + flowfile.EXT)
    images = {"a": b"A", "b": b"B"}
    flowfile.write(str(path), flow([find_step("a"), find_step("b")]), images)
    assert flowfile.template_names(str(path)) == ["a", "b"]
    flowfile.write(str(path), flow([find_step("a")]), images)
    assert flowfile.template_names(str(path)) == ["a"]


def test_存檔讀回等價的流程資料與範本(tmp_path):
    path = tmp_path / ("f" + flowfile.EXT)
    steps = [find_step("btn", offsetX=3, offsetY=-4),
             {"type": "wait", "ms": 500}]
    data = flow(steps, runMode="count", runCount=2,
                scanRegion=[10, 20, 800, 600], avoidHover=True)
    flowfile.write(str(path), data, {"btn": b"IMG"}, {"btn": [11, 22]})
    r = flowfile.read(str(path))
    assert r["data"]["steps"] == steps
    assert r["data"]["scanRegion"] == [10, 20, 800, 600]
    assert r["data"]["avoidHover"] is True
    assert r["images"] == {"btn": b"IMG"}
    assert r["pos"] == {"btn": [11, 22]}
    assert r["cal"] is None


def test_被引用卻缺圖的範本如實回報(tmp_path):
    path = tmp_path / ("f" + flowfile.EXT)
    missing = flowfile.write(str(path), flow([find_step("gone")]), {})
    assert missing == ["gone"]
    assert flowfile.template_names(str(path)) == []


def test_只讀索引取得範本清單與單張圖(tmp_path):
    path = tmp_path / ("f" + flowfile.EXT)
    flowfile.write(str(path), flow([find_step("a"), find_step("b")]),
                   {"a": b"AAA", "b": b"BBB"})
    assert flowfile.template_names(str(path)) == ["a", "b"]
    assert flowfile.template_bytes(str(path), "b") == b"BBB"
    assert flowfile.template_bytes(str(path), "nope") is None


def test_存檔攜帶校準對兩張圖與基準距離(tmp_path):
    path = tmp_path / ("f" + flowfile.EXT)
    cal = {"pair": ["calA", "calB"], "baseline": 123.5,
           "scale": 1.0, "fingerprint": None}
    flowfile.write(str(path), flow([find_step("btn")]), {"btn": b"B"},
                   cal=cal, cal_images={"calA": b"A", "calB": b"BB"})
    r = flowfile.read(str(path))
    assert r["cal"] == {"pair": ["calA", "calB"], "baseline": 123.5}
    assert r["cal_images"] == {"calA": b"A", "calB": b"BB"}
    # 校準對的圖不混進本流程的範本清單 (它不被步驟引用)
    assert flowfile.template_names(str(path)) == ["btn"]


def test_沒有校準對時存檔不帶校準資料(tmp_path):
    path = tmp_path / ("f" + flowfile.EXT)
    flowfile.write(str(path), flow([find_step("btn")]), {"btn": b"B"})
    with zipfile.ZipFile(path) as z:
        assert flowfile.CAL_ENTRY not in z.namelist()


def test_改寫存檔內的流程資料_範本圖原樣不動(tmp_path):
    path = tmp_path / ("f" + flowfile.EXT)
    flowfile.write(str(path), flow([{"type": "click", "x": 30, "y": 40}]),
                   {"btn": b"KEEPME"})
    flowfile.write(str(path), flow([find_step("btn"),
                                    {"type": "click", "x": 30, "y": 40}]),
                   {"btn": b"KEEPME"})

    def double(data):
        calibration.scale_steps(data["steps"], 2.0)

    data = flowfile.update_flow_data(str(path), double)
    assert (data["steps"][1]["x"], data["steps"][1]["y"]) == (60, 80)
    r = flowfile.read(str(path))
    assert r["data"]["steps"][1]["x"] == 60
    assert r["images"] == {"btn": b"KEEPME"}


def test_列舉profile內的流程存檔_草稿不算一份流程(tmp_path):
    profile = make_profile(tmp_path)
    for stem in ("b", "a"):
        flowfile.write(str(profile / "flows" / (stem + flowfile.EXT)),
                       flow([]), {})
    (profile / "flows" / flowfile.DRAFT_NAME).write_text("{}", encoding="utf-8")
    got = [os.path.basename(p) for p in flowfile.list_flows(str(profile))]
    assert got == ["a" + flowfile.EXT, "b" + flowfile.EXT]


# ---------- 工作區 ----------

def test_工作區解壓存檔後拿得到範本圖與pos(tmp_path):
    profile = make_profile(tmp_path)
    path = str(profile / "flows" / ("f" + flowfile.EXT))
    flowfile.write(path, flow([find_step("a"), find_step("b")]),
                   {"a": b"AA", "b": b"BB"}, {"a": [5, 6]})
    ws = flowfile.Workspace(str(profile))
    ws.load_flow(path)
    assert ws.names() == ["a", "b"]
    assert open(ws.path_of("a"), "rb").read() == b"AA"
    assert ws.pos_of("a") == [5, 6]
    assert ws.pos_of("b") is None
    assert ws.flow_path() == path


def test_切換流程時工作區整個清空_圖與登錄產物一起刪(tmp_path):
    profile = make_profile(tmp_path)
    ws = flowfile.Workspace(str(profile))
    ws.add("old", b"O")
    os.makedirs(os.path.join(ws.registered_dir, "old"), exist_ok=True)
    open(os.path.join(ws.registered_dir, "old", "ref.png"), "wb").write(b"R")

    other = str(profile / "flows" / ("other" + flowfile.EXT))
    flowfile.write(other, flow([find_step("new")]), {"new": b"N"})
    ws.load_flow(other)

    assert ws.names() == ["new"]
    assert not os.path.exists(os.path.join(ws.registered_dir, "old"))
    assert ws.pos() == {}


def test_工作區被手動刪掉能自動重建(tmp_path):
    profile = make_profile(tmp_path)
    ws = flowfile.Workspace(str(profile))
    path = str(profile / "flows" / ("f" + flowfile.EXT))
    flowfile.write(path, flow([find_step("a")]), {"a": b"AA"})
    ws.load_flow(path)
    import shutil
    shutil.rmtree(ws.root)
    assert ws.names() == []          # 快取不見了也不炸
    ws.load_flow(path)               # 真相來源是存檔 → 重建
    assert ws.names() == ["a"]


def test_加入範本撞名自動加序號(tmp_path):
    ws = flowfile.Workspace(str(make_profile(tmp_path)))
    assert ws.add("btn", b"1") == "btn"
    assert ws.add("btn", b"2") == "btn_2"
    assert open(ws.path_of("btn"), "rb").read() == b"1", "原有的圖不被蓋掉"
    assert open(ws.path_of("btn_2"), "rb").read() == b"2"


def test_跨流程複製進來的是獨立副本_來源改圖不影響本流程(tmp_path):
    profile = make_profile(tmp_path)
    src = str(profile / "flows" / ("src" + flowfile.EXT))
    flowfile.write(src, flow([find_step("shared")]), {"shared": b"V1"})
    ws = flowfile.Workspace(str(profile))
    name = ws.add("shared", flowfile.template_bytes(src, "shared"))
    # 來源流程日後改圖
    flowfile.write(src, flow([find_step("shared")]), {"shared": b"V2"})
    assert open(ws.path_of(name), "rb").read() == b"V1"


def test_pos只記本流程自己拍的圖(tmp_path):
    ws = flowfile.Workspace(str(make_profile(tmp_path)))
    ws.add("shot", b"S", pos=[100, 200])
    ws.add("copied", b"C")              # 跨流程複製/磁碟上傳: 沒有 pos
    assert ws.pos_of("shot") == [100, 200]
    assert ws.pos_of("copied") is None


def test_重新命名範本_引用同步改寫(tmp_path):
    ws = flowfile.Workspace(str(make_profile(tmp_path)))
    ws.add("a", b"A", pos=[1, 2])
    steps = [find_step("a", confirm="appear", confirmTemplate="a")]
    new = ws.rename("a", "b")
    assert new == "b"
    assert flowfile.rename_refs(steps, "a", new) == 2
    assert ws.names() == ["b"]
    assert ws.pos_of("b") == [1, 2]
    assert steps[0]["template"] == "b"


def test_刪除範本後圖與登錄產物都不在(tmp_path):
    ws = flowfile.Workspace(str(make_profile(tmp_path)))
    ws.add("a", b"A", pos=[1, 2])
    os.makedirs(os.path.join(ws.registered_dir, "a"), exist_ok=True)
    ws.remove("a")
    assert ws.names() == []
    assert ws.pos() == {}
    assert not os.path.exists(os.path.join(ws.registered_dir, "a"))


def test_工作區存回存檔_只帶被引用的圖(tmp_path):
    profile = make_profile(tmp_path)
    ws = flowfile.Workspace(str(profile))
    ws.add("used", b"U", pos=[3, 4])
    ws.add("junk", b"J")
    path = str(profile / "flows" / ("f" + flowfile.EXT))
    assert ws.put_flow(flow([find_step("used")]), path=path) == []
    r = flowfile.read(path)
    assert sorted(r["images"]) == ["used"]
    assert r["pos"] == {"used": [3, 4]}


def test_存檔與載入的round_trip(tmp_path):
    profile = make_profile(tmp_path)
    ws = flowfile.Workspace(str(profile))
    ws.add("a", b"AAA", pos=[7, 8])
    ws.add("b", b"BBB")
    steps = [find_step("a", timeout=5, interval=0.5, onNotFound="skip"),
             find_step("b", action="none"), {"type": "wait", "ms": 500}]
    data = flow(steps, runMode="count", runCount=2,
                scanRegion=[10, 20, 800, 600], avoidHover=True)
    path = str(profile / "flows" / ("rt" + flowfile.EXT))
    ws.put_flow(data, path=path)

    ws2 = flowfile.Workspace(str(make_profile(tmp_path, "q")))
    r = ws2.load_flow(path)
    assert r["data"]["steps"] == steps
    assert r["data"]["scanRegion"] == [10, 20, 800, 600]
    assert ws2.names() == ["a", "b"]
    assert open(ws2.path_of("a"), "rb").read() == b"AAA"
    assert ws2.pos_of("a") == [7, 8]


# ---------- 一次性轉換規則 ----------

def write_library(root, templates):
    """templates: {舊範本名: {截圖名: bytes}} 或 {舊範本名: bytes} (單檔)."""
    root = str(root)
    for name, val in templates.items():
        if isinstance(val, dict):
            d = os.path.join(root, *name.split("/"))
            os.makedirs(d, exist_ok=True)
            for cap, blob in val.items():
                with open(os.path.join(d, cap + ".png"), "wb") as f:
                    f.write(blob)
        else:
            p = os.path.join(root, *name.split("/")) + ".png"
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(val)
    return root


def test_掃目錄認出單檔與多截圖範本(tmp_path):
    root = write_library(tmp_path / "t", {
        "flat": b"F", "cn/V": {"cn": b"1", "翻新": b"2"}, "zh/X": {"zh": b"3"}})
    lib = flowfile.scan_templates(root)
    assert sorted(lib) == ["cn/V", "flat", "zh/X"]
    assert len(lib["cn/V"]) == 2
    assert len(lib["zh/X"]) == 1


def test_多截圖取登錄基準張_排序後第一張(tmp_path):
    root = write_library(tmp_path / "t", {"m": {"b": b"B", "a": b"A"}})
    caps = flowfile.scan_templates(root)["m"]
    assert flowfile.baseline_capture(caps).name == "a.png"


def test_轉換規則_拉平撞名加序號並改寫引用(tmp_path):
    root = write_library(tmp_path / "t", {
        "cn/返回": {"cn": b"CN", "翻新": b"NEW"},
        "zh/返回": {"zh": b"ZH"}})
    lib = flowfile.scan_templates(root)
    steps = [find_step("cn/返回"), find_step("zh/返回")]
    r = flowfile.collect_flow_templates(steps, lib)

    assert sorted(r["images"]) == ["返回", "返回_2"]
    assert [s["template"] for s in steps] == ["返回", "返回_2"]
    assert r["renamed"] == {"cn/返回": "返回", "zh/返回": "返回_2"}
    assert r["downgraded"] == ["返回"], "只有原本多截圖的才算降級"
    assert r["images"]["返回"].name == "cn.png", "取登錄基準張"


def test_轉換規則_範本庫裡沒有的範本如實回報(tmp_path):
    lib = flowfile.scan_templates(write_library(tmp_path / "t", {"a": b"A"}))
    steps = [find_step("a"), find_step("ghost")]
    r = flowfile.collect_flow_templates(steps, lib)
    assert r["missing"] == ["ghost"]
    assert sorted(r["images"]) == ["a"]


# ---------- 舊格式匯入 ----------

def test_匯入舊flow_json會遷移並存成新格式存檔(tmp_path):
    profile = make_profile(tmp_path)
    write_library(profile / "templates", {"cn/V": {"cn": b"1", "翻新": b"2"}})
    src = tmp_path / "morning.json"
    src.write_text(json.dumps(legacy_flow()), encoding="utf-8")

    r = flowfile.import_legacy(str(src), str(profile))

    assert os.path.dirname(r["flow_path"]) == str(profile / "flows")
    assert os.path.basename(r["flow_path"]) == "morning" + flowfile.EXT
    assert r["templates"] == ["V"]
    assert r["downgraded"] == ["V"]
    back = flowfile.read(r["flow_path"])
    assert back["data"]["coordSpace"] == "region"
    assert back["data"]["steps"][0]["template"] == "V"
    assert "threshold" not in back["data"]["steps"][0]
    assert back["images"]["V"] == b"1", "多截圖取登錄基準張"


def test_同名匯入不覆蓋(tmp_path):
    profile = make_profile(tmp_path)
    write_library(profile / "templates", {"cn/V": {"cn": b"1"}})
    src = tmp_path / "f.json"
    src.write_text(json.dumps(legacy_flow()), encoding="utf-8")
    p1 = flowfile.import_legacy(str(src), str(profile))["flow_path"]
    p2 = flowfile.import_legacy(str(src), str(profile))["flow_path"]
    assert p1 != p2 and os.path.exists(p1) and os.path.exists(p2)


def make_old_pack(path, flow_data, images, pos=None, cal=None):
    """舊流程包: templates/ 下是相對路徑佈局 (單檔或多截圖目錄)."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("flow.json", json.dumps(flow_data, ensure_ascii=False))
        if cal is not None:
            z.writestr("calibration.json", json.dumps(cal, ensure_ascii=False))
        z.writestr("templates/_meta.json",
                   json.dumps({"pos": pos or {}}, ensure_ascii=False))
        for rel, content in images.items():
            z.writestr(f"templates/{rel}", content)


def test_匯入舊流程包_轉成新存檔並拉平名稱(tmp_path):
    profile = make_profile(tmp_path)
    pack = tmp_path / ("m" + flowfile.EXT)
    make_old_pack(pack, legacy_flow(steps=[
        {"type": "find_click", "template": "cn/V.png", "threshold": 0.9},
        {"type": "find_click", "template": "cn/X.png"}]),
        {"cn/V/cn.png": b"V1", "cn/V/翻新.png": b"V2", "cn/X.png": b"XX"},
        pos={"cn/V": [1, 2]})

    r = flowfile.import_legacy(str(pack), str(profile))

    assert r["templates"] == ["V", "X"]
    assert r["downgraded"] == ["V"]
    back = flowfile.read(r["flow_path"])
    assert [s["template"] for s in back["data"]["steps"]] == ["V", "X"]
    assert back["images"] == {"V": b"V1", "X": b"XX"}
    assert back["pos"] == {"V": [1, 2]}


def test_匯入舊流程包_未被引用的範本不進新存檔(tmp_path):
    profile = make_profile(tmp_path)
    pack = tmp_path / ("m" + flowfile.EXT)
    make_old_pack(pack, legacy_flow(steps=[
        {"type": "find_click", "template": "a.png"}]),
        {"a.png": b"A", "junk.png": b"J"})
    r = flowfile.import_legacy(str(pack), str(profile))
    assert r["templates"] == ["a"]


# ---------- 匯入換算三分支 (ADR 0005) ----------

def _steps_with_offsets():
    return [{"type": "find_click", "template": "a", "offsetX": 10,
             "offsetY": -8},
            {"type": "click", "x": 30, "y": 40},
            {"type": "drag", "x1": 4, "y1": 4, "x2": 40, "y2": 80,
             "mode": "prev"}]


def _foreign_flow(tmp_path, cal, stem="src"):
    """另一個 profile 的存檔 (帶校準資料), 供「開啟外來檔」測試."""
    other = make_profile(tmp_path, "other")
    path = str(other / "flows" / (stem + flowfile.EXT))
    flowfile.write(path, flow(_steps_with_offsets()), {"a": b"A"},
                   cal=cal, cal_images={"calA": b"CA", "calB": b"CB"})
    return path


def test_開啟外來檔_目標無校準資料則採用來源的且倍率留空(tmp_path):
    profile = make_profile(tmp_path)
    src = _foreign_flow(tmp_path, {"pair": ["calA", "calB"], "baseline": 200.0,
                                   "scale": 1.0, "fingerprint": None})
    r = flowfile.adopt_foreign_flow(src, str(profile))
    assert r["calibration"] == {"kind": "adopted", "pair": ["calA", "calB"]}
    cal = calibration.load(str(profile))
    assert (cal["pair"], cal["baseline"]) == (["calA", "calB"], 200.0)
    assert cal["scale"] is None, "倍率留空＝未校準"
    assert r["data"]["steps"][1]["x"] == 30, "座標原樣落地"


def test_開啟外來檔_同一對依基準比值換算落地(tmp_path):
    profile = make_profile(tmp_path)
    calibration.save(str(profile), {"pair": ["calB", "calA"],  # 順序無關
                                    "baseline": 200.0, "scale": 1.0,
                                    "fingerprint": None})
    src = _foreign_flow(tmp_path, {"pair": ["calA", "calB"], "baseline": 100.0,
                                   "scale": 1.0, "fingerprint": None})
    r = flowfile.adopt_foreign_flow(src, str(profile))
    assert r["calibration"]["kind"] == "converted"
    assert r["calibration"]["ratio"] == 2.0
    s = r["data"]["steps"]
    assert (s[0]["offsetX"], s[0]["offsetY"]) == (20, -16)
    assert (s[1]["x"], s[1]["y"]) == (60, 80)
    assert (s[2]["x1"], s[2]["x2"], s[2]["y2"]) == (8, 80, 160)
    assert calibration.SOURCE_BASELINE not in r["data"]
    assert calibration.load(str(profile))["baseline"] == 200.0


def test_開啟外來檔_不同對照來源尺度落地並附來源基準標記(tmp_path):
    profile = make_profile(tmp_path)
    calibration.save(str(profile), {"pair": ["x", "y"], "baseline": 300.0,
                                    "scale": 1.0, "fingerprint": None})
    src = _foreign_flow(tmp_path, {"pair": ["calA", "calB"], "baseline": 100.0,
                                   "scale": 1.0, "fingerprint": None})
    r = flowfile.adopt_foreign_flow(src, str(profile))
    assert r["calibration"] == {"kind": "foreign", "pair": ["calA", "calB"]}
    assert r["data"]["steps"][1]["x"] == 30
    assert r["data"][calibration.SOURCE_BASELINE] == {
        "pair": ["calA", "calB"], "baseline": 100.0}
    assert calibration.load(str(profile))["pair"] == ["x", "y"]


def test_開啟外來檔_複製副本進profile_原檔不被動到(tmp_path):
    profile = make_profile(tmp_path)
    src = _foreign_flow(tmp_path, None)
    before = open(src, "rb").read()
    r = flowfile.adopt_foreign_flow(src, str(profile))
    assert flowfile.is_inside_profile(r["flow_path"], str(profile))
    assert open(src, "rb").read() == before
    assert flowfile.template_names(r["flow_path"]) == ["a"]


def test_開啟外來檔_無校準資料時不產生校準資料(tmp_path):
    profile = make_profile(tmp_path)
    src = _foreign_flow(tmp_path, None)
    r = flowfile.adopt_foreign_flow(src, str(profile))
    assert r["calibration"] is None
    assert calibration.load(str(profile)) is None

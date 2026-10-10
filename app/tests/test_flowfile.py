"""流程存檔 (自包自足的 zip) 與工作區: 資料進資料出 (暫存目錄真測, 不 mock).

對外行為＝存檔檔案的內容 (裡面有哪些範本、步驟引用指向誰)、開啟後得到的流程
資料、工作區在各操作之後的狀態。不斷言內部欄位、不斷言私有函式被呼叫。

舊格式 (座標相對搜尋範圍或更早) 的存檔、步驟草稿、舊 JSON、舊流程包一律拒絕開啟
並帶原因 (ADR 0012); 以前的遷移規則不再存在。
"""
import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calibration  # noqa: E402
import flowfile  # noqa: E402
from automation import flowfmt  # noqa: E402


def make_profile(tmp_path, name="p"):
    d = tmp_path / name
    (d / "flows").mkdir(parents=True)
    return d


def find_step(template, confirm_tmpl=None, **extra):
    """找圖步驟: 範本在`找圖目標`裡; confirm_tmpl＝確認圖 (點到確認圖出現)."""
    s = {"type": "find_click", "target": {"template": template},
         "type": "find_click"}
    if confirm_tmpl is not None:
        s.update(confirm="appear", confirm_target={"template": confirm_tmpl})
    s.update(extra)
    return s


def tmpl(step):
    return step["target"]["template"]


def flow(steps, **extra):
    """現行格式的流程資料 (座標相對`座標基準點`)."""
    data = {"steps": steps, flowfmt.COORD_SPACE: flowfmt.ANCHOR}
    data.update(extra)
    return data


def write_pack(path, data, images, meta=None):
    """照給的 data 原樣寫一個 zip (不經 flowfile.write 蓋章): 做舊格式檔用."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("flow.json", json.dumps(data, ensure_ascii=False))
        z.writestr("templates/_meta.json", json.dumps(meta or {"pos": {}}))
        for n, blob in images.items():
            z.writestr(f"templates/{n}.png", blob)


# ---------- 現行格式: 寫讀往返 ----------

def test_寫出的存檔蓋章目前版本與座標空間(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    flowfile.write(path, flow([find_step("a")]), {"a": b"A"})
    with zipfile.ZipFile(path) as z:
        raw = json.loads(z.read("flow.json"))
    assert raw["flowFormat"] == flowfile.FORMAT == 5
    assert raw["coordSpace"] == "anchor"
    assert flowfile.is_flow_file(path)


def test_沒標或標舊座標空間的資料都不能寫成存檔(tmp_path):
    """寫檔要呼叫端明確說「相對基準點」: 跟讀檔「沒標記＝舊格式」對稱, 不猜."""
    path = str(tmp_path / ("f" + flowfile.EXT))
    for data in ({"steps": [], "coordSpace": "region"}, {"steps": [find_step("a")]}):
        with pytest.raises(ValueError):
            flowfile.write(path, data, {"a": b"A"})
    assert not os.path.exists(path)


def test_存檔讀回等價的流程資料與範本(tmp_path):
    path = tmp_path / ("f" + flowfile.EXT)
    steps = [find_step("btn", offset=[3, -4]),
             {"type": "click", "click": [30, -40]},
             {"type": "wait", "wait": 0.5}]
    data = flow(steps, runMode="count", runCount=2,
                scanRegion=[10, 20, 800, 600])
    flowfile.write(str(path), data, {"btn": b"IMG"}, {"btn": [11, -22]})
    r = flowfile.read(str(path))
    assert r["data"]["steps"] == steps
    assert r["data"]["scanRegion"] == [10, 20, 800, 600]
    assert r["images"] == {"btn": b"IMG"}
    assert r["pos"] == {"btn": [11, -22]}, "拍攝位置相對基準點, 可以是負的"


def test_固定矩形與指定點存檔與草稿往返(tmp_path):
    rect = [-120, 35, 250, 60]
    near = {"near": [5, -7]}
    step = {"type": "find_click",
            "target": {"template": "a", "within": rect, "pick": near},
            "confirm": "appear",
            "confirm_target": {"template": "b", "within": list(rect)}}
    data = flow([step], busyTarget={"template": "a", "within": list(rect)})
    path = str(tmp_path / ("f" + flowfile.EXT))
    flowfile.write(path, data, {"a": b"A", "b": b"B"})
    back = flowfile.read(path)["data"]
    assert back["steps"][0]["target"]["within"] == rect
    assert back["steps"][0]["target"]["pick"] == near
    assert back["steps"][0]["confirm_target"]["within"] == rect
    assert back["busyTarget"]["within"] == rect
    flowfile.write_draft(str(tmp_path), back)
    draft = flowfile.read_draft(str(tmp_path))
    assert draft["steps"][0]["target"]["within"] == rect
    assert draft["busyTarget"]["within"] == rect


# ---------- 舊格式一律拒絕 ----------

def _old_pack(tmp_path, data, stem="old"):
    path = str(tmp_path / (stem + flowfile.EXT))
    write_pack(path, data, {"a": b"A"})
    return path


@pytest.mark.parametrize("data", [
    {"steps": [find_step("a")], "coordSpace": "region", "flowFormat": 4,
     "calibration": {"pair": ["a", "b"], "baseline": 100.0}},
    {"steps": [find_step("a")], "coordSpace": "region", "flowFormat": 3},
    {"steps": [{"type": "find_click", "template": "a.png"}],
     "coordSpace": "region", "flowFormat": 2},
    {"steps": [{"type": "click", "click": [300, 250]}],
     "scanRegion": [100, 50, 800, 600]},
    {"steps": [find_step("a")], "flowFormat": 5},
    {"steps": [find_step("a")], "coordSpace": "anchor", "flowFormat": 4},
], ids=["格式4座標相對搜尋範圍", "格式3", "格式2範本掛在步驟上", "舊流程包沒有標記",
        "格式5卻沒有座標空間標記", "座標空間對但版本舊"])
def test_舊格式存檔拒絕開啟並說明原因(tmp_path, data):
    path = _old_pack(tmp_path, data)
    assert not flowfile.is_flow_file(path)
    with pytest.raises(flowfile.OldFormatError) as e:
        flowfile.read(path)
    assert "舊格式" in str(e.value) and "座標基準不同" in str(e.value)


def test_舊flow_json拒絕開啟(tmp_path):
    src = tmp_path / "old.json"
    src.write_text(json.dumps({"steps": [{"type": "click", "click": [1, 2]}],
                               "scanRegion": [0, 0, 10, 10]}), encoding="utf-8")
    assert not flowfile.is_flow_file(str(src))
    with pytest.raises(flowfile.OldFormatError, match="舊格式"):
        flowfile.read(str(src))


def test_不是zip或沒有flow_json的檔也拒絕(tmp_path):
    junk = tmp_path / ("junk" + flowfile.EXT)
    junk.write_bytes(b"not a zip")
    with pytest.raises(flowfile.OldFormatError):
        flowfile.read(str(junk))
    nozip = tmp_path / ("empty" + flowfile.EXT)
    with zipfile.ZipFile(nozip, "w") as z:
        z.writestr("templates/a.png", b"A")
    assert not flowfile.is_flow_file(str(nozip))
    with pytest.raises(flowfile.OldFormatError):
        flowfile.read(str(nozip))


def test_舊格式的步驟草稿不復原並說明(tmp_path):
    profile = make_profile(tmp_path)
    with open(flowfile.draft_path(str(profile)), "w", encoding="utf-8") as f:
        json.dump({"steps": [find_step("a")], "coordSpace": "region",
                   "flowFormat": 4}, f)
    with pytest.raises(flowfile.OldFormatError, match="座標基準不同"):
        flowfile.read_draft(str(profile))
    for data in ({"steps": [], "coordSpace": "region"}, {"steps": []}):
        with pytest.raises(ValueError):
            flowfile.write_draft(str(profile), data)
    assert flowfile.read_draft(str(make_profile(tmp_path, "q"))) is None, \
        "沒有草稿仍是 None (不是舊格式)"


def test_草稿寫入時蓋同一套格式標記_讀回照常(tmp_path):
    profile = make_profile(tmp_path)
    flowfile.write_draft(str(profile), flow([find_step("a")]))
    raw = json.loads(open(flowfile.draft_path(str(profile)), encoding="utf-8").read())
    assert raw["flowFormat"] == flowfile.FORMAT and raw["coordSpace"] == "anchor"
    assert flowfile.read_draft(str(profile))["steps"] == [find_step("a")]


def test_開外來的舊格式檔也拒絕_profile不多任何檔(tmp_path):
    profile = make_profile(tmp_path)
    path = _old_pack(tmp_path, {"steps": [find_step("a")], "coordSpace": "region",
                                "flowFormat": 4})
    with pytest.raises(flowfile.OldFormatError):
        flowfile.adopt_foreign_flow(path, str(profile))
    assert flowfile.list_flows(str(profile)) == []


def test_舊格式遷移已退場():
    for name in ("migrate_flow", "import_legacy", "collect_flow_templates",
                 "flatten_name", "baseline_capture", "legacy_meta_pos"):
        assert not hasattr(flowfile, name), name
    assert not hasattr(flowfmt, "to_region_space")


# ---------- 名稱規則 ----------

def test_撞名加序號():
    assert flowfile.free_name("btn", []) == "btn"
    assert flowfile.free_name("btn", ["btn"]) == "btn_2"
    assert flowfile.free_name("btn", ["btn", "btn_2"]) == "btn_3"
    # 末端已是 _數字 → 從該數字往上找, 不疊字
    assert flowfile.free_name("btn_2", ["btn_2"]) == "btn_3"
    assert flowfile.free_name("btn_002", ["btn_002"]) == "btn_003"


def test_使用者輸入的名稱沒有資料夾層級():
    assert flowfile.clean_name("zh/按鈕") == "zh_按鈕"
    assert flowfile.clean_name("a:b?c") == "a_b_c"


# ---------- 校準對 (flow-scale 票 02: 存檔格式 4) ----------

CAL = {"pair": ["圖示", "關閉"], "baseline": 1696.0}


def test_校準資料存檔往返(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    data = flow([find_step("a")])
    data[calibration.FLOW_KEY] = dict(CAL)
    flowfile.write(path, data, {"a": b"A", "圖示": b"I", "關閉": b"X"})
    r = flowfile.read(path)
    assert calibration.flow_pair(r["data"]) == CAL


def test_校準對是被引用的範本_存檔帶著它們的圖(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    data = flow([find_step("a")])
    data[calibration.FLOW_KEY] = dict(CAL)
    flowfile.write(path, data, {"a": b"A", "圖示": b"I", "關閉": b"X",
                                "沒人用": b"U"})
    assert flowfile.template_names(path) == sorted(["a", "關閉", "圖示"])
    assert flowfile.flow_refs(data) == sorted(["a", "關閉", "圖示"])


def test_改名跟著改校準對():
    data = {"steps": [find_step("圖示")], calibration.FLOW_KEY: dict(CAL, pair=list(CAL["pair"]))}
    assert flowfile.rename_flow_refs(data, "圖示", "標題列") == 2
    assert data[calibration.FLOW_KEY]["pair"] == ["標題列", "關閉"]
    assert tmpl(data["steps"][0]) == "標題列"


def test_改寫引用含確認圖():
    steps = [find_step("old"), find_step("x", "old"),
             {"type": "wait", "wait": 0.01}]
    assert flowfile.rename_refs(steps, "old", "new") == 2
    assert tmpl(steps[0]) == "new"
    assert steps[1]["confirm_target"]["template"] == "new"


# ---------- 存檔內容 ----------

def test_存檔只寫入被步驟引用的範本(tmp_path):
    path = tmp_path / ("f" + flowfile.EXT)
    images = {"used": b"U", "cfm": b"C", "junk": b"J"}
    data = flow([find_step("used", "cfm")])
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


def test_確認圖只在生效確認選確認圖出現時算引用():
    stale = find_step("x", "ghost")
    stale["confirm"] = "gone"
    assert flowfile.used_templates([stale]) == ["x"]
    assert flowfile.used_templates([find_step("x", "ok")]) == ["ok", "x"]


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
    ws.add("shot", b"S", pos=[100, -200])
    ws.add("copied", b"C")              # 跨流程複製/磁碟上傳: 沒有 pos
    assert ws.pos_of("shot") == [100, -200]
    assert ws.pos_of("copied") is None


def test_換校準對時所有拍攝位置一起改成相對新基準點(tmp_path):
    ws = flowfile.Workspace(str(make_profile(tmp_path)))
    ws.add("a", b"A", pos=[100, 50])
    ws.add("b", b"B", pos=[-20, 0])
    ws.add("c", b"C")
    assert ws.shift_pos((100, 100), (130, 90)) == 2
    assert ws.pos() == {"a": [70, 60], "b": [-50, 10]}
    assert ws.pos_of("c") is None


def test_重新命名範本_引用同步改寫(tmp_path):
    ws = flowfile.Workspace(str(make_profile(tmp_path)))
    ws.add("a", b"A", pos=[1, 2])
    steps = [find_step("a", "a")]
    new = ws.rename("a", "b")
    assert new == "b"
    assert flowfile.rename_refs(steps, "a", new) == 2
    assert ws.names() == ["b"]
    assert ws.pos_of("b") == [1, 2]
    assert tmpl(steps[0]) == "b"


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
    steps = [find_step("a", timeout=5, interval=0.5, on_fail="skip"),
             find_step("b", type="find"), {"type": "wait", "wait": 0.5}]
    data = flow(steps, runMode="count", runCount=2,
                scanRegion=[10, 20, 800, 600])
    path = str(profile / "flows" / ("rt" + flowfile.EXT))
    ws.put_flow(data, path=path)

    ws2 = flowfile.Workspace(str(make_profile(tmp_path, "q")))
    r = ws2.load_flow(path)
    assert r["data"]["steps"] == steps
    assert r["data"]["scanRegion"] == [10, 20, 800, 600]
    assert ws2.names() == ["a", "b"]
    assert open(ws2.path_of("a"), "rb").read() == b"AAA"
    assert ws2.pos_of("a") == [7, 8]


# ---------- 開啟外來檔: 原樣複製, 不換算 (ADR 0009 / 0012) ----------

def _steps_with_offsets():
    return [find_step("a", offset=[10, -8]),
            {"type": "click", "click": [30, 40]},
            {"type": "drag", "drag": [4, 4], "to": [40, 80]}]


def _foreign_flow(tmp_path, cal=None, stem="src"):
    """另一個 profile 的存檔, 供「開啟外來檔」測試."""
    other = make_profile(tmp_path, "other")
    path = str(other / "flows" / (stem + flowfile.EXT))
    data = flow(_steps_with_offsets())
    images = {"a": b"A"}
    if cal:
        data[calibration.FLOW_KEY] = dict(cal)
        images.update({n: n.encode() for n in cal["pair"]})
    flowfile.write(path, data, images)
    return path


def test_開啟外來檔_原樣複製不換算_校準對跟著走(tmp_path):
    profile = make_profile(tmp_path)
    src = _foreign_flow(tmp_path, CAL)
    r = flowfile.adopt_foreign_flow(src, str(profile))
    assert r["data"]["steps"] == _steps_with_offsets()
    assert calibration.flow_pair(r["data"]) == CAL
    assert flowfile.template_names(r["flow_path"]) == sorted(["a", "圖示", "關閉"])
    assert sorted(os.listdir(str(profile))) == ["flows"], \
        "profile 不多出任何校準資料"


def test_開啟外來檔_複製副本進profile_原檔不被動到(tmp_path):
    profile = make_profile(tmp_path)
    src = _foreign_flow(tmp_path)
    before = open(src, "rb").read()
    r = flowfile.adopt_foreign_flow(src, str(profile))
    assert flowfile.is_inside_profile(r["flow_path"], str(profile))
    assert open(src, "rb").read() == before
    assert flowfile.template_names(r["flow_path"]) == ["a"]


# ---------- 座標換算與平移 (flowfmt 純函式, coord-anchor 票 03/07) ----------

def test_存檔座標與螢幕座標互換():
    anchor = (115, 76)
    assert flowfmt.to_screen((10, -6), anchor) == (125, 70)
    assert flowfmt.from_screen((125, 70), anchor) == (10, -6)
    assert flowfmt.to_screen((10, -6), anchor, 1.5) == (130, 67)
    assert flowfmt.from_screen((130, 67), anchor, 1.5) == (10, -6)
    assert flowfmt.rect_to_screen([-10, 5, 21, 7], (100, 200), 2.0) == (80, 210, 42, 14)
    assert flowfmt.rect_from_screen((80, 210, 42, 14), (100, 200), 2.0) == [-10, 5, 21, 7]


def test_換校準對後所有存下的座標改成相對新基準點():
    rect = [100, 50, 30, 20]
    data = {"steps": [
        {"type": "click", "click": [10, 20]},
        {"type": "drag", "drag": [1, 2], "to": [3, 4]},
        {"type": "find_click", "target": {"template": "a", "within": list(rect)},
         "confirm_target": {"template": "b", "within": list(rect)}},
    ], "busyTarget": {"template": "z", "within": list(rect)}}
    assert flowfmt.shift_flow(data, (100, 100), (130, 90)) == 2 + 1
    s = data["steps"]
    assert s[0]["click"] == [10, 20], "相對原點的座標不動"
    assert (s[1]["drag"], s[1]["to"]) == ([1, 2], [3, 4])
    assert s[2]["target"]["within"] == [70, 60, 30, 20]
    assert s[2]["confirm_target"]["within"][0] == 70
    assert data["busyTarget"]["within"] == [70, 60, 30, 20]


def test_倍率不是1時換校準對_落點在捨入誤差內不變():
    """每個座標用舊基準點換到螢幕、再用新基準點換回 (流程尺度存整數, 誤差 ≤ 倍率/2 px)."""
    k, old, new = 1.7, (100, 50), (233, 97)
    data = {"steps": [{"type": "find_click", "target": {"template": "a", "within": [101, 51, 31, 21]}}]}
    before = flowfmt.rect_to_screen([101, 51, 31, 21], old, k)
    flowfmt.shift_flow(data, old, new, k)
    after = flowfmt.rect_to_screen(data["steps"][0]["target"]["within"], new, k)
    assert all(abs(a - b) <= 1 for a, b in zip(before, after))

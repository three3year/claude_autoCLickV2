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


def find_step(template, confirm_tmpl=None, **extra):
    """v3 找圖步驟: 範本在`找圖目標`裡; confirm_tmpl＝確認圖 (點到確認圖出現)."""
    s = {"type": "find_click", "target": {"template": template},
         "action": "click"}
    if confirm_tmpl is not None:
        s.update(confirm="appear", confirmTarget={"template": confirm_tmpl})
    s.update(extra)
    return s


def tmpl(step):
    return step["target"]["template"]


def flow(steps, **extra):
    data = {"steps": steps, "coordSpace": "region"}
    data.update(extra)
    return data


# ---------- 遷移規則 (回歸線) ----------

def test_範本引用去副檔名():
    data = legacy_flow()
    flowfile.migrate_flow(data)
    assert tmpl(data["steps"][0]) == "cn/V"


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
    assert (tmpl(s), s["confirmTarget"]["template"]) == ("a", "ok")


def test_新格式資料再遷移是no_op():
    data = {"steps": [find_step("V", "ok", colorCheck=True),
                      {"type": "click", "x": 30, "y": 40}],
            "scanRegion": [100, 50, 800, 600], "coordSpace": "region"}
    before = json.loads(json.dumps(data))
    assert flowfile.migrate_flow(data) == []
    assert data == before
    assert data["steps"][1]["x"] == 30


# ---------- 存檔格式 v3: 範本收進`找圖目標` (find-target 票 01) ----------

def v2_steps():
    """flowFormat 2 的步驟: 範本名直接掛在步驟上."""
    return [
        {"type": "find_click", "template": "btn", "action": "click",
         "confirm": "appear", "confirmTemplate": "ok", "offsetX": 3},
        {"type": "find_click", "template": "next", "action": "click",
         "confirm": "gone", "confirmTemplate": ""},
        {"type": "wait", "ms": 100},
    ]


def write_v2_file(path, steps, images):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("flow.json", json.dumps(
            {"steps": steps, "coordSpace": "region", "flowFormat": 2},
            ensure_ascii=False))
        z.writestr("templates/_meta.json", json.dumps({"pos": {}}))
        for n, blob in images.items():
            z.writestr(f"templates/{n}.png", blob)


def test_v2存檔讀入後範本在找圖目標裡(tmp_path):
    path = str(tmp_path / ("old" + flowfile.EXT))
    write_v2_file(path, v2_steps(), {"btn": b"B", "ok": b"O", "next": b"N"})
    assert flowfile.is_flow_file(path), "v2 自包自足存檔照樣直接開"
    steps = flowfile.read(path)["data"]["steps"]
    assert steps[0]["target"] == {"template": "btn"}
    assert steps[0]["confirmTarget"] == {"template": "ok"}
    assert steps[0]["offsetX"] == 3
    assert steps[1]["target"] == {"template": "next"}
    assert "confirmTarget" not in steps[1], "沒有確認圖就不留空目標"
    for s in steps[:2]:
        assert "template" not in s and "confirmTemplate" not in s


def test_寫出的存檔蓋章目前版本(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    flowfile.write(path, flow([find_step("a")]), {"a": b"A"})
    with zipfile.ZipFile(path) as z:
        assert json.loads(z.read("flow.json"))["flowFormat"] == flowfile.FORMAT


def test_步驟草稿讀入同樣遷移(tmp_path):
    profile = make_profile(tmp_path)
    flowfile.write_draft(str(profile), {"steps": v2_steps(),
                                        "coordSpace": "region"})
    steps = flowfile.read_draft(str(profile))["steps"]
    assert steps[0]["target"] == {"template": "btn"}
    assert steps[0]["confirmTarget"] == {"template": "ok"}


def test_存檔收的範本集合與遷移前相同(tmp_path):
    """確認圖只有「點到確認圖出現」時才算引用 (與 v2 相同)."""
    path = str(tmp_path / ("old" + flowfile.EXT))
    write_v2_file(path, v2_steps(), {"btn": b"B", "ok": b"O", "next": b"N"})
    r = flowfile.read(path)
    assert flowfile.used_templates(r["data"]["steps"]) == ["btn", "next", "ok"]
    stale = find_step("x", "ghost")
    stale["confirm"] = "gone"
    assert flowfile.used_templates([stale]) == ["x"]


def test_write收到v2形狀的步驟也先遷移(tmp_path):
    path = str(tmp_path / ("f" + flowfile.EXT))
    flowfile.write(path, flow(v2_steps()), {"btn": b"B", "ok": b"O",
                                            "next": b"N"})
    assert flowfile.template_names(path) == ["btn", "next", "ok"]
    with zipfile.ZipFile(path) as z:
        raw = json.loads(z.read("flow.json"))
    assert raw["steps"][0]["target"] == {"template": "btn"}


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


def test_舊版存檔讀進來沒有校準對(tmp_path):
    path = str(tmp_path / ("old" + flowfile.EXT))
    write_v2_file(path, v2_steps(), {"btn": b"B", "ok": b"O", "next": b"N"})
    assert calibration.flow_pair(flowfile.read(path)["data"]) is None


def test_改名跟著改校準對():
    data = {"steps": [find_step("圖示")], calibration.FLOW_KEY: dict(CAL, pair=list(CAL["pair"]))}
    assert flowfile.rename_flow_refs(data, "圖示", "標題列") == 2
    assert data[calibration.FLOW_KEY]["pair"] == ["標題列", "關閉"]
    assert tmpl(data["steps"][0]) == "標題列"


def test_改寫引用含確認圖():
    steps = [find_step("old"), find_step("x", "old"),
             {"type": "wait", "ms": 10}]
    assert flowfile.rename_refs(steps, "old", "new") == 2
    assert tmpl(steps[0]) == "new"
    assert steps[1]["confirmTarget"]["template"] == "new"


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


def test_更早版本存檔裡的校準檔安靜忽略(tmp_path):
    """ADR 0009 前的存檔帶 calibration.json 與 calibration/ 圖: 不當範本、不當校準對."""
    path = tmp_path / ("old" + flowfile.EXT)
    flowfile.write(str(path), flow([find_step("btn")]), {"btn": b"B"})
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("calibration.json", json.dumps({"pair": ["p", "q"],
                                                   "baseline": 100.0}))
        z.writestr("calibration/p.png", b"P")
    r = flowfile.read(str(path))
    assert sorted(r["images"]) == ["btn"]
    assert calibration.flow_pair(r["data"]) is None


def test_來源基準標記讀進來安靜忽略(tmp_path):
    data = flow([find_step("btn")])
    data["sourceBaseline"] = {"pair": ["p", "q"], "baseline": 100.0}
    flowfile.migrate_flow(data)
    assert "sourceBaseline" not in data


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
    assert [tmpl(s) for s in steps] == ["返回", "返回_2"]
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
    assert tmpl(back["data"]["steps"][0]) == "V"
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
    assert [tmpl(s) for s in back["data"]["steps"]] == ["V", "X"]
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


# ---------- 開啟外來檔: 原樣複製, 不換算 (ADR 0009) ----------

def _steps_with_offsets():
    return [find_step("a", offsetX=10, offsetY=-8),
            {"type": "click", "x": 30, "y": 40},
            {"type": "drag", "x1": 4, "y1": 4, "x2": 40, "y2": 80,
             "mode": "prev"}]


CAL = {"pair": ["圖示", "關閉"], "baseline": 1696.0}


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


def test_固定矩形存檔與草稿往返_格式版本不變(tmp_path):
    """busy-pause-fixed-rect 票 03: 限定範圍本來就在找圖目標裡, 讀回內容一樣."""
    rect = {"kind": "rect", "x": 0.1234, "y": 0.5, "w": 0.25, "h": 0.0625}
    step = {"type": "find_click", "target": {"template": "a", "limit": rect},
            "confirm": "appear",
            "confirmTarget": {"template": "b", "limit": dict(rect)}}
    data = {"steps": [step], "coordSpace": "region"}
    path = str(tmp_path / ("f" + flowfile.EXT))
    flowfile.write(path, data, {"a": b"A", "b": b"B"})
    back = flowfile.read(path)["data"]
    assert back["flowFormat"] == 4
    assert back["steps"][0]["target"]["limit"] == rect
    assert back["steps"][0]["confirmTarget"]["limit"] == rect
    flowfile.write_draft(str(tmp_path), back)
    draft = flowfile.read_draft(str(tmp_path))
    assert draft["steps"][0]["target"]["limit"] == rect
    assert draft["steps"][0]["confirmTarget"]["limit"] == rect

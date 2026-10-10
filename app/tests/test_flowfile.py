"""流程資料夾裡「本流程的範本」(FlowTemplates) 與名稱、引用的規則: 資料進資料出
(暫存目錄真測, 不 mock). flow.yaml 本身的讀寫在 test_flowfolder.

對外行為＝資料夾與快取在各操作之後的檔案狀態、讀回來的流程。不斷言內部欄位。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowfile  # noqa: E402
from automation import flowdefaults, flowfmt  # noqa: E402


def find_step(template, confirm_tmpl=None, **extra):
    """完整的找圖步驟; confirm_tmpl＝確認圖 (點到確認圖出現)."""
    s = {"type": "find_click", "target": {"template": template}}
    if confirm_tmpl is not None:
        s.update(confirm="appear", confirm_target={"template": confirm_tmpl})
    s.update(extra)
    return flowdefaults.complete(s)


def tmpl(step):
    return step["target"]["template"]


def flow(steps, **extra):
    f = flowfile.new_flow()
    f["steps"] = steps
    f.update(extra)
    return f


def ls(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def saved_folder(tmp_path, steps, images, name="流程"):
    """寫好一份流程資料夾 (直接用寫檔函式)."""
    folder = tmp_path / name
    flowfile.write_flow(folder, flow(steps), images)
    return folder


# ---------- 名稱規則與引用 ----------

def test_撞名加序號():
    assert flowfile.free_name("btn", []) == "btn"
    assert flowfile.free_name("btn", ["btn"]) == "btn_2"
    assert flowfile.free_name("btn", ["btn", "btn_2"]) == "btn_3"
    # 末端已是 _數字 → 從該數字往上找, 不疊字
    assert flowfile.free_name("btn_2", ["btn_2"]) == "btn_3"
    assert flowfile.free_name("btn_002", ["btn_002"]) == "btn_003"


def test_自動命名的名稱清成能當檔名():
    assert flowfile.clean_name("zh/按鈕") == "zh_按鈕"
    assert flowfile.clean_name("a:b?c") == "a_b_c"


CAL = {"pair": ["圖示", "關閉"], "baseline": 1696.0,
       "fallback": {"pair": ["標題", "叉叉"], "baseline": 1600.0, "offset": [1, 2]}}


def test_引用集合含校準對_備用校準對_忙碌指示():
    f = flow([find_step("a", "確認")], calibration=CAL, busy={"template": "忙"})
    assert sorted(flowfile.template_refs(f)) == sorted(
        ["a", "確認", "圖示", "關閉", "標題", "叉叉", "忙"])


def test_改名連動步驟_確認圖_校準對_備用校準對_忙碌指示_拍攝位置():
    import copy
    f = flow([find_step("x"), find_step("y", "x")], calibration=copy.deepcopy(CAL),
             busy={"template": "x"}, template_pos={"x": [1, 2], "y": [3, 4]})
    f["calibration"]["pair"][0] = "x"
    f["calibration"]["fallback"]["pair"][1] = "x"
    assert flowfile.rename_template_refs(f, "x", "新") == 5
    assert tmpl(f["steps"][0]) == "新"
    assert f["steps"][1]["confirm_target"]["template"] == "新"
    assert f["calibration"]["pair"] == ["新", "關閉"]
    assert f["calibration"]["fallback"]["pair"] == ["標題", "新"]
    assert f["busy"]["template"] == "新"
    assert f["template_pos"] == {"新": [1, 2], "y": [3, 4]}


def test_改寫引用含確認圖():
    steps = [find_step("old"), find_step("x", "old"), {"type": "wait", "wait": 0.01}]
    assert flowfile.rename_refs(steps, "old", "new") == 2
    assert tmpl(steps[0]) == "new"
    assert steps[1]["confirm_target"]["template"] == "new"


def test_確認圖只在生效確認選確認圖出現時算引用():
    s = find_step("a", confirm="next", confirm_target={"template": "舊的"})
    assert flowfile.used_templates([s]) == ["a"]


# ---------- 本流程的範本: 開檔、新增、改名、刪除 ----------

def test_開流程資料夾_範本是templates裡的圖_上次沒存的截圖丟掉_登錄產物留著(tmp_path):
    folder = saved_folder(tmp_path, [find_step("a")], {"a": b"A"})
    shots = folder / ".cache" / "shots"
    shots.mkdir(parents=True)
    (shots / "上次沒存.png").write_bytes(b"S")
    reg = folder / ".cache" / "registered" / "a"
    reg.mkdir(parents=True)
    (reg / "meta.json").write_text("{}", encoding="utf-8")

    store = flowfile.FlowTemplates.open(folder, tmp_path / "unsaved", {"a": [5, 6]})

    assert store.names() == ["a"]
    assert store.path_of("a") == str(folder / "templates" / "a.png")
    assert store.pos_of("a") == [5, 6]
    assert not shots.exists(), "上次沒存的截圖清掉"
    assert (reg / "meta.json").is_file(), "登錄產物留著 (過期會自己重算)"


def test_新增範本放進快取_templates不動_撞名加序號(tmp_path):
    folder = saved_folder(tmp_path, [find_step("btn")], {"btn": b"OLD"})
    store = flowfile.FlowTemplates.open(folder, tmp_path / "unsaved")
    got = store.add("btn", b"NEW", pos=[1, 2])
    assert got == "btn_2"
    assert ls(folder / "templates") == ["btn.png"], "存檔前 templates/ 不動"
    assert store.is_unsaved("btn_2") and not store.is_unsaved("btn")
    with open(store.path_of("btn_2"), "rb") as f:
        assert f.read() == b"NEW"
    assert store.pos_of("btn_2") == [1, 2] and store.pos_of("btn") is None


def test_跨流程複製進來的是獨立副本_來源改圖不影響本流程(tmp_path):
    src = tmp_path / "src.png"
    src.write_bytes(b"V1")
    store = flowfile.FlowTemplates.new(tmp_path / "unsaved")
    store.add("a", str(src))
    src.write_bytes(b"V2")
    with open(store.path_of("a"), "rb") as f:
        assert f.read() == b"V1"


def test_重新命名_快取的截圖改檔名_templates的存檔時才改(tmp_path):
    folder = saved_folder(tmp_path, [find_step("a")], {"a": b"A"})
    store = flowfile.FlowTemplates.open(folder, tmp_path / "unsaved", {"a": [1, 1]})
    store.add("shot", b"S")
    assert store.rename("shot", "新截圖") == "新截圖"
    assert ls(store.shots_dir) == ["新截圖.png"]
    assert store.rename("a", "b") == "b"
    assert store.path_of("b") == str(folder / "templates" / "a.png")
    assert store.pos_of("b") == [1, 1]
    assert store.rename("b", "新截圖") == "新截圖_2", "撞名加序號"
    assert store.rename("不存在", "x") is None


def test_刪除_快取的截圖直接刪_登錄產物一起丟(tmp_path):
    store = flowfile.FlowTemplates.new(tmp_path / "unsaved")
    store.add("a", b"A", pos=[1, 1])
    reg = os.path.join(store.registered_dir, "a")
    os.makedirs(reg)
    store.remove("a")
    assert store.names() == [] and ls(store.shots_dir) == []
    assert not os.path.exists(reg)
    assert store.pos() == {}


def test_換校準對時所有拍攝位置一起改成相對新基準點(tmp_path):
    store = flowfile.FlowTemplates.new(tmp_path / "unsaved")
    store.add("a", b"A", pos=[200, 100])
    assert store.shift_pos((100, 50), (190, 95), 0.9) == 1
    assert store.pos_of("a") == [100, 50]


# ---------- 存檔 ----------

def test_存檔_截圖搬進templates_只留被引用的_沒被引用的回到快取(tmp_path):
    folder = saved_folder(tmp_path, [find_step("a"), find_step("b")],
                          {"a": b"A", "b": b"B"})
    store = flowfile.FlowTemplates.open(folder, tmp_path / "unsaved")
    store.add("新圖", b"N")
    store.add("沒用到", b"U")
    missing = store.save(flow([find_step("a"), find_step("新圖")]))

    assert missing == []
    assert ls(folder / "templates") == sorted(["a.png", "新圖.png"])
    assert store.path_of("新圖") == str(folder / "templates" / "新圖.png")
    assert ls(store.shots_dir) == sorted(["b.png", "沒用到.png"]), \
        "沒被引用的留在快取 (這次編輯還在)"
    assert sorted(store.names()) == sorted(["a", "b", "新圖", "沒用到"])
    back = flowfile.read_flow(folder)
    assert [tmpl(s) for s in back["steps"]] == ["a", "新圖"]


def test_存檔_改名後檔名跟著改(tmp_path):
    folder = saved_folder(tmp_path, [find_step("a")], {"a": b"A"})
    store = flowfile.FlowTemplates.open(folder, tmp_path / "unsaved")
    store.rename("a", "新名")
    store.save(flow([find_step("新名")]))
    assert ls(folder / "templates") == ["新名.png"]
    assert (folder / "templates" / "新名.png").read_bytes() == b"A"


def test_存檔_拍攝位置只寫被引用的(tmp_path):
    folder = saved_folder(tmp_path, [find_step("a")], {"a": b"A"})
    store = flowfile.FlowTemplates.open(folder, tmp_path / "unsaved", {"a": [1, 2]})
    store.add("沒用到", b"U", pos=[3, 4])
    store.save(flow([find_step("a")]))
    assert flowfile.read_flow(folder)["template_pos"] == {"a": [1, 2]}


def test_新流程第一次存檔_建資料夾_截圖與登錄產物搬進去_未存檔快取清空(tmp_path):
    unsaved = tmp_path / "unsaved"
    store = flowfile.FlowTemplates.new(unsaved)
    store.add("a", b"A")
    store.add("沒用到", b"U")
    os.makedirs(os.path.join(store.registered_dir, "a"))
    folder = tmp_path / "AutoClick" / "新流程"

    store.save(flow([find_step("a")]), folder)

    assert store.folder == str(folder)
    assert ls(folder) == sorted([".cache", "flow.yaml", "templates"])
    assert ls(folder / "templates") == ["a.png"]
    assert ls(folder / ".cache" / "registered") == ["a"]
    assert ls(folder / ".cache" / "shots") == ["沒用到.png"]
    assert ls(unsaved) == []


def test_新流程存檔要給資料夾_已有資料夾的不能存到別處(tmp_path):
    store = flowfile.FlowTemplates.new(tmp_path / "unsaved")
    with pytest.raises(ValueError):
        store.save(flow([]))
    folder = saved_folder(tmp_path, [], {})
    store = flowfile.FlowTemplates.open(folder, tmp_path / "unsaved")
    with pytest.raises(ValueError):
        store.save(flow([]), tmp_path / "別處")


def test_開新流程或讀取別的流程時未存檔快取清空(tmp_path):
    unsaved = tmp_path / "unsaved"
    store = flowfile.FlowTemplates.new(unsaved)
    store.add("a", b"A")
    flowfile.FlowTemplates.new(unsaved)
    assert ls(unsaved) == []
    store = flowfile.FlowTemplates.new(unsaved)
    store.add("a", b"A")
    folder = saved_folder(tmp_path, [], {})
    flowfile.FlowTemplates.open(folder, unsaved)
    assert ls(unsaved) == []


# ---------- 其他流程資料夾 ----------

def test_列出其他流程資料夾與它們的範本(tmp_path):
    saved_folder(tmp_path, [find_step("x")], {"x": b"X"}, name="甲")
    saved_folder(tmp_path, [], {}, name="乙")
    (tmp_path / "不是流程").mkdir()
    folders = flowfile.list_flow_folders(tmp_path)
    assert [os.path.basename(p) for p in folders] == ["乙", "甲"]
    assert flowfile.folder_template_names(tmp_path / "甲") == ["x"]
    assert flowfile.folder_template_bytes(tmp_path / "甲", "x") == b"X"
    assert flowfile.folder_template_bytes(tmp_path / "甲", "沒有") is None


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
    ], "busy": {"template": "z", "within": list(rect)}}
    assert flowfmt.shift_flow(data, (100, 100), (130, 90)) == 2 + 1
    s = data["steps"]
    assert s[0]["click"] == [10, 20], "相對原點的座標不動"
    assert (s[1]["drag"], s[1]["to"]) == ([1, 2], [3, 4])
    assert s[2]["target"]["within"] == [70, 60, 30, 20]
    assert s[2]["confirm_target"]["within"][0] == 70
    assert data["busy"]["within"] == [70, 60, 30, 20]


def test_倍率不是1時換校準對_落點在捨入誤差內不變():
    """每個座標用舊基準點換到螢幕、再用新基準點換回 (流程尺度存整數, 誤差 ≤ 倍率/2 px)."""
    k, old, new = 1.7, (100, 50), (233, 97)
    data = {"steps": [{"type": "find_click",
                       "target": {"template": "a", "within": [101, 51, 31, 21]}}]}
    before = flowfmt.rect_to_screen([101, 51, 31, 21], old, k)
    flowfmt.shift_flow(data, old, new, k)
    after = flowfmt.rect_to_screen(data["steps"][0]["target"]["within"], new, k)
    assert all(abs(a - b) <= 1 for a, b in zip(before, after))

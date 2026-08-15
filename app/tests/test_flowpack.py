"""舊 flow / flow pack 匯入與新 pack 匯出: 資料進資料出 (暫存目錄真測).

匯入規則見 ticket 05: 範本引用去 .png、缺圖補進 profile (不覆蓋)、legacy
座標空間遷移、每步 threshold 安靜丟棄、存檔落在當前 profile 的 flows/。
匯出規則見 ticket 06: 自包自足、多截圖範本目錄整包、未引用的不進 pack。
"""
import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowpack  # noqa: E402


def make_profile(tmp_path, name="p"):
    d = tmp_path / name
    (d / "templates").mkdir(parents=True)
    (d / "flows").mkdir()
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


# ---------- 遷移規則 ----------

def test_範本引用去副檔名():
    data = legacy_flow()
    flowpack.migrate_flow(data)
    assert data["steps"][0]["template"] == "cn/V"


def test_每步threshold安靜丟棄():
    data = legacy_flow()
    flowpack.migrate_flow(data)
    assert all("threshold" not in s for s in data["steps"])


def test_legacy螢幕座標換算為範圍座標():
    data = legacy_flow()
    flowpack.migrate_flow(data)
    assert data["steps"][1]["x"] == 300 - 100
    assert data["steps"][1]["y"] == 250 - 50


def test_確認圖引用同樣去副檔名():
    data = legacy_flow(steps=[{"type": "find_click", "template": "a.png",
                               "confirm": "appear",
                               "confirmTemplate": "ok.png"}])
    flowpack.migrate_flow(data)
    s = data["steps"][0]
    assert (s["template"], s["confirmTemplate"]) == ("a", "ok")


def test_新格式資料再遷移是no_op():
    data = {"steps": [{"type": "find_click", "template": "cn/V"},
                      {"type": "click", "x": 30, "y": 40}],
            "scanRegion": [100, 50, 800, 600], "coordSpace": "region"}
    assert flowpack.migrate_flow(data) == []
    assert data["steps"][0]["template"] == "cn/V"
    assert data["steps"][1]["x"] == 30


# ---------- 舊 flow JSON 匯入 ----------

def test_匯入舊flow_json會遷移並存進當前profile的flows(tmp_path):
    profile = make_profile(tmp_path)
    src = tmp_path / "morning.json"
    src.write_text(json.dumps(legacy_flow()), encoding="utf-8")
    saved, data, _notes = flowpack.import_flow_json(str(src), str(profile))
    assert os.path.dirname(saved) == str(profile / "flows")
    assert os.path.basename(saved) == "morning.json"
    with open(saved, encoding="utf-8") as f:
        stored = json.load(f)
    assert stored == data
    assert stored["coordSpace"] == "region"
    assert "threshold" not in stored["steps"][0]


def test_同名流程檔不覆蓋(tmp_path):
    profile = make_profile(tmp_path)
    src = tmp_path / "f.json"
    src.write_text(json.dumps(legacy_flow()), encoding="utf-8")
    p1, _, _ = flowpack.import_flow_json(str(src), str(profile))
    p2, _, _ = flowpack.import_flow_json(str(src), str(profile))
    assert p1 != p2 and os.path.exists(p1) and os.path.exists(p2)


# ---------- pack 匯入 ----------

def make_pack(path, flow, images, pos=None):
    """images: {zip 內 templates/ 下的相對路徑: bytes}."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("flow.json", json.dumps(flow, ensure_ascii=False))
        z.writestr("templates/_meta.json",
                   json.dumps({"pos": pos or {}}, ensure_ascii=False))
        for rel, content in images.items():
            z.writestr(f"templates/{rel}", content)


def test_pack缺少的範本圖補進profile_已存在的不覆蓋(tmp_path):
    profile = make_profile(tmp_path)
    old = profile / "templates" / "cn" / "V"  # 既有範本 (多截圖目錄形式)
    old.mkdir(parents=True)
    (old / "V.png").write_bytes(b"OLD")
    pack = tmp_path / "m.autoclickpack"
    make_pack(pack, legacy_flow(steps=[
        {"type": "find_click", "template": "cn/V.png", "threshold": 0.9},
        {"type": "find_click", "template": "cn/X.png"},
    ]), {"cn/V.png": b"NEW", "cn/X.png": b"XX"})
    r = flowpack.import_pack(str(pack), str(profile))
    assert r["added"] == ["cn/X"]
    assert r["skipped"] == ["cn/V"]
    assert (old / "V.png").read_bytes() == b"OLD"
    # 補進的單截圖範本以目錄形式落地 (資料夾只含影像檔會被引擎當成一個範本)
    assert (profile / "templates" / "cn" / "X" / "X.png").read_bytes() == b"XX"
    with open(r["flow_path"], encoding="utf-8") as f:
        data = json.load(f)
    assert [s["template"] for s in data["steps"]] == ["cn/V", "cn/X"]
    assert all("threshold" not in s for s in data["steps"])


def test_pack匯入帶入截圖位置到meta_不覆蓋既有記錄(tmp_path):
    profile = make_profile(tmp_path)
    (profile / "templates" / "_meta.json").write_text(
        json.dumps({"pos": {"kept": [7, 8]}}), encoding="utf-8")
    pack = tmp_path / "m.autoclickpack"
    make_pack(pack, legacy_flow(steps=[
        {"type": "find_click", "template": "a.png"}]),
        {"a.png": b"A"}, pos={"a.png": [10, 20]})
    flowpack.import_pack(str(pack), str(profile))
    with open(profile / "templates" / "_meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["pos"]["a"] == [10, 20], "匯入範本的截圖位置應帶入 (鍵去副檔名)"
    assert meta["pos"]["kept"] == [7, 8]


def test_profile已是多截圖目錄時pack單檔不覆蓋(tmp_path):
    profile = make_profile(tmp_path)
    d = profile / "templates" / "cn" / "V"
    d.mkdir(parents=True)
    (d / "cn.png").write_bytes(b"1")
    pack = tmp_path / "m.autoclickpack"
    make_pack(pack, legacy_flow(steps=[
        {"type": "find_click", "template": "cn/V.png"}]), {"cn/V.png": b"NEW"})
    r = flowpack.import_pack(str(pack), str(profile))
    assert r["skipped"] == ["cn/V"]
    assert not (profile / "templates" / "cn" / "V.png").exists()


# ---------- pack 匯出與 round-trip ----------

def test_匯出只帶被引用的範本_多截圖目錄整包(tmp_path):
    a = make_profile(tmp_path, "a")
    (a / "templates" / "single.png").write_bytes(b"S")
    d = a / "templates" / "cn" / "V"
    d.mkdir(parents=True)
    (d / "x.png").write_bytes(b"X")
    (d / "y.png").write_bytes(b"Y")
    (a / "templates" / "junk.png").write_bytes(b"J")  # 未引用 → 不進 pack
    (a / "templates" / "_meta.json").write_text(
        json.dumps({"pos": {"single": [1, 2], "junk": [9, 9]}}),
        encoding="utf-8")
    data = {"steps": [{"type": "find_click", "template": "single"},
                      {"type": "find_click", "template": "cn/V"}],
            "coordSpace": "region"}
    pack = tmp_path / "out.autoclickpack"
    used = flowpack.export_pack(str(pack), str(a), data)
    assert used == ["cn/V", "single"]
    with zipfile.ZipFile(pack) as z:
        assert set(z.namelist()) == {
            "flow.json", "templates/_meta.json", "templates/single.png",
            "templates/cn/V/x.png", "templates/cn/V/y.png"}
        pos = json.loads(z.read("templates/_meta.json"))["pos"]
    assert pos == {"single": [1, 2]}, "meta 只帶被引用範本的位置"


def test_匯出缺範本時列出缺少者(tmp_path):
    a = make_profile(tmp_path, "a")
    data = {"steps": [{"type": "find_click", "template": "ghost"}],
            "coordSpace": "region"}
    with pytest.raises(ValueError) as e:
        flowpack.export_pack(str(tmp_path / "o.autoclickpack"), str(a), data)
    assert "ghost" in str(e.value)


def test_round_trip_匯出再匯入還原流程與範本(tmp_path):
    a = make_profile(tmp_path, "a")
    (a / "templates" / "single.png").write_bytes(b"S")
    d = a / "templates" / "cn" / "V"
    d.mkdir(parents=True)
    (d / "x.png").write_bytes(b"X")
    (d / "y.png").write_bytes(b"Y")
    (a / "templates" / "_meta.json").write_text(
        json.dumps({"pos": {"single": [1, 2]}}), encoding="utf-8")
    steps = [{"type": "find_click", "template": "single", "timeout": 5,
              "interval": 0.5, "action": "click", "onNotFound": "skip"},
             {"type": "find_click", "template": "cn/V", "action": "none"},
             {"type": "wait", "ms": 500}]
    data = {"steps": steps, "runMode": "count", "runCount": 2,
            "scanRegion": [10, 20, 800, 600], "avoidHover": True,
            "coordSpace": "region"}
    pack = tmp_path / "rt.autoclickpack"
    flowpack.export_pack(str(pack), str(a), data)

    b = make_profile(tmp_path, "b")
    r = flowpack.import_pack(str(pack), str(b))
    assert r["data"]["steps"] == steps, "round-trip 後步驟一字不差"
    assert r["data"]["scanRegion"] == [10, 20, 800, 600]
    assert sorted(r["added"]) == ["cn/V", "single"]
    # 單截圖範本落地成目錄形式, 範本名不變
    assert (b / "templates" / "single" / "single.png").read_bytes() == b"S"
    assert (b / "templates" / "cn" / "V" / "x.png").read_bytes() == b"X"
    assert (b / "templates" / "cn" / "V" / "y.png").read_bytes() == b"Y"
    with open(b / "templates" / "_meta.json", encoding="utf-8") as f:
        assert json.load(f)["pos"]["single"] == [1, 2]

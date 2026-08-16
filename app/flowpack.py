"""流程檔與 flow pack 的匯入/匯出: 資料進資料出, 純檔案邏輯 (GUI 無關).

匯入 (單向, ADR 0002): autoClick 舊 flow JSON 與 .autoclickpack (zip 內含
flow 與範本圖) → 當前 profile。規則:

- 範本引用去 `.png` 副檔名, 對應引擎範本名 (正式名稱＝相對路徑不含副檔名)
- pack 內 profile 缺少的範本圖補進 templates/ (已存在的不覆蓋)
- legacy 螢幕空間座標沿用 flowfmt 的座標空間遷移轉為範圍座標
- 每步 threshold 安靜丟棄 (門檻屬 profile config, 無可靠分數換算)
- 匯入後以新格式存入當前 profile 的 flows/

匯出: 自包自足的新格式 pack (flow + 引用的範本; 多截圖範本目錄整包帶走),
可在另一個 profile 或另一台機器的同版 app 匯入還原。

校準 (票 05/06): profile 有校準資料時, 匯出的 pack 一併攜帶`校準對`範本
與`基準距離` (zip 內 calibration.json)。匯入時依目標 profile 的校準狀態
三分支處理: 無校準資料＝採用 pack 的 (倍率留空＝未校準)、同一對＝流程
座標依基準距離比值換算落地、不同對＝照 pack 尺度落地並附`來源基準`標記
(存檔守門見 app.save_flow)。沒有校準資料的 pack (含舊 pack) 照舊匯入。
"""
import json
import os
import zipfile
from pathlib import Path

from subject_detection.profile import discover_templates

import calibration
from automation import flowfmt

_TMPL_KEYS = ("template", "confirmTemplate")
_IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def strip_ext(name):
    """範本引用去 .png 副檔名 (舊 flow → 引擎範本名; 已無副檔名時不動)."""
    return name[:-4] if name.lower().endswith(".png") else name


def migrate_flow(data):
    """舊 flow dict 就地遷移成新格式, 回傳提示訊息 list.

    座標空間 (螢幕→範圍)、範本引用去副檔名、每步 threshold 丟棄。
    對已是新格式的資料是 no-op, 所有讀檔路徑一律先過這一關。
    """
    notes = []
    note = flowfmt.to_region_space(data)
    if note:
        notes.append(note)
    for s in data.get("steps") or []:
        s.pop("threshold", None)
        for k in _TMPL_KEYS:
            if s.get(k):
                s[k] = strip_ext(s[k])
    return notes


def used_templates(steps):
    """步驟引用的所有範本名 (含「點擊後確認」的確認圖), 已排序."""
    used = set()
    for s in steps:
        if s.get("type") == "find_click" and s.get("template"):
            used.add(s["template"])
        if s.get("confirm") == "appear" and s.get("confirmTemplate"):
            used.add(s["confirmTemplate"])
    return sorted(used)


def free_path(dirpath, stem, suffix):
    """dirpath 下未被占用的路徑 stem[_N]suffix (不覆蓋既有檔案)."""
    path = os.path.join(dirpath, stem + suffix)
    n = 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(dirpath, f"{stem}_{n}{suffix}")
    return path


def save_flow(profile_dir, stem, data):
    """把 flow 以新格式存進 profile 的 flows/, 回傳存檔路徑."""
    flows = os.path.join(profile_dir, "flows")
    os.makedirs(flows, exist_ok=True)
    path = free_path(flows, stem, ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def import_flow_json(path, profile_dir):
    """匯入舊 flow JSON 檔; 回傳 (存檔路徑, flow 資料, 提示訊息 list)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    notes = migrate_flow(data)
    stem = os.path.splitext(os.path.basename(path))[0]
    return save_flow(profile_dir, stem, data), data, notes


def _has_template(templates_dir, name):
    """name 的實體 (目錄或任一影像副檔名的單檔) 是否已存在於 templates."""
    base = os.path.join(templates_dir, *name.split("/"))
    return (os.path.isdir(base)
            or any(os.path.isfile(base + e) for e in _IMG_EXTS))


def _load_meta_pos(templates_dir):
    """讀 profile _meta.json 的 pos 表 (舊平面格式 name→[x,y] 一併遷移)."""
    try:
        with open(os.path.join(templates_dir, "_meta.json"),
                  encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        meta = {}
    if meta and "pos" not in meta and "rot" not in meta:
        meta = {"pos": meta}  # 舊格式 (name→[x,y]) 遷移
    return meta.get("pos", {})


def _merge_meta_pos(templates_dir, pos):
    """把匯入範本的截圖位置補進 profile 的 _meta.json (不覆蓋既有記錄)."""
    if not pos:
        return
    cur = _load_meta_pos(templates_dir)
    for name, p in pos.items():
        cur.setdefault(name, p)
    os.makedirs(templates_dir, exist_ok=True)
    with open(os.path.join(templates_dir, "_meta.json"), "w",
              encoding="utf-8") as f:
        json.dump({"pos": cur}, f, ensure_ascii=False)  # rot (旋轉沿革) 即丟


def _apply_pack_calibration(data, pack_cal, profile_dir):
    """匯入時的校準三分支 (票 05/06); 回傳說明 dict 或 None (pack 無校準資料).

    - 目標 profile 無校準資料 → 採用 pack 的 (倍率留空＝未校準) → adopted
    - 同一對校準圖 (以範本名判定, 不論順序) → 流程座標 ×(目標基準 ÷ pack
      基準) 換算落地 → converted
    - 不同對 → 流程照 pack 尺度落地、附`來源基準`標記 → foreign
      (帶標記的流程存檔前必須先歸位, 守門在 app.save_flow)
    """
    if pack_cal is None:
        return None
    target = calibration.load(profile_dir)
    if target is None:
        calibration.save(profile_dir, {
            "pair": list(pack_cal["pair"]),
            "baseline": float(pack_cal["baseline"]),
            "scale": None, "fingerprint": None})
        return {"kind": "adopted", "pair": list(pack_cal["pair"])}
    if set(target["pair"]) == set(pack_cal["pair"]):
        ratio = float(target["baseline"]) / float(pack_cal["baseline"])
        calibration.scale_steps(data.get("steps") or [], ratio)
        return {"kind": "converted", "ratio": ratio}
    data[calibration.SOURCE_BASELINE] = {
        "pair": list(pack_cal["pair"]),
        "baseline": float(pack_cal["baseline"])}
    return {"kind": "foreign", "pair": list(pack_cal["pair"])}


def import_pack(path, profile_dir):
    """匯入 .autoclickpack (舊 autoClick 格式或本 app 匯出的新格式).

    回傳 dict: flow_path, data, notes, added (補進的範本名), skipped
    (profile 已有、未覆蓋的範本名), calibration (校準三分支結果或 None,
    見 _apply_pack_calibration)。
    """
    templates_dir = os.path.join(profile_dir, "templates")
    existing = set(discover_templates(Path(templates_dir)))
    with zipfile.ZipFile(path) as z:
        data = json.loads(z.read("flow.json").decode("utf-8"))
        notes = migrate_flow(data)
        try:  # pack 的校準資料 (舊 pack 沒有); 不成形視同沒有
            pack_cal = json.loads(z.read("calibration.json").decode("utf-8"))
        except (KeyError, ValueError):
            pack_cal = None
        if pack_cal is not None and not calibration.valid(pack_cal):
            pack_cal = None
        refs = set(used_templates(data.get("steps") or []))
        if pack_cal:
            # 校準對範本也要正確落地 (目錄形式對應規則靠 refs 判定)
            refs |= set(pack_cal["pair"])
        cal_result = _apply_pack_calibration(data, pack_cal, profile_dir)
        try:
            pmeta = json.loads(z.read("templates/_meta.json").decode("utf-8"))
        except (KeyError, ValueError):
            pmeta = {}
        pos_in = pmeta.get("pos", pmeta) if isinstance(pmeta, dict) else {}

        added, skipped = set(), set()
        for info in z.infolist():
            fn = info.filename
            if (not fn.startswith("templates/") or fn.endswith("/")
                    or fn.startswith("templates/_orig/")
                    or not fn.lower().endswith(_IMG_EXTS)):
                continue
            rel = fn[len("templates/"):]
            name = strip_ext(rel)
            parent = name.rsplit("/", 1)[0] if "/" in name else ""
            # 對應規則: 整個路徑 (去副檔名) 是被引用的範本 → 單截圖範本;
            # 上層目錄才是被引用的範本 → 多截圖範本目錄裡的一張截圖
            tname = parent if (parent in refs and name not in refs) else name
            # 本次匯入剛建立的範本不算「已存在」(多截圖範本的後續截圖要繼續寫)
            if tname not in added and (tname in existing
                                       or _has_template(templates_dir, tname)):
                skipped.add(tname)
                continue
            if tname == name:
                # 單截圖範本以目錄形式落地: 資料夾內只有影像檔會被引擎
                # 當成「一個」多截圖範本, 目錄形式徹底避開這個歧義
                leaf = rel.rsplit("/", 1)[-1]
                dest = os.path.join(templates_dir, *name.split("/"), leaf)
            else:
                dest = os.path.join(templates_dir, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(z.read(info))
            added.add(tname)

        pos_out = {}
        for t in sorted(added):
            p = pos_in.get(t) or pos_in.get(t + ".png")
            if p:
                pos_out[t] = p
        _merge_meta_pos(templates_dir, pos_out)
        stem = os.path.splitext(os.path.basename(path))[0]
        flow_path = save_flow(profile_dir, stem, data)
    return {"flow_path": flow_path, "data": data, "notes": notes,
            "added": sorted(added), "skipped": sorted(skipped),
            "calibration": cal_result}


def export_pack(path, profile_dir, data):
    """匯出自包自足的新格式 flow pack (flow + 引用的範本).

    多截圖範本目錄整包帶走; 未被引用的範本不進 pack。profile 有校準資料時
    附帶`校準對`範本與`基準距離` (收到 pack 的人開箱就能校準); 沒有校準對
    的 profile 匯出的 pack 與現狀相同。帶走的範本在 profile 中不存在時丟
    ValueError (逐一列出)。回傳帶進 pack 的範本名 list。
    """
    templates_root = Path(profile_dir) / "templates"
    templates = discover_templates(templates_root)
    used = used_templates(data.get("steps") or [])
    cal = calibration.load(profile_dir)
    carry = list(used)
    if cal:
        carry += [n for n in cal["pair"] if n not in carry]
    missing = [n for n in carry if n not in templates]
    if missing:
        raise ValueError("找不到範本：" + "、".join(missing))

    pos = _load_meta_pos(str(templates_root))
    pos_out = {n: pos[n] for n in carry if n in pos}

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("flow.json", json.dumps(data, ensure_ascii=False, indent=2))
        if cal:
            z.writestr("calibration.json", json.dumps(
                {"pair": cal["pair"], "baseline": cal["baseline"]},
                ensure_ascii=False))
        z.writestr("templates/_meta.json",
                   json.dumps({"pos": pos_out}, ensure_ascii=False))
        for n in carry:
            for cap in templates[n].capture_paths:
                # 磁碟上的相對路徑就是 pack 內的佈局 (單檔與多截圖目錄通用)
                arc = "templates/" + cap.relative_to(templates_root).as_posix()
                z.write(cap, arc)
    return carry

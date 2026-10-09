"""票 09: 四份在用流程一次性換算 (見 spec.md「四份流程的其他改動」).

    .venv/Scripts/python .scratch/scale-range/convert.py [--lang cn|tw]

對每份流程 (早_繁中、晚_繁中、早_簡中、晚_簡中):
1. 主校準對換成 pick_pair.py 選定的遊戲內兩張圖 (主畫面設定鈕 × 倉庫): 在主畫面影格上用舊對
   (標題列) 量倍率 k 與舊基準點, 量新對得新基準點與距離, 新基準距離＝距離 ÷ k; 所有存下的座標
   (絕對座標、固定矩形、範本拍攝位置) 用 app 的 flowfmt.shift_flow 平移 (落點不變); 舊標題列對
   登記為備用校準對 (自己的基準距離 + 「備用第一張中心 → 新基準點」的偏移)。
2. 固定矩形: 每邊不足範本 20% 的以中心不動外擴到 pickcheck.min_rect (流程尺度)。
3. 早_簡中 第 2 步「忙碌指示等待消失」刪除。
產物寫到 converted/arknights/flows/ (不動 dist 的正本; 放回在票 11); 原始數字 results/convert_<lang>.json。
改前先備份 profiles 到 BACKUP (只做一次, 已在就不動)。重放驗證在 replay.py。
"""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile

import srcommon as sr
from srcommon import bp

import calibration  # noqa: E402
import flowfile  # noqa: E402
from automation import findtarget, flowfmt, pickcheck  # noqa: E402
from pick_pair import PAIRS  # noqa: E402

BUSY_WAIT_STEP = {"早_簡中": 2}   # 要刪的「忙碌指示等待消失」步驟 (1-based, 改前編號)


def backup_once():
    if os.path.isdir(sr.BACKUP):
        return False
    shutil.copytree(os.path.dirname(sr.PROFILE), sr.BACKUP)
    return True


def targets_of(data):
    """[(位置描述, 找圖目標 dict)]: 步驟的 target / confirmTarget 與流程層級的忙碌指示."""
    out = []
    for i, s in enumerate(data.get("steps") or []):
        for key, t in findtarget.step_targets(s):
            out.append((f"第 {i + 1} 步 {key}", t))
    busy = data.get(flowfile.BUSY_KEY)
    if isinstance(busy, dict):
        out.append(("忙碌指示", busy))
    return out


def expand_rects(data, sizes):
    """固定矩形每邊不足 20% 的以中心不動外擴到 min_rect; 回傳改動清單."""
    changes = []
    for where, t in targets_of(data):
        lim = t.get("limit") or {}
        if lim.get("kind") != "rect":
            continue
        size = sizes.get(t.get("template"))
        if size is None:
            continue
        if not pickcheck.rect_margin(t, size):
            continue
        need_w, need_h = pickcheck.min_rect(size)
        cx, cy = lim["x"] + lim["w"] / 2.0, lim["y"] + lim["h"] / 2.0
        new_w, new_h = max(lim["w"], need_w), max(lim["h"], need_h)
        new = {"kind": "rect", "x": int(round(cx - new_w / 2.0)), "y": int(round(cy - new_h / 2.0)),
               "w": int(new_w), "h": int(new_h)}
        changes.append({"where": where, "template": t.get("template"), "size": size,
                        "old": dict(lim), "new": new})
        t["limit"] = new
    return changes


def swap_pair(lang, name, data, images, pos, hub, canvas, org):
    """主校準對換成新對、舊對登記為備用; 回傳換算紀錄."""
    old = calibration.flow_pair(data)
    assert old, f"{name}: 沒有校準對"
    c = calibration.calibrate(hub.query, canvas, org, calibration.make(old["pair"], old["baseline"]))
    assert c.ok, f"{name}: 主畫面影格上量不到舊校準對: {c.describe()}"
    k, old_anchor = c.scale, c.anchor
    new_names = list(PAIRS[lang]["names"])
    m = calibration.measure(hub.query, canvas, new_names, org)
    assert m.ok, f"{name}: 主畫面影格上量不到新校準對: {m.describe()}"
    new_anchor = m.anchor
    moved = flowfmt.shift_flow(data, old_anchor, new_anchor, k)
    new_pos = {n: list(flowfmt.from_screen(flowfmt.to_screen(xy, old_anchor, k), new_anchor, k))
               for n, xy in pos.items()}
    cal = calibration.make(new_names, m.distance / k)
    cal[calibration.FALLBACK_KEY] = calibration.make_fallback(
        old["pair"], old["baseline"], calibration.fallback_offset(new_anchor, old_anchor, k))
    data[calibration.FLOW_KEY] = cal
    # 新範本的拍攝位置 (相對新基準點)
    for n in new_names:
        f = findtarget.find({"template": n}, hub, canvas, org, scale=1.0)
        new_pos[n] = list(flowfmt.from_screen(sr.center(f.picked.box), new_anchor, k))
    return {"k": k, "old_anchor": old_anchor, "new_anchor": new_anchor, "moved": moved,
            "calibration": cal}, new_pos


def convert(lang, name):
    r = sr.read_flow(name)
    data, images, pos = r["data"], dict(r["images"]), dict(r["pos"])
    before_steps = len(data["steps"])
    sizes = {n: bp.decode(b).shape[1::-1] for n, b in images.items()}
    # 新校準對的圖 (pick_pair.py 裁好的)
    for n in PAIRS[lang]["names"]:
        with open(os.path.join(sr.TEMPLATES, lang, n + ".png"), "rb") as f:
            images[n] = f.read()
        sizes[n] = bp.decode(images[n]).shape[1::-1]
    # 主畫面影格 → 實機畫布
    video, fn = sr.LANGS[lang]["menu"]
    region = data["scanRegion"]
    canvas, org = sr.place(lang, region)(sr.frame(video, fn))
    old = calibration.flow_pair(data)
    tmp = tempfile.mkdtemp(prefix="sr_conv_")
    try:
        hub = bp.make_hub(images, [*old["pair"], *PAIRS[lang]["names"]], tmp)
        pair_rec, pos = swap_pair(lang, name, data, images, pos, hub, canvas, org)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rect_changes = expand_rects(data, sizes)
    removed = None
    if name in BUSY_WAIT_STEP:
        i = BUSY_WAIT_STEP[name] - 1
        s = data["steps"][i]
        assert s["type"] == "find_click" and s.get("action") == "wait_gone" \
            and findtarget.template(s) == data[flowfile.BUSY_KEY]["template"], s
        removed = data["steps"].pop(i)
    os.makedirs(sr.CONVERTED, exist_ok=True)
    out_path = bp.flow_path(name, sr.CONVERTED)
    data.pop("flowFormat", None)
    missing = flowfile.write(out_path, data, images, pos)
    assert not missing, f"{name}: 缺圖 {missing}"
    back = flowfile.read(out_path)
    refs = set(flowfile.flow_refs(back["data"]))
    assert refs <= set(back["images"]), refs - set(back["images"])
    return {"flow": name, "path": out_path, "steps_before": before_steps,
            "steps_after": len(back["data"]["steps"]), "pair": pair_rec,
            "rects": rect_changes, "removed_step": removed,
            "templates": len(back["images"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=("cn", "tw"))
    args = ap.parse_args()
    if backup_once():
        print(f"已備份 profiles 到 {sr.BACKUP}")
    langs = [args.lang] if args.lang else ["tw", "cn"]
    for lang in langs:
        out = {}
        for name in (sr.LANGS[lang]["morning"], sr.LANGS[lang]["evening"]):
            rec = convert(lang, name)
            out[name] = rec
            p = rec["pair"]
            print(f"[{name}] k={p['k']:.3f} 舊基準點 {p['old_anchor']} → 新 {p['new_anchor']}, "
                  f"平移 {p['moved']} 個座標; 新基準距離 {p['calibration']['baseline']:.1f}, "
                  f"備用偏移 {p['calibration']['fallback']['offset']}; "
                  f"固定矩形外擴 {len(rec['rects'])} 個; 步驟 {rec['steps_before']}→{rec['steps_after']}")
            for c in rec["rects"]:
                print(f"    {c['where']} {c['template']} {c['size']}: "
                      f"{c['old']['w']}×{c['old']['h']} → {c['new']['w']}×{c['new']['h']}")
        sr.dump(os.path.join(sr.RESULTS, f"convert_{lang}.json"), out)


if __name__ == "__main__":
    main()

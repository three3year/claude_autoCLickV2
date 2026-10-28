import json
import os
import shutil
import sys
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "app"))

import flowfile  # noqa: E402
from automation import flowdefaults  # noqa: E402

FLOWS = ("早_簡中", "早_繁中", "晚_簡中", "晚_繁中")
ENGINE = {"scale_range": [0.6, 1.5]}
DROPPED = ("mode", "button", "clicks")


class ConvertError(Exception):
    pass


def need(cond, what):
    if not cond:
        raise ConvertError(what)


def target(t, where):
    need(set(t) <= {"template", "limit", "pick", "colorCheck"}, f"{where}: 沒處理的鍵 {sorted(t)}")
    out = {"template": t["template"]}
    lim = t.get("limit")
    if lim is not None:
        need(lim.get("kind") == "rect" and set(lim) == {"kind", "x", "y", "w", "h"},
             f"{where}: limit 不是固定矩形 {lim}")
        out["within"] = [lim["x"], lim["y"], lim["w"], lim["h"]]
    pick = t.get("pick")
    if pick is not None:
        need(pick.get("kind") in ("top", "left") and set(pick) == {"kind", "n"},
             f"{where}: 沒處理的 pick {pick}")
        out["pick"] = {pick["kind"]: pick["n"]}
    if t.get("colorCheck"):
        out["color"] = True
    return out


def confirm_and_wait(s, out, where):
    c = s.get("confirm", "none")
    need(c in ("none", "gone", "next", "appear"), f"{where}: confirm={c!r}")
    out["confirm"] = c
    if c == "appear":
        out["confirm_target"] = target(s["confirmTarget"], where + ".confirmTarget")
    waits = s["type"] == "find_click" or c != "none"
    if waits:
        for k in ("timeout", "interval", "onNotFound"):
            need(k in s, f"{where}: 等待步驟缺 {k} (四份不該缺)")
        need(s["onNotFound"] in ("stop", "skip", "break"), f"{where}: onNotFound={s['onNotFound']!r}")
        out.update(timeout=s["timeout"], interval=s["interval"], on_fail=s["onNotFound"])
    out["busy_check"] = bool(s.get("busyCheck", False))
    out["update_origin"] = s.get("updateOrigin", True)
    return out


STEP_KEYS = {
    "find_click": {"type", "action", "target", "offsetX", "offsetY", "confirm", "confirmTarget",
                   "timeout", "interval", "onNotFound", "busyCheck", "updateOrigin", *DROPPED},
    "click": {"type", "x", "y", "confirm", "confirmTarget", "timeout", "interval", "onNotFound",
              "busyCheck", "updateOrigin", *DROPPED},
    "drag": {"type", "x1", "y1", "x2", "y2", "ms", "holdMs", "confirm", "timeout", "interval",
             "onNotFound", "busyCheck", *DROPPED},
    "wait": {"type", "ms"},
    "loop_start": {"type", "count"},
    "loop_end": {"type", "onBreak"},
    "branch_start": {"type"},
    "branch_or": {"type"},
    "branch_end": {"type", "onBreak"},
}


def convert_step(s, no):
    where = f"步驟 {no} ({s.get('type')})"
    t = s.get("type")
    need(t in STEP_KEYS, f"{where}: 沒處理的步驟類型")
    need(set(s) <= STEP_KEYS[t], f"{where}: 沒處理的鍵 {sorted(set(s) - STEP_KEYS[t])}")
    if s.get("mode", "prev") != "prev" or s.get("button", "left") != "left" \
            or s.get("clicks", 1) != 1:
        raise ConvertError(f"{where}: mode/button/clicks 不是 prev/left/1")
    if t == "find_click":
        kind = {"click": "find_click", "none": "find", "wait_gone": "wait_gone"}[s["action"]]
        out = {"type": kind, "target": target(s["target"], where + ".target"),
               "offset": [s.get("offsetX", 0), s.get("offsetY", 0)]}
        out = confirm_and_wait(s, out, where)
    elif t == "click":
        out = confirm_and_wait(s, {"type": "click", "click": [s["x"], s["y"]]}, where)
    elif t == "drag":
        out = {"type": "drag", "drag": [s["x1"], s["y1"]], "to": [s["x2"], s["y2"]],
               "duration": s["ms"] / 1000, "hold": s["holdMs"] / 1000}
        out = confirm_and_wait(s, out, where)
    elif t == "wait":
        out = {"type": "wait", "wait": s["ms"] / 1000}
    elif t == "loop_start":
        out = {"type": "repeat_start", "repeat": s["count"]}
    elif t == "loop_end":
        out = {"type": "repeat_end", "on_break": s.get("onBreak", "continue")}
    elif t == "branch_end":
        out = {"type": "branch_end", "on_break": s.get("onBreak", "continue")}
    else:
        out = {"type": t}
    for k in [k for k in out if k not in flowdefaults.KEYS[out["type"]]]:
        need(out.pop(k) == UNUSED[k], f"{where}: {k} 在新格式的 {out['type']} 沒有, 舊值卻有作用")
    return flowdefaults.complete(out)


UNUSED = {"confirm": "none", "busy_check": False, "update_origin": True}


def convert(data, meta):
    top = {"steps", "runMode", "runCount", "scanRegion", "avoidHover", "coordSpace",
           "calibration", "busyTarget", "flowFormat"}
    need(set(data) <= top, f"頂層沒處理的鍵 {sorted(set(data) - top)}")
    need(data.get("coordSpace") == "anchor" and data.get("flowFormat") == 5,
         "不是 2026-10-10 的格式 (coordSpace anchor / flowFormat 5)")
    need(data.get("runMode", "count") == "count", f"runMode={data.get('runMode')!r}")
    need(set(meta) <= {"pos"}, f"_meta.json 沒處理的鍵 {sorted(meta)}")
    cal = data["calibration"]
    need(set(cal) <= {"pair", "baseline", "fallback"}, f"calibration 沒處理的鍵 {sorted(cal)}")
    new_cal = {"pair": list(cal["pair"]), "baseline": round(float(cal["baseline"]), 1)}
    fb = cal.get("fallback")
    if fb is not None:
        need(set(fb) == {"pair", "baseline", "offset"}, f"fallback 鍵 {sorted(fb)}")
        new_cal["fallback"] = {"pair": list(fb["pair"]),
                               "baseline": round(float(fb["baseline"]), 1),
                               "offset": list(fb["offset"])}
    flow = flowfile.new_flow()
    flow.update(
        run=data.get("runCount", 1),
        scan_region=data.get("scanRegion"),
        calibration=new_cal,
        busy=target(data["busyTarget"], "busyTarget") if data.get("busyTarget") else None,
        template_pos={n: list(p) for n, p in meta.get("pos", {}).items()},
        engine=dict(ENGINE),
        steps=[convert_step(s, i) for i, s in enumerate(data["steps"], 1)],
    )
    return flow


def back_target(t):
    out = {"template": t["template"]}
    if t.get("within") is not None:
        x, y, w, h = t["within"]
        out["limit"] = {"kind": "rect", "x": x, "y": y, "w": w, "h": h}
    if t.get("pick"):
        (kind, n), = t["pick"].items()
        out["pick"] = {"kind": kind, "n": n}
    if t.get("color"):
        out["colorCheck"] = True
    return out


def back_step(n):
    t = n["type"]
    if t == "repeat_start":
        return {"type": "loop_start", "count": n["repeat"]}
    if t == "repeat_end":
        return {"type": "loop_end", "onBreak": n["on_break"]}
    if t == "branch_end":
        return {"type": "branch_end", "onBreak": n["on_break"]}
    if t in ("branch_start", "branch_or"):
        return {"type": t}
    if t == "wait":
        return {"type": "wait", "ms": round(n["wait"] * 1000)}
    if t in ("find_click", "find", "wait_gone"):
        o = {"type": "find_click",
             "action": {"find_click": "click", "find": "none", "wait_gone": "wait_gone"}[t],
             "target": back_target(n["target"]),
             "offsetX": n["offset"][0], "offsetY": n["offset"][1]}
    elif t == "click":
        o = {"type": "click", "x": n["click"][0], "y": n["click"][1]}
    elif t == "drag":
        o = {"type": "drag", "x1": n["drag"][0], "y1": n["drag"][1],
             "x2": n["to"][0], "y2": n["to"][1],
             "ms": round(n["duration"] * 1000), "holdMs": round(n["hold"] * 1000)}
    else:
        raise ConvertError(f"反向對映: 沒處理的類型 {t}")
    o["confirm"] = n.get("confirm", "none")
    if o["confirm"] == "appear":
        o["confirmTarget"] = back_target(n["confirm_target"])
    if "timeout" in n:
        o.update(timeout=n["timeout"], interval=n["interval"], onNotFound=n["on_fail"])
    o["busyCheck"] = n.get("busy_check", False)
    if t != "drag":
        o["updateOrigin"] = n["update_origin"]
    return o


def effective_old(s):
    o = {k: v for k, v in s.items() if k not in DROPPED}
    t = o["type"]
    if t in ("loop_end", "branch_end"):
        o.setdefault("onBreak", "continue")
    if t in ("find_click", "click", "drag"):
        o.setdefault("confirm", "none")
        o.setdefault("busyCheck", False)
        if t != "drag":
            o.setdefault("updateOrigin", True)
    if t == "find_click":
        o.setdefault("offsetX", 0)
        o.setdefault("offsetY", 0)
    return o


def canon(x):
    return json.loads(json.dumps(x, sort_keys=True, ensure_ascii=False))


def self_check(name, data, meta, z, folder):
    back = flowfile.read_flow(folder)
    problems = []
    old = [canon(effective_old(s)) for s in data["steps"]]
    new = [canon(back_step(s)) for s in back["steps"]]
    if len(old) != len(new):
        problems.append(f"步數 {len(old)} → {len(new)}")
    for i, (a, b) in enumerate(zip(old, new), 1):
        if a != b:
            problems.append(f"步驟 {i} 不同:\n    舊 {a}\n    新 {b}")
    src = {n[len("templates/"):-4]: z.read(n) for n in z.namelist()
           if n.startswith("templates/") and n.endswith(".png")}
    tdir = os.path.join(folder, flowfile.TEMPLATES_DIR)
    out = {fn[:-4]: open(os.path.join(tdir, fn), "rb").read() for fn in os.listdir(tdir)}
    if sorted(src) != sorted(out):
        problems.append(f"範本集合不同: 少 {sorted(set(src) - set(out))} 多 {sorted(set(out) - set(src))}")
    problems += [f"範本圖不同: {n}" for n in sorted(set(src) & set(out)) if src[n] != out[n]]
    if back["template_pos"] != {n: list(p) for n, p in meta.get("pos", {}).items()}:
        problems.append("template_pos 不同")
    cal, bcal = data["calibration"], back["calibration"]
    pairs = [(cal, bcal, "主對")]
    if cal.get("fallback") or bcal.get("fallback"):
        if not (cal.get("fallback") and bcal.get("fallback")):
            problems.append("備用對一邊有一邊沒有")
        else:
            pairs.append((cal["fallback"], bcal["fallback"], "備用對"))
            if list(cal["fallback"]["offset"]) != bcal["fallback"]["offset"]:
                problems.append("備用對 offset 不同")
    for a, b, label in pairs:
        if list(a["pair"]) != b["pair"] or abs(float(a["baseline"]) - b["baseline"]) > 0.05:
            problems.append(f"校準{label}不同: {a} → {b}")
    want_busy = back_target(back["busy"]) if back["busy"] else None
    if canon(want_busy) != canon(data.get("busyTarget")):
        problems.append(f"忙碌指示不同: {data.get('busyTarget')} → {back['busy']}")
    if back["run"] != data.get("runCount", 1):
        problems.append(f"run 不同: {data.get('runCount')} → {back['run']}")
    if back["scan_region"] != data.get("scanRegion"):
        problems.append(f"scan_region 不同: {data.get('scanRegion')} → {back['scan_region']}")
    if back["engine"] != ENGINE:
        problems.append(f"engine 不同: {back['engine']}")
    return problems, len(back["steps"]), len(out)


def main(src_dir, out_root=None):
    out_root = out_root or os.path.join(os.path.expanduser("~"), "AutoClick")
    jobs = []
    for name in FLOWS:
        pack = os.path.join(src_dir, name + ".autoclickpack")
        folder = os.path.join(out_root, name)
        need(os.path.isfile(pack), f"找不到 {pack}")
        need(not os.path.exists(folder), f"輸出資料夾已存在 (要重轉先手動刪): {folder}")
        jobs.append((name, pack, folder))
    loaded = []
    for name, pack, folder in jobs:
        z = zipfile.ZipFile(pack)
        data = json.loads(z.read("flow.json"))
        meta = json.loads(z.read("templates/_meta.json"))
        try:
            flow = convert(data, meta)
        except ConvertError as e:
            raise ConvertError(f"{name}: {e}") from None
        loaded.append((name, pack, folder, z, data, meta, flow))
    ok = True
    for name, pack, folder, z, data, meta, flow in loaded:
        images = {n[len("templates/"):-4]: z.read(n) for n in z.namelist()
                  if n.startswith("templates/") and n.endswith(".png")}
        missing = flowfile.write_flow(folder, flow, images)
        need(not missing, f"{name}: 被引用卻沒有圖 {missing}")
        md = os.path.join(src_dir, name + ".md")
        if os.path.isfile(md):
            shutil.copyfile(md, os.path.join(folder, "交付報告.md"))
        problems, n_steps, n_tmpl = self_check(name, data, meta, z, folder)
        if problems:
            ok = False
            print(f"[{name}] 自我核對沒過:")
            for p in problems[:20]:
                print("  ", p)
        else:
            print(f"[{name}] 自我核對全過: {n_steps} 步、{n_tmpl} 張範本"
                  f"{'、交付報告.md' if os.path.isfile(md) else ''} → {folder}")
    return 0 if ok else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.exit(main(*sys.argv[1:]))
    except ConvertError as e:
        print("轉換停下:", e)
        sys.exit(2)

"""PROTOTYPE — 拋棄式。wayfinder 票 02（flow.yaml 具體 schema）的樣本產生器。

把打包版的 .autoclickpack 轉成三種 flow.yaml 寫法讓使用者比較，並做往返驗證
（yaml 讀回 → 舊步驟語意，與原檔正規化後逐步比對）。不進 app。

    .venv/Scripts/python.exe convert_proto.py <pack> <輸出目錄>
"""
import json
import os
import sys
import zipfile

import yaml

# ---------- 新格式的預設值（沒寫＝這個值） ----------
D_TIMEOUT = 10
D_INTERVAL = 0.3        # 提案：四份流程 337 個找圖全是 0.3，預設改 0.3
D_DRAG = 0.5            # 拖曳時間、按住時間（四份流程全是 500ms/500ms）
D_WAIT = 1.0
D_ON_FAIL = "stop"      # ADR 0014：找不到時沒寫＝停止


# ================= 舊步驟 → 新步驟（單步，不含區段） =================

def _target(tgt, head):
    """找圖目標 → {head: 範本, within, pick, color}."""
    out = {head: tgt["template"]}
    lim = tgt.get("limit")
    if lim:
        assert lim["kind"] == "rect", lim
        out["within"] = [lim["x"], lim["y"], lim["w"], lim["h"]]
    pick = tgt.get("pick")
    if pick and pick.get("kind", "score") != "score":
        k = pick["kind"]
        out["pick"] = {k: [pick.get("x", 0), pick.get("y", 0)]} if k == "near" \
            else {k: pick.get("n", 1)}
    if tgt.get("colorCheck"):
        out["color"] = True
    return out


def _common(s, out, old_on_fail):
    """生效確認、逾時、找不到時、忙碌檢查、更新原點."""
    c = s.get("confirm", "none")
    if c == "appear":
        ct = _target(s["confirmTarget"], "appear")
        out["confirm"] = ct
    elif c != "none":
        out["confirm"] = c
    t = s.get("type")
    has_wait = t == "find_click" or c != "none"
    if has_wait:
        if float(s.get("timeout", 10)) != D_TIMEOUT:
            out["timeout"] = _num(s.get("timeout", 10))
        if float(s.get("interval", 0.5)) != D_INTERVAL:
            out["interval"] = _num(s.get("interval", 0.5))
        nf = s.get("onNotFound", old_on_fail)
        if nf != D_ON_FAIL:
            out["on_fail"] = nf
    if s.get("busyCheck"):
        out["busy_check"] = True
    if not s.get("updateOrigin", True):
        out["update_origin"] = False
    return out


def _num(v):
    v = float(v)
    return int(v) if v.is_integer() else v


def convert_step(s):
    t = s["type"]
    if t == "find_click":
        head = {"click": "find_click", "none": "find",
                "wait_gone": "wait_gone"}[s.get("action", "click")]
        out = _target(s["target"], head)
        off = [s.get("offsetX", 0), s.get("offsetY", 0)]
        if off != [0, 0]:
            out["offset"] = off
        return _common(s, out, "skip")      # 舊執行器：找圖沒寫＝skip
    if t == "click":
        assert s.get("mode") == "prev" and s.get("button", "left") == "left"
        return _common(s, {"click": [s["x"], s["y"]]}, "stop")
    if t == "drag":
        assert s.get("mode") == "prev"
        out = {"drag": [s["x1"], s["y1"]], "to": [s["x2"], s["y2"]]}
        if s.get("ms", 300) / 1000 != D_DRAG:
            out["duration"] = _num(s.get("ms", 300) / 1000)
        if s.get("holdMs", 0) / 1000 != D_DRAG:
            out["hold"] = _num(s.get("holdMs", 0) / 1000)
        return _common(s, out, "stop")
    if t == "wait":
        return {"wait": _num(s.get("ms", 1000) / 1000)}
    raise ValueError(t)


# ================= 平面標記 → 巢狀區段 =================

def nest(steps):
    """回傳 [(節點, 舊序號)]；節點是新步驟 dict，或 repeat / branch 區段."""
    pos = 0

    def block(stop_types):
        nonlocal pos
        out = []
        while pos < len(steps):
            s = steps[pos]
            t = s["type"]
            if t in stop_types:
                return out
            no = pos + 1
            pos += 1
            if t == "loop_start":
                body = block(("loop_end",))
                end = steps[pos]; pos += 1
                node = {"repeat": s.get("count", 1), "steps": body}
                if end.get("onBreak", "continue") == "break":
                    node["on_break"] = "break"
                out.append((node, no))
            elif t == "branch_start":
                arms = []
                while True:
                    body = block(("branch_or", "branch_end"))
                    arms.append(body)
                    sep = steps[pos]; pos += 1
                    if sep["type"] == "branch_end":
                        break
                node = {"branch": [], "_arms": arms}
                if sep.get("onBreak", "continue") == "break":
                    node["on_break"] = "break"
                out.append((node, no))
            else:
                out.append((convert_step(s), no))
        return out

    return block(())


# ================= 輸出：三種寫法 =================

def flow(v):
    """單行 flow-style YAML."""
    return yaml.dump(v, allow_unicode=True, default_flow_style=True,
                     sort_keys=False, width=10_000).removesuffix("...\n").strip()


def header(data, meta):
    cal = data["calibration"]
    fb = cal.get("fallback")
    h = {"format": 1}
    if data.get("runMode") == "infinite":
        h["run"] = "forever"
    elif data.get("runCount", 1) != 1:
        h["run"] = data["runCount"]
    h["scan_region"] = data["scanRegion"]
    h["calibration"] = {"pair": cal["pair"], "baseline": round(cal["baseline"], 1)}
    if fb:
        h["calibration"]["fallback"] = {"pair": fb["pair"],
                                        "baseline": round(fb["baseline"], 1),
                                        "offset": fb["offset"]}
    bt = data.get("busyTarget")
    if bt:
        h["busy"] = _target(bt, "template")
    h["template_pos"] = meta.get("pos", {})
    return h


def emit_header(h):
    lines = []
    for k, v in h.items():
        if isinstance(v, dict) and k in ("calibration", "template_pos"):
            lines.append(f"{k}:")
            for kk, vv in v.items():
                lines.append(f"  {kk}: {flow(vv)}")
        else:
            lines.append(f"{k}: {flow(v)}")
    return lines


def emit_nested_compact(nodes, ind=2):
    lines = []
    pad = " " * ind
    for node, no in nodes:
        if "repeat" in node:
            lines.append(f"{pad}- repeat: {node['repeat']}    # {no}")
            if "on_break" in node:
                lines.append(f"{pad}  on_break: break")
            lines.append(f"{pad}  steps:")
            lines += emit_nested_compact(node["steps"], ind + 4)
        elif "branch" in node:
            lines.append(f"{pad}- branch:    # {no}")
            for arm in node["_arms"]:
                (cond, cno), rest = arm[0], arm[1:]
                lines.append(f"{pad}    - if: {flow(cond)}    # {cno}")
                if rest:
                    lines.append(f"{pad}      then:")
                    lines += emit_nested_compact(rest, ind + 8)
            if "on_break" in node:
                lines.append(f"{pad}  on_break: break")
        else:
            lines.append(f"{pad}- {flow(node)}    # {no}")
    return lines


def emit_flat_compact(steps):
    lines = []
    for i, s in enumerate(steps, 1):
        t = s["type"]
        if t == "loop_start":
            v = {"repeat": s.get("count", 1)}
        elif t == "branch_start":
            v = "branch"
        elif t == "branch_or":
            v = "or"
        elif t in ("loop_end", "branch_end"):
            v = {"end": "repeat" if t == "loop_end" else "branch"}
            if s.get("onBreak", "continue") == "break":
                v["on_break"] = "break"
        else:
            v = convert_step(s)
        lines.append(f"  - {v if isinstance(v, str) else flow(v)}    # {i}")
    return lines


def to_plain(nodes):
    """巢狀節點 → 純資料（給展開寫法用 yaml.dump）."""
    out = []
    for node, _ in nodes:
        if "repeat" in node:
            n = {"repeat": node["repeat"]}
            if "on_break" in node:
                n["on_break"] = "break"
            n["steps"] = to_plain(node["steps"])
        elif "branch" in node:
            arms = []
            for arm in node["_arms"]:
                a = {"if": arm[0][0]}
                if arm[1:]:
                    a["then"] = to_plain(arm[1:])
                arms.append(a)
            n = {"branch": arms}
            if "on_break" in node:
                n["on_break"] = "break"
        else:
            n = node
        out.append(n)
    return out


class _D(yaml.SafeDumper):
    pass


def _short_list(d, v):
    flowy = all(not isinstance(x, (list, dict)) for x in v)
    return d.represent_sequence("tag:yaml.org,2002:seq", v, flow_style=flowy)


_D.add_representer(list, _short_list)


# ================= 往返驗證：新 yaml → 舊步驟語意 =================

def back_step(n):
    """新步驟 → 舊步驟的有效語意（所有欄位補成實際值）."""
    def tgt(d, head):
        t = {"template": d[head]}
        if "within" in d:
            x, y, w, h = d["within"]
            t["limit"] = {"kind": "rect", "x": x, "y": y, "w": w, "h": h}
        if "pick" in d:
            (k, v), = d["pick"].items()
            t["pick"] = {"kind": k, "x": v[0], "y": v[1]} if k == "near" \
                else {"kind": k, "n": v}
        if d.get("color"):
            t["colorCheck"] = True
        return t

    def common(o):
        c = n.get("confirm", "none")
        if isinstance(c, dict):
            o["confirm"] = "appear"
            o["confirmTarget"] = tgt(c, "appear")
        else:
            o["confirm"] = c
        if o["type"] == "find_click" or o["confirm"] != "none":
            o["timeout"] = float(n.get("timeout", D_TIMEOUT))
            o["interval"] = float(n.get("interval", D_INTERVAL))
            o["onNotFound"] = n.get("on_fail", D_ON_FAIL)
        o["busyCheck"] = bool(n.get("busy_check", False))
        o["updateOrigin"] = n.get("update_origin", True)
        return o

    for head, action in (("find_click", "click"), ("find", "none"),
                         ("wait_gone", "wait_gone")):
        if head in n:
            off = n.get("offset", [0, 0])
            return common({"type": "find_click", "action": action,
                           "target": tgt(n, head),
                           "offsetX": off[0], "offsetY": off[1]})
    if "click" in n:
        return common({"type": "click", "x": n["click"][0], "y": n["click"][1]})
    if "drag" in n:
        return common({"type": "drag", "x1": n["drag"][0], "y1": n["drag"][1],
                       "x2": n["to"][0], "y2": n["to"][1],
                       "ms": int(n.get("duration", D_DRAG) * 1000),
                       "holdMs": int(n.get("hold", D_DRAG) * 1000)})
    if "wait" in n:
        return {"type": "wait", "ms": int(n["wait"] * 1000)}
    raise ValueError(n)


def flatten(nodes):
    out = []
    for n in nodes:
        if "repeat" in n:
            out.append({"type": "loop_start", "count": n["repeat"]})
            out += flatten(n["steps"])
            out.append({"type": "loop_end", "onBreak": n.get("on_break", "continue")})
        elif "branch" in n:
            out.append({"type": "branch_start"})
            for i, arm in enumerate(n["branch"]):
                if i:
                    out.append({"type": "branch_or"})
                out += flatten([arm["if"]] + arm.get("then", []))
            out.append({"type": "branch_end", "onBreak": n.get("on_break", "continue")})
        else:
            out.append(back_step(n))
    return out


def norm_old(s):
    """原檔步驟 → 有效語意（舊執行器的預設補齊、不再存在的欄位丟掉）."""
    t = s["type"]
    if t in ("loop_start",):
        return {"type": t, "count": s.get("count", 1)}
    if t in ("loop_end", "branch_end"):
        return {"type": t, "onBreak": s.get("onBreak", "continue")}
    if t in ("branch_start", "branch_or"):
        return {"type": t}
    if t == "wait":
        return {"type": t, "ms": s.get("ms", 1000)}
    o = {"type": t}
    if t == "find_click":
        o.update(action=s.get("action", "click"), target=s["target"],
                 offsetX=s.get("offsetX", 0), offsetY=s.get("offsetY", 0))
    elif t == "click":
        o.update(x=s["x"], y=s["y"])
    else:
        o.update(x1=s["x1"], y1=s["y1"], x2=s["x2"], y2=s["y2"],
                 ms=s.get("ms", 300), holdMs=s.get("holdMs", 0))
    o["confirm"] = s.get("confirm", "none")
    if o["confirm"] == "appear":
        o["confirmTarget"] = s["confirmTarget"]
    if t == "find_click" or o["confirm"] != "none":
        o["timeout"] = float(s.get("timeout", 10))
        o["interval"] = float(s.get("interval", 0.5))
        o["onNotFound"] = s.get("onNotFound", "skip" if t == "find_click" else "stop")
    o["busyCheck"] = bool(s.get("busyCheck", False))
    o["updateOrigin"] = s.get("updateOrigin", True)
    return o


def canon(x):
    """比對用：dict 鍵排序、limit 的 kind 統一."""
    return json.loads(json.dumps(x, sort_keys=True, ensure_ascii=False))


def check(old_steps, new_steps, label):
    a = [canon(norm_old(s)) for s in old_steps]
    b = [canon(s) for s in new_steps]
    bad = [(i + 1, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(a) != len(b) or bad:
        print(f"[{label}] 往返不一致：{len(a)} vs {len(b)} 步")
        for i, x, y in bad[:5]:
            print(" ", i, "\n   舊", x, "\n   新", y)
        return False
    print(f"[{label}] 往返一致：{len(a)} 步逐步相同")
    return True


def flat_back(items):
    out = []
    for v in items:
        if v == "branch":
            out.append({"type": "branch_start"})
        elif v == "or":
            out.append({"type": "branch_or"})
        elif "repeat" in v:
            out.append({"type": "loop_start", "count": v["repeat"]})
        elif "end" in v:
            out.append({"type": "loop_end" if v["end"] == "repeat" else "branch_end",
                        "onBreak": v.get("on_break", "continue")})
        else:
            out.append(back_step(v))
    return out


# ================= main =================

def main(pack, outdir):
    z = zipfile.ZipFile(pack)
    data = json.loads(z.read("flow.json"))
    meta = json.loads(z.read("templates/_meta.json"))
    steps = data["steps"]
    name = os.path.splitext(os.path.basename(pack))[0]
    os.makedirs(outdir, exist_ok=True)
    h = header(data, meta)
    nodes = nest(steps)
    top = f"# PROTOTYPE 樣本 — {name}（由 {os.path.basename(pack)} 轉出，票 02）\n"

    variants = {
        "A_巢狀_一步一行.yaml":
            emit_header(h) + ["steps:"] + emit_nested_compact(nodes),
        "B_平面標記_一步一行.yaml":
            emit_header(h) + ["steps:"] + emit_flat_compact(steps),
    }
    for fn, lines in variants.items():
        with open(os.path.join(outdir, fn), "w", encoding="utf-8") as f:
            f.write(top + "\n".join(lines) + "\n")
    full = dict(h, steps=to_plain(nodes))
    with open(os.path.join(outdir, "C_巢狀_展開.yaml"), "w", encoding="utf-8") as f:
        f.write(top + yaml.dump(full, Dumper=_D, allow_unicode=True,
                                sort_keys=False, width=100))

    ok = True
    for fn in ("A_巢狀_一步一行.yaml", "C_巢狀_展開.yaml"):
        d = yaml.safe_load(open(os.path.join(outdir, fn), encoding="utf-8"))
        ok &= check(steps, flatten(d["steps"]), fn)
    d = yaml.safe_load(open(os.path.join(outdir, "B_平面標記_一步一行.yaml"),
                            encoding="utf-8"))
    ok &= check(steps, flat_back(d["steps"]), "B")
    for fn in os.listdir(outdir):
        if fn.endswith(".yaml"):
            n = sum(1 for _ in open(os.path.join(outdir, fn), encoding="utf-8"))
            print(f"{fn}: {n} 行, {os.path.getsize(os.path.join(outdir, fn))} bytes")
    print("原 flow.json:", len(z.read("flow.json")), "bytes")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))

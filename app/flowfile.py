"""流程資料夾: 資料進資料出, 純檔案邏輯 (GUI 無關; 詞彙見 app/CONTEXT.md「存檔與快取」).

**一份`流程`＝一個資料夾** (ADR 0014)::

    <流程名>/flow.yaml              步驟與流程層級設定 (區段巢狀、一步一行、預設不寫、時間一律秒)
    <流程名>/templates/<範本名>.png  被引用的範本圖 (檔名即範本名)
    <流程名>/.cache/                可重建的`快取`: 引擎的登錄產物 (registered/)、
                                   還沒存檔的截圖 (shots/)
    <流程名>/交付報告.md            影片轉流程附的說明 (app 不讀不寫, 存檔不動它)

`存檔`把記憶體裡的流程整份寫回資料夾: flow.yaml 整份重寫, 還沒存檔的截圖搬進
templates/, templates/ 只留被引用的範本 (步驟的找圖目標與確認圖＋校準對＋備用校準對＋
忙碌指示, 見 `template_refs`)。還沒第一次存檔的新流程沒有資料夾, 截圖與登錄產物放在
本機狀態資料夾裡固定的「未存檔」快取。

讀檔 (`read_flow`) 是唯一的入口驗證, 格式規則只有這一個模組說得上話; UI 與執行器只呼叫它。
"""
import os
import re
import shutil

import calibration
from automation import findtarget, flowdefaults


# ================= 範本名稱與步驟引用 =================

def strip_ext(name):
    """圖檔名去 .png 副檔名 → 範本名 (已無副檔名時不動)."""
    return name[:-4] if name.lower().endswith(".png") else name


def clean_name(name):
    """清理範本名 (截圖自動命名、從磁碟挑的圖檔名): 平面名稱, 能當檔名.

    路徑分隔與檔名非法字元一律換成 `_` (不是丟棄, 否則 `a/b` 會靜靜變成 `ab`)。
    清不出東西時回空字串, 由呼叫端決定怎麼辦。使用者親手輸入的名字 (重新命名)
    不靜靜改寫, 用 `template_name_problem` 擋下並說明。
    """
    name = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip().strip(".")
    return re.sub(r"_+", "_", name)


def free_name(name, taken):
    """`name` 在 `taken` 內已被占用時加序號: name_2、name_3…

    末端已是 `_數字` 的名稱從該數字往上找 (保留補零位數), 避免 `a_1_2` 這種
    疊字。回傳未被占用的名稱。範本名＝檔名, Windows 的檔名不分大小寫, 所以只差
    大小寫也算占用 (`Btn` 與 `btn` 會寫進同一個檔)。
    """
    taken = {t.casefold() for t in taken}
    if name.casefold() not in taken:
        return name
    m = re.fullmatch(r"(.*)_(\d+)", name)
    if m:
        stem, width, n = m.group(1), len(m.group(2)), int(m.group(2)) + 1
    else:
        stem, width, n = name, 1, 2
    while f"{stem}_{n:0{width}d}".casefold() in taken:
        n += 1
    return f"{stem}_{n:0{width}d}"


def rename_refs(steps, old, new):
    """把步驟對 `old` 的引用 (所有`找圖目標`, 含`確認圖`) 就地改成 `new`;
    回傳改動筆數.

    跨流程複製撞名加序號、範本重新命名共用這一條路徑——引用漏改就等於
    流程指向一張不存在的圖。
    """
    changed = 0
    for s in steps:
        for _, t in findtarget.step_targets(s):
            if t.get("template") == old:
                t["template"] = new
                changed += 1
    return changed


def used_templates(steps):
    """所有`找圖目標`引用的範本名 (確認圖只在生效確認選「確認圖出現」時算;
    找圖、座標點擊、拖曳都有確認圖), 已排序."""
    return sorted(findtarget.referenced_templates(steps))


def _blob(src):
    """把 bytes 或檔案路徑統一成 bytes (寫圖一律寫實體內容, 不留參照)."""
    if isinstance(src, (bytes, bytearray)):
        return bytes(src)
    with open(src, "rb") as f:
        return f.read()


# ================= flow.yaml 讀寫 =================
# 記憶體裡的流程是 dict: run、scan_region、calibration、busy、template_pos、engine、steps
# (步驟是平面標記, 鍵名與單位跟 flow.yaml 相同, 補齊成完整步驟)。讀寫只做三種形狀轉換:
# 巢狀區段 ⇄ 平面標記、開頭的鍵 ⇄ type、步驟層的 within/pick/color ⇄ target 子 dict
# (確認圖 confirm: {appear: 名, …} ⇄ confirm: appear + confirm_target)。

FLOW_YAML = "flow.yaml"
TEMPLATES_DIR = "templates"
CACHE_DIR = ".cache"
FLOW_FORMAT = 1

_HEADS = ("find_click", "find", "wait_gone", "click", "drag", "wait", "repeat",
          "branch")
_TOP_KEYS = ("format", "run", "scan_region", "calibration", "busy",
             "template_pos", "engine", "steps")
_TARGET_ATTRS = ("within", "pick", "color")
_BAD_NAME_CHARS = '\\/:*?"<>|'


class FlowError(ValueError):
    """flow.yaml 讀不進來 (或流程寫不出去): 訊息給人看, 指明步驟編號與鍵."""


def template_name_problem(name):
    """範本名能不能當檔名 (範本名＝檔名): 不行回傳原因, 可以回傳 None."""
    if not isinstance(name, str) or not name:
        return "範本名不能是空的"
    bad = sorted({c for c in name if c in _BAD_NAME_CHARS})
    if bad:
        return f"範本名「{name}」不能有 {' '.join(bad)}（檔名不允許）"
    if name != name.strip():
        return f"範本名「{name}」開頭或結尾不能是空白"
    if name.endswith("."):
        return f"範本名「{name}」結尾不能是句點"
    return None


def new_flow():
    """空白的新流程 (記憶體模型)."""
    return {"run": flowdefaults.FLOW["run"], "scan_region": None,
            "calibration": None, "busy": None, "template_pos": {},
            "engine": {}, "steps": []}


def _flow_level_slots(flow):
    """流程層級引用範本的位置 [(容器, 索引或鍵)]: 校準對、備用校準對、忙碌指示.

    新增流程層級的找圖設定只要加在這裡, 引用集合與改名就一起照它。
    """
    cal = flow.get("calibration")
    fb = calibration.fallback_pair(cal) if cal else None
    slots = [(pair, i) for pair in (cal["pair"] if cal else [], fb["pair"] if fb else [])
             for i in range(len(pair))]
    busy = flow.get("busy")
    if busy:
        slots.append((busy, "template"))
    return slots


def template_refs(flow):
    """流程引用的全部範本名 (依出現順序): 步驟的找圖目標與確認圖 + 校準對 +
    備用校準對 + 忙碌指示 (findtarget.referenced_templates 是唯一的定義)."""
    extra = [box[key] for box, key in _flow_level_slots(flow)]
    return findtarget.referenced_templates(flow.get("steps") or [], extra)


def rename_template_refs(flow, old, new):
    """把整份流程 (記憶體模型) 對 old 的引用改成 new: 步驟的找圖目標與確認圖、校準對、
    備用校準對、忙碌指示、拍攝位置; 回傳改動筆數."""
    changed = rename_refs(flow.get("steps") or [], old, new)
    for box, key in _flow_level_slots(flow):
        if box[key] == old:
            box[key] = new
            changed += 1
    pos = flow.get("template_pos")
    if pos and old in pos:
        flow["template_pos"] = {(new if k == old else k): v for k, v in pos.items()}
    return changed


# ---------- 讀 ----------

def read_flow(folder):
    """讀流程資料夾的 flow.yaml → 記憶體的流程 (補齊預設); 讀不進來丟 FlowError."""
    path = os.path.join(str(folder), FLOW_YAML)
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError as e:
        raise FlowError(f"讀不到 {path}（{e.strerror or e}）") from None
    return parse_flow(text)


def missing_templates(folder, flow):
    """被引用卻不在 templates/ 的範本名 (開檔時列出缺圖用)."""
    tdir = os.path.join(str(folder), TEMPLATES_DIR)
    return [n for n in template_refs(flow)
            if not os.path.isfile(os.path.join(tdir, n + ".png"))]


def parse_flow(text):
    """flow.yaml 的文字 → 記憶體的流程 (補齊預設); 寫錯丟 FlowError (指出步驟編號與鍵)."""
    import yaml
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"第 {mark.line + 1} 行" if mark is not None else "某處"
        raise FlowError(f"flow.yaml 的 YAML 語法有錯（{where}）："
                        f"{getattr(e, 'problem', None) or e}") from None
    if not isinstance(doc, dict):
        raise FlowError("flow.yaml 的最外層要是 {鍵: 值}")
    extra = [k for k in doc if k not in _TOP_KEYS]
    if extra:
        raise FlowError(f"flow.yaml 頂層不認得的鍵：{'、'.join(map(str, extra))}")
    if "format" not in doc:
        raise FlowError("flow.yaml 缺 format（現行格式是 format: 1）")
    if doc["format"] != FLOW_FORMAT or isinstance(doc["format"], bool):
        raise FlowError(f"flow.yaml 的 format 是 {doc['format']!r}，這版 app 只讀 "
                        f"format: {FLOW_FORMAT}")
    flow = new_flow()
    if "run" in doc:
        run = doc["run"]
        if not (run == "forever" or _int(run) and run >= 1):
            raise FlowError(f"run 要是 1 以上的整數或 forever，收到 {run!r}")
        flow["run"] = run
    if doc.get("scan_region") is not None:
        flow["scan_region"] = _rect("scan_region", doc["scan_region"])
    if doc.get("calibration") is not None:
        flow["calibration"] = _calibration(doc["calibration"])
    if doc.get("busy") is not None:
        flow["busy"] = _yaml_target("busy", doc["busy"], "template")
    if doc.get("template_pos") is not None:
        flow["template_pos"] = _template_pos(doc["template_pos"])
    if doc.get("engine") is not None:
        flow["engine"] = _engine(doc["engine"])
    steps = doc.get("steps")
    if steps is None:
        steps = []
    if not isinstance(steps, list):
        raise FlowError("steps 要是步驟清單")
    out = []
    _parse_steps(steps, out)
    flow["steps"] = out
    return flow


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _xy(where, v):
    if not (isinstance(v, list) and len(v) == 2 and all(_int(c) for c in v)):
        raise FlowError(f"{where} 要寫成 [x, y] 整數，收到 {v!r}")
    return list(v)


def _rect(where, v):
    if not (isinstance(v, list) and len(v) == 4 and all(_int(c) for c in v)
            and v[2] > 0 and v[3] > 0):
        raise FlowError(f"{where} 要寫成 [x, y, w, h] 整數且寬高大於 0，收到 {v!r}")
    return list(v)


def _name(where, v):
    problem = template_name_problem(v)
    if problem:
        raise FlowError(f"{where}：{problem}")
    return v


def _calibration(c):
    where = "calibration"
    if not isinstance(c, dict):
        raise FlowError(f"{where} 要是 {{pair, baseline, fallback}}")
    extra = [k for k in c if k not in ("pair", "baseline", "fallback")]
    if extra:
        raise FlowError(f"{where} 不認得的鍵：{'、'.join(map(str, extra))}")
    out = _pair(where, c)
    if c.get("fallback") is not None:
        fb = c["fallback"]
        fw = where + ".fallback"
        if not isinstance(fb, dict):
            raise FlowError(f"{fw} 要是 {{pair, baseline, offset}}")
        extra = [k for k in fb if k not in ("pair", "baseline", "offset")]
        if extra:
            raise FlowError(f"{fw} 不認得的鍵：{'、'.join(map(str, extra))}")
        f = _pair(fw, fb)
        if "offset" not in fb:
            raise FlowError(f"{fw} 缺 offset")
        f["offset"] = _xy(fw + ".offset", fb["offset"])
        out["fallback"] = f
    return out


def _pair(where, c):
    pair = c.get("pair")
    if not (isinstance(pair, list) and len(pair) == 2 and pair[0] != pair[1]):
        raise FlowError(f"{where}.pair 要是兩個不同的範本名，收到 {pair!r}")
    for n in pair:
        _name(f"{where}.pair", n)
    base = c.get("baseline")
    if not _num(base) or base <= 0:
        raise FlowError(f"{where}.baseline 要是大於 0 的數字，收到 {base!r}")
    return {"pair": list(pair), "baseline": float(base)}


def _template_pos(tp):
    if not isinstance(tp, dict):
        raise FlowError("template_pos 要是 {範本名: [x, y]}")
    return {_name("template_pos", str(n) if _num(n) else n):
            _xy(f"template_pos.{n}", v) for n, v in tp.items()}


_ENGINE_KEYS = None


def _engine(e):
    """`引擎參數覆蓋`: 鍵名同引擎 default_config.yaml; 不認得的鍵報錯 (拼錯不能變成預設)."""
    global _ENGINE_KEYS
    if not isinstance(e, dict):
        raise FlowError("engine 要是 {引擎參數: 值}")
    if _ENGINE_KEYS is None:
        from subject_detection.library import load_default_config
        _ENGINE_KEYS = set(load_default_config())
    extra = [k for k in e if k not in _ENGINE_KEYS]
    if extra:
        raise FlowError(f"engine 不認得的鍵：{'、'.join(map(str, extra))}"
                        f"（可用：{'、'.join(sorted(_ENGINE_KEYS))}）")
    return dict(e)


def _yaml_target(where, d, head):
    """yaml 的找圖目標 ({head: 名, within, pick, color}) → 記憶體的找圖目標."""
    if not isinstance(d, dict):
        raise FlowError(f"{where} 要是 {{{head}: 範本名, …}}")
    tgt = {"template": _name(f"{where} 的 {head}", d.get(head))}
    if "within" in d:
        tgt["within"] = _rect(f"{where} 的 within", d["within"])
    if "pick" in d:
        tgt["pick"] = _pick(f"{where} 的 pick", d["pick"])
    if "color" in d:
        if d["color"] is not True:
            raise FlowError(f"{where} 的 color 只能寫 true（不比色就不寫），收到 {d['color']!r}")
        tgt["color"] = True
    extra = [k for k in d if k not in (head, *_TARGET_ATTRS)]
    if extra and head == "template":
        raise FlowError(f"{where} 不認得的鍵：{'、'.join(map(str, extra))}")
    return tgt


def _pick(where, p):
    if isinstance(p, dict) and len(p) == 1:
        (kind, v), = p.items()
        if kind in ("top", "left") and _int(v) and v >= 1:
            return {kind: v}
        if kind == "near":
            return {"near": _xy(where + ".near", v)}
    raise FlowError(f"{where} 要寫成 {{top: N}}、{{left: N}} 或 {{near: [x, y]}}，"
                    f"收到 {p!r}")


def _parse_steps(items, out):
    """巢狀的步驟清單 → 平面標記 (就地 append 到 out); 步驟編號＝out 裡的位置 + 1."""
    for item in items:
        no = len(out) + 1
        where = f"步驟 {no}"
        if not isinstance(item, dict):
            raise FlowError(f"{where} 要是 {{鍵: 值}}，收到 {item!r}")
        heads = [k for k in item if k in _HEADS]
        if len(heads) != 1:
            raise FlowError(f"{where} 要剛好一個開頭的鍵（{'/'.join(_HEADS)}），"
                            f"收到 {'、'.join(map(str, item)) or '空的'}")
        head = heads[0]
        if head == "repeat":
            _parse_repeat(where, item, out)
        elif head == "branch":
            _parse_branch(where, item, out)
        else:
            out.append(_parse_step(where, head, item))


def _on_break(where, item):
    v = item.get("on_break", "continue")
    if v not in ("continue", "break"):
        raise FlowError(f"{where} 的 on_break 只能是 break（不寫＝continue），收到 {v!r}")
    return v


def _parse_repeat(where, item, out):
    extra = [k for k in item if k not in ("repeat", "steps", "on_break")]
    if extra:
        raise FlowError(f"{where}（repeat）不認得的鍵：{'、'.join(map(str, extra))}")
    n = item["repeat"]
    if not _int(n) or n < 1:
        raise FlowError(f"{where} 的 repeat 要是 1 以上的整數，收到 {n!r}")
    body = item.get("steps")
    if not isinstance(body, list) or not body:
        raise FlowError(f"{where} 的 repeat 區段不完整：要有 steps（區段裡的步驟清單）")
    on_break = _on_break(where, item)
    out.append({"type": "repeat_start", "repeat": n})
    _parse_steps(body, out)
    out.append({"type": "repeat_end", "on_break": on_break})


def _parse_branch(where, item, out):
    extra = [k for k in item if k not in ("branch", "on_break")]
    if extra:
        raise FlowError(f"{where}（branch）不認得的鍵：{'、'.join(map(str, extra))}")
    arms = item["branch"]
    if not isinstance(arms, list) or not arms:
        raise FlowError(f"{where} 的 branch 區段不完整：要有分支清單（- if: …）")
    on_break = _on_break(where, item)
    out.append({"type": "branch_start"})
    for k, arm in enumerate(arms):
        if k:
            out.append({"type": "branch_or"})
        aw = f"步驟 {len(out) + 1}"
        if not isinstance(arm, dict) or "if" not in arm:
            raise FlowError(f"{aw}：branch 的每個分支要寫 if（分支條件）")
        extra = [x for x in arm if x not in ("if", "then")]
        if extra:
            raise FlowError(f"{aw}：branch 的分支不認得的鍵：{'、'.join(map(str, extra))}")
        cond = arm["if"]
        heads = [h for h in (cond if isinstance(cond, dict) else {})
                 if h in _HEADS]
        if len(heads) != 1 or heads[0] not in findtarget.FIND_TYPES:
            raise FlowError(f"{aw}：branch 的 if 必須是找圖步驟"
                            "（find_click / find / wait_gone）")
        then = arm.get("then") or []
        if not isinstance(then, list):
            raise FlowError(f"{aw}：then 要是步驟清單")
        _parse_steps([cond, *then], out)
    out.append({"type": "branch_end", "on_break": on_break})


def _parse_step(where, head, item):
    """一步 (flow-style mapping) → 記憶體的完整步驟."""
    t = head
    s = {"type": t}
    allowed = set(flowdefaults.KEYS[t]) - {"type", "target", "confirm_target"}
    allowed |= {head}
    if t in findtarget.FIND_TYPES:
        allowed |= set(_TARGET_ATTRS)
    extra = [k for k in item if k not in allowed]
    if extra:
        raise FlowError(f"{where}（{t}）不認得的鍵：{'、'.join(map(str, extra))}")
    if t in findtarget.FIND_TYPES:
        s["target"] = _yaml_target(where, {k: item[k] for k in (head, *_TARGET_ATTRS)
                                           if k in item}, head)
    elif t == "click":
        s["click"] = _xy(f"{where} 的 click", item["click"])
    elif t == "drag":
        s["drag"] = _xy(f"{where} 的 drag", item["drag"])
        if "to" not in item:
            raise FlowError(f"{where} 的 drag 要寫 to（終點）")
        s["to"] = _xy(f"{where} 的 to", item["to"])
    elif t == "wait":
        if not _num(item["wait"]) or item["wait"] < 0:
            raise FlowError(f"{where} 的 wait 要是秒數，收到 {item['wait']!r}")
        s["wait"] = item["wait"]
    if "offset" in item:
        s["offset"] = _xy(f"{where} 的 offset", item["offset"])
    if "confirm" in item:
        c = item["confirm"]
        if isinstance(c, dict):
            extra = [k for k in c if k not in ("appear", *_TARGET_ATTRS)]
            if extra or "appear" not in c:
                raise FlowError(f"{where} 的 confirm 要寫成 gone / next / "
                                "{appear: 範本名, within…, pick…, color…}，"
                                f"收到 {c!r}")
            s["confirm"] = "appear"
            s["confirm_target"] = _yaml_target(f"{where} 的 confirm", c, "appear")
        elif c in ("gone", "next"):
            s["confirm"] = c
        else:
            raise FlowError(f"{where} 的 confirm 只能是 gone / next / {{appear: 範本名}}，"
                            f"收到 {c!r}")
    for k in ("timeout", "duration", "hold"):
        if k in item:
            if not _num(item[k]) or item[k] < 0:
                raise FlowError(f"{where} 的 {k} 要是秒數，收到 {item[k]!r}")
            s[k] = item[k]
    if "interval" in item:
        if not _num(item["interval"]) or item["interval"] <= 0:
            raise FlowError(f"{where} 的 interval 要是大於 0 的秒數，收到 {item['interval']!r}")
        s["interval"] = item["interval"]
    if "on_fail" in item:
        if item["on_fail"] not in ("skip", "break", "stop"):
            raise FlowError(f"{where} 的 on_fail 只能是 skip / break（不寫＝stop），"
                            f"收到 {item['on_fail']!r}")
        s["on_fail"] = item["on_fail"]
    for k in ("busy_check", "update_origin"):
        if k in item:
            if not isinstance(item[k], bool):
                raise FlowError(f"{where} 的 {k} 要是 true / false，收到 {item[k]!r}")
            s[k] = item[k]
    if not flowdefaults.has_wait(s):
        waits = [k for k in flowdefaults.WAIT if k in item]
        if waits:
            raise FlowError(f"{where} 的 {'、'.join(waits)} 只有設了生效確認（confirm）"
                            "才有意義")
    return flowdefaults.complete(s)


# ---------- 寫 ----------

def dump_flow(flow):
    """記憶體的流程 → flow.yaml 的文字 (等於預設的不寫; 一步一行, 行尾 # N 是步驟編號).

    整份重寫, 手寫註解不保留。template_pos 只留被引用的範本。
    """
    lines = [f"format: {FLOW_FORMAT}"]
    run = flow.get("run", 1)
    if run != flowdefaults.FLOW["run"]:
        lines.append(f"run: {_flow_style(run)}")
    if flow.get("scan_region"):
        lines.append(f"scan_region: {_flow_style(list(flow['scan_region']))}")
    cal = flow.get("calibration")
    if cal:
        lines.append("calibration:")
        lines.append(f"  pair: {_flow_style(list(cal['pair']))}")
        lines.append(f"  baseline: {_flow_style(round(float(cal['baseline']), 1))}")
        fb = calibration.fallback_pair(cal)
        if fb:
            lines.append("  fallback: " + _flow_style({
                "pair": list(fb["pair"]),
                "baseline": round(float(fb["baseline"]), 1),
                "offset": [int(v) for v in fb["offset"]]}))
    busy = flow.get("busy")
    if busy:
        lines.append(f"busy: {_flow_style(_target_yaml(busy, 'template'))}")
    refs = set(template_refs(flow))
    pos = {n: p for n, p in (flow.get("template_pos") or {}).items() if n in refs}
    if pos:
        lines.append("template_pos:")
        for n, p in pos.items():
            lines.append(f"  {_flow_style(n)}: {_flow_style([int(p[0]), int(p[1])])}")
    if flow.get("engine"):
        lines.append(f"engine: {_flow_style(dict(flow['engine']))}")
    steps = flow.get("steps") or []
    if not steps:
        lines.append("steps: []")
    else:
        lines.append("steps:")
        lines += _emit(_nest(steps), 2)
    return "\n".join(lines) + "\n"


def _flow_style(v):
    """單行 flow-style YAML (中文名直接當值)."""
    import yaml
    text = yaml.dump(v, allow_unicode=True, default_flow_style=True,
                     sort_keys=False, width=10_000)
    return text.removesuffix("...\n").strip()


def _number(v):
    v = float(v)
    return int(v) if v.is_integer() else v


def _target_yaml(tgt, head):
    out = {head: tgt.get("template", "")}
    if tgt.get("within") is not None:
        out["within"] = [int(c) for c in tgt["within"]]
    kind, value = findtarget.pick_rule(tgt)
    if kind in ("top", "left"):
        out["pick"] = {kind: int(value)}
    elif kind == "near":
        out["pick"] = {"near": [int(value[0]), int(value[1])]}
    if tgt.get("color"):
        out["color"] = True
    return out


_ORDER = ("offset", "duration", "hold", "confirm", "timeout", "interval", "on_fail",
          "busy_check", "update_origin")


def _step_yaml(step):
    """記憶體的步驟 → yaml 的一步 (開頭的鍵在前, 等於預設的不寫)."""
    s = flowdefaults.strip(step)
    t = step["type"]
    if t in findtarget.FIND_TYPES:
        out = _target_yaml(step["target"], t)
    elif t == "click":
        out = {"click": [int(v) for v in step["click"]]}
    elif t == "drag":
        out = {"drag": [int(v) for v in step["drag"]],
               "to": [int(v) for v in step["to"]]}
    else:
        out = {"wait": _number(step["wait"])}
    for k in _ORDER:
        if k not in s:
            continue
        v = s[k]
        if k == "confirm":
            if v == "appear":
                v = _target_yaml(step.get("confirm_target") or {}, "appear")
        elif k == "offset":
            v = [int(c) for c in v]
        elif k in ("duration", "hold", "timeout", "interval"):
            v = _number(v)
        out[k] = v
    return out


def _nest(steps):
    """平面標記 → 巢狀節點 [(種類, 內容, 步驟編號)] (編號＝平面清單的位置 + 1, 標記也算一號).

    種類: "step" (yaml 的一步)、"repeat" ({repeat, steps, on_break})、
    "branch" ({arms: [[節點, ...], ...], on_break})。
    """
    pos = 0

    def block(stop):
        nonlocal pos
        out = []
        while pos < len(steps):
            s = steps[pos]
            t = s["type"]
            if t in stop:
                return out
            no = pos + 1
            pos += 1
            if t == "repeat_start":
                body = block(("repeat_end",))
                if pos >= len(steps):
                    raise FlowError(f"步驟 {no}：重複區段缺少結尾，寫不出 flow.yaml")
                end = steps[pos]
                pos += 1
                out.append(("repeat", {"repeat": s["repeat"], "steps": body,
                                       "on_break": end["on_break"]}, no))
            elif t == "branch_start":
                arms = []
                while True:
                    arms.append(block(("branch_or", "branch_end")))
                    if pos >= len(steps):
                        raise FlowError(f"步驟 {no}：分岔缺少結尾，寫不出 flow.yaml")
                    sep = steps[pos]
                    pos += 1
                    if sep["type"] == "branch_end":
                        break
                out.append(("branch", {"arms": arms, "on_break": sep["on_break"]}, no))
            elif t in ("repeat_end", "branch_or", "branch_end"):
                raise FlowError(f"步驟 {no}：區段標記不成對，寫不出 flow.yaml")
            else:
                out.append(("step", _step_yaml(s), no))
        return out

    return block(())


def _emit(nodes, ind):
    pad = " " * ind
    lines = []
    for kind, node, no in nodes:
        if kind == "repeat":
            lines.append(f"{pad}- repeat: {node['repeat']}    # {no}")
            if node["on_break"] == "break":
                lines.append(f"{pad}  on_break: break")
            lines.append(f"{pad}  steps:")
            lines += _emit(node["steps"], ind + 4)
        elif kind == "branch":
            lines.append(f"{pad}- branch:    # {no}")
            for arm in node["arms"]:
                if not arm or arm[0][0] != "step":
                    raise FlowError(f"步驟 {no}：分岔的每個分支開頭要是找圖步驟，"
                                    "寫不出 flow.yaml")
                (_, cond, cno), rest = arm[0], arm[1:]
                lines.append(f"{pad}    - if: {_flow_style(cond)}    # {cno}")
                if rest:
                    lines.append(f"{pad}      then:")
                    lines += _emit(rest, ind + 8)
            if node["on_break"] == "break":
                lines.append(f"{pad}  on_break: break")
        else:
            lines.append(f"{pad}- {_flow_style(node)}    # {no}")
    return lines


def write_flow(folder, flow, images=None):
    """把記憶體的流程寫成流程資料夾; 回傳被引用卻沒有圖的範本名.

    images: {範本名: bytes 或圖檔路徑}——要放進 templates/ 的圖 (先全部讀進記憶體再寫,
    改名互換也不會互相蓋掉)。寫完 templates/ 正好是引用集合裡有圖的那些: 沒被引用的
    png 刪掉。順序是圖 → flow.yaml (先寫暫存檔再取代) → 才刪沒被引用的: 中途失敗時舊的
    flow.yaml 引用的圖都還在。檔名不分大小寫 (只改大小寫的改名換成新檔名, 不會被當成
    沒被引用而刪掉)。
    """
    folder = str(folder)
    refs = template_refs(flow)
    for n in refs:
        problem = template_name_problem(n)
        if problem:
            raise FlowError(problem)
    text = dump_flow(flow)
    blobs = {n: _blob(src) for n, src in (images or {}).items() if n in refs}
    tdir = os.path.join(folder, TEMPLATES_DIR)
    os.makedirs(tdir, exist_ok=True)
    for n, data in blobs.items():
        for fn in _pngs(tdir):   # 只差大小寫的舊檔先移走, 新檔才會是新名字
            if fn[:-4] != n and fn[:-4].casefold() == n.casefold():
                os.remove(os.path.join(tdir, fn))
        with open(os.path.join(tdir, n + ".png"), "wb") as f:
            f.write(data)
    tmp = os.path.join(folder, FLOW_YAML + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, os.path.join(folder, FLOW_YAML))
    keep = {n.casefold() for n in refs}
    for fn in _pngs(tdir):
        if fn[:-4].casefold() not in keep:
            os.remove(os.path.join(tdir, fn))
    return [n for n in refs if not os.path.isfile(os.path.join(tdir, n + ".png"))]


def _pngs(folder):
    return [fn for fn in os.listdir(folder) if fn.lower().endswith(".png")]


# ================= 開著的流程的範本: templates/ ＋ 快取 =================

SHOTS_DIR = "shots"            # 快取裡還沒存檔的截圖
REGISTERED_DIR = "registered"  # 快取裡引擎的登錄產物


def _same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _inside(path, folder):
    return _same_path(os.path.dirname(path), folder)


def clear_unsaved(unsaved_dir):
    """清空「未存檔」快取 (開新流程、讀取別的流程、重開 app 時)."""
    shutil.rmtree(unsaved_dir, ignore_errors=True)
    os.makedirs(unsaved_dir, exist_ok=True)


class FlowTemplates:
    """一份開著的流程的範本圖在哪裡 + 拍攝位置 (記憶體裡的「本流程的範本」).

    範本名 → 圖檔路徑: 已存檔的在 templates/, 還沒存檔的截圖在快取的 shots/。新增、
    改名、刪除只動這份對照與快取 (templates/ 不動), `save` 才把流程寫回資料夾。
    拍攝位置 (flow.yaml 的 template_pos: 截圖當下的中心, 相對`座標基準點`、流程尺度)
    跟著範本一起改名與刪除。
    """

    def __init__(self, folder, cache):
        self.folder = folder      # 流程資料夾; None＝還沒第一次存檔的新流程
        self.cache = cache        # 快取: <流程資料夾>/.cache 或「未存檔」快取
        self._src = {}            # 範本名 → 圖檔路徑
        self._pos = {}            # 範本名 → [x, y]

    @classmethod
    def open(cls, folder, unsaved_dir, template_pos=None):
        """開一份流程資料夾: 上次沒存的截圖丟掉 (登錄產物留著, 過期會自己重算),
        「未存檔」快取清空."""
        clear_unsaved(unsaved_dir)
        folder = os.path.abspath(str(folder))
        cache = os.path.join(folder, CACHE_DIR)
        shutil.rmtree(os.path.join(cache, SHOTS_DIR), ignore_errors=True)
        store = cls(folder, cache)
        store.rescan()
        store._pos = {n: [int(p[0]), int(p[1])] for n, p in (template_pos or {}).items()}
        return store

    @classmethod
    def new(cls, unsaved_dir):
        """還沒有資料夾的新流程: 用清空的「未存檔」快取."""
        clear_unsaved(unsaved_dir)
        return cls(None, os.path.abspath(str(unsaved_dir)))

    # ---- 位置 ----

    @property
    def shots_dir(self):
        return os.path.join(self.cache, SHOTS_DIR)

    @property
    def registered_dir(self):
        return os.path.join(self.cache, REGISTERED_DIR)

    # ---- 範本 ----

    def names(self):
        """本流程的範本名 (已排序)."""
        return sorted(self._src)

    def has(self, name):
        return name in self._src

    def path_of(self, name):
        """範本的圖檔路徑 (還沒登記的名字＝快取 shots/ 裡它會在的位置)."""
        return self._src.get(name) or os.path.join(self.shots_dir, name + ".png")

    def images(self):
        """{範本名: 圖檔路徑}——引擎的`範本清單`與存檔都吃這個."""
        return dict(self._src)

    def rescan(self):
        """重掃 templates/ (被外力動過之後): 新放進來的圖加入, 不見了的拿掉 (快取裡的
        截圖不動; 同名時截圖優先)。回傳有變動的範本名集合."""
        if self.folder is None:
            return set()
        tdir = os.path.join(self.folder, TEMPLATES_DIR)
        changed = set()
        for n, p in list(self._src.items()):
            if _inside(p, tdir) and not os.path.isfile(p):
                del self._src[n]
                changed.add(n)
        known = {n.casefold() for n in self._src}
        if os.path.isdir(tdir):
            for fn in sorted(_pngs(tdir)):
                if fn[:-4].casefold() not in known:
                    self._src[fn[:-4]] = os.path.join(tdir, fn)
                    changed.add(fn[:-4])
        return changed

    def is_unsaved(self, name):
        """這張是不是還沒存檔的截圖 (在快取裡, 還沒進 templates/)."""
        return name in self._src and _inside(self._src[name], self.shots_dir)

    def reserve(self, name):
        """保留一個未被占用的範本名 (撞名加序號) 並登記到快取 shots/; 圖由呼叫端寫進
        `path_of(名稱)` (影像編碼是 app 的事, 只有 `automation.imgio` 碰 cv2)."""
        os.makedirs(self.shots_dir, exist_ok=True)
        final = free_name(clean_name(name) or "template", self._src)
        self._src[final] = os.path.join(self.shots_dir, final + ".png")
        return final

    def add(self, name, blob, pos=None):
        """加一張範本 (bytes 或來源圖檔路徑; 跨流程複製進來的是獨立副本) 進快取;
        撞名自動加序號。回傳最終採用的範本名。pos＝拍攝位置 (只有本流程自己拍的才有)."""
        data = _blob(blob)
        final = self.reserve(name)
        with open(self._src[final], "wb") as f:
            f.write(data)
        if pos is not None:
            self.set_pos(final, pos)
        return final

    def remove(self, name):
        """從本流程拿掉一個範本: 快取裡的截圖直接刪, templates/ 的等存檔時才離開;
        登錄產物與拍攝位置一起丟."""
        path = self._src.pop(name, None)
        if path and _inside(path, self.shots_dir):
            try:
                os.remove(path)
            except OSError:
                pass
        self.drop_registered(name)
        self._pos.pop(name, None)

    def rename(self, old, new):
        """重新命名範本 (撞名加序號); 回傳最終名稱, 來源不存在回傳 None.

        new 要先過 `template_name_problem` (呼叫端擋)。快取裡的截圖跟著改檔名, templates/
        的圖存檔時才換檔名; 引用的改寫由呼叫端以 `rename_template_refs` 處理。
        """
        if old not in self._src:
            return None
        final = free_name(new, [n for n in self._src if n != old])
        if final == old:
            return old
        path = self._src.pop(old)
        if _inside(path, self.shots_dir):
            moved = os.path.join(self.shots_dir, final + ".png")
            os.replace(path, moved)
            path = moved
        self._src[final] = path
        self.drop_registered(old)
        if old in self._pos:
            self._pos[final] = self._pos.pop(old)
        return final

    def drop_registered(self, name):
        """丟棄某範本的登錄產物 (改名、刪除、重截之後; 重建很便宜)."""
        shutil.rmtree(os.path.join(self.registered_dir, name), ignore_errors=True)

    # ---- 拍攝位置 ----

    def pos(self):
        """{範本名: [x, y]} (相對`座標基準點`, 流程尺度)."""
        return {n: list(p) for n, p in self._pos.items()}

    def pos_of(self, name):
        p = self._pos.get(name)
        return list(p) if p is not None else None

    def set_pos(self, name, xy):
        self._pos[name] = [int(xy[0]), int(xy[1])]

    def shift_pos(self, old_anchor, new_anchor, k=1.0):
        """換`校準對`時所有拍攝位置改成相對新基準點 (同 flowfmt.shift_flow 的換算)."""
        from automation import flowfmt
        self._pos = {n: list(flowfmt.from_screen(flowfmt.to_screen(xy, old_anchor, k),
                                                 new_anchor, k))
                     for n, xy in self._pos.items()}
        return len(self._pos)

    # ---- 存檔 ----

    def save(self, flow, folder=None):
        """把流程寫回資料夾; 回傳被引用卻沒有圖的範本名.

        flow.yaml 整份重寫; 被引用的截圖從快取搬進 templates/; templates/ 裡沒被引用的
        圖搬回快取的 shots/ (這次編輯期間還在, 重開或讀取別的流程時丟掉), 所以存完
        templates/ 正好是引用集合。新流程 (還沒有資料夾) 要給 folder: 第一次存檔把
        「未存檔」快取的登錄產物與其餘截圖搬進新資料夾的 .cache/。
        """
        first = self.folder is None
        if first and folder is None:
            raise ValueError("新流程第一次存檔要指定資料夾")
        if not first and folder is not None and not _same_path(folder, self.folder):
            raise ValueError("流程已經有資料夾了, 只能存回同一個資料夾")
        target = os.path.abspath(str(folder)) if first else self.folder
        refs = set(template_refs(flow))
        tdir = os.path.join(target, TEMPLATES_DIR)
        kept = {}   # templates/ 裡沒被引用的: 先複製一份到快取, write_flow 寫完才刪原檔
        if not first:
            for n, p in self._src.items():
                if n not in refs and _inside(p, tdir):
                    os.makedirs(self.shots_dir, exist_ok=True)
                    kept[n] = os.path.join(self.shots_dir, n + ".png")
                    shutil.copyfile(p, kept[n])
        images = {n: p for n, p in self._src.items() if n in refs}
        missing = write_flow(target, dict(flow, template_pos=self.pos()), images)
        self._src.update(kept)
        for n, p in images.items():
            dest = os.path.join(tdir, n + ".png")
            if not _same_path(p, dest):
                if _inside(p, self.shots_dir):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
                self._src[n] = dest
        if first:
            cache = os.path.join(target, CACHE_DIR)
            os.makedirs(cache, exist_ok=True)
            if os.path.isdir(self.registered_dir):
                shutil.move(self.registered_dir, os.path.join(cache, REGISTERED_DIR))
            shots = os.path.join(cache, SHOTS_DIR)
            for n, p in list(self._src.items()):
                if _inside(p, self.shots_dir):
                    os.makedirs(shots, exist_ok=True)
                    moved = os.path.join(shots, n + ".png")
                    shutil.move(p, moved)
                    self._src[n] = moved
            unsaved = self.cache
            self.folder, self.cache = target, cache
            clear_unsaved(unsaved)
        return missing


# ================= 其他流程資料夾 (選範本對話框的來源) =================

def list_flow_folders(root):
    """root 底下的流程資料夾 (有 flow.yaml 的子資料夾, 已排序)."""
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return []
    return [os.path.join(root, n) for n in entries
            if os.path.isfile(os.path.join(root, n, FLOW_YAML))]


def folder_template_names(folder):
    """流程資料夾 templates/ 裡的範本名 (已排序)."""
    tdir = os.path.join(folder, TEMPLATES_DIR)
    try:
        return sorted(fn[:-4] for fn in os.listdir(tdir) if fn.lower().endswith(".png"))
    except OSError:
        return []


def folder_template_bytes(folder, name):
    """流程資料夾裡某張範本的圖檔內容; 讀不到回 None."""
    try:
        with open(os.path.join(folder, TEMPLATES_DIR, name + ".png"), "rb") as f:
            return f.read()
    except OSError:
        return None

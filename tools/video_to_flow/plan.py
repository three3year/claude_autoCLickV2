"""`轉換計畫`: Claude 寫、組裝與補充讀的 JSON 介面 (不是領域詞彙; 格式見
.claude/skills/video-measure/plan-format.md).

步驟的鍵跟 flow.yaml 一樣 (開頭鍵即動作、秒、`on_fail`、`busy_check`、`repeat`/`branch`
巢狀, 見 docs/flow-format.md), 由 app 的 `flowfile.parse_steps` 驗證與補齊——工具不帶
自己的鍵表與預設。跟 flow.yaml 只差兩樣:

- 位置是**影片像素的畫面位置**: `click` 的值、`drag` 的值與 `to`、找圖的 `at`、
  `pick: {near: [x, y]}`; 偏移由工具依`原點`規則算, 不寫 `offset`。
- 影片證據: 步驟的 `frame`、找圖的 `scroll` (捲動軸)、`confirm: {appear, frame}`;
  `within` 不寫 (`固定矩形`由工具從影格上挑中的框算)。
- `共用矩形`: 最外層 `shared_rects` 宣告, 找圖的 `rect`、`confirm: {appear, rect}`、
  `busy: {rect}` 引用 (組裝時展開成各成員的 `within`; flow.yaml 不記組別)。

`load` 回傳 `Plan`: steps 是記憶體的完整步驟 (平面標記, 位置仍是影片像素), evidence 是
同一索引的影片證據。任何錯誤丟 `ToolError`, 都在寫檔之前。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import flowfile
from automation import findtarget, flowcheck

from .errors import ToolError

ASSEMBLE, INSERT = "assemble", "insert"

_TOP = {ASSEMBLE: {"video", "name", "out", "templates", "steps", "calibration",
                   "busy", "report", "shared_rects"},
        INSERT: {"video", "templates", "steps", "report", "after", "into", "expect",
                 "scale_image", "align", "shared_rects"}}
TEMPLATE_FIELDS = {"frame", "box", "present", "absent", "clean"}
SCROLL = ("vertical", "horizontal")

_RETIRED_TOP = {
    "busyTarget": "改寫 busy（{template, color, pick, frame}）",
    "retryIntervalMs": "補做間隔已退場成固定行為（1 秒），計畫不要寫",
    "profile": "profile 已退場（ADR 0015）：流程輸出成資料夾，位置寫 out（或命令列 --out）",
    "reportPath": "交付報告一律寫在流程資料夾的 交付報告/，計畫不要寫 reportPath",
}
_NO_TYPED_SCALE = ("scale", "ratio", "video_scale")

_RETIRED_STEP = {
    "type": "步驟改用開頭鍵即動作（find_click / find / wait_gone / click / drag / wait / "
            "repeat / branch），不寫 type",
    "action": "找圖三態改用開頭鍵：find_click（點）、find（不點）、wait_gone（等消失）",
    "template": "範本名寫在開頭鍵的值（例 {\"find_click\": \"開始\"}）",
    "colorCheck": "改寫 color: true",
    "onNotFound": "改寫 on_fail（skip / break；不寫＝stop）",
    "updateOrigin": "改寫 update_origin",
    "busyCheck": "改寫 busy_check",
    "onBreak": "改寫 on_break",
    "confirmTemplate": "改寫 confirm: {appear: 範本名}",
    "confirmTarget": "改寫 confirm: {appear: 範本名, color, pick}",
    "ms": "時間一律秒：等待寫 wait: 秒、拖曳寫 duration: 秒",
    "holdMs": "改寫 hold: 秒",
    "count": "重複改寫 {\"repeat\": N, \"steps\": [...]}",
    "loop_start": "重複改寫 {\"repeat\": N, \"steps\": [...]}",
    "limit": "限定範圍（以原點為基準的矩形）已退場；固定矩形由工具算",
    "appearLimitMs": "出現等候上限已退場（ADR 0014）：要等遊戲忙完，改在送出輸入的那一步勾 "
                     "busy_check",
    "button": "滑鼠鍵已退場：只剩左鍵",
    "clicks": "連點已退場：一步點一下",
    "key": "按鍵步驟已退場：流程不支援按鍵；影片裡看得到的按鍵效果寫進 report.unexplained",
    "keys": "按鍵步驟已退場：流程不支援按鍵；影片裡看得到的按鍵效果寫進 report.unexplained",
    "within": "不寫：固定矩形由工具從這一步那一幀上挑中的框算（每邊外推範本寬高的 50%）",
    "offset": "不寫：位置寫影片像素的畫面位置（找圖寫 at），偏移由工具依原點算",
}
for _k in ("x", "y", "x1", "y1", "x2", "y2", "offsetX", "offsetY", "mode"):
    _RETIRED_STEP[_k] = ("位置一律寫影片像素的畫面位置（click 的值、drag 的值與 to、"
                         "找圖的 at），偏移由工具算")


@dataclass
class Plan:
    mode: str
    video: str
    templates: dict
    steps: list                 # 記憶體的完整步驟 (平面), 位置是影片像素
    evidence: list              # 與 steps 同索引: {frame, at, scroll, rect, confirm_frame,
                                #                   confirm_rect} 或 None
    report: dict
    name: str = ""
    out: str | None = None
    calibration: dict | None = None
    busy: dict | None = None    # 記憶體的找圖目標 (無 within) ＋ "frame" (＋ "rect")
    after: int | None = None
    into: int | None = None
    expect: dict | None = None
    scale_image: str | None = None
    align: dict | None = None   # `對齊圖` {find, frame, at (影片像素), step}
    align_set: bool = False     # 計畫寫了 align (含 align: null＝刻意不對齊)
    # `共用矩形` {名: {frame, box (影片像素), scroll, why}} 或 (補充) {same_as, expect, why}
    shared_rects: dict = field(default_factory=dict)
    base: str = field(default_factory=os.getcwd)


def _err(where, msg):
    raise ToolError(f"轉換計畫有誤：{where}：{msg}")


def _xy(where, v):
    if (not isinstance(v, (list, tuple)) or len(v) != 2
            or not all(isinstance(c, (int, float)) and not isinstance(c, bool)
                       for c in v)):
        _err(where, f"位置要寫成 [x, y]（影片像素），收到 {v!r}")
    return [int(round(v[0])), int(round(v[1]))]


def _box(where, b):
    if (not isinstance(b, (list, tuple)) or len(b) != 4
            or not all(isinstance(c, int) and not isinstance(c, bool) for c in b)
            or b[2] <= 0 or b[3] <= 0):
        _err(where, f"box 要寫成 [x, y, w, h] 整數且寬高 > 0，收到 {b!r}")
    return [int(c) for c in b]


def _frame(where, v):
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        _err(where, f"影格編號要是非負整數，收到 {v!r}")
    return v


def read(plan):
    """計畫 (dict 或 JSON 檔路徑) → (dict, 相對路徑的基準目錄)."""
    if isinstance(plan, dict):
        return plan, os.getcwd()
    path = str(plan)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise ToolError(f"讀不到轉換計畫：{path}（{e}）") from None
    except ValueError as e:
        raise ToolError(f"轉換計畫不是合法的 JSON：{path}（{e}）") from None
    if not isinstance(data, dict):
        raise ToolError("轉換計畫的最外層要是 JSON 物件")
    return data, os.path.dirname(os.path.abspath(path))


def load(plan, mode=ASSEMBLE):
    """讀計畫並驗證; 回傳 `Plan`. 相對路徑以計畫檔所在目錄為準."""
    raw, base = read(plan)
    for k, why in _RETIRED_TOP.items():
        if k in raw:
            _err(k, why)
    for k in _NO_TYPED_SCALE:
        if k in raw:
            _err(k, "不收手打的倍率：影片倍率一律量出來（影片量不到校準對時，給 scale_image："
                 "跟影片同取景、同視窗大小的一張圖片）")
    if mode == INSERT:
        for k in ("calibration", "busy", "name", "out"):
            if k in raw:
                _err(k, "補充一律沿用既有流程的校準對、忙碌指示、名稱與位置，計畫不要寫")
    extra = sorted(set(raw) - _TOP[mode])
    if extra:
        _err("最外層", f"不認得的欄位 {', '.join(extra)}")
    if not isinstance(raw.get("video"), str) or not raw["video"].strip():
        _err("video", "必填（字串）")

    def resolve(p):
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))

    templates = _templates(raw.get("templates", {} if mode == INSERT else None))
    steps, evidence = _steps(raw.get("steps"))
    p = Plan(mode, resolve(raw["video"]), templates, steps, evidence,
             _report(raw.get("report")), base=base)
    p.shared_rects = _shared_rects(raw.get("shared_rects"), mode)
    if mode == ASSEMBLE:
        if not isinstance(raw.get("name"), str) or not raw["name"].strip():
            _err("name", "必填（字串）")
        p.name = flowfile.clean_name(raw["name"])
        if not p.name:
            _err("name", "清不出可用的檔名")
        p.out = resolve(raw["out"]) if raw.get("out") else None
        p.calibration = _calibration(raw.get("calibration"), templates)
        p.busy = _busy(raw.get("busy"), templates)
        _shared_refs(p)
        _references(p, set(templates))
        precheck(p.steps, p.busy)
    else:
        _insert_point(p, raw)
        if raw.get("scale_image") is not None:
            if not isinstance(raw["scale_image"], str) or not raw["scale_image"].strip():
                _err("scale_image", "要是圖片路徑（字串）")
            p.scale_image = resolve(raw["scale_image"])
        if "align" in raw:
            p.align_set = True
            p.align = _align(raw["align"])
        _shared_refs(p)
    return p


def _templates(raw):
    if not isinstance(raw, dict):
        _err("templates", "要是 {範本名: {...}} 物件")
    out = {}
    for name, t in raw.items():
        where = f"範本「{name}」"
        problem = flowfile.template_name_problem(name)
        if problem:
            _err(where, problem)
        if not isinstance(t, dict):
            _err(where, "要是物件")
        extra = sorted(set(t) - TEMPLATE_FIELDS)
        if extra:
            _err(where, f"不認得的欄位 {', '.join(extra)}")
        if "frame" not in t or "box" not in t:
            _err(where, "frame（取材幀）與 box（影片像素裁切框）必填")
        frame = _frame(where + " frame", t["frame"])
        b = _box(where, t["box"])
        present = []
        for pr in t.get("present") or []:
            if isinstance(pr, dict):
                if set(pr) - {"frame", "at"} or "frame" not in pr:
                    _err(where, f"present 的項目要是影格編號或 {{frame, at}}，收到 {pr!r}")
                present.append({"frame": _frame(where + " present", pr["frame"]),
                                "at": _xy(where + " present.at", pr["at"])
                                if "at" in pr else None})
            else:
                present.append({"frame": _frame(where + " present", pr), "at": None})
        absent = [_frame(where + " absent", a) for a in t.get("absent") or []]
        clean = t.get("clean", True)
        if not isinstance(clean, bool):
            _err(where, "clean 要是 true/false")
        out[name] = {"frame": frame, "box": b,
                     "present": present, "absent": absent, "clean": clean}
    return out


# ---------- 步驟 ----------

def _retired(no, item):
    where = f"步驟 {no}"
    for k in item:
        if k in _RETIRED_STEP:
            _err(where, f"{k}：{_RETIRED_STEP[k]}")
    for k in ("timeout", "wait"):
        v = item.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 100:
            _err(where, f"{k} 是秒（舊計畫的毫秒已改成秒），收到 {v!r}")


def _strip(no, head, item):
    """拿掉計畫專用的影片證據欄位; 回傳 (證據, 給 flowfile 驗證的一步)."""
    where = f"步驟 {no}"
    item = dict(item)
    ev = {"frame": None, "at": None, "scroll": None, "rect": None, "confirm_frame": None,
          "confirm_rect": None}
    if "frame" in item:
        ev["frame"] = _frame(where + " frame", item.pop("frame"))
    if "at" in item:
        if head not in findtarget.FIND_TYPES:
            _err(where, "at 只用在找圖（點擊或原點的位置）；座標點擊的位置寫在 click 的值、"
                 "拖曳寫在 drag 與 to")
        ev["at"] = _xy(where + " at", item.pop("at"))
    if "scroll" in item:
        if head not in findtarget.FIND_TYPES:
            _err(where, "scroll（捲動軸）只用在找圖步驟")
        if item["scroll"] not in SCROLL:
            _err(where, f"scroll 只能是 vertical（直向）或 horizontal（橫向），"
                 f"收到 {item['scroll']!r}")
        ev["scroll"] = item.pop("scroll")
    if "rect" in item:
        if head not in findtarget.FIND_TYPES:
            _err(where, "rect（共用矩形）只用在找圖步驟；確認圖寫在 confirm: {appear, rect}、"
                 "忙碌指示寫在 busy 裡；gone 與 next 沿用別步的目標，不另寫")
        if ev["scroll"] is not None:
            _err(where, "rect 跟 scroll 不能同寫：捲動軸寫在共用矩形的宣告裡")
        ev["rect"] = _rect_name(where + " rect", item.pop("rect"))
    c = item.get("confirm")
    if isinstance(c, dict):
        c = dict(c)
        if "within" in c:
            _err(where, "confirm 的 within 不寫：確認圖的固定矩形由工具算")
        if "frame" in c:
            ev["confirm_frame"] = _frame(where + " confirm.frame", c.pop("frame"))
        if "rect" in c:
            if "appear" not in c:
                _err(where, "confirm 的 rect 只用在 appear 確認圖：gone 與 next 沿用別步的目標，"
                     "不另寫")
            ev["confirm_rect"] = _rect_name(where + " confirm.rect", c.pop("rect"))
        item["confirm"] = c
    for k in ("click", "drag", "to"):
        if k in item:
            item[k] = _xy(f"{where} {k}", item[k])
    pick = item.get("pick")
    if isinstance(pick, dict) and list(pick) == ["near"]:   # 其他寫法交給 flowfile 報錯
        item["pick"] = {"near": _xy(where + " pick.near", pick["near"])}
    if isinstance(c, dict) and isinstance(c.get("pick"), dict) and list(c["pick"]) == ["near"]:
        c["pick"] = {"near": _xy(where + " confirm.pick.near", c["pick"]["near"])}
    return ev, item


def _walk(items, ev):
    """計畫的巢狀步驟 → (去掉證據的巢狀步驟, 平面證據清單); 平面順序跟
    flowfile 的平面標記一致 (repeat: 開頭/內容/結尾; branch: 開頭/各分支以「或」隔開/結尾)."""
    if not isinstance(items, list):
        return items
    out = []
    for item in items:
        no = len(ev) + 1
        if not isinstance(item, dict):
            out.append(item)
            continue
        _retired(no, item)
        heads = [k for k in item if k in flowfile.HEADS]
        if len(heads) != 1:
            out.append(item)   # flowfile 會指名報錯
            continue
        head = heads[0]
        if head == "repeat":
            ev.append(None)
            body = _walk(item.get("steps"), ev)
            ev.append(None)
            out.append(dict(item, steps=body) if "steps" in item else item)
        elif head == "branch":
            ev.append(None)
            arms = item["branch"]
            if isinstance(arms, list):
                new = []
                for k, arm in enumerate(arms):
                    if k:
                        ev.append(None)
                    if not isinstance(arm, dict) or not isinstance(arm.get("if"), dict):
                        new.append(arm)
                        continue
                    cond = _walk([arm["if"]], ev)[0]
                    then = _walk(arm.get("then") or [], ev)
                    new.append(dict(arm, **{"if": cond},
                                    **({"then": then} if "then" in arm else {})))
                arms = new
            ev.append(None)
            out.append(dict(item, branch=arms))
        else:
            e, stripped = _strip(no, head, item)
            ev.append(e)
            out.append(stripped)
    return out


def _steps(raw):
    if not isinstance(raw, list) or not raw:
        _err("steps", "要是非空的步驟清單")
    ev = []
    stripped = _walk(raw, ev)
    try:
        steps = flowfile.parse_steps(stripped)
    except flowfile.FlowError as e:
        raise ToolError(f"轉換計畫有誤：{e}") from None
    if len(steps) != len(ev):   # 防呆: 兩邊攤平的順序不一致＝工具的 bug
        raise ToolError(f"工具錯誤：計畫攤平後 {len(ev)} 步，flowfile 讀成 {len(steps)} 步")
    return steps, ev


def _references(p, known):
    """步驟與確認圖引用的範本都要在 known 裡 (組裝: 計畫的範本; 補充: 加上既有流程的)."""
    for i, s in enumerate(p.steps):
        if findtarget.is_find(s) and findtarget.template(s) not in known:
            _err(f"步驟 {i + 1}", f"引用的範本「{findtarget.template(s)}」不在計畫的範本清單裡")
        if findtarget.uses_confirm_target(s) and findtarget.confirm_template(s) not in known:
            _err(f"步驟 {i + 1}", f"確認圖「{findtarget.confirm_template(s)}」不在計畫的範本清單裡")


def precheck(steps, busy):
    """app 執行前一定會擋、而且只看步驟種類的那幾項 (找圖相連、原點的圖離開的原點、忙碌檢查
    沒有忙碌指示), 在任何量測之前先擋; 相對座標前有沒有原點由原點推算擋 (懂區段)."""
    errs = []
    bad = flowcheck.confirm_next_bad(steps)
    if bad:
        errs.append(f"步驟 {bad[0] + 1}：「點到下一步的圖出現」（confirm: next）需要下一步緊接著"
                    "是找圖步驟（不能是最後一步或區段標記）")
    bad = flowcheck.origin_leaves_bad(steps)
    if bad:
        errs.append(f"步驟 {bad[0] + 1}：「原點的圖離開」（confirm: gone）需要原點來自找圖："
                    "前面最近一個更新原點的步驟要是找圖")
    bad = flowcheck.busy_check_bad(steps, busy)
    if bad:
        errs.append(f"步驟 {bad[0] + 1}：勾了 busy_check，但沒有忙碌指示（busy）")
    if errs:
        raise ToolError("轉換計畫有誤：" + "；".join(errs))


def check_references(p, existing=()):
    """補充: 引用的範本要在計畫的範本或既有流程裡."""
    _references(p, set(p.templates) | set(existing))


# ---------- 流程層級 ----------

def _pair(where, pair, templates, what):
    if (not isinstance(pair, list) or len(pair) != 2
            or not all(isinstance(n, str) for n in pair) or pair[0] == pair[1]):
        _err(where, f"pair 要是兩個不同的範本名，收到 {pair!r}")
    for n in pair:
        if n not in templates:
            _err(where, f"{what}的範本「{n}」不在計畫的範本清單裡")
    return list(pair)


def _calibration(raw, templates):
    """`校準對`（新流程必填）: {"pair": [兩個範本名], "frame": 量測幀, "fallback": {"pair"}}."""
    if raw is None:
        _err("calibration", "新流程必須有校準對：{\"pair\": [兩張遊戲畫面內相距夠遠的固定圖], "
             "\"frame\": 兩張都在的那一幀}（標題列圖示＋關閉鈕放 fallback）")
    where = "calibration"
    if not isinstance(raw, dict) or set(raw) - {"pair", "frame", "fallback"}:
        _err(where, f"要是 {{pair, frame, fallback}} 物件，收到 {raw!r}")
    pair = _pair(where, raw.get("pair"), templates, "校準對")
    frame = (_frame(where + " frame", raw["frame"]) if "frame" in raw
             else templates[pair[0]]["frame"])
    fallback = None
    if raw.get("fallback") is not None:
        fb = raw["fallback"]
        if not isinstance(fb, dict) or set(fb) - {"pair"}:
            _err(where + " fallback", f"要是 {{pair}} 物件（兩張備用校準對的範本），收到 {fb!r}")
        fb_pair = _pair(where + " fallback", fb.get("pair"), templates, "備用校準對")
        if set(fb_pair) == set(pair):
            _err(where + " fallback", "備用校準對不能與校準對相同")
        fallback = {"pair": fb_pair}
    return {"pair": pair, "frame": frame, "fallback": fallback}


def _busy(raw, templates):
    """`忙碌指示`: {template, color, pick, frame}; frame＝它出現的證據影格 (預設＝取材幀)."""
    if raw is None:
        return None
    where = "busy"
    if not isinstance(raw, dict):
        _err(where, f"要是 {{template, color, pick, frame}} 物件，收到 {raw!r}")
    d = dict(raw)
    if "within" in d:
        _err(where, "within 不寫：忙碌指示的固定矩形由工具從證據影格上的位置算")
    frame = _frame(where + " frame", d.pop("frame")) if "frame" in d else None
    rect = _rect_name(where + " rect", d.pop("rect")) if "rect" in d else None
    try:
        tgt = flowfile.parse_target(where, d)
    except flowfile.FlowError as e:
        raise ToolError(f"轉換計畫有誤：{e}") from None
    if findtarget.needs_origin(tgt):
        _err(where, "忙碌指示沒有原點可依靠，pick 不能用 near")
    if tgt["template"] not in templates:
        _err(where, f"忙碌指示的範本「{tgt['template']}」不在計畫的範本清單裡")
    tgt["frame"] = frame if frame is not None else templates[tgt["template"]]["frame"]
    if rect is not None:
        tgt["rect"] = rect
    return tgt


# ---------- 共用矩形 ----------

_SHARED_VIDEO = {"frame", "box", "scroll", "why"}
_SHARED_SAME = {"same_as", "expect", "why"}


def _rect_name(where, v):
    if not isinstance(v, str) or not v.strip():
        _err(where, f"要寫共用矩形的名字（shared_rects 裡的鍵），收到 {v!r}")
    return v


def _shared_rects(raw, mode):
    """`共用矩形`的宣告: 影片像素宣告 {frame, box, scroll, why}; 補充另可
    {same_as: N, expect, why} (照抄既有流程第 N 步的固定矩形)."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _err("shared_rects", "要是 {名字: {...}} 物件")
    out = {}
    for name, d in raw.items():
        where = f"shared_rects「{name}」"
        if not isinstance(d, dict):
            _err(where, "要是物件")
        for k in ("within", "offset"):
            if k in d:
                _err(where, f"{k} 不寫：共用矩形的框由工具從容器框（box）算，"
                     "組裝時才寫進各成員的 within")
        if "same_as" in d and mode != INSERT:
            _err(where, "same_as 只用在補充（沿用既有流程某一步的固定矩形）；新流程寫 frame 與 box")
        keys = _SHARED_SAME if "same_as" in d else _SHARED_VIDEO
        extra = sorted(set(d) - keys)
        if extra:
            _err(where, f"不認得的欄位 {', '.join(extra)}"
                 + ("（same_as 跟 frame／box／scroll 擇一）" if "same_as" in d else ""))
        why = d.get("why")
        if not isinstance(why, str) or not why.strip():
            _err(where, "why 必填：一句話說明為什麼這幾個目標算同一組（進交付報告給使用者確認）")
        if "same_as" in d:
            n = d["same_as"]
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                _err(where + " same_as", f"要是步驟編號（從 1 起算），收到 {n!r}")
            out[name] = {"same_as": n, "expect": _expect(where + " expect", d.get("expect")),
                         "why": why}
            continue
        if "frame" not in d or "box" not in d:
            _err(where, "frame（容器完整可見的那一幀）與 box（容器框，影片像素）必填")
        box = _box(where, d["box"])
        scroll = d.get("scroll")
        if scroll is not None and scroll not in SCROLL:
            _err(where, f"scroll 只能是 vertical（直向）或 horizontal（橫向），收到 {scroll!r}")
        out[name] = {"frame": _frame(where + " frame", d["frame"]), "box": box,
                     "scroll": scroll, "why": why}
    return out


def shared_refs(p):
    """引用共用矩形的成員 → {名: [(步驟索引或 None (忙碌指示), "step"/"confirm"/"busy")]}."""
    refs = {}
    for i, ev in enumerate(p.evidence):
        for key, kind in (("rect", "step"), ("confirm_rect", "confirm")):
            if ev and ev.get(key):
                refs.setdefault(ev[key], []).append((i, kind))
    if p.busy and p.busy.get("rect"):
        refs.setdefault(p.busy["rect"], []).append((None, "busy"))
    return refs


def _shared_refs(p):
    refs = shared_refs(p)
    for name, members in refs.items():
        if name not in p.shared_rects:
            i, kind = members[0]
            where = "busy" if i is None else f"步驟 {i + 1}"
            _err(where, f"rect 引用的共用矩形「{name}」不在 shared_rects 裡")
    for name in p.shared_rects:
        if name not in refs:
            _err(f"shared_rects「{name}」", "沒有任何找圖步驟、確認圖或忙碌指示引用（rect）："
                 "沒用到就刪掉")


def scroll_of(p, ev):
    """這一步的找圖實際生效的捲動軸: 自己宣告的, 或它引用的共用矩形宣告的."""
    if not ev:
        return None
    return ev.get("scroll") or (p.shared_rects.get(ev.get("rect")) or {}).get("scroll")


def _report(raw):
    raw = raw or {}
    if not isinstance(raw, dict):
        _err("report", "要是物件")
    if "keys" in raw:
        _err("report.keys", "「口頭補充的按鍵」一節已刪：流程不支援按鍵；影片裡按鍵造成的畫面變化"
             "寫進 report.unexplained（報告會請使用者改用點擊）")
    extra = sorted(set(raw) - {"branches", "unexplained", "notes"})
    if extra:
        _err("report", f"不認得的欄位 {', '.join(extra)}")
    out = {}
    for k in ("branches", "unexplained", "notes"):
        v = raw.get(k) or []
        if not isinstance(v, list) or not all(isinstance(s, str) for s in v):
            _err(f"report.{k}", "要是字串清單")
        out[k] = list(v)
    return out


# ---------- 補充的插入點 ----------

def _insert_point(p, raw):
    has_after, has_into = "after" in raw, "into" in raw
    if has_after == has_into:
        _err("after/into", "插入點要寫 after: N（插在第 N 步之後、同一層）或 into: N"
             "（插在重複區段 N 裡最前面），擇一")
    key = "after" if has_after else "into"
    n = raw[key]
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        _err(key, f"要是步驟編號（從 1 起算），收到 {n!r}")
    setattr(p, key, n)
    p.expect = _expect("expect", raw.get("expect"))


def _expect(where, exp):
    """核對步驟編號用的 expect: 第 N 步的開頭鍵＋值 (插入點與 same_as 同一套)."""
    if (not isinstance(exp, dict) or len(exp) != 1
            or next(iter(exp)) not in flowfile.HEADS):
        _err(where, "要寫第 N 步的開頭鍵＋值（例 {\"find\": \"标题_办公室\"}），工具拿它核對"
             f"編號沒寫錯，收到 {exp!r}")
    return dict(exp)


def _align(raw):
    """`對齊圖`: {"find": 範本名, "frame": 影片幀, "at": [x, y], "step": N} 或 null."""
    if raw is None:
        return None
    where = "align"
    if not isinstance(raw, dict) or set(raw) != {"find", "frame", "at", "step"}:
        _err(where, "要寫 {\"find\": 範本名, \"frame\": 影片幀, \"at\": [x, y]（影片裡的大約位置）, "
             "\"step\": N（插入點前定位這張圖的那一步，flow.yaml 行尾的 # N）}，"
             f"刻意不對齊寫 align: null，收到 {raw!r}")
    if not isinstance(raw["find"], str) or not raw["find"].strip():
        _err(where + ".find", "要是既有範本的名字（字串）")
    n = raw["step"]
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        _err(where + ".step", f"要是步驟編號（從 1 起算），收到 {n!r}")
    return {"find": raw["find"], "frame": _frame(where + ".frame", raw["frame"]),
            "at": _xy(where + ".at", raw["at"]), "step": n}

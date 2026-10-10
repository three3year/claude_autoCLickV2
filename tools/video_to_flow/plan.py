"""`轉換計畫`: Claude 寫、組裝讀的 JSON 介面 (不是領域詞彙).

    {
      "video":   "示範影片路徑",
      "profile": "目標 profile 目錄",
      "name":    "流程名稱 (存檔檔名, 撞名自動加序號)",
      "templates": {
        "開始行動": {"frame": 120, "box": [x, y, w, h],
                     "present": [150, {"frame": 300, "at": [x, y]}],
                     "absent": [100], "clean": true}
      },
      "steps": [
        {"type": "find_click", "template": "開始行動", "frame": 130, "at": [x, y],
         "colorCheck": true, "pick": {"kind": "top", "n": 3}},
        {"type": "click", "at": [x, y]},
        {"type": "drag", "from": [x, y], "to": [x, y]},
        {"type": "loop_start", "count": 5}, ..., {"type": "loop_end"}
      ],
      "calibration": {"pair": ["左上圖示", "右下按鈕"], "frame": 120,
                      "fallback": {"pair": ["標題列圖示", "關閉鈕"]}},
      "retryIntervalMs": 1000,
      "busyTarget": {"template": "提交中", "colorCheck": true},
      "report": {"branches": ["…"], "unexplained": ["…"], "keys": ["…"]}
    }

步驟用流程既有的步驟種類與欄位詞彙; 位置一律寫**影片像素的畫面位置**
(`at` / `from` / `to`), 不寫偏移、不寫相對座標——那由組裝依`原點`規則推算。
`frame` 是「這一步在影片裡看的是哪一幀」: 找圖步驟在這一幀上照它的`找圖目標`
實際挑到範本框 (預設＝範本的取材幀)。偏移欄位 (offsetX/Y、x/y、x1…y2) 由組裝產生,
計畫寫了就報錯。

找圖步驟 (與確認圖 `confirmTarget`) 的`找圖目標`屬性: `colorCheck` (比色)、
`pick` (挑選規則: {kind: top/left, n} 或 {kind: near, at: [x, y]})。指定點寫影片
像素的畫面位置, 組裝依該步的`原點`換成相對值 (確認圖用點擊後的原點)。工具不產出
限定範圍 (`固定矩形`相對`座標基準點`, 影片轉流程階段才會產; 以原點為基準的矩形已退場)。
`confirmTemplate` 是只有範本的確認圖簡寫。

已退場的寫法 (ADR 0014) 一律報錯: 按鍵步驟、限定範圍 (limit)、出現等候上限
(appearLimitMs)、非左鍵 (button)、連點 (clicks); 寫預設值 (左鍵、1 下) 的照收。

`calibration` 指名這份流程的`校準對` (兩個計畫裡的範本: 遊戲畫面內相距夠遠的兩張
固定圖) 與量基準距離的那一幀 (預設＝第一張的取材幀)。影片尺度就是流程尺度
(ADR 0009): 組裝在那一幀上量兩張的中心距離當`基準距離`。沒寫＝產出的流程沒有
校準對, 不能執行 (交付報告會寫明)。可選的 `fallback` 指名`備用校準對` (例: 標題列
圖示＋關閉鈕, 任何畫面都在): 組裝在同一幀上量它的基準距離與「備用第一張中心 →
座標基準點」的偏移 (ADR 0013); 量不到＝流程不帶備用對, 報告寫明。

`生效確認` (ADR 0008): 座標點擊與拖曳也可寫 confirm (gone＝`原點的圖離開`、
appear、next) 與 confirmTemplate/confirmTarget、timeout、interval、onNotFound;
流程層級的`補做間隔` (retryIntervalMs) 與`忙碌指示` (busyTarget: 範本＋比色,
不限定範圍)。
"""
from __future__ import annotations

import json
import os

import flowfile
from automation.runner import (POINTER_TYPES, confirm_next_connected,
                               origin_source, uses_confirm_next)

from . import origin
from .errors import ToolError

RETAKE_PREFIX = "待重拍_"   # `待重拍`範本名前綴 (存檔格式不為它加任何欄位)

# 計畫專用的位置詞彙 (影片像素), 由組裝換成存檔的偏移欄位
_POS_KEYS = {"frame", "at", "from", "to"}

# 每種步驟允許的欄位 (流程既有詞彙 + 位置詞彙); type 另計
STEP_FIELDS = {
    "find_click": {"template", "frame", "at", "action",
                   "timeout", "interval", "onNotFound", "confirm",
                   "confirmTemplate", "confirmTarget", "updateOrigin",
                   "colorCheck", "pick"},
    "click": {"at", "frame", "updateOrigin", "confirm",
              "confirmTemplate", "confirmTarget", "timeout", "interval",
              "onNotFound"},
    "drag": {"from", "to", "frame", "ms", "holdMs", "confirm",
             "confirmTemplate", "confirmTarget", "timeout", "interval",
             "onNotFound"},
    "wait": {"ms"},
    "loop_start": {"count"},
    "loop_end": {"onBreak"},
    "branch_start": set(),
    "branch_or": set(),
    "branch_end": {"onBreak"},
}

ENUMS = {
    "action": ("click", "none", "wait_gone"),
    "onNotFound": ("skip", "break", "stop"),
    "confirm": ("none", "gone", "appear", "next"),
    "onBreak": ("continue", "break"),
}

_NUMBERS = {"timeout", "interval", "ms", "holdMs", "count", "frame"}

TEMPLATE_FIELDS = {"frame", "box", "present", "absent", "clean"}


def _err(where, msg):
    raise ToolError(f"轉換計畫有誤：{where}：{msg}")


def _xy(where, v):
    if (not isinstance(v, (list, tuple)) or len(v) != 2
            or not all(isinstance(c, (int, float)) and not isinstance(c, bool)
                       for c in v)):
        _err(where, f"位置要寫成 [x, y]（影片像素），收到 {v!r}")
    return [int(round(v[0])), int(round(v[1]))]


def _frame(where, v):
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        _err(where, f"影格編號要是非負整數，收到 {v!r}")
    return v


_TARGET_ATTRS = {"colorCheck", "pick"}


def _retired(where, s):
    """已退場的計畫寫法 (ADR 0014) 一律報錯; 寫預設值的滑鼠鍵與連點數照收 (拿掉)."""
    if s.get("type") == "key":
        _err(where, "按鍵步驟已退場（ADR 0014）：流程不支援按鍵，請改用點擊；"
             "影片裡看不到的按鍵寫進 report.keys")
    if "appearLimitMs" in s:
        _err(where, "出現等候上限（appearLimitMs）已退場（ADR 0014）："
             "要等遊戲忙完，改在送出輸入的那一步勾忙碌檢查")
    for d, what in ((s, ""), (s.get("confirmTarget"), "確認圖的")):
        if isinstance(d, dict) and "limit" in d:
            _err(where, f"{what}以原點為基準的限定範圍（limit）已退場（ADR 0014）；"
                 "影片轉流程階段改產固定矩形，現在先不寫限定範圍")
    if s.get("button", "left") != "left":
        _err(where, f"滑鼠鍵只剩左鍵（button 已退場，ADR 0014），收到 {s['button']!r}")
    if s.get("clicks", 1) != 1:
        _err(where, f"連點已退場（clicks，ADR 0014）：一步點一下，收到 {s['clicks']!r}")
    s.pop("button", None)
    s.pop("clicks", None)


def _target_attrs(where, d):
    """驗證並正規化找圖目標的屬性 (比色、挑選規則), 就地改寫 d."""
    if "colorCheck" in d and not isinstance(d["colorCheck"], bool):
        _err(where, f"colorCheck 要是 true/false，收到 {d['colorCheck']!r}")
    if "pick" in d:
        p = d["pick"]
        kind = p.get("kind") if isinstance(p, dict) else None
        if kind not in ("top", "left", "near"):
            _err(where, "pick（挑選規則）的 kind 只能是 top（由上到下第 N 個）、"
                 f"left（由左到右第 N 個）、near（最接近指定點），收到 {p!r}")
        if kind in ("top", "left"):
            if set(p) - {"kind", "n"}:
                _err(where, f"pick 的 {kind} 只有 n 欄位，收到 {p!r}")
            n = p.get("n")
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                _err(where, f"pick 的第 N 個（n）要是從 1 起算的整數，收到 {n!r}")
            d["pick"] = {"kind": kind, "n": n}
        else:
            if set(p) - {"kind", "at"} or "at" not in p:
                _err(where, "pick 的 near 只寫 at（影片像素的指定點畫面位置，組裝換成"
                     f"相對原點的偏移；沒有以搜尋範圍為基準這回事），收到 {p!r}")
            d["pick"] = {"kind": "near", "at": _xy(where + " pick.at", p["at"])}


def load(plan):
    """讀計畫 (dict 或 JSON 檔路徑) 並驗證詞彙; 回傳正規化後的 dict.

    計畫檔裡的相對路徑以計畫檔所在目錄為準。結構檢查 (區段成對、範本存在、
    `找圖相連`…) 也在這裡做——任何組裝動作之前就擋下。
    """
    base = os.getcwd()
    if not isinstance(plan, dict):
        path = str(plan)
        try:
            with open(path, encoding="utf-8") as f:
                plan = json.load(f)
        except OSError as e:
            raise ToolError(f"讀不到轉換計畫：{path}（{e}）") from None
        except ValueError as e:
            raise ToolError(f"轉換計畫不是合法的 JSON：{path}（{e}）") from None
        base = os.path.dirname(os.path.abspath(path))
    if not isinstance(plan, dict):
        raise ToolError("轉換計畫的最外層要是 JSON 物件")

    known = {"video", "profile", "name", "templates", "steps", "report",
             "reportPath", "calibration", "retryIntervalMs", "busyTarget"}
    extra = sorted(set(plan) - known)
    if extra:
        _err("最外層", f"不認得的欄位 {', '.join(extra)}")
    for key in ("video", "profile", "name"):
        if not isinstance(plan.get(key), str) or not plan[key].strip():
            _err(key, "必填（字串）")

    def resolve(p):
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))

    name = flowfile.clean_name(plan["name"])
    if not name:
        _err("name", "清不出可用的檔名")
    out = {
        "video": resolve(plan["video"]),
        "profile": resolve(plan["profile"]),
        "name": name,
        "report_path": resolve(plan["reportPath"]) if plan.get("reportPath") else None,
        "templates": _templates(plan.get("templates")),
        "report": _report(plan.get("report")),
    }
    out["steps"] = _steps(plan.get("steps"), out["templates"])
    out["calibration"] = _calibration(plan.get("calibration"), out["templates"])
    out["retry_interval_ms"] = _retry_interval(plan.get("retryIntervalMs"))
    out["busy"] = _busy(plan.get("busyTarget"), out["templates"])
    origin.derive(out["steps"], out["templates"], None)  # 相對座標前要有原點
    return out


def _templates(raw):
    if not isinstance(raw, dict):
        _err("templates", "要是 {範本名: {...}} 物件")
    out = {}
    for name, t in raw.items():
        where = f"範本「{name}」"
        if flowfile.clean_name(name) != name or not name:
            _err(where, "範本名要是平面名稱（不能有 / \\ : * ? \" < > | 或前後的 .）")
        if name.startswith(RETAKE_PREFIX):
            _err(where, f"範本名不能以「{RETAKE_PREFIX}」開頭（那是組裝標待重拍用的前綴）")
        if not isinstance(t, dict):
            _err(where, "要是物件")
        extra = sorted(set(t) - TEMPLATE_FIELDS)
        if extra:
            _err(where, f"不認得的欄位 {', '.join(extra)}")
        if "frame" not in t or "box" not in t:
            _err(where, "frame（取材幀）與 box（影片像素裁切框）必填")
        frame = _frame(where + " frame", t["frame"])
        b = t["box"]
        if (not isinstance(b, (list, tuple)) or len(b) != 4
                or not all(isinstance(c, int) and not isinstance(c, bool) for c in b)
                or b[2] <= 0 or b[3] <= 0):
            _err(where, f"box 要寫成 [x, y, w, h] 整數且寬高 > 0，收到 {b!r}")
        present = []
        for p in t.get("present") or []:
            if isinstance(p, dict):
                if set(p) - {"frame", "at"} or "frame" not in p:
                    _err(where, f"present 的項目要是影格編號或 {{frame, at}}，收到 {p!r}")
                present.append({"frame": _frame(where + " present", p["frame"]),
                                "at": _xy(where + " present.at", p["at"])
                                if "at" in p else None})
            else:
                present.append({"frame": _frame(where + " present", p), "at": None})
        absent = [_frame(where + " absent", a) for a in t.get("absent") or []]
        clean = t.get("clean", True)
        if not isinstance(clean, bool):
            _err(where, "clean 要是 true/false")
        out[name] = {"frame": frame, "box": [int(c) for c in b],
                     "present": present, "absent": absent, "clean": clean}
    return out


def _pair(where, pair, templates, what):
    if (not isinstance(pair, list) or len(pair) != 2
            or not all(isinstance(n, str) for n in pair) or pair[0] == pair[1]):
        _err(where, f"pair 要是兩個不同的範本名，收到 {pair!r}")
    for n in pair:
        if n not in templates:
            _err(where, f"{what}的範本「{n}」不在計畫的範本清單裡")
    return list(pair)


def _calibration(raw, templates):
    """`校準對`: {"pair": [兩個範本名], "frame": 量測幀, "fallback": {"pair": [...]}};
    沒寫回傳 None; fallback (備用校準對) 沒寫＝None."""
    if raw is None:
        return None
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


def _retry_interval(raw):
    """`補做間隔` (毫秒); 沒寫回傳 None (存檔不寫＝預設 1000)."""
    if raw is None:
        return None
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        _err("retryIntervalMs", f"要是非負整數（毫秒），收到 {raw!r}")
    return raw


def _busy(raw, templates):
    """`忙碌指示`: {template, colorCheck}; 沒寫回傳 None.

    忙碌指示在補做前查, 沒有可依靠的原點——工具不產出它的限定範圍 (`固定矩形`相對
    `座標基準點`, 請在 app 的找圖設定裡框)。
    """
    if raw is None:
        return None
    where = "busyTarget"
    if not isinstance(raw, dict) or set(raw) - {"template", "colorCheck", "limit"}:
        _err(where, f"要是 {{template, colorCheck}} 物件，收到 {raw!r}")
    if raw.get("template") not in templates:
        _err(where, f"忙碌指示的範本「{raw.get('template')}」不在計畫的範本清單裡")
    d = dict(raw)
    if "limit" in d:
        _err(where, "忙碌指示不寫限定範圍（沒有原點可依靠；固定矩形請在 app 的找圖設定裡框）")
    _target_attrs(where, d)
    return d


def _report(raw):
    raw = raw or {}
    if not isinstance(raw, dict):
        _err("report", "要是物件")
    extra = sorted(set(raw) - {"branches", "unexplained", "keys", "notes"})
    if extra:
        _err("report", f"不認得的欄位 {', '.join(extra)}")
    out = {}
    for k in ("branches", "unexplained", "keys", "notes"):
        v = raw.get(k) or []
        if not isinstance(v, list) or not all(isinstance(s, str) for s in v):
            _err(f"report.{k}", "要是字串清單")
        out[k] = list(v)
    return out


def _steps(raw, templates):
    if not isinstance(raw, list) or not raw:
        _err("steps", "要是非空的步驟清單")
    out = []
    for i, s in enumerate(raw):
        where = f"步驟 {i + 1}"
        if not isinstance(s, dict):
            _err(where, "要是物件")
        s = dict(s)
        _retired(where, s)
        t = s.get("type")
        if t not in STEP_FIELDS:
            _err(where, f"不認得的步驟種類 {t!r}"
                 f"（可用：{', '.join(STEP_FIELDS)}）")
        extra = sorted(set(s) - STEP_FIELDS[t] - {"type"})
        if extra:
            hint = ""
            if set(extra) & {"x", "y", "x1", "y1", "x2", "y2", "offsetX",
                             "offsetY", "mode"}:
                hint = "（位置一律寫影片像素的 at/from/to，偏移由組裝推算）"
            _err(where, f"「{t}」沒有欄位 {', '.join(extra)}{hint}")
        for k, choices in ENUMS.items():
            if k in s and s[k] not in choices:
                _err(where, f"{k} 只能是 {'/'.join(choices)}，收到 {s[k]!r}")
        for k in _NUMBERS & set(s):
            v = s[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                _err(where, f"{k} 要是非負數字，收到 {v!r}")
        if "updateOrigin" in s and not isinstance(s["updateOrigin"], bool):
            _err(where, "updateOrigin 要是 true/false")
        if "frame" in s:
            _frame(where + " frame", s["frame"])
        if t == "find_click":
            if s.get("template") not in templates:
                _err(where, f"引用的範本「{s.get('template')}」不在計畫的範本清單裡")
            if "at" in s:
                s["at"] = _xy(where + " at", s["at"])
            _target_attrs(where, s)
            if "confirmTarget" in s:
                if "confirmTemplate" in s:
                    _err(where, "confirmTemplate 與 confirmTarget 只能擇一"
                         "（confirmTemplate 是只有範本的確認圖簡寫）")
                ct = s["confirmTarget"]
                if not isinstance(ct, dict) or set(ct) - (_TARGET_ATTRS | {"template"}):
                    _err(where, "confirmTarget 要是 {template, colorCheck, pick}"
                         f" 物件，收到 {ct!r}")
                ct = dict(ct)
                _target_attrs(where + " confirmTarget", ct)
                s["confirmTarget"] = ct
            elif s.get("confirmTemplate"):
                s["confirmTarget"] = {"template": s.pop("confirmTemplate")}
            else:
                s.pop("confirmTemplate", None)
            if s.get("action", "click") != "click" and (
                    s.get("confirm", "none") != "none" or s.get("confirmTarget")):
                _err(where, "生效確認 (confirm/confirmTemplate/confirmTarget) 只有"
                     "動作為點擊的找圖才有意義，不點擊的找圖不要寫")
            if s.get("confirm") == "appear":
                cname = (s.get("confirmTarget") or {}).get("template")
                if cname not in templates:
                    _err(where, f"確認圖「{cname}」不在計畫的範本清單裡")
            elif s.get("confirmTarget"):
                _err(where, "只有 confirm 為 appear 時才能指定確認圖"
                     "（confirmTemplate/confirmTarget）")
        if t in POINTER_TYPES:
            _pointer_confirm(where, s, templates)
        if t == "click":
            if "at" not in s:
                _err(where, "座標點擊要寫 at（影片像素的點擊位置）")
            s["at"] = _xy(where + " at", s["at"])
        elif t == "drag":
            if "from" not in s or "to" not in s:
                _err(where, "拖曳要寫 from 與 to（影片像素的起訖位置）")
            s["from"] = _xy(where + " from", s["from"])
            s["to"] = _xy(where + " to", s["to"])
        elif t == "loop_start":
            if not isinstance(s.get("count"), int) or s["count"] < 1:
                _err(where, "重複開始要寫 count（重複次數，正整數）")
        out.append(s)
    _check_sections(out)
    for i, s in enumerate(out):
        if uses_confirm_next(s) and not confirm_next_connected(out, i):
            _err(f"步驟 {i + 1}", "「下一步的圖出現」(confirm: next) 需要「找圖相連」："
                 "下一步必須緊接著是找圖步驟（不能是最後一步或區段標記）")
        if (s["type"] in POINTER_TYPES and s.get("confirm") == "gone"
                and origin_source(out, i) != "find"):
            _err(f"步驟 {i + 1}", "「原點的圖離開」(confirm: gone) 需要原點來自找圖："
                 "前面最近一個更新原點的步驟要是找圖")
    return out


def _pointer_confirm(where, s, templates):
    """座標點擊/拖曳的`生效確認`欄位 (就地正規化確認圖簡寫)."""
    if "confirmTarget" in s:
        if "confirmTemplate" in s:
            _err(where, "confirmTemplate 與 confirmTarget 只能擇一")
        ct = s["confirmTarget"]
        if not isinstance(ct, dict) or set(ct) - (_TARGET_ATTRS | {"template"}):
            _err(where, "confirmTarget 要是 {template, colorCheck, pick}"
                 f" 物件，收到 {ct!r}")
        ct = dict(ct)
        _target_attrs(where + " confirmTarget", ct)
        s["confirmTarget"] = ct
    elif s.get("confirmTemplate"):
        s["confirmTarget"] = {"template": s.pop("confirmTemplate")}
    else:
        s.pop("confirmTemplate", None)
    mode = s.get("confirm", "none")
    if mode == "appear":
        cname = (s.get("confirmTarget") or {}).get("template")
        if cname not in templates:
            _err(where, f"確認圖「{cname}」不在計畫的範本清單裡")
    elif s.get("confirmTarget"):
        _err(where, "只有 confirm 為 appear 時才能指定確認圖"
             "（confirmTemplate/confirmTarget）")
    if mode == "none" and set(s) & {"timeout", "interval", "onNotFound"}:
        _err(where, "timeout/interval/onNotFound 是生效確認的設定，"
             "沒寫 confirm 的座標點擊/拖曳不要寫")


def _check_sections(steps):
    """區段標記完整巢狀 (成對、不交錯; 分岔每個分支開頭是找圖)."""
    stack = []
    for i, s in enumerate(steps):
        t = s["type"]
        where = f"步驟 {i + 1}"
        if t in ("loop_start", "branch_start"):
            stack.append((t, i + 1))
            if t == "branch_start" and (i + 1 >= len(steps)
                                        or steps[i + 1]["type"] != "find_click"):
                _err(where, "分岔的每個分支開頭必須是找圖步驟")
        elif t == "branch_or":
            if not stack or stack[-1][0] != "branch_start":
                _err(where, "「分岔（或）」必須直接位於分岔區段內")
            if i + 1 >= len(steps) or steps[i + 1]["type"] != "find_click":
                _err(where, "分岔的每個分支開頭必須是找圖步驟")
        elif t in ("loop_end", "branch_end"):
            need = "loop_start" if t == "loop_end" else "branch_start"
            if not stack:
                _err(where, f"「{t}」缺少對應的開始標記")
            if stack[-1][0] != need:
                _err(where, f"區段交錯：要先結束步驟 {stack[-1][1]} 開始的"
                     f"「{stack[-1][0]}」區段")
            stack.pop()
    if stack:
        _err(f"步驟 {stack[-1][1]}", f"「{stack[-1][0]}」缺少對應的結束標記")

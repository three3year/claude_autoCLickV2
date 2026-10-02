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
        {"type": "find_click", "template": "開始行動", "frame": 130, "at": [x, y]},
        {"type": "click", "at": [x, y]},
        {"type": "drag", "from": [x, y], "to": [x, y]},
        {"type": "key", "keys": "esc"},
        {"type": "loop_start", "count": 5}, ..., {"type": "loop_end"}
      ],
      "report": {"branches": ["…"], "unexplained": ["…"], "keys": ["…"]}
    }

步驟用流程既有的步驟種類與欄位詞彙; 位置一律寫**影片像素的畫面位置**
(`at` / `from` / `to`), 不寫偏移、不寫相對座標——那由組裝依`原點`規則推算。
`frame` 是「這一步在影片裡看的是哪一幀」: 找圖步驟在這一幀上讓引擎實際找到
範本框 (預設＝範本的取材幀)。偏移欄位 (offsetX/Y、x/y、x1…y2) 與座標模式
(mode) 由組裝產生, 計畫寫了就報錯。
"""
from __future__ import annotations

import json
import os

import flowfile
from automation.runner import confirm_next_connected, uses_confirm_next

from . import origin
from .errors import ToolError

RETAKE_PREFIX = "待重拍_"   # `待重拍`範本名前綴 (存檔格式不為它加任何欄位)

# 計畫專用的位置詞彙 (影片像素), 由組裝換成存檔的偏移欄位
_POS_KEYS = {"frame", "at", "from", "to"}

# 每種步驟允許的欄位 (流程既有詞彙 + 位置詞彙); type 另計
STEP_FIELDS = {
    "find_click": {"template", "frame", "at", "action", "button", "clicks",
                   "timeout", "interval", "onNotFound", "confirm",
                   "confirmTemplate", "updateOrigin"},
    "click": {"at", "frame", "button", "clicks", "updateOrigin"},
    "drag": {"from", "to", "frame", "button", "ms", "holdMs"},
    "wait": {"ms"},
    "key": {"keys"},
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
    "button": ("left", "right", "middle"),
    "onBreak": ("continue", "break"),
}

_NUMBERS = {"clicks", "timeout", "interval", "ms", "holdMs", "count", "frame"}

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
             "reportPath"}
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
        t = s.get("type")
        if t not in STEP_FIELDS:
            _err(where, f"不認得的步驟種類 {t!r}"
                 f"（可用：{', '.join(STEP_FIELDS)}）")
        extra = sorted(set(s) - STEP_FIELDS[t] - {"type"})
        if extra:
            hint = ""
            if set(extra) & {"x", "y", "x1", "y1", "x2", "y2", "offsetX",
                             "offsetY", "mode"}:
                hint = "（位置一律寫影片像素的 at/from/to，偏移與座標模式由組裝推算）"
            _err(where, f"「{t}」沒有欄位 {', '.join(extra)}{hint}")
        s = dict(s)
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
            if s.get("action", "click") != "click" and (
                    s.get("confirm", "none") != "none" or s.get("confirmTemplate")):
                _err(where, "點擊後確認 (confirm/confirmTemplate) 只有動作為點擊的"
                     "找圖才有意義，不點擊的找圖不要寫")
            if s.get("confirm") == "appear":
                if s.get("confirmTemplate") not in templates:
                    _err(where, f"確認圖「{s.get('confirmTemplate')}」"
                         "不在計畫的範本清單裡")
            elif s.get("confirmTemplate"):
                _err(where, "只有 confirm 為 appear 時才能指定 confirmTemplate")
        elif t == "click":
            if "at" not in s:
                _err(where, "座標點擊要寫 at（影片像素的點擊位置）")
            s["at"] = _xy(where + " at", s["at"])
        elif t == "drag":
            if "from" not in s or "to" not in s:
                _err(where, "拖曳要寫 from 與 to（影片像素的起訖位置）")
            s["from"] = _xy(where + " from", s["from"])
            s["to"] = _xy(where + " to", s["to"])
        elif t == "key":
            if not isinstance(s.get("keys"), str) or not s["keys"].strip():
                _err(where, "按鍵要寫 keys（例如 \"esc\"）")
        elif t == "loop_start":
            if not isinstance(s.get("count"), int) or s["count"] < 1:
                _err(where, "重複開始要寫 count（重複次數，正整數）")
        out.append(s)
    _check_sections(out)
    for i, s in enumerate(out):
        if uses_confirm_next(s) and not confirm_next_connected(out, i):
            _err(f"步驟 {i + 1}", "「點到下一步的圖出現」(confirm: next) 需要「找圖相連」："
                 "下一步必須緊接著是找圖步驟（不能是最後一步或區段標記）")
    return out


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

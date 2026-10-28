import os
import re

import harness
import yaml

import flowfile
from automation import findtarget, flowdefaults

DOC = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "flow-format.md")
TOP = "頂層"
_SECTION_END = {"repeat": "repeat_end", "branch": "branch_end"}


def expected_keys():
    keys = {TOP: set(flowfile.TOP_KEYS),
            "calibration": set(flowfile.CALIBRATION_KEYS),
            "calibration.fallback": set(flowfile.FALLBACK_KEYS),
            "busy": {"template", *flowfile.TARGET_ATTRS},
            "confirm.appear": {"appear", *flowfile.TARGET_ATTRS},
            "branch.分支": set(flowfile.ARM_KEYS)}
    for head in ("find_click", "find", "wait_gone", "click", "drag", "wait",
                 "repeat", "branch"):
        keys[head] = flowfile.step_keys(head)
    return keys


_MISSING = object()


def expected_default(where, key):
    if where == TOP:
        return flowdefaults.FLOW.get(key, _MISSING)
    if where in _SECTION_END:
        return flowdefaults.STEP[_SECTION_END[where]].get(key, _MISSING)
    if where in flowdefaults.STEP or where in flowdefaults.KEYS:
        d = dict(flowdefaults.STEP.get(where, {}))
        waits = where in findtarget.FIND_TYPES or where in findtarget.POINTER_TYPES
        if waits:
            d.update(flowdefaults.WAIT)
        return d.get(key, _MISSING)
    return _MISSING


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _ticks(cell):
    return re.findall(r"`([^`]*)`", cell)


def read_table(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and "適用" in line and "沒寫＝" in line:
            head = _cells(line)
            col_where, col_key = head.index("適用"), head.index("鍵")
            col_def = head.index("沒寫＝")
            rows = []
            for n, row in enumerate(lines[i + 2:], 1):
                if not row.startswith("|"):
                    break
                c = _cells(row)
                where = _ticks(c[col_where]) or [c[col_where]]
                key = (_ticks(c[col_key]) or [c[col_key]])[0]
                rows.append((n, where, key, c[col_def]))
            return rows
    raise AssertionError("docs/flow-format.md 找不到欄位表（表頭要有「適用」「鍵」「沒寫＝」）")


def _same(a, b):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return list(a) == list(b)
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return a == b


def problems(text):
    rows = read_table(text)
    want = expected_keys()
    seen = {w: set() for w in want}
    out = []
    for n, wheres, key, default in rows:
        lit = _ticks(default)
        for w in wheres:
            cell = f"欄位表第 {n} 列（適用 {w}、鍵 {key}）"
            if w not in want:
                out.append(f"{cell}：不認得的「適用」{w!r}")
                continue
            seen[w].add(key)
            if key not in want[w]:
                out.append(f"{cell}：app 讀檔不認得這個鍵（多出來的）")
                continue
            app = expected_default(w, key)
            if lit:
                doc = yaml.safe_load(lit[0])
                if app is _MISSING:
                    out.append(f"{cell}：沒寫＝寫了 `{lit[0]}`，但 app 沒有預設")
                elif not _same(doc, app):
                    out.append(f"{cell}：沒寫＝ `{lit[0]}` ≠ app 預設 {app!r}")
            elif app is not _MISSING:
                out.append(f"{cell}：沒寫＝沒寫預設值，但 app 預設是 {app!r}")
    for w, keys in want.items():
        for key in sorted(keys - seen[w]):
            out.append(f"欄位表少了（適用 {w}、鍵 {key}）：app 讀檔認得這個鍵")
    return out


def doc_text():
    with open(DOC, encoding="utf-8") as f:
        return f.read()


def test_格式規範的欄位表跟app一致():
    assert problems(doc_text()) == []


def _row(text, where, key):
    for line in text.splitlines():
        c = _cells(line) if line.startswith("|") else []
        if len(c) > 2 and where in c[0] and c[1] == f"`{key}`":
            return line
    raise AssertionError((where, key))


def test_改壞的副本_多一個鍵():
    text = doc_text()
    line = _row(text, "`drag`", "hold")
    bad = text.replace(line, line + "\n" + line.replace("`hold`", "`speed`"))
    [got] = problems(bad)
    assert "適用 drag、鍵 speed" in got and "多出來的" in got


def test_改壞的副本_少一個鍵():
    text = doc_text()
    bad = text.replace(_row(text, "`drag`", "hold") + "\n", "")
    assert problems(bad) == ["欄位表少了（適用 drag、鍵 hold）：app 讀檔認得這個鍵"]


def test_改壞的副本_預設值不同():
    text = doc_text()
    line = _row(text, "`find_click`、`find`、`wait_gone`、`click`、`drag`", "timeout")
    bad = text.replace(line, line.replace("| `5` |", "| `11` |"))
    got = problems(bad)
    assert len(got) == 5, got
    assert all("鍵 timeout" in p and "`11` ≠ app 預設 5" in p for p in got)


def test_改壞的副本_沒寫預設但app有():
    text = doc_text()
    line = _row(text, TOP, "run")
    bad = text.replace(line, line.replace("| `1` |", "| 一輪 |"))
    [got] = problems(bad)
    assert "適用 頂層、鍵 run" in got and "app 預設是 1" in got

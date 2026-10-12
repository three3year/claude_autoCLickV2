"""格式規範對照: docs/flow-format.md 的欄位表 ⇄ app 讀檔認得的鍵與「沒寫＝」表.

改了 flowfile / flowdefaults 卻沒同步規範 (或反過來) 就紅, 訊息指出是哪一格。
比三件事: 每個「適用」的鍵集合＝讀檔認得的鍵; 「沒寫＝」欄有反引號的值＝app 的預設;
沒有反引號的＝app 沒有預設。
"""
import os
import re

import harness  # noqa: F401  # 先把 app/ 加進 sys.path
import yaml

import flowfile
from automation import findtarget, flowdefaults

DOC = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "flow-format.md")
TOP = "頂層"
# yaml 的區段開頭鍵 → 記憶體裡帶 on_break 的結尾標記
_SECTION_END = {"repeat": "repeat_end", "branch": "branch_end"}


def expected_keys():
    """每個「適用」位置讀檔認得的鍵."""
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
    """app 對 (適用, 鍵) 的「沒寫＝」; 沒有預設回 _MISSING."""
    if where == TOP:
        return flowdefaults.FLOW.get(key, _MISSING)
    if where in _SECTION_END:
        return flowdefaults.STEP[_SECTION_END[where]].get(key, _MISSING)
    if where in flowdefaults.STEP or where in flowdefaults.KEYS:
        d = dict(flowdefaults.STEP.get(where, {}))
        waits = where in findtarget.FIND_TYPES or where in findtarget.POINTER_TYPES
        if waits:   # 座標點擊/拖曳要設了生效確認才有等待欄位, 預設值相同
            d.update(flowdefaults.WAIT)
        return d.get(key, _MISSING)
    return _MISSING


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _ticks(cell):
    return re.findall(r"`([^`]*)`", cell)


def read_table(text):
    """欄位表 → [(列號, 適用清單, 鍵, 沒寫＝原文)]; 找表頭「適用 | 鍵 | … | 沒寫＝」."""
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
    """欄位表跟 app 對不上的地方 (一則一行; 空＝一致)."""
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

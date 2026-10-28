"""檢查指令: 不載引擎、不開視窗, 檢查一個流程資料夾 app 讀不讀得進來、執行前會不會被擋.

    python tools/flow_check <流程資料夾> [--normalize]

輸出分兩類: **錯誤** (讀不進來或執行時一定被擋; 以 1 結束) 與**缺圖** (列成「要在 app 截的
範本」; 缺圖本身不算錯, 以 0 結束)。預設一個檔都不寫; `--normalize` 且沒有錯誤時, 經 app 的
`flowfile.dump_flow` 把 flow.yaml 重寫一次 (行尾步驟編號與排版回到標準; templates/ 不動)。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "app", _ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import flowfile  # noqa: E402
from automation import flowcheck  # noqa: E402


@dataclass
class Result:
    folder: str
    errors: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    unused: list = field(default_factory=list)
    flow: dict | None = None
    normalized: bool = False

    @property
    def ok(self):
        return not self.errors


def check(folder):
    """檢查流程資料夾 (只讀); 回傳 Result."""
    folder = os.path.abspath(str(folder))
    res = Result(folder)
    try:
        flow = flowfile.read_flow(folder)
    except flowfile.FlowError as e:
        res.errors.append(str(e))
        return res
    res.flow = flow
    res.errors += flowcheck.flow_errors(flow)
    res.missing = flowfile.missing_templates(folder, flow)
    refs = {n.casefold() for n in flowfile.template_refs(flow)}
    res.unused = [n for n in flowfile.folder_template_names(folder)
                  if n.casefold() not in refs]
    return res


def normalize(folder):
    """檢查; 沒有錯誤時經 app 的寫檔排版把 flow.yaml 重寫 (內容不變的話不寫)."""
    res = check(folder)
    if not res.ok:
        return res
    path = os.path.join(res.folder, flowfile.FLOW_YAML)
    text = flowfile.dump_flow(res.flow)
    with open(path, encoding="utf-8-sig") as f:
        old = f.read()
    if old != text:
        flowfile.replace_flow_yaml(res.folder, text)
        res.normalized = True
    return res


def report(res):
    """給人看的結果文字 (一行一則)."""
    lines = []
    if res.errors:
        lines.append(f"錯誤（{len(res.errors)}）：")
        lines += [f"  {e}" for e in res.errors]
    if res.missing:
        lines.append("要在 app 截的範本（引用了但 templates/ 裡沒有）：")
        lines += [f"  {n}" for n in res.missing]
    if res.unused:
        lines.append("templates/ 裡沒被引用的圖（app 下次存檔會移出 templates/）：")
        lines += [f"  {n}" for n in res.unused]
    if res.ok:
        n = len(res.flow["steps"]) if res.flow else 0
        lines.append(f"沒有錯誤（{n} 步）")
        if res.normalized:
            lines.append("已重寫 flow.yaml（步驟編號與排版）")
    return "\n".join(lines)


def main(argv=None):
    import argparse
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="flow_check",
                                 description="檢查流程資料夾（不載引擎、不開視窗）")
    ap.add_argument("folder", help="流程資料夾（有 flow.yaml 的那一層）")
    ap.add_argument("--normalize", action="store_true",
                    help="沒有錯誤時經 app 的寫檔把 flow.yaml 重寫成標準排版")
    args = ap.parse_args(argv)
    res = (normalize if args.normalize else check)(args.folder)
    print(report(res))
    return 0 if res.ok else 1

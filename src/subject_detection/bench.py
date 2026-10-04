"""Benchmark runner: replay every case in <profile>/benchmark/ and report
accuracy with miss / false-alarm breakdown.

**Every case carries its own template image**, so the benchmark needs no
template library of any kind — only the case folders themselves.

Case folder contract (adding a case = dropping files, no code change):

    benchmark/<case_name>/
        template.png     the template handed to the engine (this case's subject)
        screenshot.png   the search-region image handed to query()
        expect.yaml      expected: present | absent
                         center: [x, y]      (required when present)
                         centers: [[x, y], ...]  (present, repeated subject:
                                  every listed center matched, nothing else)
                         tolerance: 15       (px, optional)
                         color_check: true   (optional: query with the color
                                             check, ADR 0007)
                         template: <file>    (optional, defaults template.png)
                         screenshot: <file>  (optional, defaults screenshot.png)

Folders starting with "_" are assets, not cases; registration artifacts are
cached under benchmark/_registered/. A "miss" is a present-case reported
not-found; a wrong position or a hit on an absent-case are both "false_alarm"
(per CONTEXT.md both are equally unacceptable).

CLI: python -m subject_detection.bench <profile_dir> [-v]
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .engine import Engine
from .imio import imread
from .library import load_config

ARTIFACTS_DIRNAME = "_registered"


@dataclass
class Case:
    name: str
    dir: Path
    expect: dict

    @property
    def template_path(self) -> Path:
        return self.dir / self.expect.get("template", "template.png")

    @property
    def screenshot_path(self) -> Path:
        return self.dir / self.expect.get("screenshot", "screenshot.png")


@dataclass
class CaseResult:
    name: str
    expected: str            # 'present' | 'absent'
    verdict: str             # 'correct' | 'miss' | 'false_alarm'
    found: bool
    score: float
    box: tuple | None
    elapsed_ms: float
    debug: dict = field(default_factory=dict)


@dataclass
class BenchReport:
    cases: list[CaseResult]

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def correct(self) -> int:
        return sum(1 for c in self.cases if c.verdict == "correct")

    @property
    def misses(self) -> int:
        return sum(1 for c in self.cases if c.verdict == "miss")

    @property
    def false_alarms(self) -> int:
        return sum(1 for c in self.cases if c.verdict == "false_alarm")

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def bench_dir(profile_dir: str | Path) -> Path:
    return Path(profile_dir) / "benchmark"


def load_cases(profile_dir: str | Path) -> list[Case]:
    root = bench_dir(profile_dir)
    if not root.is_dir():
        return []
    cases = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        expect_path = child / "expect.yaml"
        if not expect_path.is_file():
            continue
        with open(expect_path, encoding="utf-8") as f:
            cases.append(Case(name=child.name, dir=child,
                              expect=yaml.safe_load(f)))
    return cases


def run_case(engine: Engine, library, case: Case) -> CaseResult:
    expect = case.expect
    expected = expect["expected"]
    tolerance = float(expect.get("tolerance", 15))
    scene = imread(case.screenshot_path)

    t0 = time.perf_counter()
    res = engine.query(library, case.name, scene,
                       color_check=bool(expect.get("color_check", False)))
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if expected == "present" and "centers" in expect:
        # 同款多張: 每個列出的中心都要被某個匹配命中, 且沒有沒列的匹配
        got = [(x + w / 2, y + h / 2) for x, y, w, h in
               (m.box for m in res.matches)]

        def hit(c, e):
            return abs(c[0] - e[0]) <= tolerance and abs(c[1] - e[1]) <= tolerance

        if not all(any(hit(c, e) for c in got) for e in expect["centers"]):
            verdict = "miss"
        elif not all(any(hit(c, e) for e in expect["centers"]) for c in got):
            verdict = "false_alarm"
        else:
            verdict = "correct"
    elif expected == "present":
        if not res.found:
            verdict = "miss"
        else:
            x, y, w, h = res.box
            cx, cy = x + w / 2, y + h / 2
            ex, ey = expect["center"]
            ok = abs(cx - ex) <= tolerance and abs(cy - ey) <= tolerance
            verdict = "correct" if ok else "false_alarm"
    elif expected == "absent":
        verdict = "false_alarm" if res.found else "correct"
    else:
        raise ValueError(f"{case.name}: expected must be present|absent, "
                         f"got {expected!r}")

    return CaseResult(name=case.name, expected=expected, verdict=verdict,
                      found=res.found, score=res.score, box=res.box,
                      elapsed_ms=elapsed_ms, debug=res.debug)


def run_bench(profile_dir: str | Path, engine: Engine | None = None) -> BenchReport:
    engine = engine or Engine()
    cases = load_cases(profile_dir)
    # 每個 case 自帶模板圖 → 範本清單就是「case 名 → 該 case 的模板圖」
    library = engine.load_templates(
        {c.name: c.template_path for c in cases},
        config=load_config(profile_dir),
        artifacts_dir=bench_dir(profile_dir) / ARTIFACTS_DIRNAME)
    return BenchReport(cases=[run_case(engine, library, c) for c in cases])


def format_report(report: BenchReport, verbose: bool = False) -> str:
    lines = []
    for c in sorted(report.cases, key=lambda c: (c.verdict == "correct", c.name)):
        mark = {"correct": "PASS", "miss": "MISS", "false_alarm": "FALSE"}[c.verdict]
        lines.append(f"  [{mark:5}] {c.name:48} "
                     f"score={c.score:.3f} {c.elapsed_ms:6.1f}ms")
        if verbose and c.debug:
            lines.append(f"          debug: {c.debug}")
    lines.append("")
    lines.append(f"cases: {report.total}  correct: {report.correct}/{report.total} "
                 f"({report.accuracy * 100:.1f}%)  "
                 f"misses: {report.misses}  false_alarms: {report.false_alarms}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("profile_dir")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    report = run_bench(args.profile_dir)
    print(format_report(report, verbose=args.verbose))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

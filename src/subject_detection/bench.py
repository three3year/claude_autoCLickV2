"""Benchmark runner: replay every case in <profile>/benchmark/ and report
accuracy with miss / false-alarm breakdown.

Case folder contract (adding a case = dropping files, no code change):

    benchmark/<case_name>/
        screenshot.png   the search-region image handed to query()
        expect.yaml      template: <name>
                         expected: present | absent
                         center: [x, y]      (required when present)
                         tolerance: 15       (px, optional)

Folders starting with "_" are assets, not cases. A "miss" is a present-case
reported not-found; a wrong position or a hit on an absent-case are both
"false_alarm" (per CONTEXT.md both are equally unacceptable).

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


@dataclass
class CaseResult:
    name: str
    template: str
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


def iter_case_dirs(profile_dir: Path):
    bench_dir = Path(profile_dir) / "benchmark"
    if not bench_dir.is_dir():
        return
    for child in sorted(bench_dir.iterdir()):
        if child.is_dir() and not child.name.startswith("_") \
                and (child / "expect.yaml").is_file():
            yield child


def run_case(engine: Engine, profile, case_dir: Path) -> CaseResult:
    with open(case_dir / "expect.yaml", encoding="utf-8") as f:
        expect = yaml.safe_load(f)
    template = expect["template"]
    expected = expect["expected"]
    tolerance = float(expect.get("tolerance", 15))
    screenshot = expect.get("screenshot", "screenshot.png")
    scene = imread(case_dir / screenshot)

    t0 = time.perf_counter()
    res = engine.query(profile, template, scene)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if expected == "present":
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
        raise ValueError(f"{case_dir.name}: expected must be present|absent, "
                         f"got {expected!r}")

    return CaseResult(name=case_dir.name, template=template, expected=expected,
                      verdict=verdict, found=res.found, score=res.score,
                      box=res.box, elapsed_ms=elapsed_ms, debug=res.debug)


def run_bench(profile_dir: str | Path, engine: Engine | None = None) -> BenchReport:
    engine = engine or Engine()
    profile = engine.load_profile(profile_dir)
    cases = [run_case(engine, profile, d) for d in iter_case_dirs(Path(profile_dir))]
    return BenchReport(cases=cases)


def format_report(report: BenchReport, verbose: bool = False) -> str:
    lines = []
    for c in sorted(report.cases, key=lambda c: (c.verdict == "correct", c.name)):
        mark = {"correct": "PASS", "miss": "MISS", "false_alarm": "FALSE"}[c.verdict]
        lines.append(f"  [{mark:5}] {c.name:40} {c.template:24} "
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

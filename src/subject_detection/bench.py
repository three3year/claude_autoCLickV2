"""Benchmark runner: replay every case in a benchmark folder and report
accuracy with miss / false-alarm breakdown, known failures listed apart.

**Every case carries its own template image**, so the benchmark needs no
template library of any kind — only the case folders themselves. The engine
runs on its **built-in defaults only**: no config file anywhere is read, so
the numbers are what the app ships with.

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
                         expected_scale: 1.15  (optional, default 1.0: the
                                  expected scale handed to the query, as the
                                  app does; centers are in the scaled image)
                         known_failure: <why>  (optional: a known engine
                                  weakness — reported apart, never fails
                                  the run)
                         source: {...}       (optional, for people, never
                                  read: flow, template, video, frame, kind,
                                  client, answer_from, template_video, …)
                         template: <file>    (optional, defaults template.png)
                         screenshot: <file>  (optional, defaults screenshot.png)

Folders starting with "_" are assets, not cases; registration artifacts are
cached under <benchmark>/_registered/. A "miss" is a present-case reported
not-found; a wrong position or a hit on an absent-case are both "false_alarm"
(per CONTEXT.md both are equally unacceptable).

CLI: python -m subject_detection.bench [benchmark_dir] [-v]
     (default: the repo's benchmark/; exit status 1 when any case that is not
     a known failure fails)
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .engine import Engine
from .imio import imread
from .library import load_default_config

ARTIFACTS_DIRNAME = "_registered"
DEFAULT_BENCH_DIR = Path(__file__).resolve().parents[2] / "benchmark"


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

    @property
    def expected_scale(self) -> float:
        return float(self.expect.get("expected_scale", 1.0))

    @property
    def color_check(self) -> bool:
        return bool(self.expect.get("color_check", False))

    @property
    def known_failure(self) -> str | None:
        """The reason text; a `known_failure:` key left empty still marks one."""
        if "known_failure" not in self.expect:
            return None
        return str(self.expect["known_failure"] or "(沒寫原因)")


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
    known_failure: str | None = None   # why it is a known engine weakness

    @property
    def is_known_failure(self) -> bool:
        return self.known_failure is not None


def _count(cases: list[CaseResult], verdict: str) -> int:
    return sum(1 for c in cases if c.verdict == verdict)


@dataclass
class BenchReport:
    cases: list[CaseResult]

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def correct(self) -> int:
        return _count(self.cases, "correct")

    @property
    def misses(self) -> int:
        return _count(self.cases, "miss")

    @property
    def false_alarms(self) -> int:
        return _count(self.cases, "false_alarm")

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def regular(self) -> list[CaseResult]:
        """Cases that are not known failures (the ones that decide `ok`)."""
        return [c for c in self.cases if not c.is_known_failure]

    @property
    def known_failures(self) -> list[CaseResult]:
        return [c for c in self.cases if c.is_known_failure]

    @property
    def ok(self) -> bool:
        """Every case that is not a known failure is correct."""
        return all(c.verdict == "correct" for c in self.regular)


def load_cases(bench_dir: str | Path) -> list[Case]:
    root = Path(bench_dir)
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
                       color_check=case.color_check,
                       expected_scale=case.expected_scale)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if expected == "present" and "centers" in expect:
        # 同款多張: 每個列出的中心都要有匹配對上, 且沒有沒列的匹配
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
                      elapsed_ms=elapsed_ms, debug=res.debug,
                      known_failure=case.known_failure)


def run_bench(bench_dir: str | Path | None = None,
              engine: Engine | None = None) -> BenchReport:
    bench_dir = Path(bench_dir) if bench_dir is not None else DEFAULT_BENCH_DIR
    engine = engine or Engine()
    cases = load_cases(bench_dir)
    # 每個 case 自帶模板圖 → 範本清單就是「case 名 → 該 case 的模板圖」;
    # 引擎參數只用內建預設 (量的是 app 出廠的行為)
    library = engine.load_templates(
        {c.name: c.template_path for c in cases},
        config=load_default_config(),
        artifacts_dir=bench_dir / ARTIFACTS_DIRNAME)
    return BenchReport(cases=[run_case(engine, library, c) for c in cases])


_MARKS = {"correct": "PASS", "miss": "MISS", "false_alarm": "FALSE"}


def _case_line(c: CaseResult) -> str:
    return (f"  [{_MARKS[c.verdict]:5}] {c.name:48} "
            f"score={c.score:.3f} {c.elapsed_ms:6.1f}ms")


def _counts(cases: list[CaseResult]) -> str:
    return (f"{_count(cases, 'correct')}/{len(cases)}  "
            f"misses: {_count(cases, 'miss')}  "
            f"false_alarms: {_count(cases, 'false_alarm')}")


def format_report(report: BenchReport, verbose: bool = False) -> str:
    lines = []

    def add(c: CaseResult, note: str = "") -> None:
        lines.append(_case_line(c) + note)
        if verbose and c.debug:
            lines.append(f"          debug: {c.debug}")

    for c in sorted(report.regular,
                    key=lambda c: (c.verdict == "correct", c.name)):
        add(c)
    known = report.known_failures
    if known:
        lines.append("")
        lines.append("已知失敗:")
        for c in sorted(known, key=lambda c: c.name):
            add(c, "  <- 這次通過, 可拿掉標記" if c.verdict == "correct"
                else f"  ({c.known_failure})")
    lines.append("")
    lines.append(f"其他案例 {_counts(report.regular)}  |  "
                 f"已知失敗 {_counts(known)}  |  "
                 f"{'OK' if report.ok else 'FAIL'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bench_dir", nargs="?", default=None,
                        help="benchmark folder (default: the repo's benchmark/)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    bench_dir = Path(args.bench_dir) if args.bench_dir else DEFAULT_BENCH_DIR
    report = run_bench(bench_dir)
    # 輸出被導向 (管線、檔案) 時預設是系統代碼頁 (cp950), 編不出簡中案例名
    if not sys.stdout.isatty() and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not report.cases:
        # 空集合不能算「沒退步」: 多半是路徑打錯
        print(f"沒有案例: {bench_dir}")
        return 1
    print(format_report(report, verbose=args.verbose))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

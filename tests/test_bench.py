"""Ticket 02 — bench tool: given a known case set, the numbers are right.

Case contract: every case carries its own `template.png`, so the bench needs
no template library at all (ADR 0006) — these tests write nothing but case
folders. benchmark-rebuild 01: the bench is handed the benchmark folder
itself (default: the repo's `benchmark/`), queries with the case's expected
scale, uses the engine's built-in defaults only, and reports known failures
apart from the rest.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import yaml

from synth import imwrite, make_scene, make_template, paste

from subject_detection import bench
from subject_detection.bench import format_report, load_cases, run_bench
from subject_detection.library import load_default_config

REPO = Path(__file__).resolve().parent.parent


def _write_case(bench_dir, name, scene, template, expected,
                center=None, tolerance=15, **extra):
    case_dir = bench_dir / name
    imwrite(case_dir / "screenshot.png", scene)
    imwrite(case_dir / "template.png", template)
    expect = {"expected": expected}
    if center is not None:
        expect["center"] = [int(center[0]), int(center[1])]
    expect["tolerance"] = tolerance
    expect.update(extra)
    (case_dir / "expect.yaml").write_text(
        yaml.safe_dump(expect, allow_unicode=True), encoding="utf-8")


def test_bench_counts_correct_miss_and_false_alarm(tmp_path):
    tpl = make_template(seed=11)
    th, tw = tpl.shape[:2]
    bench_dir = tmp_path / "benchmark"

    # correct: subject pasted where expected
    scene1 = paste(make_scene(seed=60), tpl, 200, 100)
    _write_case(bench_dir, "case_correct", scene1, tpl, "present",
                center=(200 + tw / 2, 100 + th / 2))
    # miss: expected present but subject not in scene
    scene2 = make_scene(seed=61)
    _write_case(bench_dir, "case_miss", scene2, tpl, "present",
                center=(320, 180))
    # correct absent: clean negative
    scene3 = make_scene(seed=62)
    _write_case(bench_dir, "case_absent_ok", scene3, tpl, "absent")
    # false alarm: declared absent but the subject actually sits in the scene
    scene4 = paste(make_scene(seed=63), tpl, 50, 50)
    _write_case(bench_dir, "case_false_alarm", scene4, tpl, "absent")
    # false alarm (wrong position): present far from the expected center
    scene5 = paste(make_scene(seed=64), tpl, 400, 250)
    _write_case(bench_dir, "case_wrong_pos", scene5, tpl, "present",
                center=(50, 50))

    report = run_bench(bench_dir)

    assert report.total == 5
    assert report.correct == 2
    assert report.misses == 1
    assert report.false_alarms == 2
    assert abs(report.accuracy - 2 / 5) < 1e-9

    by_name = {c.name: c for c in report.cases}
    assert by_name["case_correct"].verdict == "correct"
    assert by_name["case_miss"].verdict == "miss"
    assert by_name["case_absent_ok"].verdict == "correct"
    assert by_name["case_false_alarm"].verdict == "false_alarm"
    assert by_name["case_wrong_pos"].verdict == "false_alarm"


def test_bench_report_formatting_lists_every_case(tmp_path):
    tpl = make_template(seed=12)
    bench_dir = tmp_path / "benchmark"
    scene = paste(make_scene(seed=65), tpl, 10, 10)
    _write_case(bench_dir, "only_case", scene, tpl, "present",
                center=(10 + tpl.shape[1] / 2, 10 + tpl.shape[0] / 2))

    report = run_bench(bench_dir)
    text = format_report(report, verbose=True)

    assert "only_case" in text
    assert "1/1" in text or "100.0%" in text


def test_bench_empty_benchmark_dir_reports_zero_cases(tmp_path):
    report = run_bench(tmp_path / "benchmark")
    assert report.total == 0


def test_underscore_folders_are_assets_not_cases(tmp_path):
    """登錄產物與素材都住在 _ 開頭的資料夾裡, 不能被當成 case."""
    tpl = make_template(seed=13)
    bench_dir = tmp_path / "benchmark"
    _write_case(bench_dir, "real_case", paste(make_scene(seed=66), tpl, 5, 5),
                tpl, "present", center=(5 + tpl.shape[1] / 2,
                                        5 + tpl.shape[0] / 2))
    _write_case(bench_dir, "_registered", make_scene(seed=67), tpl, "absent")
    assert [c.name for c in load_cases(bench_dir)] == ["real_case"]


def test_case_may_name_its_own_template_and_screenshot_files(tmp_path):
    """檔名可自訂 (預設 template.png / screenshot.png), 加 case 仍是丟檔案."""
    tpl = make_template(seed=14)
    case = tmp_path / "benchmark" / "custom"
    imwrite(case / "shot.png", paste(make_scene(seed=68), tpl, 30, 40))
    imwrite(case / "subject.png", tpl)
    (case / "expect.yaml").write_text(yaml.safe_dump(
        {"expected": "present", "tolerance": 15,
         "center": [int(30 + tpl.shape[1] / 2), int(40 + tpl.shape[0] / 2)],
         "template": "subject.png", "screenshot": "shot.png"}),
        encoding="utf-8")

    report = run_bench(tmp_path / "benchmark")
    assert [c.verdict for c in report.cases] == ["correct"]


def test_centers列出每個同款_全部匹配到且沒有多的才算對(tmp_path):
    """同款多張的 case: expect 的 centers 列出每一個, 查詢要剛好回報這些匹配."""
    tpl = make_template(seed=15)
    th, tw = tpl.shape[:2]
    bench_dir = tmp_path / "benchmark"
    scene = make_scene(w=800, h=360, seed=69)
    for x in (60, 360, 660):
        scene = paste(scene, tpl, x, 150)
    all3 = [[x + tw // 2, 150 + th // 2] for x in (60, 360, 660)]

    for name, centers in (("all", all3), ("too_few", all3[:2]),
                          ("wrong", all3[:2] + [[400, 40]])):
        case_dir = bench_dir / name
        imwrite(case_dir / "screenshot.png", scene)
        imwrite(case_dir / "template.png", tpl)
        (case_dir / "expect.yaml").write_text(yaml.safe_dump(
            {"expected": "present", "tolerance": 15, "centers": centers}),
            encoding="utf-8")

    by_name = {c.name: c for c in run_bench(bench_dir).cases}
    assert by_name["all"].verdict == "correct"
    assert by_name["too_few"].verdict == "false_alarm", "多出沒列的匹配"
    assert by_name["wrong"].verdict == "miss", "列了卻沒匹配到"


class _SpyEngine:
    """Records what the bench hands the engine; queries go to the real one."""

    def __init__(self, engine):
        self._engine = engine
        self.scales: dict[str, float | None] = {}
        self.configs: list[dict] = []

    def load_templates(self, templates, config=None, artifacts_dir=None):
        self.configs.append(dict(config))
        return self._engine.load_templates(templates, config=config,
                                           artifacts_dir=artifacts_dir)

    def query(self, library, name, scene, color_check=False,
              expected_scale=None):
        self.scales[name] = expected_scale
        return self._engine.query(library, name, scene,
                                  color_check=color_check,
                                  expected_scale=expected_scale)


def _present_case(bench_dir, name, seed, **extra):
    tpl = make_template(seed=seed)
    scene = paste(make_scene(seed=seed + 50), tpl, 120, 90)
    _write_case(bench_dir, name, scene, tpl, "present",
                center=(120 + tpl.shape[1] / 2, 90 + tpl.shape[0] / 2),
                **extra)


def _missed_case(bench_dir, name, seed, **extra):
    """expected present, but the subject is not in the scene → miss."""
    tpl = make_template(seed=seed)
    _write_case(bench_dir, name, make_scene(seed=seed + 50), tpl, "present",
                center=(320, 180), **extra)


def _resize(img, scale):
    h, w = img.shape[:2]
    return cv2.resize(img, (round(w * scale), round(h * scale)),
                      interpolation=cv2.INTER_AREA)


def test_預期尺度_案例寫了就傳它_沒寫傳1(engine, tmp_path):
    bench_dir = tmp_path / "benchmark"
    tpl = make_template(w=56, h=40, seed=21)
    big = _resize(tpl, 1.15)
    scene = paste(make_scene(seed=71), big, 200, 120)
    _write_case(bench_dir, "scaled", scene, tpl, "present",
                center=(200 + big.shape[1] / 2, 120 + big.shape[0] / 2),
                expected_scale=1.15)
    _present_case(bench_dir, "plain", seed=22)

    spy = _SpyEngine(engine)
    report = run_bench(bench_dir, engine=spy)

    assert spy.scales == {"scaled": 1.15, "plain": 1.0}
    assert [c.verdict for c in report.cases] == ["correct", "correct"]


def test_資料夾裡的設定檔不讀_只用引擎內建預設(engine, tmp_path):
    bench_dir = tmp_path / "benchmark"
    _present_case(bench_dir, "case", seed=23)
    # 讀了它的話門檻高到什麼都找不到
    (bench_dir / "config.yaml").write_text(yaml.safe_dump(
        {"match_threshold": 0.999, "verify_threshold": 0.999}),
        encoding="utf-8")
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(
        {"match_threshold": 0.999}), encoding="utf-8")

    spy = _SpyEngine(engine)
    report = run_bench(bench_dir, engine=spy)

    assert spy.configs == [load_default_config()]
    assert [c.verdict for c in report.cases] == ["correct"]


def test_已知失敗沒過_不算其他案例的失敗_列在已知失敗區(engine, tmp_path):
    bench_dir = tmp_path / "benchmark"
    _present_case(bench_dir, "good", seed=24)
    _missed_case(bench_dir, "weak", seed=25, known_failure="引擎弱點: 測試用")

    report = run_bench(bench_dir, engine=engine)

    assert report.ok
    assert [c.name for c in report.regular] == ["good"]
    assert [c.name for c in report.known_failures] == ["weak"]
    weak = report.known_failures[0]
    assert weak.verdict == "miss" and weak.known_failure == "引擎弱點: 測試用"
    text = format_report(report)
    known_part = text.split("已知失敗")[1]
    assert "weak" in known_part and "引擎弱點: 測試用" in known_part
    assert "可拿掉標記" not in text
    assert bench.main([str(bench_dir)]) == 0


def test_已知失敗沒寫原因也算已知失敗(engine, tmp_path):
    """`known_failure:` 後面空著 (YAML 讀成 None) 仍是已知失敗, 不算其他案例的失敗."""
    bench_dir = tmp_path / "benchmark"
    _missed_case(bench_dir, "weak", seed=35, known_failure=None)

    report = run_bench(bench_dir, engine=engine)

    assert report.ok
    assert [c.name for c in report.known_failures] == ["weak"]
    assert report.regular == []


def test_已知失敗通過_報表標示可拿掉標記(engine, tmp_path):
    bench_dir = tmp_path / "benchmark"
    _present_case(bench_dir, "now_fixed", seed=26, known_failure="以前會漏")

    report = run_bench(bench_dir, engine=engine)

    assert report.ok
    assert report.known_failures[0].verdict == "correct"
    line = next(l for l in format_report(report).splitlines()
                if "now_fixed" in l)
    assert "可拿掉標記" in line


def test_總結行分開算其他案例與已知失敗(engine, tmp_path):
    bench_dir = tmp_path / "benchmark"
    _present_case(bench_dir, "a_good", seed=27)
    _missed_case(bench_dir, "b_bad", seed=28)
    _missed_case(bench_dir, "c_known", seed=29, known_failure="弱點")

    report = run_bench(bench_dir, engine=engine)
    summary = format_report(report).splitlines()[-1]

    assert "其他案例 1/2" in summary
    assert "已知失敗 0/1" in summary


def test_非已知失敗的案例沒過_結束碼失敗(tmp_path):
    bench_dir = tmp_path / "benchmark"
    _present_case(bench_dir, "good", seed=30)
    _missed_case(bench_dir, "bad", seed=31)

    assert bench.main([str(bench_dir)]) == 1


def test_全部命中_結束碼成功(tmp_path):
    bench_dir = tmp_path / "benchmark"
    _present_case(bench_dir, "good", seed=32)

    assert bench.main([str(bench_dir)]) == 0


def test_來源欄位讀得進來_不影響判定(engine, tmp_path):
    bench_dir = tmp_path / "benchmark"
    source = {"flow": "早_簡中", "template": "基建BASE", "video": "demo5.mp4",
              "frame": 1234, "kind": "一般正例"}
    _present_case(bench_dir, "with_source", seed=33, source=source)

    (case,) = load_cases(bench_dir)
    assert case.expect["source"] == source
    report = run_bench(bench_dir, engine=engine)
    assert [c.verdict for c in report.cases] == ["correct"]


def test_不帶參數就跑repo的benchmark資料夾(monkeypatch, tmp_path):
    assert bench.DEFAULT_BENCH_DIR == REPO / "benchmark"
    # 預設資料夾換成一個只有沒過案例的: 不帶參數跑的就是它
    default = tmp_path / "benchmark"
    _missed_case(default, "bad", seed=36)
    monkeypatch.setattr(bench, "DEFAULT_BENCH_DIR", default)

    assert [c.name for c in run_bench().cases] == ["bad"]
    assert bench.main([]) == 1


def test_登錄快取在底線資料夾且不進版控(engine, tmp_path):
    bench_dir = tmp_path / "benchmark"
    _present_case(bench_dir, "case", seed=34)
    run_bench(bench_dir, engine=engine)

    cache_dirs = [p.name for p in bench_dir.iterdir()
                  if p.is_dir() and p.name != "case"]
    assert cache_dirs and all(n.startswith("_") for n in cache_dirs)
    ignore = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/benchmark/_*/" in ignore

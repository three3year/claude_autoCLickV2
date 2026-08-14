"""Ticket 02 — bench tool: given a known case set, the numbers are right."""
from __future__ import annotations

import yaml

from conftest import imwrite, make_scene, make_template, paste, write_profile

from subject_detection.bench import format_report, run_bench


def _write_case(profile_dir, name, scene, template, expected,
                center=None, tolerance=15):
    case_dir = profile_dir / "benchmark" / name
    imwrite(case_dir / "screenshot.png", scene)
    expect = {"template": template, "expected": expected}
    if center is not None:
        expect["center"] = [int(center[0]), int(center[1])]
    expect["tolerance"] = tolerance
    (case_dir / "expect.yaml").write_text(
        yaml.safe_dump(expect, allow_unicode=True), encoding="utf-8")


def test_bench_counts_correct_miss_and_false_alarm(tmp_path):
    tpl = make_template(seed=11)
    th, tw = tpl.shape[:2]
    profile_dir = write_profile(tmp_path, {"btn": tpl})

    # correct: subject pasted where expected
    scene1 = paste(make_scene(seed=60), tpl, 200, 100)
    _write_case(profile_dir, "case_correct", scene1, "btn", "present",
                center=(200 + tw / 2, 100 + th / 2))
    # miss: expected present but subject not in scene
    scene2 = make_scene(seed=61)
    _write_case(profile_dir, "case_miss", scene2, "btn", "present",
                center=(320, 180))
    # correct absent: clean negative
    scene3 = make_scene(seed=62)
    _write_case(profile_dir, "case_absent_ok", scene3, "btn", "absent")
    # false alarm: declared absent but the subject actually sits in the scene
    scene4 = paste(make_scene(seed=63), tpl, 50, 50)
    _write_case(profile_dir, "case_false_alarm", scene4, "btn", "absent")
    # false alarm (wrong position): present far from the expected center
    scene5 = paste(make_scene(seed=64), tpl, 400, 250)
    _write_case(profile_dir, "case_wrong_pos", scene5, "btn", "present",
                center=(50, 50))

    report = run_bench(profile_dir)

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
    profile_dir = write_profile(tmp_path, {"btn": tpl})
    scene = paste(make_scene(seed=65), tpl, 10, 10)
    _write_case(profile_dir, "only_case", scene, "btn", "present",
                center=(10 + tpl.shape[1] / 2, 10 + tpl.shape[0] / 2))

    report = run_bench(profile_dir)
    text = format_report(report, verbose=True)

    assert "only_case" in text
    assert "1/1" in text or "100.0%" in text


def test_bench_empty_benchmark_dir_reports_zero_cases(tmp_path):
    profile_dir = write_profile(tmp_path, {"btn": make_template(seed=13)})
    report = run_bench(profile_dir)
    assert report.total == 0

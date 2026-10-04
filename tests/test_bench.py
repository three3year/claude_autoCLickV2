"""Ticket 02 — bench tool: given a known case set, the numbers are right.

Case contract: every case carries its own `template.png`, so the bench needs
no template library at all (ADR 0006) — these tests write nothing but case
folders.
"""
from __future__ import annotations

import yaml

from synth import imwrite, make_scene, make_template, paste

from subject_detection.bench import format_report, load_cases, run_bench


def _write_case(profile_dir, name, scene, template, expected,
                center=None, tolerance=15):
    case_dir = profile_dir / "benchmark" / name
    imwrite(case_dir / "screenshot.png", scene)
    imwrite(case_dir / "template.png", template)
    expect = {"expected": expected}
    if center is not None:
        expect["center"] = [int(center[0]), int(center[1])]
    expect["tolerance"] = tolerance
    (case_dir / "expect.yaml").write_text(
        yaml.safe_dump(expect, allow_unicode=True), encoding="utf-8")


def test_bench_counts_correct_miss_and_false_alarm(tmp_path):
    tpl = make_template(seed=11)
    th, tw = tpl.shape[:2]
    profile_dir = tmp_path / "profile"

    # correct: subject pasted where expected
    scene1 = paste(make_scene(seed=60), tpl, 200, 100)
    _write_case(profile_dir, "case_correct", scene1, tpl, "present",
                center=(200 + tw / 2, 100 + th / 2))
    # miss: expected present but subject not in scene
    scene2 = make_scene(seed=61)
    _write_case(profile_dir, "case_miss", scene2, tpl, "present",
                center=(320, 180))
    # correct absent: clean negative
    scene3 = make_scene(seed=62)
    _write_case(profile_dir, "case_absent_ok", scene3, tpl, "absent")
    # false alarm: declared absent but the subject actually sits in the scene
    scene4 = paste(make_scene(seed=63), tpl, 50, 50)
    _write_case(profile_dir, "case_false_alarm", scene4, tpl, "absent")
    # false alarm (wrong position): present far from the expected center
    scene5 = paste(make_scene(seed=64), tpl, 400, 250)
    _write_case(profile_dir, "case_wrong_pos", scene5, tpl, "present",
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
    profile_dir = tmp_path / "profile"
    scene = paste(make_scene(seed=65), tpl, 10, 10)
    _write_case(profile_dir, "only_case", scene, tpl, "present",
                center=(10 + tpl.shape[1] / 2, 10 + tpl.shape[0] / 2))

    report = run_bench(profile_dir)
    text = format_report(report, verbose=True)

    assert "only_case" in text
    assert "1/1" in text or "100.0%" in text


def test_bench_empty_benchmark_dir_reports_zero_cases(tmp_path):
    report = run_bench(tmp_path / "profile")
    assert report.total == 0


def test_underscore_folders_are_assets_not_cases(tmp_path):
    """登錄產物與素材都住在 _ 開頭的資料夾裡, 不能被當成 case."""
    tpl = make_template(seed=13)
    profile_dir = tmp_path / "profile"
    _write_case(profile_dir, "real_case", paste(make_scene(seed=66), tpl, 5, 5),
                tpl, "present", center=(5 + tpl.shape[1] / 2,
                                        5 + tpl.shape[0] / 2))
    _write_case(profile_dir, "_registered", make_scene(seed=67), tpl, "absent")
    assert [c.name for c in load_cases(profile_dir)] == ["real_case"]


def test_case_may_name_its_own_template_and_screenshot_files(tmp_path):
    """檔名可自訂 (預設 template.png / screenshot.png), 加 case 仍是丟檔案."""
    tpl = make_template(seed=14)
    case = tmp_path / "profile" / "benchmark" / "custom"
    imwrite(case / "shot.png", paste(make_scene(seed=68), tpl, 30, 40))
    imwrite(case / "subject.png", tpl)
    (case / "expect.yaml").write_text(yaml.safe_dump(
        {"expected": "present", "tolerance": 15,
         "center": [int(30 + tpl.shape[1] / 2), int(40 + tpl.shape[0] / 2)],
         "template": "subject.png", "screenshot": "shot.png"}),
        encoding="utf-8")

    report = run_bench(tmp_path / "profile")
    assert [c.verdict for c in report.cases] == ["correct"]


def test_centers列出每個同款_全部匹配到且沒有多的才算對(tmp_path):
    """同款多張的 case: expect 的 centers 列出每一個, 查詢要剛好回報這些匹配."""
    tpl = make_template(seed=15)
    th, tw = tpl.shape[:2]
    profile_dir = tmp_path / "profile"
    scene = make_scene(w=800, h=360, seed=69)
    for x in (60, 360, 660):
        scene = paste(scene, tpl, x, 150)
    all3 = [[x + tw // 2, 150 + th // 2] for x in (60, 360, 660)]

    for name, centers in (("all", all3), ("too_few", all3[:2]),
                          ("wrong", all3[:2] + [[400, 40]])):
        case_dir = profile_dir / "benchmark" / name
        imwrite(case_dir / "screenshot.png", scene)
        imwrite(case_dir / "template.png", tpl)
        (case_dir / "expect.yaml").write_text(yaml.safe_dump(
            {"expected": "present", "tolerance": 15, "centers": centers}),
            encoding="utf-8")

    by_name = {c.name: c for c in run_bench(profile_dir).cases}
    assert by_name["all"].verdict == "correct"
    assert by_name["too_few"].verdict == "false_alarm", "多出沒列的匹配"
    assert by_name["wrong"].verdict == "miss", "列了卻沒匹配到"

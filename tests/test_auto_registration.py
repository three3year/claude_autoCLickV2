"""Ticket 05 — auto-registration: drop a file, reload, query. No manual steps.

All tests operate the profile folder and config like a user would, then
assert query behavior and whether registration artifacts were (re)built.
"""
from __future__ import annotations

import yaml

from conftest import imwrite, make_scene, make_template, paste, write_profile


def _mtimes(reg_dir):
    return {p.name: p.stat().st_mtime_ns for p in sorted(reg_dir.iterdir())}


def _set_config(profile_dir, **overrides):
    cfg_path = profile_dir / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg.update(overrides)
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")


def test_new_template_dropped_into_folder_is_usable(engine, tmp_path):
    profile_dir = write_profile(tmp_path, {"old": make_template(seed=41)})
    engine.load_profile(profile_dir)

    new_tpl = make_template(seed=42)
    imwrite(profile_dir / "templates" / "new.png", new_tpl)  # just drop a file

    profile = engine.load_profile(profile_dir)
    scene = paste(make_scene(seed=90), new_tpl, 220, 140)
    res = engine.query(profile, "new", scene)
    assert res.found is True


def test_changed_template_content_reregisters_only_that_template(engine, tmp_path):
    tpl_a, tpl_b = make_template(seed=43), make_template(seed=44)
    profile_dir = write_profile(tmp_path, {"a": tpl_a, "b": tpl_b})
    engine.load_profile(profile_dir)

    reg_a = profile_dir / "registered" / "a"
    reg_b = profile_dir / "registered" / "b"
    before_a, before_b = _mtimes(reg_a), _mtimes(reg_b)

    replacement = make_template(seed=45)  # same filename, new content
    imwrite(profile_dir / "templates" / "b.png", replacement)
    profile = engine.load_profile(profile_dir)

    assert _mtimes(reg_a) == before_a          # untouched
    assert _mtimes(reg_b) != before_b          # rebuilt
    scene = paste(make_scene(seed=91), replacement, 100, 100)
    assert engine.query(profile, "b", scene).found is True


def test_registration_config_change_triggers_rebuild(engine, tmp_path):
    profile_dir = write_profile(tmp_path, {"a": make_template(seed=46)})
    engine.load_profile(profile_dir)
    reg = profile_dir / "registered" / "a"
    before = _mtimes(reg)

    _set_config(profile_dir, scale_range=[0.8, 1.2])
    engine.load_profile(profile_dir)
    after = _mtimes(reg)
    assert after != before

    _set_config(profile_dir, scale_range=[0.8, 1.2], mask_strategy="single")
    engine.load_profile(profile_dir)
    assert _mtimes(reg) != after


def test_threshold_change_applies_immediately_without_rebuild(engine, tmp_path):
    tpl = make_template(seed=47)
    scene = paste(make_scene(seed=92), tpl, 200, 120)
    profile_dir = write_profile(tmp_path, {"a": tpl})

    profile = engine.load_profile(profile_dir)
    assert engine.query(profile, "a", scene).found is True
    reg = profile_dir / "registered" / "a"
    before = _mtimes(reg)

    _set_config(profile_dir, match_threshold=1.01)
    profile = engine.load_profile(profile_dir)
    assert _mtimes(reg) == before              # thresholds never re-register
    assert engine.query(profile, "a", scene).found is False  # yet take effect


def test_corrupt_artifacts_are_rebuilt_not_fatal(engine, tmp_path):
    tpl = make_template(seed=48)
    scene = paste(make_scene(seed=93), tpl, 150, 150)
    profile_dir = write_profile(tmp_path, {"a": tpl})
    engine.load_profile(profile_dir)
    reg = profile_dir / "registered" / "a"

    (reg / "mask.png").write_bytes(b"this is not a png")
    profile = engine.load_profile(profile_dir)
    assert engine.query(profile, "a", scene).found is True

    (reg / "meta.json").unlink()
    profile = engine.load_profile(profile_dir)
    assert engine.query(profile, "a", scene).found is True

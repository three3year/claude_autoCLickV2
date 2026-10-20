"""Ticket 05 — auto-registration: drop a file, reload, query. No manual steps.

All tests operate the template folder and its config.yaml like a user would, then
assert query behavior and whether registration artifacts were (re)built.
"""
from __future__ import annotations

import hashlib
import json

import yaml

from synth import (imwrite, load_library, make_scene, make_template, paste,
                   write_profile)


def _mtimes(reg_dir):
    return {p.name: p.stat().st_mtime_ns for p in sorted(reg_dir.iterdir())}


def _set_config(profile_dir, **overrides):
    cfg_path = profile_dir / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg.update(overrides)
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")


def test_new_template_dropped_into_folder_is_usable(engine, tmp_path):
    profile_dir = write_profile(tmp_path, {"old": make_template(seed=41)})
    load_library(engine, profile_dir)

    new_tpl = make_template(seed=42)
    imwrite(profile_dir / "templates" / "new.png", new_tpl)  # just drop a file

    profile = load_library(engine, profile_dir)
    scene = paste(make_scene(seed=90), new_tpl, 220, 140)
    res = engine.query(profile, "new", scene)
    assert res.found is True


def test_changed_template_content_reregisters_only_that_template(engine, tmp_path):
    tpl_a, tpl_b = make_template(seed=43), make_template(seed=44)
    profile_dir = write_profile(tmp_path, {"a": tpl_a, "b": tpl_b})
    load_library(engine, profile_dir)

    reg_a = profile_dir / "registered" / "a"
    reg_b = profile_dir / "registered" / "b"
    before_a, before_b = _mtimes(reg_a), _mtimes(reg_b)

    replacement = make_template(seed=45)  # same filename, new content
    imwrite(profile_dir / "templates" / "b.png", replacement)
    profile = load_library(engine, profile_dir)

    assert _mtimes(reg_a) == before_a          # untouched
    assert _mtimes(reg_b) != before_b          # rebuilt
    scene = paste(make_scene(seed=91), replacement, 100, 100)
    assert engine.query(profile, "b", scene).found is True


def test_registration_config_change_triggers_rebuild(engine, tmp_path):
    profile_dir = write_profile(tmp_path, {"a": make_template(seed=46)})
    load_library(engine, profile_dir)
    reg = profile_dir / "registered" / "a"
    before = _mtimes(reg)

    _set_config(profile_dir, scale_range=[0.8, 1.2])
    load_library(engine, profile_dir)
    assert _mtimes(reg) != before


def test_刪路徑前的舊快取_比對資訊帶遮罩策略_失效重建一次(engine, tmp_path):
    tpl = make_template(seed=49)
    profile_dir = write_profile(tmp_path, {"a": tpl})
    load_library(engine, profile_dir)
    reg = profile_dir / "registered" / "a"
    # 引擎刪多張圖路徑之前寫下的比對資訊 (ADR 0016 之前的格式)
    png = profile_dir / "templates" / "a.png"
    (reg / "meta.json").write_text(json.dumps({
        "version": 2,
        "captures": {"a.png": hashlib.sha1(png.read_bytes()).hexdigest()},
        "config": {"mask_strategy": "multi_capture", "scale_range": [0.5, 2.0]},
    }, sort_keys=True), encoding="utf-8")
    before = _mtimes(reg)

    profile = load_library(engine, profile_dir)
    rebuilt = _mtimes(reg)
    assert rebuilt != before                       # 失效, 重建
    scene = paste(make_scene(seed=94), tpl, 120, 80)
    assert engine.query(profile, "a", scene).found is True

    load_library(engine, profile_dir)
    assert _mtimes(reg) == rebuilt                 # 只重建一次


def test_threshold_change_applies_immediately_without_rebuild(engine, tmp_path):
    tpl = make_template(seed=47)
    scene = paste(make_scene(seed=92), tpl, 200, 120)
    profile_dir = write_profile(tmp_path, {"a": tpl})

    profile = load_library(engine, profile_dir)
    assert engine.query(profile, "a", scene).found is True
    reg = profile_dir / "registered" / "a"
    before = _mtimes(reg)

    _set_config(profile_dir, match_threshold=1.01)
    profile = load_library(engine, profile_dir)
    assert _mtimes(reg) == before              # thresholds never re-register
    assert engine.query(profile, "a", scene).found is False  # yet take effect


def test_corrupt_artifacts_are_rebuilt_not_fatal(engine, tmp_path):
    tpl = make_template(seed=48)
    scene = paste(make_scene(seed=93), tpl, 150, 150)
    profile_dir = write_profile(tmp_path, {"a": tpl})
    load_library(engine, profile_dir)
    reg = profile_dir / "registered" / "a"

    (reg / "mask.png").write_bytes(b"this is not a png")
    profile = load_library(engine, profile_dir)
    assert engine.query(profile, "a", scene).found is True

    (reg / "meta.json").unlink()
    profile = load_library(engine, profile_dir)
    assert engine.query(profile, "a", scene).found is True

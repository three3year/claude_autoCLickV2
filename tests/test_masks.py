"""Ticket 04 — registration masks: subject vs mutable-region separation.

All assertions go through the public API: build profiles whose captures
disagree in some regions (translucent bleed, counter digits), then check
query behavior on scenes where those regions differ yet again.
"""
from __future__ import annotations

import cv2
import numpy as np

from synth import make_scene, paste, write_profile

rng = np.random.default_rng(4)


def _busy_bg(w, h, seed):
    r = np.random.default_rng(seed)
    img = r.integers(0, 255, (h, w, 3), dtype=np.uint8)
    img = cv2.GaussianBlur(img, (0, 0), 1.2)
    for _ in range(6):
        p1 = (int(r.integers(0, w)), int(r.integers(0, h)))
        p2 = (int(r.integers(0, w)), int(r.integers(0, h)))
        cv2.line(img, p1, p2, tuple(int(c) for c in r.integers(0, 255, 3)), 3)
    return img


def translucent_card(bg: np.ndarray, alpha: float = 0.22) -> np.ndarray:
    """Subject = opaque border + glyph; interior mostly shows the background
    through (bleed). Captures on different backgrounds share only the subject."""
    h, w = 72, 96
    card = bg[:h, :w].astype(np.float32)
    panel = np.full((h, w, 3), 210.0)
    card = (1 - alpha) * card + alpha * panel          # translucent interior
    card = card.astype(np.uint8)
    cv2.rectangle(card, (2, 2), (w - 3, h - 3), (250, 250, 250), 4)   # border
    cv2.circle(card, (w // 2, h // 2), 16, (40, 220, 250), -1)        # glyph
    cv2.line(card, (10, h - 12), (w - 10, h - 12), (250, 250, 250), 3)
    return card


def counter_badge(digit: str) -> np.ndarray:
    """Fixed frame + icon, mutable counter text region."""
    img = np.full((40, 120, 3), 60, dtype=np.uint8)
    cv2.rectangle(img, (1, 1), (118, 38), (230, 230, 230), 2)
    cv2.circle(img, (20, 20), 10, (90, 200, 250), -1)
    cv2.putText(img, f"{digit}/7", (40, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                (240, 240, 240), 2, cv2.LINE_AA)
    return img


def glyph_card(glyph: str) -> np.ndarray:
    """Same frame, different glyph — for fine-grained discrimination.
    The glyph carries most of the structure (as on real clue cards, where
    the big digit dominates); the shared frame is thin."""
    img = np.full((80, 60, 3), 70, dtype=np.uint8)
    cv2.rectangle(img, (2, 2), (57, 77), (220, 220, 220), 1)
    cv2.putText(img, glyph, (8, 60), cv2.FONT_HERSHEY_SIMPLEX, 2.2,
                (245, 245, 245), 5, cv2.LINE_AA)
    return img


def test_translucent_template_matches_on_new_background(engine, tmp_path):
    cap1 = translucent_card(_busy_bg(96, 72, 1))
    cap2 = translucent_card(_busy_bg(96, 72, 2))
    scene_card = translucent_card(_busy_bg(96, 72, 3))   # third background
    scene = paste(make_scene(seed=80), scene_card, 250, 140)

    profile_dir = write_profile(tmp_path, {"card": {"a": cap1, "b": cap2}},
                                config={"mask_strategy": "multi_capture"})
    profile = engine.load_profile(profile_dir)
    res = engine.query(profile, "card", scene)

    assert res.found is True
    bx, by, bw, bh = res.box
    assert abs((bx + bw / 2) - (250 + 48)) <= 8
    assert abs((by + bh / 2) - (140 + 36)) <= 8


def test_mutable_counter_digits_do_not_break_match(engine, tmp_path):
    cap1, cap2 = counter_badge("0"), counter_badge("3")
    scene = paste(make_scene(seed=81), counter_badge("5"), 300, 200)

    profile_dir = write_profile(tmp_path, {"badge": {"a": cap1, "b": cap2}},
                                config={"mask_strategy": "multi_capture"})
    profile = engine.load_profile(profile_dir)
    res = engine.query(profile, "badge", scene)

    assert res.found is True
    bx, by, bw, bh = res.box
    assert abs((bx + bw / 2) - (300 + 60)) <= 8
    assert abs((by + bh / 2) - (200 + 20)) <= 8


def test_similar_templates_are_not_confused(engine, tmp_path):
    # captures of "A" on two backgrounds keep the glyph in the mask,
    # so a scene containing "B" must not match
    a1, a2 = glyph_card("A"), glyph_card("A")
    scene_with_b = paste(make_scene(seed=82), glyph_card("B"), 200, 100)

    profile_dir = write_profile(tmp_path, {"cardA": {"a": a1, "b": a2}},
                                config={"mask_strategy": "multi_capture"})
    profile = engine.load_profile(profile_dir)
    res = engine.query(profile, "cardA", scene_with_b)

    assert res.found is False


def test_single_strategy_works_with_one_capture(engine, tmp_path):
    card = glyph_card("Z")
    scene = paste(make_scene(seed=83), card, 150, 90)
    profile_dir = write_profile(tmp_path, {"cardZ": card},
                                config={"mask_strategy": "single"})
    profile = engine.load_profile(profile_dir)
    res = engine.query(profile, "cardZ", scene)
    assert res.found is True


def test_multi_capture_strategy_degrades_gracefully_on_one_capture(engine, tmp_path):
    card = glyph_card("Q")
    scene = paste(make_scene(seed=84), card, 400, 250)
    profile_dir = write_profile(tmp_path, {"cardQ": card},
                                config={"mask_strategy": "multi_capture"})
    profile = engine.load_profile(profile_dir)
    res = engine.query(profile, "cardQ", scene)
    assert res.found is True


def test_registration_artifacts_persisted_and_reused(engine, tmp_path):
    cap1, cap2 = counter_badge("0"), counter_badge("3")
    profile_dir = write_profile(tmp_path, {"badge": {"a": cap1, "b": cap2}})

    engine.load_profile(profile_dir)
    reg = profile_dir / "registered" / "badge"
    assert (reg / "meta.json").is_file()
    artifact_files = sorted(p.name for p in reg.iterdir())
    mtimes = {p.name: p.stat().st_mtime_ns for p in reg.iterdir()}

    engine.load_profile(profile_dir)  # second load: reuse, don't recompute
    assert sorted(p.name for p in reg.iterdir()) == artifact_files
    assert {p.name: p.stat().st_mtime_ns for p in reg.iterdir()} == mtimes

"""Regenerate the arknights benchmark set (deterministic).

Scenes are composites of REAL template captures (from one set) pasted onto
backgrounds, then queried with ANOTHER set's capture as the case's template
where possible — this is the cross-set scale-invariance test from the spec.
Backgrounds come from the real clue-board screenshot plus seeded synthetic
clutter.

Source captures live in `benchmark/_assets/templates/` — the benchmark owns its
own inputs and depends on no template library (see ADR 0006).
Every case gets its own `template.png` (the referenced template's registration
baseline capture = sorted-first), so cases stay self-contained.

Run:  python tools/build_arknights_benchmark.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from subject_detection.imio import imread, imwrite  # noqa: E402

PROFILE = ROOT / "profiles" / "arknights"
BENCH = PROFILE / "benchmark"
TPL = BENCH / "_assets" / "templates"
BOARD = BENCH / "_assets" / "clue_board.png"


def synth_bg(w: int, h: int, seed: int) -> np.ndarray:
    r = np.random.default_rng(seed)
    img = r.integers(0, 110, (h, w, 3), dtype=np.uint8)
    img = cv2.GaussianBlur(img, (0, 0), 4)
    for _ in range(14):
        p1 = (int(r.integers(0, w)), int(r.integers(0, h)))
        p2 = (int(r.integers(0, w)), int(r.integers(0, h)))
        cv2.rectangle(img, p1, p2, tuple(int(c) for c in r.integers(20, 200, 3)), -1)
    img = cv2.GaussianBlur(img, (0, 0), 1)
    return img


def board_crop(x: int, y: int, w: int = 800, h: int = 560) -> np.ndarray:
    board = imread(BOARD)
    return board[y:y + h, x:x + w].copy()


def backgrounds(i: int) -> np.ndarray:
    picks = [
        lambda: board_crop(0, 0),
        lambda: board_crop(220, 180),
        lambda: synth_bg(800, 560, 7),
        lambda: synth_bg(800, 560, 21),
        lambda: board_crop(100, 120),
        lambda: synth_bg(800, 560, 42),
    ]
    return picks[i % len(picks)]()


def capture(name: str, cap: str) -> np.ndarray:
    return imread(TPL / name / f"{cap}.png")


def baseline_capture(name: str) -> Path:
    """The template's registration baseline capture = sorted-first image.

    Multi-capture templates are gone from the app, and the engine registers one
    image per template, so a case carries exactly this one.
    """
    return sorted((TPL / name).glob("*.png"))[0]


def write_case(name: str, scene: np.ndarray, template: str, expected: str,
               center: tuple[float, float] | None = None, tolerance: int = 15):
    case = BENCH / name
    case.mkdir(parents=True, exist_ok=True)
    imwrite(case / "screenshot.png", scene)
    shutil.copyfile(baseline_capture(template), case / "template.png")
    expect: dict = {"expected": expected, "tolerance": tolerance}
    if center is not None:
        expect["center"] = [int(round(center[0])), int(round(center[1]))]
    (case / "expect.yaml").write_text(
        yaml.safe_dump(expect, allow_unicode=True), encoding="utf-8")


def paste_case(name: str, template: str, patch: np.ndarray, bg_i: int,
               pos: tuple[int, int], scale: float = 1.0,
               tolerance: int = 15, transform=None):
    scene = backgrounds(bg_i)
    if scale != 1.0:
        patch = cv2.resize(patch, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    h, w = patch.shape[:2]
    x, y = pos
    scene[y:y + h, x:x + w] = patch
    if transform is not None:
        scene = transform(scene)
    write_case(name, scene, template, "present",
               center=(x + w / 2, y + h / 2), tolerance=tolerance)


def darken(img):
    return (img.astype(np.float32) * 0.55).astype(np.uint8)


def blue_tint(img):
    out = img.astype(np.float32)
    out[..., 0] = np.clip(out[..., 0] * 1.25 + 20, 0, 255)  # boost blue
    out[..., 2] = np.clip(out[..., 2] * 0.8, 0, 255)        # cut red
    return out.astype(np.uint8)


def gamma_up(img):
    lut = (np.linspace(0, 1, 256) ** (1 / 1.6) * 255).astype(np.uint8)
    return lut[img]


def main() -> None:
    if BENCH.exists():
        for child in BENCH.iterdir():
            if child.is_dir() and not child.name.startswith("_"):
                shutil.rmtree(child)

    # A. same-set positives (cn capture, cn template) — skeleton-passable
    for i, name in enumerate(["返回", "基建鈴鐺", "信用購買", "好友列表",
                              "天bar首頁", "採購信用領取"]):
        paste_case(f"a{i}_sameset_{name}", f"cn/{name}", capture(f"cn/{name}", "cn"),
                   bg_i=i, pos=(80 + 90 * i, 60 + 60 * i))

    # B. cross-set: 翻新 capture pasted, cn template queried (real scale gap)
    for i, name in enumerate(["返回", "基建鈴鐺", "每日線索", "製造站加速",
                              "會客室線索", "線索3", "快速置入", "經驗圖"]):
        tol = 25 if name.startswith("線索") else 15
        paste_case(f"b{i}_crossset_{name}", f"cn/{name}", capture(f"cn/{name}", "翻新"),
                   bg_i=i + 1, pos=(60 + 80 * i, 40 + 55 * i), tolerance=tol)

    # C. synthetic scale sweep on cn captures
    for i, (name, s) in enumerate([("返回", 0.7), ("信用購買", 1.4), ("基建代辦", 1.2)]):
        paste_case(f"c{i}_scale{int(s * 100)}_{name}", f"cn/{name}",
                   capture(f"cn/{name}", "cn"), bg_i=i + 2, pos=(300, 150 + 80 * i),
                   scale=s)

    # D. color / brightness shifts applied to the whole scene
    for i, (name, cap, fx) in enumerate([("返回", "翻新", darken),
                                         ("每日線索", "翻新", blue_tint),
                                         ("好友列表", "cn", gamma_up)]):
        paste_case(f"d{i}_color_{name}", f"cn/{name}", capture(f"cn/{name}", cap),
                   bg_i=i, pos=(420, 90 + 100 * i), transform=fx)

    # E. semi-transparent clue cards on two different backgrounds each
    for i, name in enumerate(["線索1", "線索5"]):
        for j in (0, 1):
            paste_case(f"e{i}{j}_cluebg_{name}", f"cn/{name}",
                       capture(f"cn/{name}", "翻新"), bg_i=2 * i + j + 1,
                       pos=(150 + 260 * j, 120 + 90 * i), tolerance=25)

    # F. mutable counter digits: real board shows 0/7; template captures are
    # 0/7 and 3/7; a 5/7 board must still match
    board = imread(BOARD)
    write_case("f0_counter_0of7", board.copy(), "zh/解鎖線索計數", "present",
               center=(345 + 175, 693 + 37), tolerance=20)
    board5 = board.copy()
    bar = board5[693:768, 345:695]
    bg = bar[15:60, 152:172].reshape(-1, 3).mean(axis=0).astype(np.uint8)
    bar[8:65, 70:112] = bg
    cv2.putText(bar, "5", (72, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.7,
                (235, 235, 235), 4, cv2.LINE_AA)
    write_case("f1_counter_5of7", board5, "zh/解鎖線索計數", "present",
               center=(345 + 175, 693 + 37), tolerance=20)

    # G. fine-grained confusers among clue cards
    scene = backgrounds(3)
    p = capture("cn/線索2", "翻新")
    scene[100:100 + p.shape[0], 300:300 + p.shape[1]] = p
    write_case("g0_confuser_線索1_vs_2", scene, "cn/線索1", "absent")

    scene = backgrounds(4)
    p = capture("cn/線索3", "翻新")
    scene[80:80 + p.shape[0], 200:200 + p.shape[1]] = p
    write_case("g1_confuser_線索2_vs_3", scene, "cn/線索2", "absent")

    scene = backgrounds(5)
    p1 = capture("cn/線索1", "翻新")
    p2 = capture("cn/線索2", "翻新")
    scene[60:60 + p1.shape[0], 120:120 + p1.shape[1]] = p1
    scene[60:60 + p2.shape[0], 420:420 + p2.shape[1]] = p2
    write_case("g2_pick_線索1_among_2", scene, "cn/線索1", "present",
               center=(120 + p1.shape[1] / 2, 60 + p1.shape[0] / 2), tolerance=25)

    # H. negatives: subject truly absent
    write_case("h0_neg_返回_board", imread(BOARD), "cn/返回", "absent")
    write_case("h1_neg_基建鈴鐺_synth", synth_bg(800, 560, 77), "cn/基建鈴鐺", "absent")
    write_case("h2_neg_採購信用頁籤_crop", board_crop(150, 100), "zh/採購信用頁籤", "absent")
    scene = backgrounds(0)
    for k, nm in enumerate(["返回", "信用購買", "好友列表"]):
        p = capture(f"cn/{nm}", "cn")
        scene[40 + 120 * k:40 + 120 * k + p.shape[0], 600:600 + p.shape[1]] = p
    write_case("h3_neg_線索6_busy", scene, "cn/線索6", "absent")
    write_case("h4_neg_製造站收取_board", board_crop(60, 200), "cn/製造站收取", "absent")

    # I. zh same-set positives
    for i, name in enumerate(["返回", "V", "X"]):
        paste_case(f"i{i}_zh_{name}", f"zh/{name}", capture(f"zh/{name}", "zh"),
                   bg_i=i + 3, pos=(500 + 40 * i, 300 + 50 * i))

    # J. near-fullscreen scene for perf measurement (also a correctness case)
    board = imread(BOARD)
    p = capture("cn/返回", "翻新")
    board[600:600 + p.shape[0], 900:900 + p.shape[1]] = p
    write_case("j0_fullscreen_返回", board, "cn/返回", "present",
               center=(900 + p.shape[1] / 2, 600 + p.shape[0] / 2))

    n = len(list(d for d in BENCH.iterdir()
                 if d.is_dir() and not d.name.startswith("_")))
    print(f"benchmark cases: {n}")


if __name__ == "__main__":
    main()

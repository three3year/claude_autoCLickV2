"""辨識入口: 截圖 + 招募池快照 → 五格各是哪個`招募標籤`、嚴格通過與否、保底組合.

29 張渲染範本在同一個模板庫登錄一次 (登錄產物放暫存目錄, 載進記憶體後刪掉);
每格的搜尋區域 = 格子外擴少量邊, 對 29 張各查一次, expected_scale = 截圖尺度。
引擎參數讀 arknights profile 的 config.yaml。

每格的判定 (嚴格標準, 不調門檻):
- 只有中心落在格子中心附近的匹配/候選算數 (字面在格子裡置中, 見 layout.CENTER_TOLERANCE)
- found = 引擎回報的匹配 (過粗篩與驗證門檻) 中有置中的
- 恰一張 found → 該格的標籤; 它的粗篩分數減去其他 28 張最佳候選粗篩分數的最大值
  (差距) ≥ 0.1 → pass, 否則 low_margin (標籤照認, 但不算通過)
- 兩張以上 found → confused (列出全部, 不參與組合); 沒有 → unrecognized
- 整張通過 = 五格都 pass
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import cv2
import numpy as np

from . import layout, render
from .combos import guarantees
from .errors import ToolError
from .pool import tag_names

PROFILE = Path(__file__).resolve().parents[2] / "profiles" / "arknights"
MIN_MARGIN = 0.1

STATUS_TEXT = {"pass": "通過", "low_margin": "差距不足", "confused": "混淆",
               "unrecognized": "未辨識"}


def _read(image):
    if isinstance(image, np.ndarray):
        return image
    data = np.fromfile(str(image), np.uint8) if os.path.isfile(str(image)) else None
    img = cv2.imdecode(data, cv2.IMREAD_COLOR) if data is not None and data.size else None
    if img is None:
        raise ToolError(f"讀不到截圖 {image}")
    return img


def _engine():
    import warnings

    from subject_detection import Engine
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Engine()


_LIBRARIES = {}   # 同一個引擎、同一組字面/渲染設定/引擎參數的模板庫只登錄一次 (行程內)


def _library(engine, pool, settings, config):
    key = (id(engine), settings, tuple((t["id"], t["name"]) for t in pool["tags"]),
           repr(sorted(config.items())))
    if key not in _LIBRARIES:
        _LIBRARIES[key] = (engine, _register(engine, pool, settings, config))
    return _LIBRARIES[key][1]


def _register(engine, pool, settings, config):
    from subject_detection import make_library
    with tempfile.TemporaryDirectory(prefix="recruit_tags_") as tmp:
        paths = {}
        for name, img in render.templates(pool, settings).items():
            p = os.path.join(tmp, f"{name}.png")
            cv2.imencode(".png", img)[1].tofile(p)
            paths[name] = p
        lib = make_library(paths, config, os.path.join(tmp, "registered"))
        for name in paths:   # 登錄產物載進記憶體, 暫存目錄刪掉後照樣能查
            engine.register(lib, name)
    return lib


def _score(engine, lib, name, region, offset, cell, scale):
    """一張範本在一格的結果: found、置中的最佳候選粗篩與驗證分數.

    粗篩候選與驗證分數取自 `QueryResult.debug` (格式引擎不承諾穩定; 引擎改了這裡跟著改)。
    候選依粗篩分數由高到低, 過門檻的是前綴, 驗證分數依序對應那個前綴。
    """
    r = engine.query(lib, name, region, expected_scale=scale)
    ox, oy = offset

    def shift(box):
        return (box[0] + ox, box[1] + oy, box[2], box[3])

    cands = r.debug.get("candidates", [])
    verify = r.debug.get("verify_scores") or []
    best = max((i for i, c in enumerate(cands)
                if layout.centered(shift(c["box"]), cell, scale)),
               key=lambda i: cands[i]["score"], default=None)
    found = [m for m in r.matches if layout.centered(shift(m.box), cell, scale)]
    return {
        "found": bool(found),
        "coarse": round(float(cands[best]["score"]), 4) if best is not None else 0.0,
        "verify": (round(float(verify[best]), 4)
                   if best is not None and best < len(verify) else None),
        # 置中匹配的相似度 (有驗證時是驗證分數, 只有粗篩時是粗篩分數)
        "similarity": round(float(found[0].score), 4) if found else None,
    }


def _judge(index, cell, scores, names):
    found = sorted((t for t, s in scores.items() if s["found"]),
                   key=lambda t: (scores[t]["coarse"], scores[t]["similarity"]), reverse=True)
    by_coarse = sorted(scores, key=lambda t: scores[t]["coarse"], reverse=True)
    best = found[0] if found else by_coarse[0]
    runner = max((t for t in scores if t != best), key=lambda t: scores[t]["coarse"])
    margin = round(scores[best]["coarse"] - scores[runner]["coarse"], 4)
    if len(found) == 1:
        status = "pass" if margin >= MIN_MARGIN else "low_margin"
    else:
        status = "confused" if found else "unrecognized"
    tag = found[0] if len(found) == 1 else None

    def ref(t):
        return {"id": t, "name": names[t]}

    return {
        "index": index,
        "box": list(cell),
        "status": status,
        "tag": ref(tag) if tag else None,
        "best": {**ref(best), **{k: scores[best][k] for k in ("coarse", "verify", "similarity")}},
        "runner_up": {**ref(runner), "coarse": scores[runner]["coarse"]},
        "margin": margin,
        "found": found,
        "scores": [{**ref(t), **{k: scores[t][k] for k in ("found", "coarse", "verify")}}
                   for t in by_coarse],
    }


def recognize(image, pool, engine=None, client="tw", cells=None, render_settings=None,
              config=None):
    """截圖 (路徑或 BGR 影像) + 招募池快照 → 辨識結果 (dict, 可直接寫成 JSON).

    cells: 整組覆寫五格版面 (1.0 尺度 (x, y, w, h)); render_settings: render.Settings
    (預設該客戶端的預設字型與字級); config: 引擎參數 (預設 arknights profile)。
    """
    from subject_detection import load_config

    if client != pool.get("server"):   # 客戶端代號就是伺服器代號 (tw 台服、cn 國服)
        raise ToolError(f"客戶端「{client}」要配同一個伺服器的招募池快照，"
                        f"拿到的是「{pool.get('server')}」")
    img = _read(image)
    h, w = img.shape[:2]
    scale = layout.scale_of(w, h)
    boxes = layout.scaled_cells(scale, cells)
    settings = render_settings or render.default_settings(client)
    config = config or load_config(PROFILE)
    engine = engine or _engine()
    lib = _library(engine, pool, settings, config)
    names = tag_names(pool)

    results = []
    for i, cell in enumerate(boxes, 1):
        x0, y0, x1, y1 = layout.search_box(cell, scale, w, h)
        region = img[y0:y1, x0:x1]
        scores = {t: _score(engine, lib, render.template_name(t), region, (x0, y0), cell,
                            scale) for t in names}
        results.append(_judge(i, cell, scores, names))

    tags = [c["tag"]["id"] for c in results if c["tag"]]
    combos = guarantees(tags, pool)
    return {
        "passed": all(c["status"] == "pass" for c in results),
        "size": [w, h],
        "scale": round(scale, 4),
        "client": client,
        "layout": [list(c) for c in (cells or layout.CELLS)],
        "cells": results,
        **combos,
        "render": settings.describe(),
        "engine": {"match_threshold": float(config["match_threshold"]),
                   "verify_threshold": float(config["verify_threshold"]),
                   "scale_range": list(config["scale_range"]),
                   "verification": "coarse" if engine.coarse_only else "full",
                   "min_margin": MIN_MARGIN},
        "pool": {"server": pool["server"], **pool.get("source", {})},
    }

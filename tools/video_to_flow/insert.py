"""`補充`: 補充計畫＋只錄一段的示範影片 → 插進一份既有流程的指定位置 (直接改寫, 不備份).

順序 (任何報錯都在寫檔前; 失敗時既有資料夾一個位元都不變)::

    讀計畫與既有流程 → 核對插入點 (after/into＋expect)、`對齊圖`的參考步驟、`共用矩形`的
    same_as (照抄第 N 步的固定矩形) → 量`影片倍率` →
    影格整張縮放 1/倍率、對齊`座標基準點` → 量`對齊位移`並套到插入段 → 與 assemble 同一段
    量測 (原點推算、固定矩形、拾取檢查、忙碌兩向) → 插入後的原點來源比對 → 結構檢查 →
    寫回 (新範本、flow.yaml、交付報告) → 檢查指令

影片倍率在影格上量既有流程的`校準對` (主對量不到改備用對; 都量不到改量計畫的
scale_image——跟影片同取景的一張圖片), 支援倍率範圍外報錯。量到之後影片的一切像素量
÷倍率才進流程, 新範本也縮放到流程尺度 (詞彙見 app/CONTEXT.md「補充」「影片倍率」)。
"""
from __future__ import annotations

import os
from dataclasses import replace

import calibration
import flowfile
from automation import findtarget, flowcheck, flowfmt, imgio, pickcheck
from automation.runner import origin_step
from subject_detection.library import load_default_config

from .assemble import crop, png, retake_of, scroll_confirm, shared_info
from . import align as align_mod
from . import measure as measure_mod
from . import plan as plan_mod
from . import report as report_mod
from . import verify as verify_mod
from . import video as video_mod
from .errors import ToolError

_HEAD = {"repeat_start": "repeat", "branch_start": "branch"}
_MARKERS = ("repeat_end", "branch_or", "branch_end")


def _yaml_head(s):
    t = s["type"]
    head = _HEAD.get(t, t)
    if findtarget.is_find(s):
        return head, findtarget.template(s)
    value = {"click": s.get("click"), "drag": s.get("drag"), "wait": s.get("wait"),
             "repeat": s.get("repeat")}.get(head)
    return head, value


def _expect_value(steps, i):
    """第 i 步 (平面) 在 expect 裡的值: 找圖是範本名, 分岔是第一個分支條件的範本名."""
    head, value = _yaml_head(steps[i])
    if head == "branch":
        value = findtarget.template(steps[i + 1])
    return head, value


def _in_range(steps, n, key):
    if n > len(steps):
        raise ToolError(f"{key}: {n} 超出流程（共 {len(steps)} 步）")


def _check_expect(steps, n, expect, key):
    """第 n 步 (從 1 起算) 跟 expect 核對 (插入點與共用矩形的 same_as 同一套)."""
    head, value = _expect_value(steps, n - 1)
    (ehead, evalue), = expect.items()
    same = ehead == head and (evalue is None and head in ("repeat", "branch", "click",
                                                          "drag", "wait")
                              or evalue == value)
    if not same:
        raise ToolError(f"{key}: 第 {n} 步是 {{{head}: {value}}}，跟 expect 寫的 "
                        f"{{{ehead}: {evalue}}} 不符——步驟編號可能寫錯"
                        "（編號是 flow.yaml 行尾的 # N）")


def copy_shared(p, steps):
    """`共用矩形`的 same_as: 核對第 N 步並照抄它的固定矩形 (就地寫進宣告的 within)
    → {名: 第 N 步的內容指稱}."""
    source = {}
    for name, d in p.shared_rects.items():
        if "same_as" not in d:
            continue
        key, n = f"共用矩形「{name}」的 same_as", d["same_as"]
        _in_range(steps, n, key)
        _check_expect(steps, n, d["expect"], key)
        s = steps[n - 1]
        within = findtarget.target(s).get("within") if findtarget.is_find(s) else None
        if not findtarget.valid_fixed_rect(within):
            raise ToolError(f"{key}: 第 {n} 步（{measure_mod.label(s)}）沒有固定矩形，照抄不到框"
                            "——same_as 要指同組既有成員的找圖步驟（flow.yaml 裡有 within 的那一步）")
        d["within"] = list(within)
        source[name] = measure_mod.label(s)
    return source


def insertion_index(steps, p):
    """插入點 → 平面索引 (插入段放在 steps[idx] 之前); 核對 expect."""
    key = "after" if p.after is not None else "into"
    n = p.after if p.after is not None else p.into
    _in_range(steps, n, key)
    s = steps[n - 1]
    if s["type"] in _MARKERS:
        raise ToolError(f"{key}: 第 {n} 步是區段的結尾或「或」標記，插入點要指有開頭鍵的步驟"
                        "（要插在區段之後：after 寫區段開頭那一步）")
    _check_expect(steps, n, p.expect, key)
    if key == "into":
        if s["type"] != "repeat_start":
            raise ToolError(f"into: 第 {n} 步不是重複區段的開頭；into 只用在重複區段"
                            "（插進分岔的某個分支：after 寫那個分支的條件步驟）")
        return n
    if s["type"] in ("repeat_start", "branch_start"):
        return report_mod.section_end(steps, n - 1)
    return n


# ---------- 影片倍率 ----------

def _detector(engine, images, config):
    """只為量校準對建的小偵測接縫 (images: {名: 影像})."""
    return verify_mod.detector(engine, images, config)


def video_scale(p, cal, frames, detector):
    """在影格上 (依編號) 量既有流程的校準對 → (倍率, 基準點 (影片像素), 量法說明).

    主對量不到改備用對 (`calibration.calibrate` 的規則); 全部影格都量不到時量
    p.scale_image; 沒有圖片＝報錯 (不收手打的倍率)。
    """
    last = None
    for f in sorted(frames):
        c = calibration.calibrate(detector.query, frames[f], (0, 0), cal)
        if c.ok:
            how = "主校準對" if c.used == "main" else "備用校準對"
            return c.scale, c.anchor, f"第 {f} 幀上的{how}量得"
        last = c
    why = last.describe() if last else "沒有可量的影格"
    if not p.scale_image:
        raise ToolError(f"影片裡量不到既有流程的校準對（{why}）：請使用者另給一張跟影片同取景、"
                        "同視窗大小與位置的圖片（例：同一個錄影框截一張主畫面），寫進計畫的 "
                        "scale_image")
    img = imgio.imread(p.scale_image)
    if img is None:
        raise ToolError(f"讀不到 scale_image：{p.scale_image}")
    c = calibration.calibrate(detector.query, img, (0, 0), cal)
    if not c.ok:
        raise ToolError(f"scale_image 上也量不到既有流程的校準對（{c.describe()}）："
                        "圖片要跟影片同取景，而且看得到校準對（或備用校準對）")
    how = "主校準對" if c.used == "main" else "備用校準對"
    return c.scale, c.anchor, f"scale_image 上的{how}量得"


def _div(v, r):
    return int(round(v / r))


def scaled_plan(p, r):
    """影片像素 → 流程尺度 (÷r): 步驟的位置、證據的 at、範本的裁切框與 present.at、
    共用矩形的容器框 (same_as 照抄的框已是流程尺度, 不動)."""
    if r == 1:
        return p

    def xy(v):
        return [_div(v[0], r), _div(v[1], r)]

    def near(tgt):
        kind, value = findtarget.pick_rule(tgt)
        if kind == "near":
            tgt["pick"] = {"near": xy(value)}

    steps = []
    for s in p.steps:
        s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in s.items()}
        for k in ("click", "drag", "to"):
            if k in s:
                s[k] = xy(s[k])
        for k in ("target", "confirm_target"):
            if isinstance(s.get(k), dict):
                near(s[k])
        steps.append(s)
    evidence = [dict(e, at=xy(e["at"]) if e and e.get("at") else None) if e else e
                for e in p.evidence]
    templates = {}
    for n, t in p.templates.items():
        x, y, w, h = t["box"]
        templates[n] = dict(t, box=[_div(x, r), _div(y, r), max(1, _div(w, r)),
                                    max(1, _div(h, r))],
                            present=[dict(pr, at=xy(pr["at"]) if pr["at"] else None)
                                     for pr in t["present"]])
    align = dict(p.align, at=xy(p.align["at"])) if p.align else p.align
    shared = {n: (dict(d, box=[_div(d["box"][0], r), _div(d["box"][1], r),
                               max(1, _div(d["box"][2], r)), max(1, _div(d["box"][3], r))])
                  if "box" in d else d)
              for n, d in p.shared_rects.items()}
    return replace(p, steps=steps, evidence=evidence, templates=templates, align=align,
                   shared_rects=shared)


# ---------- 範本 ----------

def similar_existing(engine, config, crops, frames, templates, existing, size):
    """新範本跟哪張既有範本幾乎一樣 (既有的在新範本取材處附近匹配得到) → {新: 既有}."""
    cands = {}
    for n, img in crops.items():
        if n not in templates:
            continue
        h, w = img.shape[:2]
        for e, eimg in existing.items():
            eh, ew = eimg.shape[:2]
            if abs(ew - w) <= 0.25 * w and abs(eh - h) <= 0.25 * h:
                cands.setdefault(n, []).append(e)
    if not cands:
        return {}
    names = {e for es in cands.values() for e in es}
    det = verify_mod.detector(engine, {e: existing[e] for e in names}, config)
    out = {}
    for n, es in cands.items():
        t = templates[n]
        x, y, w, h = t["box"]
        x0, y0 = max(0, x - w // 2), max(0, y - h // 2)
        x1, y1 = min(size[0], x + w + w // 2), min(size[1], y + h + h // 2)
        region = frames[t["frame"]][y0:y1, x0:x1]
        for e in es:
            r = det.query(e, region, expected_scale=1.0)
            if r.matches:
                out[n] = e
                break
    return out


# ---------- 原點來源 ----------

def _uses_origin(s):
    t = s["type"]
    if t in ("click", "drag"):
        return True
    return findtarget.is_find(s) and findtarget.needs_origin(findtarget.target(s))


def origin_changes(old, new, pos, n):
    """插入點後面的舊步驟 (用到原點的) 原點來源有沒有變 → [(舊索引, 舊來源, 新來源)]."""
    bad = []
    for j in range(pos, len(old)):
        if not _uses_origin(old[j]):
            continue
        before = origin_step(old, j)
        want = None if before is None else (before if before < pos else before + n)
        got = origin_step(new, j + n)
        if got != want:
            bad.append((j, before, got))
    return bad


def _origin_check(old, new, pos, n):
    bad = origin_changes(old, new, pos, n)
    if not bad:
        return
    parts = []
    for j, before, got in bad:
        src = ("沒有原點" if got is None else
               f"插入段的「{measure_mod.label(new[got])}」" if pos <= got < pos + n
               else f"步驟 {got + 1}")
        parts.append(f"舊的步驟 {j + 1}（{measure_mod.label(old[j])}，插入後是步驟 "
                     f"{j + 1 + n}）原點本來來自步驟 "
                     f"{before + 1 if before is not None else '（無）'}，插入後變成{src}")
    raise ToolError("插入會改變後面舊步驟的原點來源：" + "；".join(parts)
                    + "——請換插入點，或在插入段尾重新定位（例：最後一步不更新原點）")


# ---------- 入口 ----------

def insert(plan, folder, engine=None):
    """把補充計畫量好的步驟插進既有流程資料夾; 回傳結果 dict."""
    from flow_check import check

    p = plan_mod.load(plan, plan_mod.INSERT)
    folder = os.path.abspath(str(folder))
    try:
        flow = flowfile.read_flow(folder)
    except flowfile.FlowError as e:
        raise ToolError(f"既有流程讀不進來：{e}") from None
    existing = flowfile.folder_template_names(folder)
    taken = {n.casefold(): n for n in existing}
    for n in p.templates:
        if n.casefold() in taken:
            raise ToolError(f"範本「{n}」跟既有範本「{taken[n.casefold()]}」撞名：改名，"
                            "或直接引用既有的（步驟寫它的名字、不寫進 templates）")
    plan_mod.check_references(p, existing)
    cal = flow.get("calibration")
    if not cal:
        raise ToolError("既有流程沒有校準對：量不了影片倍率，請先在 app 設定校準對")
    old = flow["steps"]
    pos = insertion_index(old, p)
    # 只看步驟種類的檢查先做 (不必等量測): 找圖相連、原點的圖離開、後面舊步驟的原點來源
    plan_mod.precheck(old[:pos] + p.steps + old[pos:], flow.get("busy"))
    _origin_check(old, old[:pos] + p.steps + old[pos:], pos, len(p.steps))
    source = copy_shared(p, old)
    align_mod.require(p)
    ref = None
    if p.align:
        align_mod.check_segment(p)
        ref = align_mod.reference(p, old, pos, existing, measure_mod.label)

    info = video_mod.probe(p.video)
    raw_frames = video_mod.read_frames(
        p.video, measure_mod.frames_needed(p, [p.align["frame"]] if p.align else []))
    config = dict(load_default_config(), **(flow.get("engine") or {}))
    engine = engine or verify_mod.make_engine()
    pair_imgs = {}
    for n in [*cal["pair"], *((calibration.fallback_pair(cal) or {}).get("pair") or [])]:
        img = imgio.imread(os.path.join(folder, flowfile.TEMPLATES_DIR, n + ".png"))
        if img is not None:
            pair_imgs[n] = img
    r, anchor_v, how = video_scale(p, cal, raw_frames,
                                   _detector(engine, pair_imgs, config))
    if not calibration.in_supported_range(r):
        raise ToolError(f"影片倍率 ×{r:.3f} 超出支援倍率範圍 {calibration.SCALE_RANGE_LABEL}"
                        f"（{how}）：錄影時把遊戲視窗調成跟建流程時差不多大再錄")

    def rescale(img):
        return img if r == 1 else pickcheck.resize_image(img, 1.0 / r)

    frames = {f: rescale(img) for f, img in raw_frames.items()}
    size = ((_div(info["width"], r), _div(info["height"], r)) if r != 1
            else (info["width"], info["height"]))
    anchor = (_div(anchor_v[0], r), _div(anchor_v[1], r))
    q = scaled_plan(p, r)
    crops = {n: crop(frames, n, t, size) for n, t in q.templates.items()}
    refs = set(findtarget.referenced_templates(q.steps))
    old_imgs = {}
    need = refs - set(q.templates)
    if flow.get("busy"):
        need.add(flow["busy"]["template"])
    if q.align:
        need.add(q.align["find"])
    for n in sorted(need):
        img = imgio.imread(os.path.join(folder, flowfile.TEMPLATES_DIR, n + ".png"))
        if img is None:
            raise ToolError(f"引用的既有範本「{n}」在 templates/ 裡沒有圖")
        old_imgs[n] = img
    checker = verify_mod.Checker(engine, {**crops, **old_imgs}, q.templates, q.steps, frames,
                                 config, anchor, size,
                                 extra_targets=[flow["busy"]] if flow.get("busy") else [])
    shifts, shift, drag_change = None, None, None
    if q.align:
        h, w = old_imgs[q.align["find"]].shape[:2]
        shift = align_mod.measure_shift(q, ref, (w, h), frames, checker.detector, anchor)
        q, shifts, drag_change = align_mod.apply(q, shift.d)
    measured = measure_mod.measure(q, checker, flow.get("busy"), shifts)
    measure_mod.busy_two_way(q, measured, checker, info, rescale)
    checked = checker.finish()
    seg = measured.steps
    others = {}
    for n in existing:
        if n not in old_imgs:
            img = imgio.imread(os.path.join(folder, flowfile.TEMPLATES_DIR, n + ".png"))
            if img is not None:
                others[n] = img
    similar = similar_existing(engine, config, crops, frames, q.templates,
                               {**others, **old_imgs}, size)

    new_steps = old[:pos] + seg + old[pos:]
    new_flow = dict(flow, steps=new_steps)
    errs = flowcheck.flow_errors(new_flow)
    if errs:
        raise ToolError("插入後的流程 app 執行前會擋下：" + "；".join(errs))
    images = {n: png(img) for n, img in crops.items() if n in refs}
    missing = [n for n in refs if n not in existing and n not in images]
    if missing:
        raise ToolError(f"工具錯誤：插入後缺圖 {'、'.join(missing)}")
    pos_map = dict(flow.get("template_pos") or {})
    for n in images:
        x, y, w, h = q.templates[n]["box"]
        pos_map[n] = list(flowfmt.from_screen((x + w // 2, y + h // 2), anchor))
    new_flow["template_pos"] = pos_map

    used = set(images) | refs
    retake = retake_of(checked, used)
    scroll = [(i - pos, text) for i, text in scroll_confirm(
        new_steps, _shifted_scroll(measured, pos)) if pos <= i < pos + len(seg)]
    confirm = ([("捲動清單", f"{t}：段落有拖曳但沒宣告捲動軸，確認是否在捲動清單裡")
                for _, t in scroll]
               + [("忙碌檢查", f"{t} 勾了，但之後的影格沒看到忙碌指示")
                  for _, t in measured.busy_unseen]
               + [("忙碌檢查", f"{t} 沒勾，但之後的影格看到忙碌指示")
                  for _, t in measured.busy_unchecked]
               + [("範本重複", f"新範本「{n}」跟既有的「{e}」幾乎一樣，建議改用既有的")
                  for n, e in similar.items()])
    note = f"來源影片 `{os.path.basename(p.video)}`（影片倍率 ×{r:.3f}，{how}）。"
    if shift is not None:
        note += _align_note(q.align["find"], old[p.align["step"] - 1], shift, drag_change)
    shared = shared_info(q, measured, seg, source)
    for n, info in shared.items():   # 報告的容器框照計畫寫的影片像素 (q 已除過倍率)
        info["box"] = p.shared_rects[n].get("box")
    files = report_mod.supplement(folder, old, new_steps, (pos, pos + len(seg)), note,
                                  list(retake.items()), confirm, list(shared.items()))
    def verify():
        res = check(folder)
        if not res.ok:
            raise ToolError("工具錯誤：寫回後的流程沒通過檢查指令：" + "；".join(res.errors))

    _write_back(folder, new_flow, images, files, verify)
    return {"flow_path": folder, "position": pos + 1, "inserted": len(seg),
            "video": p.video, "video_scale": r, "scale_from": how,
            "retake": retake, "similar": similar,
            "scroll_confirm": scroll, "busy_unseen": measured.busy_unseen,
            "busy_unchecked": measured.busy_unchecked,
            "shared_rects": shared,
            "align": None if shift is None else {
                "shift": list(shift.d), "video": list(shift.video),
                "runtime": list(shift.runtime), "axis": shift.axis,
                "drag": list(drag_change) if drag_change else None},
            "report_files": sorted(files), "steps": len(new_steps),
            "step_list": new_steps}


def _align_note(name, ref_step, shift, drag_change):
    """交付報告裡對齊的一句 (參考步驟用內容指稱)."""
    d = shift.d
    text = (f"對齊圖「{name}」（參考插入點前{measure_mod.label(ref_step)}那一步的固定矩形）："
            f"影片裡在 ({shift.video[0]}, {shift.video[1]})、執行時在 "
            f"({shift.runtime[0]}, {shift.runtime[1]})，對齊位移 ({d[0]}, {d[1]}) px")
    if drag_change:
        text += f"；第一次拖曳的距離從 {drag_change[0]} px 改成 {drag_change[1]} px"
    return text + "。"


def _shifted_scroll(measured, pos):
    """measured.no_scroll 是插入段內的索引; 換成插入後整份流程的索引."""
    return replace(measured, no_scroll={i + pos for i in measured.no_scroll})


def _write_back(folder, flow, images, files, verify):
    """寫回既有資料夾: 新範本 → flow.yaml → 交付報告 → verify() (檢查指令);
    任何一步失敗 (含檢查沒過) 就把寫過的還原."""
    tdir = os.path.join(folder, flowfile.TEMPLATES_DIR)
    ypath = os.path.join(folder, flowfile.FLOW_YAML)
    rdir = os.path.join(folder, report_mod.DIR)
    text = flowfile.dump_flow(flow)
    with open(ypath, "rb") as f:
        old_yaml = f.read()
    old_reports = {}
    for name in files:
        path = os.path.join(rdir, name)
        old_reports[name] = None
        if os.path.isfile(path):
            with open(path, "rb") as f:
                old_reports[name] = f.read()
    had_rdir = os.path.isdir(rdir)
    written = []
    tmp = ypath + ".tmp"
    try:
        os.makedirs(tdir, exist_ok=True)
        for n, data in images.items():
            path = os.path.join(tdir, n + ".png")
            with open(path, "xb") as f:
                written.append(path)
                f.write(data)
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, ypath)
        report_mod.write(folder, files)
        verify()
    except BaseException:
        for path in written + [tmp]:
            try:
                os.remove(path)
            except OSError:
                pass
        with open(ypath, "wb") as f:
            f.write(old_yaml)
        for name, data in old_reports.items():
            path = os.path.join(rdir, name)
            if data is None:
                if os.path.isfile(path):
                    os.remove(path)
            else:
                with open(path, "wb") as f:
                    f.write(data)
        if not had_rdir and os.path.isdir(rdir) and not os.listdir(rdir):
            os.rmdir(rdir)
        raise

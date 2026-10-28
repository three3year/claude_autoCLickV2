"""自我驗證: 用引擎公開 API 對影格重跑每張範本, 沒過的標`待重拍`; 順便算`固定矩形`.

範本經 `make_library` + `Engine.register` 一張一張登錄 (一張登錄失敗不拖垮
其他張), 再以 `Engine.query` 在指定影格上查詢; 搜尋區域就是整張影格
(影片＝遊戲畫面＝搜尋範圍)。影格已是`流程尺度` (補充時先縮放過), 查詢一律帶預期尺度 1。

每張範本要通過的檢查 (以引用它的找圖目標用到的每一種`比色`設定各查一次):

- 取材幀與 present 幀: 有匹配落在預期位置附近 (預設＝裁切框中心,
  present 可寫明新位置)——同款多張時其他位置也有匹配不算錯
- absent 幀 (還沒出現的那幾幀): 整張影格上沒有任何匹配
- 計畫標示 clean: false (找不到乾淨影格): 不論結果都待重拍
- `拾取檢查`的縮放餘裕 (ADR 0013): 取材幀縮到 ×0.85 與放大到 ×1.15 各找一次

每個找圖目標 (找圖步驟、確認圖、忙碌指示) 在它那一幀上照它的設定完整執行一次
(與執行器同一個模組: 裁限定範圍 → 查詢 → 比色 → 挑選規則): 挑中的框就是原點推算用的框,
`固定矩形`＝挑中的框每邊外推範本寬高的 50% (宣告了捲動軸的那一軸拉到影片兩端;
`停點差`那一軸每邊至少 DRIFT_MARGIN; `遞補方向`那一端拉到影片邊緣), 超出影片的
部分裁掉; 加上固定矩形再挑一次要挑到同一個, 再跑`拾取檢查`的唯一與矩形餘裕。判斷都只呼叫
app 的 pickcheck 模組。矩形餘裕照規則必過 (裁過的那一側不算), 沒過＝工具的 bug。

`共用矩形`的成員先只挑框 (記下來), 全部挑完後 `resolve_shared` 才算框 (容器每邊外推最大成員
框寬高的一半; 補充的 same_as 照抄既有那一步的), 寫進每個成員的 within, 再對每個成員跑上面
同一套檢查。成員挑中的框要整個落在容器 (same_as: 照抄的框) 裡, 不然報錯。

報告裡的原因用內容 (範本、動作、影格) 指稱步驟, 不寫步驟編號。
"""
from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass

import cv2

from automation import findtarget, flowfmt, pickcheck

from .errors import ToolError
from .geom import center as _center

def position_tolerance(box):
    """中心容許偏離的距離 (px): 壓縮失真讓框抖個 1-2px 是常態."""
    return max(6.0, 0.25 * min(box[2], box[3]))


def make_engine():
    """建構引擎 (載深度驗證模型; 載不起來會降級 coarse-only 並發警告)."""
    import warnings

    from subject_detection.engine import Engine
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Engine()


DRIFT_MARGIN = 80   # `停點差`: 沿宣告方向每邊至少外推這麼多 (流程尺度, 執行時跟著畫面倍率縮放)


def fixed_rect(box, size, anchor, scroll=None, drift=None, toward=None):
    """`固定矩形`: 挑中的框每邊外推框寬高的 50% (中心不變); 宣告捲動軸的那一軸拉到影片兩端,
    `停點差`那一軸每邊至少 DRIFT_MARGIN, `遞補方向` (toward) 那一端拉到影片邊緣;
    超出影片的部分裁掉 → (相對座標基準點的 [x, y, w, h], 被裁掉的邊 set)."""
    return expand_rect(box, (box[2], box[3]), size, anchor, scroll, drift, toward)


def expand_rect(box, tpl, size, anchor, scroll=None, drift=None, toward=None):
    """box 每邊外推 tpl (寬, 高) 的一半 (進位; drift 那一軸至少 DRIFT_MARGIN), 捲動軸那一軸拉到
    影片兩端, toward 那一端拉到影片邊緣, 超出影片的部分裁掉
    → (相對座標基準點的 [x, y, w, h], 被裁掉的邊 set)."""
    x, y, w, h = box
    W, H = size
    mx, my = math.ceil(tpl[0] / 2), math.ceil(tpl[1] / 2)
    if drift == "vertical":
        my = max(my, DRIFT_MARGIN)
    elif drift == "horizontal":
        mx = max(mx, DRIFT_MARGIN)
    x0, y0, x1, y1 = x - mx, y - my, x + w + mx, y + h + my
    if scroll == "vertical":
        y0, y1 = 0, H
    elif scroll == "horizontal":
        x0, x1 = 0, W
    if toward == "left":
        x0 = 0
    elif toward == "right":
        x1 = W
    elif toward == "up":
        y0 = 0
    elif toward == "down":
        y1 = H
    clipped = {side for side, out in (("left", x0 < 0), ("top", y0 < 0),
                                      ("right", x1 > W), ("bottom", y1 > H)) if out}
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    return flowfmt.rect_from_screen((x0, y0, x1 - x0, y1 - y0), anchor), clipped


class _Detector:
    """找圖目標模組要的偵測接縫 (query(範本名, 影像, color_check, expected_scale))."""

    def __init__(self, engine, lib):
        self.engine, self.lib = engine, lib

    def query(self, name, image, color_check=False, expected_scale=None):
        return self.engine.query(self.lib, name, image, color_check=color_check,
                                 expected_scale=expected_scale)


def detector(engine, images, config):
    """只要偵測接縫時 (量校準對、比對既有範本): 登錄 images ({名: 影像}) 後回傳 detector."""
    return Checker(engine, images, {}, [], {}, config, None, (1, 1)).detector


def color_modes(name, steps, extra=()):
    """引用這張範本的找圖目標用到的`比色`設定 (沒人引用＝只查不比色)."""
    tgts = list(extra)
    for s in steps:
        if findtarget.is_find(s):
            tgts.append(findtarget.target(s))
        if findtarget.uses_confirm_target(s):
            tgts.append(findtarget.confirm_target(s))
    modes = {bool(t.get("color")) for t in tgts if t.get("template") == name}
    return sorted(modes) or [False]


@dataclass
class _Member:
    """`共用矩形`的一個成員: 找圖目標 (同一個 dict, 之後寫進 within) 與它挑中的框."""
    tgt: dict
    frame: int
    origin: tuple | None
    label: str
    box: tuple | None        # 影片位置 (挑不到＝計畫的取材框; 既有範本挑不到＝None)
    picked: tuple | None     # 真的挑中的框 (挑不到＝None: 不查是否落在框內、不複查)
    shift: tuple


class Checker:
    """自我驗證: 建構時登錄範本並跑範本層級的檢查; `locate`/`locate_target` 在原點推算時
    逐一驗證找圖目標並算固定矩形.

    crops: {範本名: 影像 (流程尺度)}——計畫裁的新範本＋引用到的既有範本;
    templates: 計畫的範本 (有取材證據; 既有範本不在這裡, 不跑範本層級的檢查);
    anchor: `座標基準點`在影格上的位置; size: 影格 (寬, 高)。

    results: {範本名: {"reasons": [...], "boxes": {幀: 框或 None}}}; reasons
    為空＝通過。
    """

    def __init__(self, engine, crops, templates, steps, frames, config, anchor, size,
                 extra_targets=()):
        from subject_detection import make_library

        self.engine, self.templates, self.frames = engine, templates, frames
        self.anchor, self.size = anchor, size
        self.sizes = {n: (img.shape[1], img.shape[0]) for n, img in crops.items()}
        self.results = {n: {"reasons": [], "boxes": {}} for n in crops}
        self._registered = set()
        self._scale_checked = set()
        with tempfile.TemporaryDirectory(prefix="vtf_verify_") as tmp:
            paths = {}
            for i, (name, img) in enumerate(crops.items()):
                p = os.path.join(tmp, f"t{i:03d}.png")
                ok, buf = cv2.imencode(".png", img)
                if not ok:
                    raise ToolError(f"範本「{name}」無法編碼成 PNG")
                buf.tofile(p)
                paths[name] = p
            self.lib = make_library(paths, config, os.path.join(tmp, "registered"))
            for name in crops:
                try:   # 登錄產物載進記憶體, 暫存目錄刪掉後照樣能查
                    engine.register(self.lib, name)
                    self._registered.add(name)
                except Exception as e:  # 純色/無結構的框連登錄都過不了
                    self.results[name]["reasons"].append(
                        f"引擎無法登錄這張範本（{e}）")
        self.detector = _Detector(engine, self.lib)
        self.registered = frozenset(self._registered)
        self._cache = {}
        self._members = {}   # 共用矩形名 → [_Member] (挑過框、等 resolve_shared 算框)
        for name, t in templates.items():
            if name not in crops:
                continue
            if name in self._registered:
                for color in color_modes(name, steps, extra_targets):
                    self._check_template(name, t, color)
                    self._check_scale(name, t["frame"], color)
            if not t["clean"]:
                self.results[name]["reasons"].append("找不到乾淨影格（計畫標示）")

    def _matches(self, name, frame, color):
        key = (name, frame, color)
        if key not in self._cache:
            r = self.engine.query(self.lib, name, self.frames[frame],
                                  color_check=color, expected_scale=1.0)
            self._cache[key] = [tuple(int(v) for v in m.box) for m in r.matches]
        return self._cache[key]

    def _check_template(self, name, t, color):
        res = self.results[name]
        tol = position_tolerance(t["box"])
        checks = [(t["frame"], _center(t["box"]), "取材幀")]
        checks += [(p["frame"], tuple(p["at"]) if p["at"] else _center(t["box"]),
                    "出現幀") for p in t["present"]]
        for frame, want, label in checks:
            boxes = self._matches(name, frame, color)
            if not boxes:
                res["reasons"].append(f"{label}（第 {frame} 幀）找不到")
                continue
            near = min(boxes, key=lambda b: (_center(b)[0] - want[0]) ** 2
                       + (_center(b)[1] - want[1]) ** 2)
            gx, gy = _center(near)
            if ((gx - want[0]) ** 2 + (gy - want[1]) ** 2) ** 0.5 > tol:
                res["reasons"].append(
                    f"位置不符（第 {frame} 幀：預期中心 {want[0]},{want[1]}、"
                    f"找到 {gx},{gy}）")
            else:
                res["boxes"].setdefault(frame, near)
        for frame in t["absent"]:
            if self._matches(name, frame, color):
                res["reasons"].append(f"出現前就匹配（第 {frame} 幀不該找得到）")

    def _check_scale(self, name, frame, color):
        """`拾取檢查`的縮放餘裕: 那一幀 ×0.85 / ×1.15 各查一次 (pickcheck 的標準)."""
        key = (name, color)
        if key in self._scale_checked:
            return
        self._scale_checked.add(key)
        probe = {"template": name, "color": color}
        for w in pickcheck.scale_margin(self.detector, self.frames[frame], (0, 0),
                                        probe, anchor=None, scale=1.0):
            self.results[name]["reasons"].append(f"縮放餘裕：{w.text}")

    def locate_target(self, tgt, frame, origin, label, at=None, scroll=None,
                      fallback_box=None, shift=(0, 0), shared=None, drift=None, toward=None):
        """照找圖目標在 frame 上挑一次, 算固定矩形 → (挑中的框, within).

        tgt: 找圖目標 (pick near 已是相對 origin 的值, 沒有 within); 挑不到時用
        fallback_box (計畫的取材框) 算框並標待重拍。at: 計畫寫的點擊位置 (要落在挑中的框附近)。
        shift: 這一步的`對齊位移`——origin、at 是執行時的位置, 減掉它才是影片裡的位置;
        在影格上挑中的框加回它才算固定矩形, 回傳的框也是執行時的位置。
        shared: 引用的`共用矩形`名——只挑框、回傳 within None; `resolve_shared` 再把框寫進
        tgt (同一個 dict) 並跑檢查。drift / toward: `停點差`的軸 / `遞補方向` (見 fixed_rect)。
        """
        dx, dy = shift
        if origin is not None:
            origin = (origin[0] - dx, origin[1] - dy)
        if at is not None:
            at = [at[0] - dx, at[1] - dy]
        box, within = self._locate(tgt, frame, origin, label, at,
                                   (scroll, drift, toward), fallback_box, (dx, dy), shared)
        if box is not None and (dx, dy) != (0, 0):
            box = (box[0] + dx, box[1] + dy, box[2], box[3])
        return box, within

    def _locate(self, tgt, frame, origin, label, at, rule, fallback_box, shift, shared):
        """locate_target 在影片位置上的本體 (origin、at、回傳的框都是影片裡的位置);
        rule: (捲動軸, 停點差, 遞補方向)."""
        name = tgt["template"]
        res = self.results[name]
        size = self.sizes[name]
        if frame not in self.frames:
            raise ToolError(f"工具錯誤：第 {frame} 幀沒有讀進來")
        box = fallback_box
        picked = None
        if name in self._registered:
            if name not in self.templates:   # 引用的既有範本: 在它第一次被用的那一幀查縮放餘裕
                self._check_scale(name, frame, bool(tgt.get("color")))
            f = findtarget.find(tgt, self.detector, self.frames[frame], (0, 0),
                                origin=origin, scale=1.0)
            if f.picked is None:
                why = {"count": f"（挑選規則挑不到：只有 {len(f.matches)} 個匹配）"}.get(
                    f.reason, "")
                res["reasons"].append(f"{label}（第 {frame} 幀）找不到{why}")
                res["boxes"].setdefault(frame, None)
            else:
                picked = box = f.picked.box
                res["boxes"][frame] = box
                gx, gy = _center(box)
                if at is not None:
                    if abs(at[0] - gx) > box[2] or abs(at[1] - gy) > box[3]:
                        res["reasons"].append(
                            f"位置不符（{label}，第 {frame} 幀：點擊位置 {at[0]},{at[1]} "
                            f"離挑中的框 {gx},{gy} 太遠）")
                elif (name in self.templates and frame == self.templates[name]["frame"]
                      and fallback_box is not None):
                    want = _center(fallback_box)
                    if math.dist((gx, gy), want) > position_tolerance(fallback_box):
                        res["reasons"].append(
                            f"位置不符（{label}，第 {frame} 幀：挑中的是 {gx},{gy}，"
                            f"不是取材的 {want[0]},{want[1]}）")
        if shared is not None:
            self._members.setdefault(shared, []).append(
                _Member(tgt, frame, origin, label, box, picked, shift))
            return box, None
        if box is None:   # 引用的既有範本在這一幀找不到 (已標待重拍): 不寫固定矩形 (＝整個搜尋範圍)
            return fallback_box, None
        # 固定矩形照執行時的位置 (框加位移) 算
        moved = (box[0] + shift[0], box[1] + shift[1], box[2], box[3])
        within, clipped = fixed_rect(moved, self.size, self.anchor, *rule)
        for w in pickcheck.rect_margin(dict(tgt, within=within), size):
            if not clipped:
                raise ToolError(f"工具錯誤：{label} 的固定矩形沒過矩形餘裕：{w.text}")
        self._recheck(tgt, within, frame, origin, label, picked, shift)
        return box, within

    def _recheck(self, tgt, within, frame, origin, label, picked, shift):
        """加上固定矩形再挑一次要挑到同一個, 再跑`拾取檢查`的唯一 (挑不到的不查)."""
        if picked is not None:
            res = self.results[tgt["template"]]
            # 在影格上複查時基準點反向挪 (對齊位移), 框才落回影片位置
            anchor = (self.anchor[0] - shift[0], self.anchor[1] - shift[1])
            full = dict(tgt, within=within)
            f2 = findtarget.find(full, self.detector, self.frames[frame], (0, 0),
                                 origin=origin, scale=1.0, anchor=anchor)
            if (f2.picked is None or math.dist(_center(f2.picked.box), _center(picked))
                    > position_tolerance(picked)):
                res["reasons"].append(
                    f"加上固定矩形後挑到的不是同一個（{label}，第 {frame} 幀）")
            for w in pickcheck.unique(self.detector, self.frames[frame], (0, 0), full,
                                      anchor=anchor, scale=1.0, origin=origin):
                res["reasons"].append(f"唯一（{label}，第 {frame} 幀）：{w.text}")

    def resolve_shared(self, decls):
        """算每個`共用矩形`並寫進成員的 within (就地), 再對成員跑檢查 → {名: within}.

        decls: {名: 宣告}——影片像素宣告 {frame, box, scroll} (box 已是流程尺度的影格座標);
        same_as 的宣告帶 within (照抄來的, 相對座標基準點, 原樣用)。
        """
        out = {}
        for name, members in self._members.items():
            d = decls[name]
            copied = "within" in d
            if copied:
                within, clipped = list(d["within"]), set()
                where = flowfmt.rect_to_screen(within, self.anchor)
                what = f"照抄的框 {list(where)}（流程尺度、執行時的位置）"
            else:
                shifts = {m.shift for m in members}
                if len(shifts) > 1:
                    raise ToolError(
                        f"共用矩形「{name}」的成員有的在插入段第一次拖曳之前、有的在之後"
                        "（對齊位移不同），容器的位置對不上全部成員——拆成兩個共用矩形")
                dx, dy = shifts.pop()
                x, y, w, h = d["box"]
                where = (x + dx, y + dy, w, h)
                what = f"容器框 {d['box']}（第 {d['frame']} 幀）"
                # 挑不到框的成員 (引用的既有範本) 用範本圖的大小
                sizes = [m.box[2:] if m.box is not None else self.sizes[m.tgt["template"]]
                         for m in members]
                tpl = (max(w for w, _ in sizes), max(h for _, h in sizes))
                within, clipped = expand_rect(where, tpl, self.size, self.anchor,
                                              d.get("scroll"))
            for m in members:
                if m.picked is None:
                    continue
                x, y, w, h = m.box[0] + m.shift[0], m.box[1] + m.shift[1], *m.box[2:]
                if (x < where[0] or y < where[1] or x + w > where[0] + where[2]
                        or y + h > where[1] + where[3]):
                    raise ToolError(
                        f"共用矩形「{name}」：{m.label}在第 {m.frame} 幀挑中的框 "
                        f"{[x, y, w, h]} 有一部分在{what}外——"
                        + ("新成員不在同一個容器裡，或錄影畫面對不上：確認 same_as 指的那一組"
                           if copied else
                           "容器要框整個容器的所有格子（重框 box）；挑錯目標就改那一步的 "
                           "frame／at 或挑選規則"))
            for m in members:
                m.tgt["within"] = within
                for w in pickcheck.rect_margin(m.tgt, self.sizes[m.tgt["template"]]):
                    if copied:
                        raise ToolError(f"共用矩形「{name}」照抄的框對{m.label}餘裕不足：{w.text}"
                                        "——新成員的圖比同組既有的大；改用影片像素宣告新的共用矩形")
                    if not clipped:
                        raise ToolError(f"工具錯誤：{m.label}的共用矩形「{name}」沒過矩形餘裕："
                                        f"{w.text}")
                self._recheck(m.tgt, within, m.frame, m.origin, m.label, m.picked, m.shift)
            out[name] = within
        return out

    def finish(self):
        """全部驗證跑完後的最終結果 (原因去重、保序)."""
        for res in self.results.values():
            res["reasons"] = list(dict.fromkeys(res["reasons"]))
        return self.results


RETAKE_ADVICE = {
    "找不到乾淨影格": "在遊戲裡停在這個畫面、游標移開後，用編輯器的範本面板重新拾取",
    "縮放餘裕": "範本在縮放後貼近門檻（視窗模式／最大化會縮放畫面）；重截或裁小：框按鈕本體、"
             "避開會變的數字與透出的背景，或換一幀",
    "唯一": "固定矩形裡有多個同款：這張圖不能當參考點；換一張畫面上唯一的圖當參考點，"
          "或設挑選規則（第 N 個／最接近指定點）",
    "出現前就匹配": "範本框到了畫面上本來就有的東西；重新框只屬於這個按鈕的部分（文字、圖示）；"
               "只差顏色時開比色",
    "位置不符": "畫面上可能有長得一樣的東西；框大一點把周邊有辨識度的部分包進來，"
            "或用挑選規則指定是哪一個",
    "加上固定矩形後": "框附近有同款圖；換一張唯一的圖或設挑選規則",
    "找不到": "範本可能框到空白處或被游標/特效污染；換一幀或重新框按鈕本體；"
           "有設挑選規則時確認設定",
    "引擎無法登錄": "範本沒有可辨識的結構（純色）；改框有文字或圖示的地方",
}


def advice(reasons):
    """依原因給重拍建議 (同一建議只說一次)."""
    out = []
    for why in reasons:
        for key, tip in RETAKE_ADVICE.items():   # 由具體到籠統, 取第一個符合的
            if key in why:
                if tip not in out:
                    out.append(tip)
                break
    return out or ["用編輯器的範本面板重新拾取這張範本"]

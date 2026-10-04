"""自我驗證: 用引擎公開 API 對影格重跑每張範本, 沒過的標`待重拍`.

範本經 `make_library` + `Engine.register` 一張一張登錄 (一張登錄失敗不拖垮
其他張), 再以 `Engine.query` 在指定影格上查詢; 搜尋區域就是整張影格
(影片＝遊戲畫面＝搜尋範圍)。

每張範本要通過的檢查 (以引用它的找圖目標用到的每一種`比色`設定各查一次):

- 取材幀與 present 幀: 有匹配落在預期位置附近 (預設＝裁切框中心,
  present 可寫明新位置)——同款多張時其他位置也有匹配不算錯
- absent 幀 (還沒出現的那幾幀): 整張影格上沒有任何匹配
- 計畫標示 clean: false (找不到乾淨影格): 不論結果都待重拍

引用它的每個找圖步驟, 在該步驟的 frame 上照**步驟的`找圖目標`**完整執行一次
(與執行器同一個模組: 裁限定範圍 → 查詢 → 比色 → 挑選規則, 原點用組裝推算的
那一步之前的原點): 要挑得到, 且步驟的點擊位置 `at` 落在挑中的框附近 (框外最多
再一個框寬高; 沒寫 at 而該幀就是取材幀時, 挑中的要是取材的那一個)——挑中的框就是
原點推算用的框, 挑錯同款圖偏移就全錯。驗證通過＝執行時會挑到同一個。
"""
from __future__ import annotations

import os
import tempfile

import cv2

from automation import findtarget

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


def frames_needed(templates, steps):
    """驗證要讀的影格編號."""
    need = set()
    for t in templates.values():
        need.add(t["frame"])
        need.update(p["frame"] for p in t["present"])
        need.update(t["absent"])
    for s in steps:
        if s["type"] == "find_click":
            need.add(step_frame(s, templates))
    return need


def step_frame(step, templates):
    """找圖步驟看的是哪一幀 (預設＝範本的取材幀)."""
    return step.get("frame", templates[step["template"]]["frame"])


def _color_modes(name, steps, extra=()):
    """引用這張範本的找圖目標用到的`比色`設定 (沒人引用＝只查不比色).

    extra: 流程層級的找圖目標 (忙碌指示)。
    """
    modes = {bool(t.get("colorCheck")) for t in extra
             if t.get("template") == name}
    for s in steps:
        if s["type"] == "find_click" and s["template"] == name:
            modes.add(bool(s.get("colorCheck")))
        cfm = s.get("confirmTarget")
        if cfm and cfm.get("template") == name:
            modes.add(bool(cfm.get("colorCheck")))
    return sorted(modes) or [False]


class _Detector:
    """找圖目標模組要的偵測接縫 (query(範本名, 影像, color_check, expected_scale))."""

    def __init__(self, engine, lib):
        self.engine, self.lib = engine, lib

    def query(self, name, image, color_check=False, expected_scale=None):
        return self.engine.query(self.lib, name, image, color_check=color_check,
                                 expected_scale=expected_scale)


class Checker:
    """自我驗證: 建構時登錄範本並跑範本層級的檢查; `locate` 在原點推算時
    逐步驗證找圖步驟 (要知道那一步之前的原點, 才能照找圖目標挑).

    results: {範本名: {"reasons": [...], "boxes": {幀: 框或 None}}}; reasons
    為空＝通過。boxes 是各檢查幀實際用到的框 (影片像素; 步驟幀＝挑中的那個)。
    """

    def __init__(self, engine, crops, templates, steps, frames, config,
                 extra_targets=()):
        from subject_detection import make_library

        self.engine, self.templates, self.frames = engine, templates, frames
        self.results = {n: {"reasons": [], "boxes": {}} for n in templates}
        self._registered = set()
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
            for name in templates:
                try:   # 登錄產物載進記憶體, 暫存目錄刪掉後照樣能查
                    engine.register(self.lib, name)
                    self._registered.add(name)
                except Exception as e:  # 純色/無結構的框連登錄都過不了
                    self.results[name]["reasons"].append(
                        f"引擎無法登錄這張範本（{e}）")
        self.detector = _Detector(engine, self.lib)
        self.registered = frozenset(self._registered)
        self._cache = {}
        for name, t in templates.items():
            if name in self._registered:
                for color in _color_modes(name, steps, extra_targets):
                    self._check_template(name, t, color)
            if not t["clean"]:
                self.results[name]["reasons"].append("找不到乾淨影格（計畫標示）")

    def _matches(self, name, frame, color):
        key = (name, frame, color)
        if key not in self._cache:
            # 影片尺度＝流程尺度: 與倍率 1 的執行同樣以預期尺度 1 查詢
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

    def locate(self, i, step, target, origin):
        """照找圖步驟的找圖目標在它那一幀挑一次; 回傳挑中的框 (影片像素),
        挑不到或範本登錄失敗時回傳取材的裁切框 (範本會標待重拍).

        target: 該步驟的找圖目標 (像素設定已換成相對原點/搜尋範圍的影片像素);
        origin: 這一步之前的原點 (影片像素)。
        """
        name = step["template"]
        t = self.templates[name]
        res = self.results[name]
        if name not in self._registered:
            return t["box"]
        no, frame = i + 1, step_frame(step, self.templates)
        f = findtarget.find(target, self.detector, self.frames[frame], (0, 0),
                            origin=origin, scale=1.0)
        if f.picked is None:
            why = {"count": f"（挑選規則挑不到：只有 {len(f.matches)} 個匹配）",
                   "none": "（限定範圍內沒有）" if f.limit else ""}.get(f.reason, "")
            res["reasons"].append(
                f"步驟 {no} 該點的那一幀（第 {frame} 幀）找不到{why}")
            res["boxes"].setdefault(frame, None)
            return t["box"]
        got = f.picked.box
        res["boxes"][frame] = got
        gx, gy = _center(got)
        if "at" in step:
            if abs(step["at"][0] - gx) > got[2] or abs(step["at"][1] - gy) > got[3]:
                res["reasons"].append(
                    f"位置不符（步驟 {no} 第 {frame} 幀：點擊位置 "
                    f"{step['at'][0]},{step['at'][1]} 離挑中的框 {gx},{gy} 太遠）")
        elif frame == t["frame"]:
            want = _center(t["box"])
            if ((gx - want[0]) ** 2 + (gy - want[1]) ** 2) ** 0.5 \
                    > position_tolerance(t["box"]):
                res["reasons"].append(
                    f"位置不符（步驟 {no} 第 {frame} 幀：挑中的是 {gx},{gy}，"
                    f"不是取材的 {want[0]},{want[1]}）")
        return got

    def finish(self):
        """原點推算 (逐步 locate) 跑完後的最終結果 (原因去重、保序)."""
        for res in self.results.values():
            res["reasons"] = list(dict.fromkeys(res["reasons"]))
        return self.results


RETAKE_ADVICE = {
    "找不到乾淨影格": "在遊戲裡停在這個畫面、游標移開後，用編輯器的範本面板重新拾取",
    "出現前就匹配": "範本框到了畫面上本來就有的東西；重新框只屬於這個按鈕的部分（文字、圖示）；"
               "只差顏色時開比色",
    "位置不符": "畫面上可能有長得一樣的東西；框大一點把周邊有辨識度的部分包進來，"
            "或用挑選規則／限定範圍指定是哪一個",
    "找不到": "範本可能框到空白處或被游標/特效污染；換一幀或重新框按鈕本體；"
           "有設限定範圍或挑選規則時確認設定",
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

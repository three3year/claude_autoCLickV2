"""`交付報告` (流程資料夾裡的 `交付報告/`): 總覽＋每個頂層區段一份.

app 不讀不寫, 流程存檔格式不為它增加任何欄位。報告用內容指稱步驟 (範本名＋動作),
不寫步驟編號——補充插入後編號會位移。

檔名 (`sections`): 一個頂層區段一份, 取區段開頭找圖的範本名 (`分岔-公告关闭.md`、
`重複-标题_制造站.md`); 兩個區段之間連續的零散頂層步驟併成一份, 用那段第一個找圖的範本
命名 (`步驟-基建入口.md`); 撞名加序號。總覽依流程順序連到各份。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import flowfile
from automation import findtarget
from automation.runner import branch_layout, enclosing_end

from . import labels
from . import verify as verify_mod

DIR = "交付報告"
OVERVIEW = "總覽.md"
OLD = "舊紀錄.md"
NO_KEYS = "流程不支援按鍵，請改用點擊"


# ================= 頂層區段切法 (工具與一次性拆檔腳本共用) =================

@dataclass
class Section:
    name: str       # 檔名 (不含 .md)
    kind: str       # "repeat" / "branch" / "steps"
    start: int      # 平面步驟索引 [start, end)
    end: int

    @property
    def file(self):
        return self.name + ".md"


_PREFIX = {"repeat": "重複", "branch": "分岔", "steps": "步驟"}
_KIND_OF = {"repeat_start": "repeat", "branch_start": "branch"}


def section_end(steps, i):
    """steps[i] (區段開頭) 這個區段結束之後的索引; 標記不成對＝清單結尾."""
    end = enclosing_end(steps, i)
    return len(steps) if end is None else end + 1


def sections(steps):
    """記憶體的平面步驟 → 頂層區段清單 (依流程順序; 名稱已處理撞名)."""
    out, taken = [], []
    i = 0
    while i < len(steps):
        t = steps[i]["type"]
        if t in _KIND_OF:
            kind, end = _KIND_OF[t], section_end(steps, i)
        else:
            kind, end = "steps", i
            while end < len(steps) and steps[end]["type"] not in _KIND_OF:
                end += 1
        first = next((findtarget.template(s) for s in steps[i:end]
                      if findtarget.is_find(s)), None)
        stem = f"{_PREFIX[kind]}-{first}" if first else \
            f"{_PREFIX[kind]}-{labels.STEP.get(steps[i]['type'], _PREFIX[kind])}"
        name = flowfile.free_name(flowfile.clean_name(stem), taken)
        taken.append(name)
        out.append(Section(name, kind, i, end))
        i = end
    return out


def section_of(secs, i):
    return next(s for s in secs if s.start <= i < s.end)


# ================= 步驟的內容描述 =================

_CONFIRM = {"gone": "，點到目標圖消失", "next": "，點到下一步的圖出現",
            "appear": "，點到確認圖出現"}
_POINTER_CONFIRM = {"gone": "，做到原點的圖離開", "next": "，做到下一步的圖出現",
                    "appear": "，做到確認圖出現"}
_NF = {"stop": "停止", "skip": "跳過", "break": "跳出區段"}


def _rect_text(tgt):
    w = tgt.get("within")
    return f"，固定矩形 ({w[0]:+d},{w[1]:+d}) {w[2]}×{w[3]}" if w else ""


def describe(s):
    """一步的一行摘要 (內容指稱, 偏移是流程尺度)."""
    t = s["type"]
    if t in findtarget.FIND_TYPES:
        tgt = findtarget.target(s)
        text = labels.label(s)
        tags = [x for x in findtarget.tags(tgt) if x != "限定"]
        if tags:
            text += f"〔{'、'.join(tags)}〕"
        ox, oy = s["offset"]
        if ox or oy:
            text += f"，偏移 {ox:+d},{oy:+d}"
        if t == "find_click" and s["confirm"] != "none":
            text += _CONFIRM[s["confirm"]]
            if s["confirm"] == "appear":
                text += f"「{findtarget.confirm_template(s)}」"
        text += f"（逾時 {s['timeout']:g}s→{_NF[s['on_fail']]}）"
        if s.get("busy_check"):
            text += "〔忙碌檢查〕"
        if not s["update_origin"]:
            text += "〔不更新原點〕"
        return text
    if t in ("click", "drag"):
        if t == "click":
            text = "座標點擊 相對原點 {:+d},{:+d}".format(*s["click"])
        else:
            text = "拖曳 相對原點 {:+d},{:+d} → {:+d},{:+d}".format(*s["drag"], *s["to"])
        if s["confirm"] != "none":
            text += _POINTER_CONFIRM[s["confirm"]]
            if s["confirm"] == "appear":
                text += f"「{findtarget.confirm_template(s)}」"
            text += f"（逾時 {s['timeout']:g}s→{_NF[s['on_fail']]}）"
        if s.get("busy_check"):
            text += "〔忙碌檢查〕"
        if t == "click" and not s["update_origin"]:
            text += "〔不更新原點〕"
        return text
    if t == "wait":
        return f"等待 {s['wait']:g} 秒"
    return {"repeat_start": f"重複 {s.get('repeat')} 次：", "branch_start": "分岔：",
            "branch_or": "或", "repeat_end": "（重複結束）", "branch_end": "（分岔結束）"}.get(t, t)


def outline(steps, start=0, end=None):
    """平面步驟 → 縮排的條列 (區段巢狀照縮排; 不寫步驟編號)."""
    end = len(steps) if end is None else end
    lines, depth = [], 0
    for i in range(start, end):
        s = steps[i]
        t = s["type"]
        pad = "  " * depth
        if t == "repeat_start":
            lines.append(f"{pad}- 重複 {s['repeat']} 次：")
            depth += 1
        elif t == "branch_start":
            lay = branch_layout(steps, i)
            one = lay is not None and len(lay[0]) == 1
            lines.append(f"{pad}- " + ("分岔（只有一個分支：找到第一步那張才往下做）：" if one
                                       else "分岔（先找到哪個走哪個）："))
            depth += 1
        elif t in ("repeat_end", "branch_end"):
            depth -= 1
            if s.get("on_break") == "break":
                lines.append(f"{'  ' * (depth + 1)}- （因找不到跳出到這裡時，連外層一起跳出）")
        elif t == "branch_or":
            lines.append(f"{'  ' * (depth - 1)}  - 或：")
        else:
            lines.append(f"{pad}- {describe(s)}")
    return lines


# ================= 組裝產出的報告 =================

def _link(sec):
    return f"[{sec.name}]({sec.file})"


def _calibration_line(res):
    cal = res["calibration"]
    a, b = cal["pair"]
    text = (f"{a} × {b}，基準距離 {float(cal['baseline']):.1f}px"
            f"（第 {res['calibration_frame']} 幀量得）")
    fb = res.get("fallback")
    if fb:
        text += (f"；備用校準對：{fb['pair'][0]} × {fb['pair'][1]}，基準距離 "
                 f"{float(fb['baseline']):.1f}px，對座標基準點的偏移 "
                 f"({fb['offset'][0]:+d},{fb['offset'][1]:+d})")
    elif res.get("fallback_problem"):
        text += f"；**備用校準對量不到**（{res['fallback_problem']}），流程不帶備用對"
    else:
        text += "；沒有備用校準對"
    return text


def _busy_line(busy):
    if busy:
        return f"「{busy['template']}」{_rect_text(busy)}"
    return "沒有（補做只看固定的補做間隔；計畫不能勾忙碌檢查）"


def _bullets(items, empty="無。"):
    return [f"- {x}" for x in items] or [empty]


SHARED = "## 共用矩形"
_SCROLL_ZH = {"vertical": "直向", "horizontal": "橫向", None: "沒有"}
_SHARED_HELP = ("這幾組目標落在同一個容器裡、每次出現在哪一格不一定，各組共用一個固定矩形"
                "（容器框每邊外推最大成員圖框的一半；宣告捲動軸的那一軸拉到影片兩端）。"
                "分組是影片轉流程判斷的，請確認；flow.yaml 只記各步驟一模一樣的固定矩形，"
                "要改框時同組每一步一起改。")


def shared_line(name, info):
    """一個共用矩形的一行說明 (名字、理由、成員、捲動軸、框從哪來)."""
    why = info["why"].rstrip("。")
    members = "、".join(text for _, text in info["members"])
    text = f"「{name}」：{why}。成員：{members}；"
    if info.get("source"):
        text += f"沿用{info['source']}那一步的共用矩形"
    else:
        text += f"捲動軸：{_SCROLL_ZH[info.get('scroll')]}；容器框 {info['box']}" \
                f"（第 {info['frame']} 幀）"
    if info.get("within"):
        text += _rect_text(info)
    return text


def _shared_homes(res, secs):
    """{名: 第一個成員所在的區段 (只有忙碌指示＝None)}."""
    homes = {}
    for name, info in (res.get("shared_rects") or {}).items():
        idx = [i for i, _ in info["members"] if i is not None]
        homes[name] = section_of(secs, min(idx)) if idx else None
    return homes


def render(res, plan, steps):
    """組裝結果 → {檔名: 文字} (總覽＋各區段)."""
    secs = sections(steps)
    by_sec = {sec.name: {"retake": [], "scroll": [], "unseen": [], "unchecked": [],
                         "shared": []}
              for sec in secs}
    used_in = {}
    for i, s in enumerate(steps):
        sec = section_of(secs, i)
        names = []
        if findtarget.is_find(s):
            names.append(findtarget.template(s))
        if findtarget.uses_confirm_target(s):
            names.append(findtarget.confirm_template(s))
        for n in names:
            used_in.setdefault(n, [])
            if sec.name not in used_in[n]:
                used_in[n].append(sec.name)
    for n in res["retake"]:
        for sec_name in used_in.get(n, []):
            by_sec[sec_name]["retake"].append(n)
    cal = res["calibration"]
    fb = res.get("fallback")
    for n in [*cal["pair"], *(fb["pair"] if fb else [])]:
        used_in.setdefault(n, []).append("（校準對）")
    if res["busy"]:
        used_in.setdefault(res["busy"]["template"], []).append("（忙碌指示）")
    for key, items in (("scroll", res["scroll_confirm"]), ("unseen", res["busy_unseen"]),
                       ("unchecked", res["busy_unchecked"])):
        for i, text in items:
            by_sec[section_of(secs, i).name][key].append(text)
    sec_map = {sec.name: sec for sec in secs}
    homes = _shared_homes(res, secs)
    for name, info in (res.get("shared_rects") or {}).items():
        home = homes[name]
        if home is not None:
            by_sec[home.name]["shared"].append((True, shared_line(name, info)))
        others = []
        for i, _ in info["members"]:
            sec = section_of(secs, i) if i is not None else home
            if sec is not home and sec not in others:
                others.append(sec)
        for sec in others:
            by_sec[sec.name]["shared"].append((False, f"「{name}」：見 {_link(home)}"))

    files = {OVERVIEW: _overview(res, plan, secs, by_sec, used_in, sec_map, homes)}
    for sec in secs:
        files[sec.file] = _section_file(res, sec, steps, by_sec[sec.name], plan)
    return files


def _retake_rows(res, names, used_in=None, sec_map=None):
    rows = ["| 範本 | 原因 | 重拍建議 |" + (" 用在 |" if used_in else ""),
            "|---|---|---|" + ("---|" if used_in else "")]
    for n in names:
        why = res["retake"][n]
        row = f"| {n} | {'；'.join(why)} | {'；'.join(verify_mod.advice(why))} |"
        if used_in:
            row += " " + "、".join(_link(sec_map[x]) if x in sec_map else x
                                   for x in used_in.get(n, [])) + " |"
        rows.append(row)
    return rows


_SCROLL_HELP = ("這些找圖步驟所在的段落有拖曳，但計畫沒宣告捲動軸：固定矩形只在影片那一次的位置"
                "外推 50%。如果它們其實在捲動清單裡（內容每次會變），請在 app 把框沿捲動方向拉長，"
                "或在計畫補 scroll 重新組裝。")


def _confirm_block(scroll, unseen, unchecked):
    lines = ["### 捲動清單", ""]
    lines += ([_SCROLL_HELP, ""] + _bullets(scroll)) if scroll else ["無。"]
    lines += ["", "### 勾了忙碌檢查、但之後的影格沒看到忙碌指示", ""]
    lines += (["確認這一步真的會讓遊戲忙；不會的話取消勾選（每次多等約 1 秒）。", ""]
              + _bullets(unseen)) if unseen else ["無。"]
    lines += ["", "### 沒勾忙碌檢查、但之後的影格看到忙碌指示", ""]
    lines += (["這一步之後遊戲在忙；下一個輸入可能被吃掉，考慮勾忙碌檢查。", ""]
              + _bullets(unchecked)) if unchecked else ["無。"]
    return lines


def _overview(res, plan, secs, by_sec, used_in, sec_map, homes):
    lines = [f"# 交付報告：{os.path.basename(res['flow_path'])}", "",
             "總覽；每個頂層區段另有一份，改哪段只讀那一份。步驟用內容指稱（範本名＋動作），"
             "不寫步驟編號。", "",
             "## 概要", "",
             f"- 來源影片：`{res['video']}`（{res['video_size'][0]}×{res['video_size'][1]}；"
             "影片尺度就是流程尺度）",
             "- 搜尋範圍：不寫（＝全螢幕；執行前在 app 裡框）",
             f"- 校準對：{_calibration_line(res)}",
             f"- 忙碌指示：{_busy_line(res['busy'])}",
             f"- 步驟數：{res['steps']}；範本數：{res['templates']}"]
    if res["verification"] == "coarse":
        lines.append("- **自我驗證不完整**：深度驗證模型無法載入，引擎只剩粗篩；「找得到」可能是誤判，"
                     "請在遊戲裡實跑確認每一個找圖步驟")
    else:
        lines.append("- 自我驗證：每張範本都用引擎（粗篩＋深度驗證）對影格重跑過；每個找圖目標都有"
                     "固定矩形（挑中的框每邊外推 50%"
                     + ("；共用矩形的成員用容器框算，見下面「共用矩形」" if homes else "") + "）")
    if res["unused"]:
        lines.append(f"- 沒有步驟引用、沒放進流程的範本：{'、'.join(res['unused'])}")
    lines += ["", "## 各段報告（依流程順序）", ""]
    for sec in secs:
        lines.append(f"- {_link(sec)}")
    if homes:
        lines += ["", SHARED, "", _SHARED_HELP, ""]
        for name, home in homes.items():
            lines.append(f"- 「{name}」：{_link(home)}" if home is not None
                         else f"- {shared_line(name, res['shared_rects'][name])}")
    lines += ["", "## 待重拍", ""]
    if res["retake"]:
        lines += ["這些範本沒通過自我驗證；步驟照寫，在 app 重截同名範本即可。", ""]
        lines += _retake_rows(res, list(res["retake"]), used_in, sec_map)
    else:
        lines.append("無——每張範本都通過驗證。")
    lines += ["", "## 待確認", ""]

    def tagged(key):
        return [f"{t}（{_link(sec)}）" for sec in secs for t in by_sec[sec.name][key]]
    lines += _confirm_block(tagged("scroll"), tagged("unseen"), tagged("unchecked"))
    notes = plan.report
    lines += ["", "## 分岔建議", ""]
    lines += _bullets(notes["branches"],
                      "無。影片裡沒出現的彈窗不會被加成分岔；實跑卡住時再補。")
    lines += ["", f"## 無法用點擊解釋的畫面變化（{NO_KEYS}）", ""]
    lines += _bullets(notes["unexplained"])
    if notes["notes"]:
        lines += ["", "## 其他說明", ""] + _bullets(notes["notes"])
    return "\n".join(lines) + "\n"


def _section_file(res, sec, steps, mine, plan):
    lines = [f"# {sec.name}", "", f"[← 總覽]({OVERVIEW})", "",
             "## 這段做什麼", ""]
    lines += outline(steps, sec.start, sec.end)
    lines += ["", "## 怎麼建的", "",
              f"影片轉流程從 `{os.path.basename(res['video'])}` 量出來：找圖的框是那一步那一幀上"
              "實際挑中的框，固定矩形每邊外推 50%；座標點擊與拖曳是影片位置減原點。", ""]
    for i in range(sec.start, sec.end):
        f = res["frames"].get(i)
        if f is not None:
            lines.append(f"- {describe(steps[i])}：第 {f} 幀")
    if mine["shared"]:
        lines += ["", SHARED, ""]
        if any(full for full, _ in mine["shared"]):   # 只有指過去的那幾行就不重複說明
            lines += [_SHARED_HELP, ""]
        lines += _bullets([text for _, text in mine["shared"]])
    lines += ["", "## 已知風險", ""]
    risks = []
    if any(steps[i]["type"] == "drag" for i in range(sec.start, sec.end)):
        risks.append("有拖曳捲動：後面的找圖與點擊依賴捲到的位置；清單長度變了要重錄或改框")
    if res["verification"] == "coarse":
        risks.append("自我驗證只有粗篩")
    lines += _bullets(risks, "無自動判斷得出的風險；實跑發現後補在這裡。")
    lines += ["", "## 待重拍", ""]
    lines += _retake_rows(res, mine["retake"]) if mine["retake"] else ["無。"]
    lines += ["", "## 待確認", ""]
    lines += _confirm_block(mine["scroll"], mine["unseen"], mine["unchecked"])
    return "\n".join(lines) + "\n"


def write(folder, files):
    """把 {檔名: 文字} 寫進 <folder>/交付報告/."""
    d = os.path.join(folder, DIR)
    os.makedirs(d, exist_ok=True)
    for name, text in files.items():
        with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


# ================= 補充: 更新插入處那份與總覽 =================

def add_under(text, heading, lines):
    """在 `heading` 這一節的尾端加幾行 (節裡只有「無。」時換掉它); 沒有這節就加在檔尾."""
    rows = text.split("\n")
    try:
        h = rows.index(heading)
    except ValueError:
        body = text.rstrip("\n")
        return body + "\n\n" + heading + "\n\n" + "\n".join(lines) + "\n"
    end = next((j for j in range(h + 1, len(rows)) if re.match(r"#{1,2} ", rows[j])),
               len(rows))
    block = rows[h + 1:end]
    if [r for r in block if r.strip()] in (["無。"], ["無"]):
        block = [""]
    while block and not block[-1].strip():
        block.pop()
    if not block:
        block = [""]
    block += lines + [""]
    return "\n".join(rows[:h + 1] + block + rows[end:])


def replace_under(text, heading, lines):
    """把 `heading` 這一節的內容整個換成 lines; 沒有這節就加在檔尾."""
    rows = text.split("\n")
    try:
        h = rows.index(heading)
    except ValueError:
        return add_under(text, heading, lines)
    end = next((j for j in range(h + 1, len(rows)) if re.match(r"#{1,2} ", rows[j])),
               len(rows))
    return "\n".join(rows[:h + 1] + [""] + lines + [""] + rows[end:])


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


_MARKERS = ("repeat_end", "branch_or", "branch_end")


def supplement(folder, old_steps, steps, seg, note, retake, confirm, shared=()):
    """補充插入後更新 `交付報告/`: 插入處那份與總覽 (沒有就建一份最小的).

    old_steps / steps: 插入前後的整份步驟; seg: 插入段在插入後的平面索引 [start, end);
    note: 這次補充的一行說明; retake: [(範本, 原因)]; confirm: [(標題, 文字)];
    shared: [(名, 共用矩形說明 (見 `shared_line`))]。
    插入處那份: 插入段併進既有的頂層段落時用那段**插入前**的檔名 (插入不會讓別段的序號位移
    而寫錯檔); 插入段自成一個頂層區段時開一份新的 (名字避開已有的檔)。那份的「這段做什麼」
    照插入後的流程重寫, 說明寫進「補充」。回傳 {檔名: 新文字}——呼叫端負責寫檔。
    """
    d = os.path.join(folder, DIR)
    secs = sections(steps)
    new_sec = section_of(secs, seg[0])
    if new_sec.start == seg[0] and new_sec.end == seg[1]:
        taken = [fn[:-3] for fn in (os.listdir(d) if os.path.isdir(d) else [])
                 if fn.endswith(".md")] + [x.name for x in sections(old_steps)]
        sec = Section(flowfile.free_name(new_sec.name, taken), new_sec.kind,
                      new_sec.start, new_sec.end)
        old = None
    else:
        old_secs = sections(old_steps)
        # 插入點前一步 (插入前後索引相同); 插在最前面就用原本的第一步
        old_sec = section_of(old_secs, max(seg[0] - 1, 0))
        sec = Section(old_sec.name, new_sec.kind, new_sec.start, new_sec.end)
        old = _read(os.path.join(d, sec.file))
    if old is None:
        old = f"# {sec.name}\n\n[← 總覽]({OVERVIEW})\n\n## 這段做什麼\n"
    text = replace_under(old, "## 這段做什麼", outline(steps, sec.start, sec.end))
    seg_text = "；".join(describe(s) for s in steps[seg[0]:seg[1]] if s["type"] not in _MARKERS)
    before = next((describe(steps[j]) for j in range(seg[0] - 1, -1, -1)
                   if steps[j]["type"] not in _MARKERS), "流程開頭")
    text = add_under(text, "## 補充", [f"- 在「{before}」之後插入：{seg_text}。{note}"])
    if retake:
        text = add_under(text, "## 待重拍",
                         [f"- {n_}：{'；'.join(why)}（{'；'.join(verify_mod.advice(why))}）"
                          for n_, why in retake])
    if confirm:
        text = add_under(text, "## 待確認", [f"- {k}：{v}" for k, v in confirm])
    if shared:
        text = add_under(text, SHARED, [f"- {shared_line(n_, info)}" for n_, info in shared])
    files = {sec.file: text}
    ov = _read(os.path.join(d, OVERVIEW))
    if ov is None:
        ov = (f"# 交付報告：{os.path.basename(folder)}\n\n總覽；每個頂層區段另有一份。\n\n"
              "## 各段報告（依流程順序）\n\n"
              + "\n".join(f"- {_link(s)}" for s in secs if s is not new_sec) + "\n")
    if f"]({sec.file})" not in ov:
        ov = add_under(ov, "## 各段報告（依流程順序）", [f"- {_link(sec)}"])
    ov = add_under(ov, "## 補充", [f"- {_link(sec)}：插入 {seg_text}。{note}"])
    if retake:
        ov = add_under(ov, "## 待重拍", [f"- {n_}（{_link(sec)}）：{'；'.join(why)}"
                                       for n_, why in retake])
    if confirm:
        ov = add_under(ov, "## 待確認", [f"- {k}（{_link(sec)}）：{v}" for k, v in confirm])
    if shared:
        ov = add_under(ov, SHARED, [f"- {_link(sec)}：{shared_line(n_, info)}"
                                    for n_, info in shared])
    files[OVERVIEW] = ov
    return files

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


_DRIFT_ZH = {"vertical": "直向", "horizontal": "橫向"}
_SHIFT_ZH = {"left": ("往左", "左"), "right": ("往右", "右"), "up": ("往上", "上"),
             "down": ("往下", "下")}


def loosened_text(kind, value):
    """`停點差`／`遞補方向`的一句說明 (kind: "drift"/"shift")."""
    if kind == "drift":
        return (f"容許停點差（{_DRIFT_ZH[value]}每邊至少外推 {verify_mod.DRIFT_MARGIN} px，"
                "吸收拖曳停點每次不同）")
    way, end = _SHIFT_ZH[value]
    return f"遞補方向{way}（框的{end}端拉到影片邊緣）"


def loosened_lines(steps, items):
    """[(索引, 鍵, 值)] → 每步一行「<內容指稱>：<說明>」."""
    return [f"{labels.label(steps[i])}：{loosened_text(k, v)}" for i, k, v in items]


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


_SCROLL_HELP = ("這些找圖步驟所在的段落有拖曳，但計畫沒宣告捲動軸或停點差：固定矩形只在影片那一次的"
                "位置外推 50%。如果它們其實在捲動清單裡（內容每次會變），請在 app 把框沿捲動方向拉長，"
                "或在計畫補 scroll 重新組裝；在被拖過的清單裡、內容不變只是停點每次不同，補 drift"
                "（停點差）。")


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
                     + ("；共用矩形的成員用容器框算，見下面「共用矩形」" if homes else "")
                     + ("；容許停點差、用了遞補方向的另外放寬，見各段報告「怎麼建的」"
                        if res.get("loosened") else "") + "）")
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
    mine_loose = [x for x in res.get("loosened") or [] if sec.start <= x[0] < sec.end]
    if mine_loose:
        lines += ["", "固定矩形另外放寬的找圖（落在被拖過的清單或只往一邊遞補的一排裡，影片轉流程判斷的，"
                  "請確認）：", ""]
        lines += _bullets(loosened_lines(steps, mine_loose))
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

_NONE = re.compile(r"無(。|——|$)")
EXTRA = "### 補充"


def _drop_empty(block):
    """拿掉寫「無」的那幾行 (「無。」「無——…」) 與因此變空的 ### 小節, 連續空行併成一行."""
    block = [r for r in block if not _NONE.match(r.strip())]
    out = []
    for k, r in enumerate(block):
        if r.startswith("### "):
            rest = block[k + 1:]
            nxt = next((j for j, x in enumerate(rest) if x.startswith("### ")), len(rest))
            if not any(x.strip() for x in rest[:nxt]):
                continue
        if not r.strip() and out and not out[-1].strip():
            continue
        out.append(r)
    return out


def add_under(text, heading, lines):
    """在 `heading` 這一節的尾端加幾行 (拿掉原本寫「無」的那行與空的小節; 節裡還有別的 ### 小節時
    加在「### 補充」底下, 不讓新條目看起來屬於最後一個小節); 沒有這節就加在檔尾."""
    rows = text.split("\n")
    try:
        h = rows.index(heading)
    except ValueError:
        body = text.rstrip("\n")
        return body + "\n\n" + heading + "\n\n" + "\n".join(lines) + "\n"
    end = next((j for j in range(h + 1, len(rows)) if re.match(r"#{1,2} ", rows[j])),
               len(rows))
    block = _drop_empty(rows[h + 1:end])
    while block and not block[-1].strip():
        block.pop()
    subs = [r for r in block if r.startswith("### ")]
    if subs and subs[-1] != EXTRA:
        block += ["", EXTRA]
    # 接在既有條目後面不空行 (同一個清單); 接在小節標題或說明文字後面空一行
    gap = [""] if block and not block[-1].startswith("- ") else []
    block = (block or [""]) + gap + lines + [""]
    return "\n".join(rows[:h + 1] + block + rows[end:])


def insert_link(text, heading, line, after=None, before=None):
    """在 `heading` 清單裡照流程順序放一行連結: 放在連到 after 那一行之後, 不然 before 那一行之前,
    都找不到才接在最後 (after / before: 前後段落的檔名)."""
    rows = text.split("\n")
    try:
        h = rows.index(heading)
    except ValueError:
        return add_under(text, heading, [line])
    end = next((j for j in range(h + 1, len(rows)) if re.match(r"#{1,2} ", rows[j])),
               len(rows))
    for target, offset in ((after, 1), (before, 0)):
        if target is None:
            continue
        at = next((j for j in range(h + 1, end) if f"]({target})" in rows[j]), None)
        if at is not None:
            return "\n".join(rows[:at + offset] + [line] + rows[at + offset:])
    return add_under(text, heading, [line])


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


def segment_section(folder, old_steps, steps, seg):
    """插入段寫進哪一份段落報告 → (Section (名稱＝檔名), 是否新開一份).

    插入段併進既有的頂層段落時用那段**插入前**的檔名 (插入不會讓別段的序號位移而寫錯檔);
    插入段自成一個頂層區段時開一份新的 (名字避開已有的檔)。"""
    d = os.path.join(folder, DIR)
    new_sec = section_of(sections(steps), seg[0])
    if new_sec.start == seg[0] and new_sec.end == seg[1]:
        taken = [fn[:-3] for fn in (os.listdir(d) if os.path.isdir(d) else [])
                 if fn.endswith(".md")] + [x.name for x in sections(old_steps)]
        return Section(flowfile.free_name(new_sec.name, taken), new_sec.kind,
                       new_sec.start, new_sec.end), True
    # 插入點前一步 (插入前後索引相同); 插在最前面就用原本的第一步
    old_sec = section_of(sections(old_steps), max(seg[0] - 1, 0))
    return Section(old_sec.name, new_sec.kind, new_sec.start, new_sec.end), False


def file_of(old_steps, seg, sec):
    """插入後第 i 步 (平面) 寫在哪一份段落報告 (檔名): 插入處那份是 sec, 其他照插入前的段落."""
    old_secs = sections(old_steps)
    n = seg[1] - seg[0]

    def where(i):
        if sec.start <= i < sec.end:
            return sec.file
        return section_of(old_secs, i if i < seg[0] else i - n).file
    return where


def template_uses(old_steps, steps, seg, sec, name):
    """插入後的流程裡引用範本 name 的步驟 (找圖目標或確認圖) → (步驟數, [段落報告檔名, 依流程順序])."""
    where = file_of(old_steps, seg, sec)
    idx = [i for i, s in enumerate(steps)
           if (findtarget.is_find(s) and findtarget.template(s) == name)
           or (findtarget.uses_confirm_target(s) and findtarget.confirm_template(s) == name)]
    return len(idx), list(dict.fromkeys(where(i) for i in idx))


def file_link(fn):
    return f"[{fn[:-3]}]({fn})"


def join_steps(texts):
    """步驟描述接成一句 (「；」分隔; 區段開頭「分岔：」「重複 N 次：」後面不再加分隔號)."""
    out = ""
    for t in texts:
        if out and not out.endswith("："):
            out += "；"
        out += t
    return out


def supplement(folder, old_steps, steps, seg, note, retake, confirm, shared=()):
    """補充插入後更新 `交付報告/`: 插入處那份與總覽 (沒有就建一份最小的).

    old_steps / steps: 插入前後的整份步驟; seg: 插入段在插入後的平面索引 [start, end);
    note: 這次補充的一行說明; retake: [(範本, 原因)]; confirm: [(標題, 文字)];
    shared: [(名, 共用矩形說明 (見 `shared_line`))]。
    插入處那份見 `segment_section`; 那份的「這段做什麼」照插入後的流程重寫, 說明寫進「補充」;
    新開的那份照流程順序插進總覽的清單。回傳 {檔名: 新文字}——呼叫端負責寫檔。
    """
    d = os.path.join(folder, DIR)
    sec, fresh = segment_section(folder, old_steps, steps, seg)
    old = None if fresh else _read(os.path.join(d, sec.file))
    if old is None:
        old = f"# {sec.name}\n\n[← 總覽]({OVERVIEW})\n\n## 這段做什麼\n"
    text = replace_under(old, "## 這段做什麼", outline(steps, sec.start, sec.end))
    seg_text = join_steps(describe(s) for s in steps[seg[0]:seg[1]] if s["type"] not in _MARKERS)
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
    listed = "## 各段報告（依流程順序）"
    if ov is None:
        ov = (f"# 交付報告：{os.path.basename(folder)}\n\n總覽；每個頂層區段另有一份。\n\n"
              f"{listed}\n\n"
              + "\n".join(f"- {_link(s)}" for s in sections(steps) if s.start != sec.start)
              + "\n")
    if f"]({sec.file})" not in ov:
        where = file_of(old_steps, seg, sec)
        ov = insert_link(ov, listed, f"- {_link(sec)}",
                         after=where(sec.start - 1) if sec.start > 0 else None,
                         before=where(sec.end) if sec.end < len(steps) else None)
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

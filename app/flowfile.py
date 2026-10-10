"""流程存檔與工作區: 資料進資料出, 純檔案邏輯 (GUI 無關).

**一份`流程`＝一個自包自足的存檔** (副檔名 `.autoclickpack`, zip)::

    flow.json               步驟與流程層級設定 (含 coordSpace、`校準對`與`基準距離`、
                            `忙碌指示`)
    templates/<名稱>.png    本流程引用到的範本圖 (一範本一張圖, 名稱平面無層級)
    templates/_meta.json    範本元資料: {"pos": {範本名: [x, y]}}——拍攝位置 (截圖當下的中心),
                            相對`座標基準點`、`流程尺度` (ADR 0012)

存檔**只寫入被引用的**範本 (步驟的找圖目標含`確認圖`, 以及流程的`校準對`與
`忙碌指示`, 見 `flow_refs`): 刪掉引用它的步驟再存檔, 那張圖就離開存檔——檔案內容永遠等於
流程真正需要的東西。

**工作區** (`<profile>/workspace/`) 是 profile 底下可重建的快取: 當前流程解出來
的範本圖與引擎的`登錄產物`都放這。**存檔是真相來源, 工作區只是快取**——被刪或
毀損時自動重建; 切換流程時整個清空 (圖與登錄產物一起刪)。

**舊格式一律拒絕開啟** (ADR 0012): 座標空間標記不是現行值的存檔、步驟草稿、舊 autoClick
flow JSON、舊流程包都不讀, 回報「這是舊格式, 座標基準不同」——舊檔沒記當時視窗在哪,
自動換算可能靜靜換錯; 在用的流程已一次性換算。以前的舊格式遷移 (螢幕→搜尋範圍座標、
範本名收進找圖目標、去副檔名、丟每步門檻、舊流程包單向匯入) 隨之退場。
存檔原樣搬到哪台機器、哪個 profile 都一樣 (尺度、比例尺與座標基準跟著流程走), 所以開
外來檔不換算座標。格式規則只有這一個地方說得上話。
"""
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

import calibration
from automation import findtarget, flowdefaults, flowfmt

EXT = ".autoclickpack"          # 流程存檔副檔名 (沿用舊流程包的副檔名)
DRAFT_NAME = "_autosave.json"   # 步驟草稿 (自動存檔; 輕量 JSON, 圖留在工作區)

FLOW_ENTRY = "flow.json"
TMPL_PREFIX = "templates/"
META_ENTRY = "templates/_meta.json"

# 自包自足存檔的格式標記: 舊流程包同樣是「zip 內含 flow.json」, 沒有標記就無從
# 分辨「直接開得起來的存檔」與「要走單向轉換的舊流程包」
FORMAT_KEY = "flowFormat"
FORMAT = 5                 # 寫檔一律蓋這個版本 (3: 範本收進`找圖目標`, ADR 0007;
                           # 4: 流程自帶`校準對`與`基準距離`, ADR 0009;
                           # 5: 座標相對`座標基準點`, coordSpace＝anchor, ADR 0012)

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


# ================= 範本名稱與步驟引用 =================

def strip_ext(name):
    """圖檔名去 .png 副檔名 → 範本名 (已無副檔名時不動)."""
    return name[:-4] if name.lower().endswith(".png") else name


def clean_name(name):
    """清理使用者輸入的範本名: 平面名稱, 沒有資料夾層級.

    路徑分隔與檔名非法字元一律換成 `_` (不是丟棄, 否則 `a/b` 會靜靜變成 `ab`)。
    清不出東西時回空字串, 由呼叫端決定怎麼辦。
    """
    name = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip().strip(".")
    return re.sub(r"_+", "_", name)


def free_name(name, taken):
    """`name` 在 `taken` 內已被占用時加序號: name_2、name_3…

    末端已是 `_數字` 的名稱從該數字往上找 (保留補零位數), 避免 `a_1_2` 這種
    疊字。回傳未被占用的名稱。
    """
    taken = set(taken)
    if name not in taken:
        return name
    m = re.fullmatch(r"(.*)_(\d+)", name)
    if m:
        stem, width, n = m.group(1), len(m.group(2)), int(m.group(2)) + 1
    else:
        stem, width, n = name, 1, 2
    while f"{stem}_{n:0{width}d}" in taken:
        n += 1
    return f"{stem}_{n:0{width}d}"


def rename_refs(steps, old, new):
    """把步驟對 `old` 的引用 (所有`找圖目標`, 含`確認圖`) 就地改成 `new`;
    回傳改動筆數.

    跨流程複製撞名加序號、範本重新命名共用這一條路徑——引用漏改就等於
    流程指向一張不存在的圖。
    """
    changed = 0
    for s in steps:
        for _, t in findtarget.step_targets(s):
            if t.get("template") == old:
                t["template"] = new
                changed += 1
    return changed


# 流程層級的`忙碌指示` (ADR 0008): 一個`找圖目標`, 不設＝沒有這個鍵。
# 補做間隔、忙碌出現等候、開始延遲、避開游標是固定行為, 不進存檔 (舊存檔帶著也不讀)
BUSY_KEY = "busyTarget"


def busy_target(data):
    """流程的`忙碌指示` (找圖目標); 沒設回傳 None."""
    tgt = (data or {}).get(BUSY_KEY)
    return tgt if isinstance(tgt, dict) and tgt.get("template") else None


def flow_refs(data):
    """一份流程引用的全部範本名 (已排序): 步驟的`找圖目標` + 流程層級設定
    (`校準對`、`備用校準對`、`忙碌指示`).

    規則在 findtarget.referenced_templates (範本預載也照它): 存檔只打包它們、
    對話框收回未使用的新圖時保留它們——校準對不被步驟引用, 漏了它, 存檔一整理
    流程就不能執行。
    """
    cal = calibration.flow_pair(data)
    fb = calibration.fallback_pair(cal)
    busy = busy_target(data)
    extra = [*(cal["pair"] if cal else ()), *(fb["pair"] if fb else ()),
             *([busy["template"]] if busy else ())]
    return sorted(findtarget.referenced_templates(data.get("steps") or [], extra))


def rename_flow_refs(data, old, new):
    """把整份流程對 `old` 的引用 (步驟 + 校準對 + 備用校準對 + 忙碌指示) 就地改成
    `new`; 回傳改動筆數."""
    changed = rename_refs(data.get("steps") or [], old, new)
    cal = calibration.flow_pair(data)
    fb = calibration.fallback_pair(cal)
    for pair in [cal["pair"] if cal else [], fb["pair"] if fb else []]:
        for i, n in enumerate(pair):
            if n == old:
                pair[i] = new
                changed += 1
    busy = busy_target(data)
    if busy and busy["template"] == old:
        busy["template"] = new
        changed += 1
    return changed


def used_templates(steps):
    """所有`找圖目標`引用的範本名 (確認圖只在生效確認選「確認圖出現」時算;
    找圖、座標點擊、拖曳都有確認圖), 已排序."""
    return sorted(findtarget.referenced_templates(steps))


# ======== 舊存檔鍵名 ⇄ 記憶體鍵名 (過渡碼: 讀寫換成流程資料夾 flow.yaml 時整段刪掉) ========
# 記憶體裡的步驟已改用 flow.yaml 的鍵名與單位 (秒); .autoclickpack 的 flow.json 還是舊鍵。
# 已退場的欄位 (座標模式、滑鼠鍵、連點數、出現等候上限) 讀進來就丟掉。

_RENAMES = (("onNotFound", "on_fail"), ("updateOrigin", "update_origin"),
            ("busyCheck", "busy_check"), ("onBreak", "on_break"))
_RETIRED = ("mode", "button", "clicks", "appearLimitMs")
_ACTION_TYPE = {"click": "find_click", "none": "find", "wait_gone": "wait_gone"}


def _ms_to_s(ms):
    s = float(ms) / 1000.0
    return int(s) if s.is_integer() else s


def _s_to_ms(s):
    return int(round(float(s) * 1000))


def _old_target(t):
    """舊找圖目標 {template, limit, pick:{kind,n|x,y}, colorCheck} → 新."""
    if not isinstance(t, dict):
        return t
    out = {k: v for k, v in t.items() if k not in ("limit", "pick", "colorCheck")}
    lim = t.get("limit")
    if isinstance(lim, dict) and lim.get("kind") == "rect":
        out["within"] = [lim.get(k) for k in ("x", "y", "w", "h")]
    pick = t.get("pick") or {}
    kind = pick.get("kind")
    if kind in ("top", "left"):
        out["pick"] = {kind: pick.get("n", 1)}
    elif kind == "near":
        out["pick"] = {"near": [pick.get("x", 0), pick.get("y", 0)]}
    if t.get("colorCheck"):
        out["color"] = True
    return out


def _new_target(t):
    """新找圖目標 → 舊 (寫回 flow.json)."""
    if not isinstance(t, dict):
        return t
    out = {k: v for k, v in t.items() if k not in ("within", "pick", "color")}
    if t.get("within") is not None:
        out["limit"] = dict(zip(("x", "y", "w", "h"), t["within"]), kind="rect")
    kind, value = findtarget.pick_rule(t)
    if kind in ("top", "left"):
        out["pick"] = {"kind": kind, "n": value}
    elif kind == "near":
        out["pick"] = {"kind": "near", "x": value[0], "y": value[1]}
    if t.get("color"):
        out["colorCheck"] = True
    return out


def _old_step(s):
    s = {k: v for k, v in s.items() if k not in _RETIRED}
    for old, new in _RENAMES:
        if old in s:
            s[new] = s.pop(old)
    if "target" in s:
        s["target"] = _old_target(s["target"])
    if "confirmTarget" in s:
        s["confirm_target"] = _old_target(s.pop("confirmTarget"))
    t = s.get("type")
    if t == "find_click":
        s["type"] = _ACTION_TYPE.get(s.pop("action", "click"), "find_click")
        if "offsetX" in s or "offsetY" in s:
            s["offset"] = [s.pop("offsetX", 0), s.pop("offsetY", 0)]
    elif t == "click":
        s["click"] = [s.pop("x", 0), s.pop("y", 0)]
    elif t == "drag":
        s["drag"] = [s.pop("x1", 0), s.pop("y1", 0)]
        s["to"] = [s.pop("x2", 0), s.pop("y2", 0)]
        if "ms" in s:
            s["duration"] = _ms_to_s(s.pop("ms"))
        if "holdMs" in s:
            s["hold"] = _ms_to_s(s.pop("holdMs"))
    elif t == "wait":
        if "ms" in s:
            s["wait"] = _ms_to_s(s.pop("ms"))
    elif t == "loop_start":
        s["type"] = "repeat_start"
        if "count" in s:
            s["repeat"] = s.pop("count")
    elif t == "loop_end":
        s["type"] = "repeat_end"
    return s


def _new_step(s):
    s = dict(s)
    for old, new in _RENAMES:
        if new in s:
            s[old] = s.pop(new)
    if "target" in s:
        s["target"] = _new_target(s["target"])
    if "confirm_target" in s:
        s["confirmTarget"] = _new_target(s.pop("confirm_target"))
    t = s.get("type")
    if t in findtarget.FIND_TYPES:
        s["action"] = {v: k for k, v in _ACTION_TYPE.items()}[t]
        s["type"] = "find_click"
        if "offset" in s:
            s["offsetX"], s["offsetY"] = s.pop("offset")
    elif t == "click":
        s["x"], s["y"] = s.pop("click")
    elif t == "drag":
        s["x1"], s["y1"] = s.pop("drag")
        s["x2"], s["y2"] = s.pop("to")
        if "duration" in s:
            s["ms"] = _s_to_ms(s.pop("duration"))
        if "hold" in s:
            s["holdMs"] = _s_to_ms(s.pop("hold"))
    elif t == "wait":
        if "wait" in s:
            s["ms"] = _s_to_ms(s.pop("wait"))
    elif t == "repeat_start":
        s["type"] = "loop_start"
        if "repeat" in s:
            s["count"] = s.pop("repeat")
    elif t == "repeat_end":
        s["type"] = "loop_end"
    return s


def _from_old(data):
    """flow.json (舊鍵) → 記憶體的流程資料 (步驟與忙碌指示換成新鍵)."""
    data = dict(data)
    data["steps"] = [flowdefaults.complete(_old_step(s))
                     for s in data.get("steps") or []]
    if isinstance(data.get(BUSY_KEY), dict):
        data[BUSY_KEY] = _old_target(data[BUSY_KEY])
    data.pop("avoidHover", None)
    return data


def _to_old(data):
    """記憶體的流程資料 → flow.json (舊鍵)."""
    data = dict(data)
    data["steps"] = [_new_step(s) for s in data.get("steps") or []]
    if isinstance(data.get(BUSY_KEY), dict):
        data[BUSY_KEY] = _new_target(data[BUSY_KEY])
    return data


# ================= 格式檢查: 舊格式一律拒絕 =================

class OldFormatError(ValueError):
    """舊格式 (座標基準不同) 或根本不是流程存檔: 不開, 訊息給使用者看."""


OLD_FORMAT_MSG = ("這是舊格式的存檔，座標基準不同（舊格式的座標相對搜尋範圍，"
                  "現在一律相對校準對第一張圖的中心），無法開啟。"
                  "在用的流程已一次性換算；其餘舊檔請刪除或重新建立")


def format_problem(data):
    """這份流程資料開不開得起來: 舊格式回傳說明, 現行格式回傳 None.

    現行格式＝flowFormat ≥ 5 且座標空間標記是 anchor; 任一不符都是舊格式
    (座標相對搜尋範圍、或更早的螢幕座標), 一律拒絕——不猜、不換算。
    """
    if not isinstance(data, dict):
        return OLD_FORMAT_MSG
    try:
        fmt = int(data.get(FORMAT_KEY, 0))
    except (TypeError, ValueError):
        fmt = 0
    if fmt < FORMAT or not flowfmt.is_anchor_space(data):
        return OLD_FORMAT_MSG
    return None


def check_format(data):
    """舊格式就丟 OldFormatError; 所有讀檔路徑 (存檔、步驟草稿) 一律先過這一關."""
    problem = format_problem(data)
    if problem:
        raise OldFormatError(problem)


# ================= 目錄掃描 (工作區) =================

def scan_templates(root):
    """掃一個範本圖目錄成`範本清單`: {範本名: [圖檔路徑, ...]}.

    範本名＝相對路徑不含副檔名; 「只含影像檔的資料夾」是一個多截圖範本
    (引擎仍認得的形式), 含子資料夾的資料夾是命名空間。工作區是平面的單張圖,
    同一套規則掃得出來——引擎的`範本清單`由此組出。
    """
    root = Path(root)
    found = {}

    def is_template_dir(path):
        has_image = False
        for child in path.iterdir():
            if child.is_dir():
                return False
            if child.suffix.lower() in _IMG_EXTS:
                has_image = True
        return has_image

    def walk(d):
        for child in sorted(d.iterdir()):
            if child.is_file() and child.suffix.lower() in _IMG_EXTS:
                found[child.relative_to(root).with_suffix("").as_posix()] = [child]
            elif child.is_dir():
                if is_template_dir(child):
                    found[child.relative_to(root).as_posix()] = sorted(
                        p for p in child.iterdir()
                        if p.suffix.lower() in _IMG_EXTS)
                else:
                    walk(child)

    if root.is_dir():
        walk(root)
    return found


# ================= 流程存檔 (zip) =================

def _blob(src):
    """把 bytes 或檔案路徑統一成 bytes (存檔一律寫實體內容, 不留參照)."""
    if isinstance(src, (bytes, bytearray)):
        return bytes(src)
    return Path(src).read_bytes()


def write(path, data, images, pos=None):
    """寫出一份自包自足的流程存檔; 回傳被引用卻缺圖的範本名 list.

    images: {範本名: bytes 或圖檔路徑}。只有 `data` 引用到的範本 (步驟、校準對、
    忙碌指示, `flow_refs`) 會進存檔 (未被引用的圖不進去, 存檔才不會囤積用不到的圖)。缺圖不是
    致命錯誤 (使用者可能剛刪掉範本, 步驟由既有機制標示為有問題), 回報給呼叫端
    寫進執行紀錄即可。
    """
    images = images or {}
    refs = flow_refs(data)
    stamped = _stamped(_to_old(data))
    pos = pos or {}
    missing = [n for n in refs if n not in images]
    tmp = str(path) + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(FLOW_ENTRY, json.dumps(stamped, ensure_ascii=False, indent=2))
        z.writestr(META_ENTRY, json.dumps(
            {"pos": {n: pos[n] for n in refs if n in pos}}, ensure_ascii=False))
        for n in refs:
            if n in images:
                z.writestr(f"{TMPL_PREFIX}{n}.png", _blob(images[n]))
    os.replace(tmp, path)   # 寫壞的存檔不會取代舊的那份
    return missing


def _stamped(data):
    """寫檔用的深拷貝 (不改呼叫端的資料), 蓋上現行版本與座標空間標記.

    呼叫端必須明確標了 coordSpace＝anchor: 沒標或標舊值的資料 (座標相對搜尋範圍、
    或更早的螢幕座標) 寫成現行標記＝把舊數字當新偏移, 絕不能發生。
    """
    if not flowfmt.is_anchor_space(data):
        raise ValueError("流程資料沒有標明座標相對座標基準點 (coordSpace=anchor), 不能寫出")
    stamped = json.loads(json.dumps(data))
    stamped[FORMAT_KEY] = FORMAT
    return stamped


def _entry_names(z, prefix):
    """zip 內某前綴下的範本名 (只讀索引, 不解壓內容)."""
    out = []
    for fn in z.namelist():
        if (not fn.startswith(prefix) or fn.endswith("/")
                or not fn.lower().endswith(_IMG_EXTS)):
            continue
        rel = fn[len(prefix):]
        if rel.startswith("_"):
            continue
        out.append(os.path.splitext(rel)[0])
    return sorted(out)


def _flow_json(path):
    """zip 內的 flow.json; 不是 zip、沒有 flow.json、不是 JSON 都算舊格式/不是存檔."""
    if not zipfile.is_zipfile(path):
        raise OldFormatError(OLD_FORMAT_MSG)
    try:
        with zipfile.ZipFile(path) as z:
            return json.loads(z.read(FLOW_ENTRY).decode("utf-8"))
    except (OSError, KeyError, ValueError) as e:
        raise OldFormatError(OLD_FORMAT_MSG) from e


def is_flow_file(path):
    """這份檔案是本 app 現行格式的存檔嗎 (舊格式、舊 JSON、舊流程包、非 zip 都不是)."""
    try:
        return format_problem(_flow_json(path)) is None
    except OldFormatError:
        return False


def template_names(path):
    """存檔內的範本名 (只讀 zip 索引, 不整包解壓——供對話框列出縮圖清單)."""
    with zipfile.ZipFile(path) as z:
        return _entry_names(z, TMPL_PREFIX)


def template_bytes(path, name):
    """存檔內某個範本的圖檔內容; 不存在回傳 None (只取這一張, 不解壓整包)."""
    with zipfile.ZipFile(path) as z:
        try:
            return z.read(f"{TMPL_PREFIX}{name}.png")
        except KeyError:
            return None


def read(path):
    """讀一份流程存檔, 回傳資料進資料出的 dict; 舊格式丟 OldFormatError (不開).

    keys: data (流程資料, 校準對在 data 裡)、images ({範本名: bytes})、pos
    (範本拍攝位置, 相對座標基準點)。
    """
    data = _flow_json(path)
    check_format(data)
    data = _from_old(data)
    with zipfile.ZipFile(path) as z:
        try:
            meta = json.loads(z.read(META_ENTRY).decode("utf-8"))
        except (KeyError, ValueError):
            meta = {}
        pos = meta.get("pos", {}) if isinstance(meta, dict) else {}
        images = {n: z.read(f"{TMPL_PREFIX}{n}.png")
                  for n in _entry_names(z, TMPL_PREFIX)}
    return {"data": data, "images": images,
            "pos": {k: v for k, v in pos.items() if k in images}}


# ================= profile 內的流程存檔 =================

def flows_dir(profile_dir):
    return os.path.join(profile_dir, "flows")


def list_flows(profile_dir):
    """profile 內的流程存檔路徑 (已排序); 草稿不算一份流程."""
    d = flows_dir(profile_dir)
    try:
        entries = sorted(os.listdir(d))
    except OSError:
        return []
    return [os.path.join(d, fn) for fn in entries
            if fn.lower().endswith(EXT)
            and os.path.isfile(os.path.join(d, fn))]


def draft_path(profile_dir):
    return os.path.join(flows_dir(profile_dir), DRAFT_NAME)


def write_draft(profile_dir, data):
    """自動存檔: **只寫步驟草稿** (輕量 JSON), 圖留在工作區.

    拖曳排序一次動作就存一次, 若每次都重壓整包 zip (幾十張圖) 會卡頓;
    圖已經在工作區裡, 當機重開時草稿與工作區的圖一起復原。草稿與存檔同一套
    格式標記 (版本與座標空間), 讀回時過同一關。
    """
    stamped = _stamped(_to_old(data))
    try:
        os.makedirs(flows_dir(profile_dir), exist_ok=True)
        with open(draft_path(profile_dir), "w", encoding="utf-8") as f:
            json.dump(stamped, f, ensure_ascii=False)
    except OSError:
        pass


def read_draft(profile_dir):
    """讀步驟草稿; 缺檔/壞檔回傳 None; 舊格式丟 OldFormatError (不復原, 呼叫端開空白並提示)."""
    try:
        with open(draft_path(profile_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    check_format(data)
    return _from_old(data)


def free_path(dirpath, stem, suffix):
    """dirpath 下未被占用的路徑 stem[_N]suffix (不覆蓋既有檔案)."""
    path = os.path.join(dirpath, stem + suffix)
    n = 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(dirpath, f"{stem}_{n}{suffix}")
    return path


def is_inside_profile(path, profile_dir):
    """這份存檔是否就住在本 profile 的 flows/ 裡 (外來檔要先複製副本進來)."""
    return (os.path.normcase(os.path.dirname(os.path.abspath(path)))
            == os.path.normcase(os.path.abspath(flows_dir(profile_dir))))


# ================= 工作區 =================

class Workspace:
    """profile 底下可重建的快取: 當前流程的範本圖 + 引擎`登錄產物`.

    存檔才是真相來源; 工作區被手動刪掉或毀損時自動重建 (下次載入流程即補齊)。
    切換流程時 `clear()` 整個清空——磁碟上刻意不留任何非當前流程的圖, 代價是
    切回去時該流程的範本要重新登錄。
    """

    DIRNAME = "workspace"

    def __init__(self, profile_dir):
        self.profile_dir = str(profile_dir)

    # ---- 路徑 ----

    @property
    def root(self):
        return os.path.join(self.profile_dir, self.DIRNAME)

    @property
    def templates_dir(self):
        return os.path.join(self.root, "templates")

    @property
    def registered_dir(self):
        return os.path.join(self.root, "registered")

    @property
    def _meta_path(self):
        return os.path.join(self.root, "_meta.json")

    @property
    def _state_path(self):
        return os.path.join(self.root, "state.json")

    def path_of(self, name):
        return os.path.join(self.templates_dir, name + ".png")

    # ---- 生命週期 ----

    def ensure(self):
        """工作區目錄就位 (不存在就建); 回傳工作區根目錄."""
        os.makedirs(self.templates_dir, exist_ok=True)
        return self.root

    def clear(self):
        """整個清空: 解出來的範本圖與登錄產物一起刪, 元資料歸零."""
        shutil.rmtree(self.root, ignore_errors=True)
        self.ensure()

    # ---- 範本 ----

    def names(self):
        """工作區內的範本名 (已排序)——即本流程目前帶著的範本."""
        try:
            entries = os.listdir(self.templates_dir)
        except OSError:
            return []
        return sorted(strip_ext(fn) for fn in entries
                      if fn.lower().endswith(".png") and not fn.startswith("_"))

    def has(self, name):
        return os.path.isfile(self.path_of(name))

    def images(self):
        """{範本名: 圖檔路徑}——存檔與引擎`範本清單`都吃這個."""
        return {n: self.path_of(n) for n in self.names()}

    def reserve(self, name):
        """保留一個未被占用的範本名 (撞名加序號), 圖由呼叫端自己寫進去.

        影像編碼是 app 的事 (`automation.imgio` 才碰 cv2), 但「撞名怎麼處理」
        只有這一條規則。
        """
        self.ensure()
        return free_name(clean_name(name) or "template", self.names())

    def add(self, name, blob, pos=None):
        """加一張範本進本流程; 撞名自動加序號. 回傳最終採用的範本名.

        `blob` 是 bytes 或來源圖檔路徑 (跨流程複製進來的是獨立副本, 來源日後
        改圖不影響本流程)。`pos`＝拍攝位置 (截圖當下的中心, 相對`座標基準點`、
        流程尺度), 只有本流程自己拍的圖才有 (跨流程複製與磁碟上傳的沒有)。
        """
        final = self.reserve(name)
        with open(self.path_of(final), "wb") as f:
            f.write(_blob(blob))
        if pos is not None:
            self.set_pos(final, pos)
        return final

    def remove(self, name):
        """從本流程移除一個範本 (圖與它的登錄產物一起刪)."""
        try:
            os.remove(self.path_of(name))
        except OSError:
            pass
        self._drop_registered(name)
        meta = self.pos()
        if meta.pop(name, None) is not None:
            self._write_pos(meta)

    def rename(self, old, new):
        """重新命名範本 (撞名加序號); 回傳最終名稱, 來源不存在回傳 None.

        引用的改寫由呼叫端以 `rename_refs` 處理 (工作區不認識步驟)。
        """
        if not self.has(old):
            return None
        final = free_name(clean_name(new) or old,
                          [n for n in self.names() if n != old])
        if final == old:
            return old
        os.replace(self.path_of(old), self.path_of(final))
        self._drop_registered(old)
        meta = self.pos()
        if old in meta:
            meta[final] = meta.pop(old)
            self._write_pos(meta)
        return final

    def _drop_registered(self, name):
        """丟棄某範本的登錄產物 (改名/刪除後留著只是佔空間, 重建很便宜)."""
        shutil.rmtree(os.path.join(self.registered_dir, name),
                      ignore_errors=True)

    def invalidate_registered(self):
        """整個登錄產物目錄作廢 (工作區內容整批換掉時用)."""
        shutil.rmtree(self.registered_dir, ignore_errors=True)

    # ---- 範本元資料 (pos) ----

    def pos(self):
        """{範本名: [x, y]}: 各範本的拍攝位置 (相對`座標基準點`, 流程尺度; 缺檔＝空)."""
        try:
            with open(self._meta_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        if isinstance(data, dict):
            return dict(data.get("pos", {}))
        return {}

    def _write_pos(self, pos):
        self.ensure()
        try:
            with open(self._meta_path, "w", encoding="utf-8") as f:
                json.dump({"pos": pos}, f, ensure_ascii=False)
        except OSError:
            pass

    def set_pos(self, name, xy):
        pos = self.pos()
        pos[name] = [int(xy[0]), int(xy[1])]
        self._write_pos(pos)

    def pos_of(self, name):
        return self.pos().get(name)

    def shift_pos(self, old_anchor, new_anchor, k=1.0):
        """換`校準對`時所有拍攝位置改成相對新基準點 (同 flowfmt.shift_flow 的換算)."""
        pos = self.pos()
        if not pos:
            return 0
        self._write_pos({n: list(flowfmt.from_screen(flowfmt.to_screen(xy, old_anchor, k),
                                                     new_anchor, k))
                         for n, xy in pos.items()})
        return len(pos)

    # ---- 當前流程 ----

    def flow_path(self):
        """工作區裡這批圖屬於哪一份存檔 (檔案路徑); 新流程未存檔時 None."""
        try:
            with open(self._state_path, encoding="utf-8") as f:
                p = json.load(f).get("flow")
        except (OSError, ValueError, AttributeError):
            return None
        return p or None

    def set_flow_path(self, path):
        self.ensure()
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump({"flow": str(path) if path else None}, f,
                          ensure_ascii=False)
        except OSError:
            pass

    # ---- 與存檔之間 ----

    def load_flow(self, path):
        """把一份存檔解到工作區 (先整個清空), 回傳 `read()` 的結果."""
        r = read(path)
        self.clear()
        for name, blob in r["images"].items():
            with open(self.path_of(name), "wb") as f:
                f.write(blob)
        self._write_pos(dict(r["pos"]))
        self.set_flow_path(path)
        return r

    def put_flow(self, data, path=None):
        """把工作區的圖與 `data` 一起寫成存檔; 回傳缺圖的範本名 list."""
        path = path or self.flow_path()
        missing = write(path, data, self.images(), self.pos())
        self.set_flow_path(path)
        return missing


# ================= 開啟外來檔 =================

def adopt_foreign_flow(path, profile_dir):
    """開啟不在本 profile 裡的存檔: 原樣複製副本進 profile 再開 (原檔不被動到).

    不換算: 流程自帶尺度、校準對與座標基準 (ADR 0009、0012), 搬到哪裡都一樣,
    執行開頭自己量。舊格式由 read 拒絕。回傳 dict: flow_path (副本)、data。
    """
    r = read(path)
    os.makedirs(flows_dir(profile_dir), exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    dest = free_path(flows_dir(profile_dir), stem, EXT)
    write(dest, r["data"], r["images"], r["pos"])
    return {"flow_path": dest, "data": r["data"]}


# ================= 流程資料夾 (flow.yaml) =================
# 一份流程＝一個資料夾 (ADR 0014)::
#
#     <流程名>/flow.yaml             步驟與流程層級設定 (區段巢狀、一步一行、預設不寫、時間一律秒)
#     <流程名>/templates/<範本名>.png 被引用的範本圖 (檔名即範本名)
#     <流程名>/.cache/               可重建的快取 (登錄產物、還沒存檔的截圖)
#
# 記憶體裡的流程是 dict: run、scan_region、calibration、busy、template_pos、engine、steps
# (步驟是平面標記, 鍵名與單位跟 flow.yaml 相同, 補齊成完整步驟)。讀寫只做三種形狀轉換:
# 巢狀區段 ⇄ 平面標記、開頭的鍵 ⇄ type、步驟層的 within/pick/color ⇄ target 子 dict
# (確認圖 confirm: {appear: 名, …} ⇄ confirm: appear + confirm_target)。
# 讀檔是唯一的入口驗證: 寫錯就報錯並指出步驟編號與鍵, 目前開著的流程不動。

FLOW_YAML = "flow.yaml"
TEMPLATES_DIR = "templates"
CACHE_DIR = ".cache"
FLOW_FORMAT = 1

_HEADS = ("find_click", "find", "wait_gone", "click", "drag", "wait", "repeat",
          "branch")
_TOP_KEYS = ("format", "run", "scan_region", "calibration", "busy",
             "template_pos", "engine", "steps")
_TARGET_ATTRS = ("within", "pick", "color")
_BAD_NAME_CHARS = '\\/:*?"<>|'


class FlowError(ValueError):
    """flow.yaml 讀不進來 (或流程寫不出去): 訊息給人看, 指明步驟編號與鍵."""


def template_name_problem(name):
    """範本名能不能當檔名 (範本名＝檔名): 不行回傳原因, 可以回傳 None."""
    if not isinstance(name, str) or not name:
        return "範本名不能是空的"
    bad = sorted({c for c in name if c in _BAD_NAME_CHARS})
    if bad:
        return f"範本名「{name}」不能有 {' '.join(bad)}（檔名不允許）"
    if name != name.strip():
        return f"範本名「{name}」開頭或結尾不能是空白"
    if name.endswith("."):
        return f"範本名「{name}」結尾不能是句點"
    return None


def new_flow():
    """空白的新流程 (記憶體模型)."""
    return {"run": flowdefaults.FLOW["run"], "scan_region": None,
            "calibration": None, "busy": None, "template_pos": {},
            "engine": {}, "steps": []}


def template_refs(flow):
    """流程引用的全部範本名 (依出現順序): 步驟的找圖目標與確認圖 + 校準對 +
    備用校準對 + 忙碌指示 (findtarget.referenced_templates 是唯一的定義)."""
    cal = flow.get("calibration")
    fb = calibration.fallback_pair(cal) if cal else None
    busy = flow.get("busy")
    extra = [*(cal["pair"] if cal else ()), *(fb["pair"] if fb else ()),
             *([busy["template"]] if busy else ())]
    return findtarget.referenced_templates(flow.get("steps") or [], extra)


def rename_template_refs(flow, old, new):
    """把整份流程 (記憶體模型) 對 old 的引用改成 new: 步驟的找圖目標與確認圖、校準對、
    備用校準對、忙碌指示、拍攝位置; 回傳改動筆數."""
    changed = rename_refs(flow.get("steps") or [], old, new)
    cal = flow.get("calibration")
    fb = calibration.fallback_pair(cal) if cal else None
    for pair in [cal["pair"] if cal else [], fb["pair"] if fb else []]:
        for i, n in enumerate(pair):
            if n == old:
                pair[i] = new
                changed += 1
    busy = flow.get("busy")
    if busy and busy.get("template") == old:
        busy["template"] = new
        changed += 1
    pos = flow.get("template_pos")
    if pos and old in pos:
        flow["template_pos"] = {(new if k == old else k): v for k, v in pos.items()}
    return changed


# ---------- 讀 ----------

def read_flow(folder):
    """讀流程資料夾的 flow.yaml → 記憶體的流程 (補齊預設); 讀不進來丟 FlowError."""
    path = os.path.join(str(folder), FLOW_YAML)
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError as e:
        raise FlowError(f"讀不到 {path}（{e.strerror or e}）") from None
    return parse_flow(text)


def missing_templates(folder, flow):
    """被引用卻不在 templates/ 的範本名 (開檔時列出缺圖用)."""
    tdir = os.path.join(str(folder), TEMPLATES_DIR)
    return [n for n in template_refs(flow)
            if not os.path.isfile(os.path.join(tdir, n + ".png"))]


def parse_flow(text):
    """flow.yaml 的文字 → 記憶體的流程 (補齊預設); 寫錯丟 FlowError (指出步驟編號與鍵)."""
    import yaml
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"第 {mark.line + 1} 行" if mark is not None else "某處"
        raise FlowError(f"flow.yaml 的 YAML 語法有錯（{where}）："
                        f"{getattr(e, 'problem', None) or e}") from None
    if not isinstance(doc, dict):
        raise FlowError("flow.yaml 的最外層要是 {鍵: 值}")
    extra = [k for k in doc if k not in _TOP_KEYS]
    if extra:
        raise FlowError(f"flow.yaml 頂層不認得的鍵：{'、'.join(map(str, extra))}")
    if "format" not in doc:
        raise FlowError("flow.yaml 缺 format（現行格式是 format: 1）")
    if doc["format"] != FLOW_FORMAT or isinstance(doc["format"], bool):
        raise FlowError(f"flow.yaml 的 format 是 {doc['format']!r}，這版 app 只讀 "
                        f"format: {FLOW_FORMAT}")
    flow = new_flow()
    if "run" in doc:
        run = doc["run"]
        if not (run == "forever" or _int(run) and run >= 1):
            raise FlowError(f"run 要是 1 以上的整數或 forever，收到 {run!r}")
        flow["run"] = run
    if doc.get("scan_region") is not None:
        flow["scan_region"] = _rect("scan_region", doc["scan_region"])
    if doc.get("calibration") is not None:
        flow["calibration"] = _calibration(doc["calibration"])
    if doc.get("busy") is not None:
        flow["busy"] = _yaml_target("busy", doc["busy"], "template")
    if doc.get("template_pos") is not None:
        flow["template_pos"] = _template_pos(doc["template_pos"])
    if doc.get("engine") is not None:
        flow["engine"] = _engine(doc["engine"])
    steps = doc.get("steps")
    if steps is None:
        steps = []
    if not isinstance(steps, list):
        raise FlowError("steps 要是步驟清單")
    out = []
    _parse_steps(steps, out)
    flow["steps"] = out
    return flow


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _xy(where, v):
    if not (isinstance(v, list) and len(v) == 2 and all(_int(c) for c in v)):
        raise FlowError(f"{where} 要寫成 [x, y] 整數，收到 {v!r}")
    return list(v)


def _rect(where, v):
    if not (isinstance(v, list) and len(v) == 4 and all(_int(c) for c in v)
            and v[2] > 0 and v[3] > 0):
        raise FlowError(f"{where} 要寫成 [x, y, w, h] 整數且寬高大於 0，收到 {v!r}")
    return list(v)


def _name(where, v):
    problem = template_name_problem(v)
    if problem:
        raise FlowError(f"{where}：{problem}")
    return v


def _calibration(c):
    where = "calibration"
    if not isinstance(c, dict):
        raise FlowError(f"{where} 要是 {{pair, baseline, fallback}}")
    extra = [k for k in c if k not in ("pair", "baseline", "fallback")]
    if extra:
        raise FlowError(f"{where} 不認得的鍵：{'、'.join(map(str, extra))}")
    out = _pair(where, c)
    if c.get("fallback") is not None:
        fb = c["fallback"]
        fw = where + ".fallback"
        if not isinstance(fb, dict):
            raise FlowError(f"{fw} 要是 {{pair, baseline, offset}}")
        extra = [k for k in fb if k not in ("pair", "baseline", "offset")]
        if extra:
            raise FlowError(f"{fw} 不認得的鍵：{'、'.join(map(str, extra))}")
        f = _pair(fw, fb)
        if "offset" not in fb:
            raise FlowError(f"{fw} 缺 offset")
        f["offset"] = _xy(fw + ".offset", fb["offset"])
        out["fallback"] = f
    return out


def _pair(where, c):
    pair = c.get("pair")
    if not (isinstance(pair, list) and len(pair) == 2 and pair[0] != pair[1]):
        raise FlowError(f"{where}.pair 要是兩個不同的範本名，收到 {pair!r}")
    for n in pair:
        _name(f"{where}.pair", n)
    base = c.get("baseline")
    if not _num(base) or base <= 0:
        raise FlowError(f"{where}.baseline 要是大於 0 的數字，收到 {base!r}")
    return {"pair": list(pair), "baseline": float(base)}


def _template_pos(tp):
    if not isinstance(tp, dict):
        raise FlowError("template_pos 要是 {範本名: [x, y]}")
    return {_name("template_pos", str(n) if _num(n) else n):
            _xy(f"template_pos.{n}", v) for n, v in tp.items()}


_ENGINE_KEYS = None


def _engine(e):
    """`引擎參數覆蓋`: 鍵名同引擎 default_config.yaml; 不認得的鍵報錯 (拼錯不能變成預設)."""
    global _ENGINE_KEYS
    if not isinstance(e, dict):
        raise FlowError("engine 要是 {引擎參數: 值}")
    if _ENGINE_KEYS is None:
        from subject_detection.library import load_default_config
        _ENGINE_KEYS = set(load_default_config())
    extra = [k for k in e if k not in _ENGINE_KEYS]
    if extra:
        raise FlowError(f"engine 不認得的鍵：{'、'.join(map(str, extra))}"
                        f"（可用：{'、'.join(sorted(_ENGINE_KEYS))}）")
    return dict(e)


def _yaml_target(where, d, head):
    """yaml 的找圖目標 ({head: 名, within, pick, color}) → 記憶體的找圖目標."""
    if not isinstance(d, dict):
        raise FlowError(f"{where} 要是 {{{head}: 範本名, …}}")
    tgt = {"template": _name(f"{where} 的 {head}", d.get(head))}
    if "within" in d:
        tgt["within"] = _rect(f"{where} 的 within", d["within"])
    if "pick" in d:
        tgt["pick"] = _pick(f"{where} 的 pick", d["pick"])
    if "color" in d:
        if d["color"] is not True:
            raise FlowError(f"{where} 的 color 只能寫 true（不比色就不寫），收到 {d['color']!r}")
        tgt["color"] = True
    extra = [k for k in d if k not in (head, *_TARGET_ATTRS)]
    if extra and head == "template":
        raise FlowError(f"{where} 不認得的鍵：{'、'.join(map(str, extra))}")
    return tgt


def _pick(where, p):
    if isinstance(p, dict) and len(p) == 1:
        (kind, v), = p.items()
        if kind in ("top", "left") and _int(v) and v >= 1:
            return {kind: v}
        if kind == "near":
            return {"near": _xy(where + ".near", v)}
    raise FlowError(f"{where} 要寫成 {{top: N}}、{{left: N}} 或 {{near: [x, y]}}，"
                    f"收到 {p!r}")


def _parse_steps(items, out):
    """巢狀的步驟清單 → 平面標記 (就地 append 到 out); 步驟編號＝out 裡的位置 + 1."""
    for item in items:
        no = len(out) + 1
        where = f"步驟 {no}"
        if not isinstance(item, dict):
            raise FlowError(f"{where} 要是 {{鍵: 值}}，收到 {item!r}")
        heads = [k for k in item if k in _HEADS]
        if len(heads) != 1:
            raise FlowError(f"{where} 要剛好一個開頭的鍵（{'/'.join(_HEADS)}），"
                            f"收到 {'、'.join(map(str, item)) or '空的'}")
        head = heads[0]
        if head == "repeat":
            _parse_repeat(where, item, out)
        elif head == "branch":
            _parse_branch(where, item, out)
        else:
            out.append(_parse_step(where, head, item))


def _on_break(where, item):
    v = item.get("on_break", "continue")
    if v not in ("continue", "break"):
        raise FlowError(f"{where} 的 on_break 只能是 break（不寫＝continue），收到 {v!r}")
    return v


def _parse_repeat(where, item, out):
    extra = [k for k in item if k not in ("repeat", "steps", "on_break")]
    if extra:
        raise FlowError(f"{where}（repeat）不認得的鍵：{'、'.join(map(str, extra))}")
    n = item["repeat"]
    if not _int(n) or n < 1:
        raise FlowError(f"{where} 的 repeat 要是 1 以上的整數，收到 {n!r}")
    body = item.get("steps")
    if not isinstance(body, list) or not body:
        raise FlowError(f"{where} 的 repeat 區段不完整：要有 steps（區段裡的步驟清單）")
    on_break = _on_break(where, item)
    out.append({"type": "repeat_start", "repeat": n})
    _parse_steps(body, out)
    out.append({"type": "repeat_end", "on_break": on_break})


def _parse_branch(where, item, out):
    extra = [k for k in item if k not in ("branch", "on_break")]
    if extra:
        raise FlowError(f"{where}（branch）不認得的鍵：{'、'.join(map(str, extra))}")
    arms = item["branch"]
    if not isinstance(arms, list) or not arms:
        raise FlowError(f"{where} 的 branch 區段不完整：要有分支清單（- if: …）")
    on_break = _on_break(where, item)
    out.append({"type": "branch_start"})
    for k, arm in enumerate(arms):
        if k:
            out.append({"type": "branch_or"})
        aw = f"步驟 {len(out) + 1}"
        if not isinstance(arm, dict) or "if" not in arm:
            raise FlowError(f"{aw}：branch 的每個分支要寫 if（分支條件）")
        extra = [x for x in arm if x not in ("if", "then")]
        if extra:
            raise FlowError(f"{aw}：branch 的分支不認得的鍵：{'、'.join(map(str, extra))}")
        cond = arm["if"]
        heads = [h for h in (cond if isinstance(cond, dict) else {})
                 if h in _HEADS]
        if len(heads) != 1 or heads[0] not in findtarget.FIND_TYPES:
            raise FlowError(f"{aw}：branch 的 if 必須是找圖步驟"
                            "（find_click / find / wait_gone）")
        then = arm.get("then") or []
        if not isinstance(then, list):
            raise FlowError(f"{aw}：then 要是步驟清單")
        _parse_steps([cond, *then], out)
    out.append({"type": "branch_end", "on_break": on_break})


def _parse_step(where, head, item):
    """一步 (flow-style mapping) → 記憶體的完整步驟."""
    t = head
    s = {"type": t}
    allowed = set(flowdefaults.KEYS[t]) - {"type", "target", "confirm_target"}
    allowed |= {head}
    if t in findtarget.FIND_TYPES:
        allowed |= set(_TARGET_ATTRS)
    extra = [k for k in item if k not in allowed]
    if extra:
        raise FlowError(f"{where}（{t}）不認得的鍵：{'、'.join(map(str, extra))}")
    if t in findtarget.FIND_TYPES:
        s["target"] = _yaml_target(where, {k: item[k] for k in (head, *_TARGET_ATTRS)
                                           if k in item}, head)
    elif t == "click":
        s["click"] = _xy(f"{where} 的 click", item["click"])
    elif t == "drag":
        s["drag"] = _xy(f"{where} 的 drag", item["drag"])
        if "to" not in item:
            raise FlowError(f"{where} 的 drag 要寫 to（終點）")
        s["to"] = _xy(f"{where} 的 to", item["to"])
    elif t == "wait":
        if not _num(item["wait"]) or item["wait"] < 0:
            raise FlowError(f"{where} 的 wait 要是秒數，收到 {item['wait']!r}")
        s["wait"] = item["wait"]
    if "offset" in item:
        s["offset"] = _xy(f"{where} 的 offset", item["offset"])
    if "confirm" in item:
        c = item["confirm"]
        if isinstance(c, dict):
            extra = [k for k in c if k not in ("appear", *_TARGET_ATTRS)]
            if extra or "appear" not in c:
                raise FlowError(f"{where} 的 confirm 要寫成 gone / next / "
                                "{appear: 範本名, within…, pick…, color…}，"
                                f"收到 {c!r}")
            s["confirm"] = "appear"
            s["confirm_target"] = _yaml_target(f"{where} 的 confirm", c, "appear")
        elif c in ("gone", "next"):
            s["confirm"] = c
        else:
            raise FlowError(f"{where} 的 confirm 只能是 gone / next / {{appear: 範本名}}，"
                            f"收到 {c!r}")
    for k in ("timeout", "duration", "hold"):
        if k in item:
            if not _num(item[k]) or item[k] < 0:
                raise FlowError(f"{where} 的 {k} 要是秒數，收到 {item[k]!r}")
            s[k] = item[k]
    if "interval" in item:
        if not _num(item["interval"]) or item["interval"] <= 0:
            raise FlowError(f"{where} 的 interval 要是大於 0 的秒數，收到 {item['interval']!r}")
        s["interval"] = item["interval"]
    if "on_fail" in item:
        if item["on_fail"] not in ("skip", "break", "stop"):
            raise FlowError(f"{where} 的 on_fail 只能是 skip / break（不寫＝stop），"
                            f"收到 {item['on_fail']!r}")
        s["on_fail"] = item["on_fail"]
    for k in ("busy_check", "update_origin"):
        if k in item:
            if not isinstance(item[k], bool):
                raise FlowError(f"{where} 的 {k} 要是 true / false，收到 {item[k]!r}")
            s[k] = item[k]
    if not flowdefaults.has_wait(s):
        waits = [k for k in flowdefaults.WAIT if k in item]
        if waits:
            raise FlowError(f"{where} 的 {'、'.join(waits)} 只有設了生效確認（confirm）"
                            "才有意義")
    return flowdefaults.complete(s)


# ---------- 寫 ----------

def dump_flow(flow):
    """記憶體的流程 → flow.yaml 的文字 (等於預設的不寫; 一步一行, 行尾 # N 是步驟編號).

    整份重寫, 手寫註解不保留。template_pos 只留被引用的範本。
    """
    lines = [f"format: {FLOW_FORMAT}"]
    run = flow.get("run", 1)
    if run != flowdefaults.FLOW["run"]:
        lines.append(f"run: {_flow_style(run)}")
    if flow.get("scan_region"):
        lines.append(f"scan_region: {_flow_style(list(flow['scan_region']))}")
    cal = flow.get("calibration")
    if cal:
        lines.append("calibration:")
        lines.append(f"  pair: {_flow_style(list(cal['pair']))}")
        lines.append(f"  baseline: {_flow_style(round(float(cal['baseline']), 1))}")
        fb = calibration.fallback_pair(cal)
        if fb:
            lines.append("  fallback: " + _flow_style({
                "pair": list(fb["pair"]),
                "baseline": round(float(fb["baseline"]), 1),
                "offset": [int(v) for v in fb["offset"]]}))
    busy = flow.get("busy")
    if busy:
        lines.append(f"busy: {_flow_style(_target_yaml(busy, 'template'))}")
    refs = set(template_refs(flow))
    pos = {n: p for n, p in (flow.get("template_pos") or {}).items() if n in refs}
    if pos:
        lines.append("template_pos:")
        for n, p in pos.items():
            lines.append(f"  {_flow_style(n)}: {_flow_style([int(p[0]), int(p[1])])}")
    if flow.get("engine"):
        lines.append(f"engine: {_flow_style(dict(flow['engine']))}")
    steps = flow.get("steps") or []
    if not steps:
        lines.append("steps: []")
    else:
        lines.append("steps:")
        lines += _emit(_nest(steps), 2)
    return "\n".join(lines) + "\n"


def _flow_style(v):
    """單行 flow-style YAML (中文名直接當值)."""
    import yaml
    text = yaml.dump(v, allow_unicode=True, default_flow_style=True,
                     sort_keys=False, width=10_000)
    return text.removesuffix("...\n").strip()


def _number(v):
    v = float(v)
    return int(v) if v.is_integer() else v


def _target_yaml(tgt, head):
    out = {head: tgt.get("template", "")}
    if tgt.get("within") is not None:
        out["within"] = [int(c) for c in tgt["within"]]
    kind, value = findtarget.pick_rule(tgt)
    if kind in ("top", "left"):
        out["pick"] = {kind: int(value)}
    elif kind == "near":
        out["pick"] = {"near": [int(value[0]), int(value[1])]}
    if tgt.get("color"):
        out["color"] = True
    return out


_ORDER = ("offset", "duration", "hold", "confirm", "timeout", "interval", "on_fail",
          "busy_check", "update_origin")


def _step_yaml(step):
    """記憶體的步驟 → yaml 的一步 (開頭的鍵在前, 等於預設的不寫)."""
    s = flowdefaults.strip(step)
    t = step["type"]
    if t in findtarget.FIND_TYPES:
        out = _target_yaml(step["target"], t)
    elif t == "click":
        out = {"click": [int(v) for v in step["click"]]}
    elif t == "drag":
        out = {"drag": [int(v) for v in step["drag"]],
               "to": [int(v) for v in step["to"]]}
    else:
        out = {"wait": _number(step["wait"])}
    for k in _ORDER:
        if k not in s:
            continue
        v = s[k]
        if k == "confirm":
            if v == "appear":
                v = _target_yaml(step.get("confirm_target") or {}, "appear")
        elif k == "offset":
            v = [int(c) for c in v]
        elif k in ("duration", "hold", "timeout", "interval"):
            v = _number(v)
        out[k] = v
    return out


def _nest(steps):
    """平面標記 → 巢狀節點 [(種類, 內容, 步驟編號)] (編號＝平面清單的位置 + 1, 標記也算一號).

    種類: "step" (yaml 的一步)、"repeat" ({repeat, steps, on_break})、
    "branch" ({arms: [[節點, ...], ...], on_break})。
    """
    pos = 0

    def block(stop):
        nonlocal pos
        out = []
        while pos < len(steps):
            s = steps[pos]
            t = s["type"]
            if t in stop:
                return out
            no = pos + 1
            pos += 1
            if t == "repeat_start":
                body = block(("repeat_end",))
                if pos >= len(steps):
                    raise FlowError(f"步驟 {no}：重複區段缺少結尾，寫不出 flow.yaml")
                end = steps[pos]
                pos += 1
                out.append(("repeat", {"repeat": s["repeat"], "steps": body,
                                       "on_break": end["on_break"]}, no))
            elif t == "branch_start":
                arms = []
                while True:
                    arms.append(block(("branch_or", "branch_end")))
                    if pos >= len(steps):
                        raise FlowError(f"步驟 {no}：分岔缺少結尾，寫不出 flow.yaml")
                    sep = steps[pos]
                    pos += 1
                    if sep["type"] == "branch_end":
                        break
                out.append(("branch", {"arms": arms, "on_break": sep["on_break"]}, no))
            elif t in ("repeat_end", "branch_or", "branch_end"):
                raise FlowError(f"步驟 {no}：區段標記不成對，寫不出 flow.yaml")
            else:
                out.append(("step", _step_yaml(s), no))
        return out

    return block(())


def _emit(nodes, ind):
    pad = " " * ind
    lines = []
    for kind, node, no in nodes:
        if kind == "repeat":
            lines.append(f"{pad}- repeat: {node['repeat']}    # {no}")
            if node["on_break"] == "break":
                lines.append(f"{pad}  on_break: break")
            lines.append(f"{pad}  steps:")
            lines += _emit(node["steps"], ind + 4)
        elif kind == "branch":
            lines.append(f"{pad}- branch:    # {no}")
            for arm in node["arms"]:
                if not arm or arm[0][0] != "step":
                    raise FlowError(f"步驟 {no}：分岔的每個分支開頭要是找圖步驟，"
                                    "寫不出 flow.yaml")
                (_, cond, cno), rest = arm[0], arm[1:]
                lines.append(f"{pad}    - if: {_flow_style(cond)}    # {cno}")
                if rest:
                    lines.append(f"{pad}      then:")
                    lines += _emit(rest, ind + 8)
            if node["on_break"] == "break":
                lines.append(f"{pad}  on_break: break")
        else:
            lines.append(f"{pad}- {_flow_style(node)}    # {no}")
    return lines


def write_flow(folder, flow, images=None):
    """把記憶體的流程寫成流程資料夾; 回傳被引用卻沒有圖的範本名.

    images: {範本名: bytes 或圖檔路徑}——要放進 templates/ 的圖 (先全部讀進記憶體再寫,
    改名互換也不會互相蓋掉)。寫完 templates/ 正好是引用集合裡有圖的那些: 沒被引用的
    png 刪掉。flow.yaml 先寫暫存檔再取代, 寫到一半失敗不會留半份。
    """
    folder = str(folder)
    refs = template_refs(flow)
    for n in refs:
        problem = template_name_problem(n)
        if problem:
            raise FlowError(problem)
    text = dump_flow(flow)
    blobs = {n: _blob(src) for n, src in (images or {}).items() if n in refs}
    tdir = os.path.join(folder, TEMPLATES_DIR)
    os.makedirs(tdir, exist_ok=True)
    for n, data in blobs.items():
        with open(os.path.join(tdir, n + ".png"), "wb") as f:
            f.write(data)
    keep = set(refs)
    for fn in os.listdir(tdir):
        if fn.lower().endswith(".png") and fn[:-4] not in keep:
            os.remove(os.path.join(tdir, fn))
    tmp = os.path.join(folder, FLOW_YAML + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, os.path.join(folder, FLOW_YAML))
    return [n for n in refs if not os.path.isfile(os.path.join(tdir, n + ".png"))]

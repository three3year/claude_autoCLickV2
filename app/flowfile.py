"""流程存檔與工作區: 資料進資料出, 純檔案邏輯 (GUI 無關).

**一份`流程`＝一個自包自足的存檔** (副檔名 `.autoclickpack`, zip)::

    flow.json               步驟與流程層級設定 (含 coordSpace、`校準對`與`基準距離`、
                            `補做間隔`、`忙碌指示`)
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
from automation import findtarget, flowfmt

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


# 流程層級的`補做`設定 (ADR 0008; 存法比照 avoidHover, 缺鍵＝預設值, 舊存檔不必遷移)
RETRY_KEY = "retryIntervalMs"   # `補做間隔` (毫秒)
RETRY_DEFAULT_MS = 1000
BUSY_KEY = "busyTarget"         # `忙碌指示`: 一個`找圖目標`, 不設＝沒有這個鍵
# `忙碌出現等候` (ADR 0011): `忙碌檢查`送出輸入後最多等忙碌指示出現的毫秒數
BUSY_APPEAR_KEY = "busyAppearMs"
BUSY_APPEAR_DEFAULT_MS = 1000


def _ms_setting(data, key, default):
    """流程層級的毫秒設定; 缺鍵或壞值＝預設."""
    try:
        return max(0, int((data or {}).get(key, default)))
    except (TypeError, ValueError):
        return default


def retry_interval_ms(data):
    """流程的`補做間隔` (毫秒); 缺或壞＝預設 1000."""
    return _ms_setting(data, RETRY_KEY, RETRY_DEFAULT_MS)


def busy_appear_ms(data):
    """流程的`忙碌出現等候` (毫秒); 缺或壞＝預設 1000."""
    return _ms_setting(data, BUSY_APPEAR_KEY, BUSY_APPEAR_DEFAULT_MS)


def busy_target(data):
    """流程的`忙碌指示` (找圖目標); 沒設回傳 None."""
    tgt = (data or {}).get(BUSY_KEY)
    return tgt if isinstance(tgt, dict) and tgt.get("template") else None


def flow_refs(data):
    """一份流程引用的全部範本名 (已排序): 步驟的`找圖目標` + 流程層級設定
    (`校準對`、`忙碌指示`).

    規則在 findtarget.referenced_templates (範本預載也照它): 存檔只打包它們、
    對話框收回未使用的新圖時保留它們——校準對不被步驟引用, 漏了它, 存檔一整理
    流程就不能執行。
    """
    cal = calibration.flow_pair(data)
    busy = busy_target(data)
    extra = [*(cal["pair"] if cal else ()), *([busy["template"]] if busy else ())]
    return sorted(findtarget.referenced_templates(data.get("steps") or [], extra))


def rename_flow_refs(data, old, new):
    """把整份流程對 `old` 的引用 (步驟 + 校準對 + 忙碌指示) 就地改成 `new`;
    回傳改動筆數."""
    changed = rename_refs(data.get("steps") or [], old, new)
    cal = calibration.flow_pair(data)
    if cal:
        for i, n in enumerate(cal["pair"]):
            if n == old:
                cal["pair"][i] = new
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
    stamped = _stamped(data)
    refs = flow_refs(stamped)
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
    stamped = _stamped(data)
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
    return data


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

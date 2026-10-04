"""流程存檔與工作區: 資料進資料出, 純檔案邏輯 (GUI 無關).

**一份`流程`＝一個自包自足的存檔** (副檔名 `.autoclickpack`, zip)::

    flow.json               步驟與流程層級設定 (含 coordSpace、`校準對`與`基準距離`)
    templates/<名稱>.png    本流程引用到的範本圖 (一範本一張圖, 名稱平面無層級)
    templates/_meta.json    範本元資料: {"pos": {範本名: [x, y]}}

存檔**只寫入被引用的**範本 (步驟的找圖目標含`確認圖`, 以及流程的`校準對`,
見 `flow_refs`): 刪掉引用它的步驟再存檔, 那張圖就離開存檔——檔案內容永遠等於
流程真正需要的東西。

**工作區** (`<profile>/workspace/`) 是 profile 底下可重建的快取: 當前流程解出來
的範本圖與引擎的`登錄產物`都放這。**存檔是真相來源, 工作區只是快取**——被刪或
毀損時自動重建; 切換流程時整個清空 (圖與登錄產物一起刪)。

舊格式的單向匯入 (舊 autoClick flow JSON、舊流程包) 與一次性轉換所需的規則
(多截圖取`登錄基準張`、範本名拉平、撞名加序號並改寫引用) 都在本模組, 不另立
門戶: 格式規則只有一個地方說得上話。存檔原樣搬到哪台機器、哪個 profile 都一樣
(尺度與比例尺跟著流程走, ADR 0009), 所以開外來檔與匯入都不換算座標。
(更早版本存檔裡的 calibration.json / calibration/ 項目讀檔時安靜忽略。)
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
FORMAT = 4                 # 寫檔一律蓋這個版本 (3: 範本收進`找圖目標`, ADR 0007;
                           # 4: 流程自帶`校準對`與`基準距離`, ADR 0009)
SELF_CONTAINED_SINCE = 2   # 2 起就是自包自足存檔; 2 → 3 只是步驟結構遷移;
                           # 3 以前沒有校準對 (讀進來＝沒有校準對, 不能執行)

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


# ================= 範本名稱與步驟引用 =================

def strip_ext(name):
    """範本引用去 .png 副檔名 (舊 flow → 引擎範本名; 已無副檔名時不動)."""
    return name[:-4] if name.lower().endswith(".png") else name


def clean_name(name):
    """清理使用者輸入的範本名: 平面名稱, 沒有資料夾層級.

    路徑分隔與檔名非法字元一律換成 `_` (不是丟棄, 否則 `a/b` 會靜靜變成 `ab`)。
    清不出東西時回空字串, 由呼叫端決定怎麼辦。
    """
    name = re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip().strip(".")
    return re.sub(r"_+", "_", name)


def flatten_name(name):
    """一次性轉換用: 舊的相對路徑範本名拉平成平面名稱 (`cn/V` → `V`).

    子路徑前綴在新格式裡失去意義 (一份流程的範本不需要命名空間), 拿掉之後
    範本面板上的名字才乾淨好認; 拉平撞名由 `free_name` 加序號解決。
    """
    return clean_name(str(name).replace("\\", "/").rsplit("/", 1)[-1]) or "template"


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


def retry_interval_ms(data):
    """流程的`補做間隔` (毫秒); 缺或壞＝預設 1000."""
    try:
        return max(0, int((data or {}).get(RETRY_KEY, RETRY_DEFAULT_MS)))
    except (TypeError, ValueError):
        return RETRY_DEFAULT_MS


def busy_target(data):
    """流程的`忙碌指示` (找圖目標); 沒設回傳 None."""
    tgt = (data or {}).get(BUSY_KEY)
    return tgt if isinstance(tgt, dict) and tgt.get("template") else None


def flow_refs(data):
    """一份流程引用的全部範本名 (已排序): 步驟的`找圖目標` + 流程層級設定
    (`校準對`、`忙碌指示`).

    「被引用的範本」只有這一份定義: 存檔只打包它們、範本預載載它們、對話框
    收回未使用的新圖時保留它們——校準對不被步驟引用, 漏了它, 存檔一整理
    流程就不能執行。
    """
    refs = set(used_templates(data.get("steps") or []))
    cal = calibration.flow_pair(data)
    if cal:
        refs.update(cal["pair"])
    busy = busy_target(data)
    if busy:
        refs.add(busy["template"])
    return sorted(refs)


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
    used = set()
    for s in steps:
        if s.get("type") == "find_click" and findtarget.template(s):
            used.add(findtarget.template(s))
        if (s.get("type") in findtarget.CONFIRMABLE
                and s.get("confirm") == "appear"
                and findtarget.confirm_template(s)):
            used.add(findtarget.confirm_template(s))
    return sorted(used)


# flowFormat 2 的步驟欄位: 範本名直接掛在步驟上 → 3 的`找圖目標`
_V2_KEYS = (("template", findtarget.TARGET),
            ("confirmTemplate", findtarget.CONFIRM_TARGET))


def _migrate_step(step):
    """flowFormat 2 → 3: 範本名與確認圖範本名搬進對應的找圖目標 (就地, 冪等).

    空的確認圖範本名不留空目標。
    """
    for old, new in _V2_KEYS:
        if old not in step:
            continue
        name = step.pop(old)
        if isinstance(name, str) and name and not isinstance(step.get(new), dict):
            step[new] = {"template": name}


def _migrate_steps(steps):
    """flowFormat 2 → 3 的步驟結構遷移 (冪等): 範本名搬進`找圖目標`."""
    for s in steps or []:
        _migrate_step(s)


def migrate_flow(data):
    """舊 flow dict 就地遷移成新格式, 回傳提示訊息 list.

    座標空間 (螢幕→範圍)、範本名搬進`找圖目標` (flowFormat 2 → 3)、範本引用
    去副檔名、每步 threshold 丟棄。對已是新格式的資料是 no-op, 所有讀檔路徑
    (存檔、步驟草稿、舊 JSON、舊流程包) 一律先過這一關。
    """
    notes = []
    note = flowfmt.to_region_space(data)
    if note:
        notes.append(note)
    # 退場的`來源基準`標記 (ADR 0009 前的匯入換算): 帶著的舊存檔安靜忽略
    data.pop("sourceBaseline", None)
    for s in data.get("steps") or []:
        s.pop("threshold", None)
        _migrate_step(s)
        for _, t in findtarget.step_targets(s):
            if t.get("template"):
                t["template"] = strip_ext(t["template"])
    return notes


# ================= 目錄掃描 (舊範本庫 / 工作區) =================

def scan_templates(root):
    """掃一個範本圖目錄成`範本清單`: {範本名: [圖檔路徑, ...]}.

    範本名＝相對路徑不含副檔名; 「只含影像檔的資料夾」是一個多截圖範本
    (舊範本庫的形式), 含子資料夾的資料夾是命名空間。工作區是平面的單張圖,
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


def baseline_capture(paths):
    """多截圖範本降為單張時保留的那一張＝`登錄基準張` (排序後第一張).

    與引擎登錄時的排序一致, 所以降級後的圖就是原本的參考影像來源。
    """
    return sorted(paths)[0]


# ================= 流程存檔 (zip) =================

def _blob(src):
    """把 bytes 或檔案路徑統一成 bytes (存檔一律寫實體內容, 不留參照)."""
    if isinstance(src, (bytes, bytearray)):
        return bytes(src)
    return Path(src).read_bytes()


def write(path, data, images, pos=None):
    """寫出一份自包自足的流程存檔; 回傳被引用卻缺圖的範本名 list.

    images: {範本名: bytes 或圖檔路徑}。只有 `data` 引用到的範本 (步驟與校準對,
    `flow_refs`) 會進存檔 (未被引用的圖不進去, 存檔才不會囤積用不到的圖)。缺圖不是
    致命錯誤 (使用者可能剛刪掉範本, 步驟由既有機制標示為有問題), 回報給呼叫端
    寫進執行紀錄即可。
    """
    images = images or {}
    stamped = json.loads(json.dumps(data))  # 深拷貝: 不改呼叫端的資料
    _migrate_steps(stamped.get("steps"))     # 寫出的步驟一律是 v3 結構
    stamped[FORMAT_KEY] = FORMAT
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


def is_flow_file(path):
    """這份檔案是本 app 的自包自足存檔嗎 (不是＝舊格式, 要走單向轉換).

    只讀 zip 內的 flow.json 判標記; 不是 zip、讀不出來都算不是。
    """
    try:
        if not zipfile.is_zipfile(path):
            return False
        with zipfile.ZipFile(path) as z:
            data = json.loads(z.read(FLOW_ENTRY).decode("utf-8"))
        return int(data.get(FORMAT_KEY, 0)) >= SELF_CONTAINED_SINCE
    except (OSError, KeyError, ValueError, TypeError):
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
    """讀一份流程存檔, 回傳資料進資料出的 dict.

    keys: data (已過 migrate_flow 的流程資料, 校準對在 data 裡)、notes (遷移
    提示)、images ({範本名: bytes})、pos。
    """
    with zipfile.ZipFile(path) as z:
        data = json.loads(z.read(FLOW_ENTRY).decode("utf-8"))
        notes = migrate_flow(data)
        try:
            meta = json.loads(z.read(META_ENTRY).decode("utf-8"))
        except (KeyError, ValueError):
            meta = {}
        pos = meta.get("pos", meta) if isinstance(meta, dict) else {}
        images = {n: z.read(f"{TMPL_PREFIX}{n}.png")
                  for n in _entry_names(z, TMPL_PREFIX)}
    return {"data": data, "notes": notes, "images": images,
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
    圖已經在工作區裡, 當機重開時草稿與工作區的圖一起復原。
    """
    try:
        os.makedirs(flows_dir(profile_dir), exist_ok=True)
        with open(draft_path(profile_dir), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def read_draft(profile_dir):
    """讀步驟草稿 (已過遷移); 缺檔/壞檔回傳 None."""
    try:
        with open(draft_path(profile_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    migrate_flow(data)
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
        改圖不影響本流程)。`pos`＝截圖當下的中心螢幕座標, 只有本流程自己拍的
        圖才有 (跨流程複製與磁碟上傳的沒有)。
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
        """{範本名: [x, y]}: 各範本截圖當下的中心螢幕座標 (缺檔＝空)."""
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


# ================= 一次性轉換 / 舊格式匯入的共用規則 =================

def collect_flow_templates(steps, library, taken=()):
    """把一份舊流程引用的範本收成新存檔要的平面`範本清單`, 並就地改寫引用.

    `library`: {舊範本名: [圖檔路徑, ...]} (`scan_templates` 的結果)。
    規則: 範本名拉平 → 撞名加序號並同步改寫步驟引用 → 多截圖取`登錄基準張`。

    回傳 dict: images ({新名稱: 圖檔路徑})、mapping ({舊名: 新名}, 全部收進來
    的都列)、renamed (mapping 中真的改了名的)、downgraded (原本是多截圖、降為
    單張的新名稱)、missing (範本庫裡找不到的舊名)。
    """
    images, mapping, downgraded, missing = {}, {}, [], []
    used = set(taken)
    for old in used_templates(steps):
        caps = library.get(old)
        if not caps:
            missing.append(old)
            continue
        new = free_name(flatten_name(old), used)
        used.add(new)
        images[new] = baseline_capture(caps)
        mapping[old] = new
        if len(caps) > 1:
            downgraded.append(new)
        if new != old:
            rename_refs(steps, old, new)
    return {"images": images, "mapping": mapping,
            "renamed": {k: v for k, v in mapping.items() if k != v},
            "downgraded": sorted(downgraded), "missing": sorted(missing)}


# ================= 舊格式匯入 =================

def _pack_library(z, refs):
    """舊流程包 (zip) 內的範本佈局 → {舊範本名: [zip 內項目名, ...]}.

    對應規則與舊 pack 落地時相同: 整個路徑 (去副檔名) 是被引用的範本 → 單截圖;
    上層目錄才是被引用的範本 → 多截圖範本目錄裡的一張截圖。
    """
    lib = {}
    for fn in z.namelist():
        if (not fn.startswith(TMPL_PREFIX) or fn.endswith("/")
                or fn.startswith(TMPL_PREFIX + "_orig/")
                or not fn.lower().endswith(_IMG_EXTS)):
            continue
        rel = fn[len(TMPL_PREFIX):]
        name = strip_ext(rel)
        parent = name.rsplit("/", 1)[0] if "/" in name else ""
        tname = parent if (parent in refs and name not in refs) else name
        lib.setdefault(tname, []).append(fn)
    return {k: sorted(v) for k, v in lib.items()}


def import_legacy(path, profile_dir, stem=None):
    """匯入舊格式 (舊 autoClick flow JSON 或舊流程包) → 一份新存檔.

    單向轉換 (ADR 0002): 舊格式進得來、出不去。回傳 dict:
    flow_path (落地的新存檔)、data、notes、templates (帶進來的範本名)、
    renamed、downgraded、missing。舊格式沒有流程層級的`校準對`: 匯入後的流程
    可以開、可以看, 設定校準對之前不能執行。
    """
    stem = stem or os.path.splitext(os.path.basename(path))[0]
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            data = json.loads(z.read(FLOW_ENTRY).decode("utf-8"))
            notes = migrate_flow(data)
            refs = set(used_templates(data.get("steps") or []))
            lib = _pack_library(z, refs)
            try:
                meta = json.loads(z.read(META_ENTRY).decode("utf-8"))
            except (KeyError, ValueError):
                meta = {}
            pos_in = meta.get("pos", meta) if isinstance(meta, dict) else {}
            r = collect_flow_templates(data.get("steps") or [], lib)
            images = {n: z.read(entry) for n, entry in r["images"].items()}
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        notes = migrate_flow(data)
        # 舊 flow JSON 只有步驟, 範本要從舊範本庫 (同 profile 的 templates/) 收
        lib = scan_templates(os.path.join(profile_dir, "templates"))
        r = collect_flow_templates(data.get("steps") or [], lib)
        images = dict(r["images"])
        pos_in = legacy_meta_pos(os.path.join(profile_dir, "templates"))

    pos = {}
    for old, new in r["mapping"].items():
        p = pos_in.get(old) or pos_in.get(old + ".png")
        if p:
            pos[new] = p
    os.makedirs(flows_dir(profile_dir), exist_ok=True)
    flow_path = free_path(flows_dir(profile_dir), stem, EXT)
    write(flow_path, data, images, pos)
    return {"flow_path": flow_path, "data": data, "notes": notes,
            "templates": sorted(r["images"]), "renamed": r["renamed"],
            "downgraded": r["downgraded"], "missing": r["missing"]}


def legacy_meta_pos(templates_dir):
    """讀舊範本庫的 `_meta.json` pos 表 (舊平面格式 name→[x,y] 一併遷移)."""
    try:
        with open(os.path.join(templates_dir, "_meta.json"),
                  encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return {}
    if meta and "pos" not in meta and "rot" not in meta:
        return meta  # 舊格式 (name→[x,y])
    return meta.get("pos", {})


def adopt_foreign_flow(path, profile_dir):
    """開啟不在本 profile 裡的存檔: 原樣複製副本進 profile 再開 (原檔不被動到).

    不換算: 流程自帶尺度與校準對 (ADR 0009), 搬到哪裡都一樣, 執行開頭自己量。
    回傳 dict: flow_path (副本)、data、notes。
    """
    r = read(path)
    os.makedirs(flows_dir(profile_dir), exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    dest = free_path(flows_dir(profile_dir), stem, EXT)
    write(dest, r["data"], r["images"], r["pos"])
    return {"flow_path": dest, "data": r["data"], "notes": r["notes"]}

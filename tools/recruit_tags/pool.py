"""建池: gacha_table + character_table → `招募池`快照 (一服一份 JSON, 進版控).

- 29 個`招募標籤`取自 gacha_table 的 gachaTags (tagId 1-29; 國服另有的性別標籤
  1012/1013 不是招募標籤, 不收)。組合邏輯只認 tagId, 字面只用於渲染與顯示。
- 招募池成員取自 recruitDetail: 去標記、按行, 星數行之後的行以「/」拆名; 以名字
  到 character_table 找幹員 (只認 char_ 開頭的條目——召喚物 trap_ 會和幹員同名)。
- 幹員的標籤集合 = tagList + 職業標籤 + 位置標籤 + 資質標籤 (5★ 資深、6★ 高資——
  tagList 裡沒有, 照 arkntools 依星數補); 稀有度 TIER_n → n。
- 名字對不上、欄位缺、標籤字面不認得: 失敗並列出全部問題, 不產生快照。
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from .errors import ToolError

DATA_DIR = Path(__file__).resolve().parent / "data"

SOURCES = {
    "tw": {
        "repo": "arkntools/arknights-data-tw-for-maa",
        "branch": "main",
        "path": "",
    },
    "cn": {
        "repo": "Kengxxiao/ArknightsGameData",
        "branch": "master",
        "path": "zh_CN/gamedata/excel/",
    },
}

# 組合邏輯只認 tagId; 本工具用到的 tagId 都在這裡
TAG_IDS = range(1, 30)
SENIOR_PLUS = 11   # 高級資深幹員
SENIOR = 14        # 資深幹員
ROBOT = 28         # 支援機械

PROFESSION_TAG = {"WARRIOR": 1, "SNIPER": 2, "TANK": 3, "MEDIC": 4, "SUPPORT": 5,
                  "CASTER": 6, "SPECIAL": 7, "PIONEER": 8}
POSITION_TAG = {"MELEE": 9, "RANGED": 10}
RARITY_TAG = {6: SENIOR_PLUS, 5: SENIOR}

# 上游資料本身字面不一致的名字: recruitDetail 的寫法 → character_table 的寫法
NAME_ALIASES = {
    # 台服 recruitDetail 寫「奧」(U+5967), character_table 寫「奥」(U+5965)
    "tw": {"奧斯塔": "奥斯塔"},
    "cn": {},
}

_MARKUP = re.compile(r"<[@$][^>]*>|</>")
_STARS = re.compile(r"^(★+)\s*$")


def raw_url(server, table):
    src = SOURCES[server]
    return (f"https://raw.githubusercontent.com/{src['repo']}/{src['branch']}/"
            f"{src['path']}{table}.json")


def snapshot_path(server):
    return DATA_DIR / f"pool_{server}.json"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def recruit_names(detail):
    """recruitDetail → 招募池名字清單 (保序)."""
    text = _MARKUP.sub("", detail).replace("\\n", "\n").replace("\r", "")
    names, in_pool = [], False
    for line in text.split("\n"):
        line = line.strip()
        if _STARS.match(line):
            in_pool = True
            continue
        if not in_pool or not line or set(line) == {"-"}:
            continue
        names += [n.strip() for n in line.split("/") if n.strip()]
    return names


def _operators(character):
    """名字 → character_table 條目 (只收 char_ 開頭)."""
    out = {}
    for key, v in character.items():
        if key.startswith("char_") and isinstance(v, dict) and "name" in v:
            out.setdefault(v["name"], v)
    return out


def build_pool(gacha, character, server, *, upstream_updated=None, fetched_at=None):
    """gacha_table、character_table (已解析的 JSON) → 招募池快照 (dict).

    upstream_updated: 上游最後提交時間 (CLI 從 GitHub API 取); fetched_at 預設現在。
    """
    if server not in SOURCES:
        raise ToolError(f"不認得的伺服器「{server}」（只有 {'、'.join(SOURCES)}）")
    try:
        detail = gacha["recruitDetail"]
        tags = sorted(({"id": int(t["tagId"]), "name": t["tagName"]}
                       for t in gacha["gachaTags"]), key=lambda t: t["id"])
    except (KeyError, TypeError, ValueError):
        raise ToolError("gacha_table 缺 gachaTags 或 recruitDetail，或 gachaTags 格式不認得") from None
    tags = [t for t in tags if t["id"] in TAG_IDS]
    if [t["id"] for t in tags] != list(TAG_IDS):
        raise ToolError(f"gachaTags 的招募標籤不是 tagId 1-29 各一個"
                        f"（拿到 {[t['id'] for t in tags]}）")
    by_text = {t["name"]: t["id"] for t in tags}

    table = _operators(character)
    aliases = NAME_ALIASES[server]
    missing, broken, operators = [], [], []
    for name in recruit_names(detail):
        c = table.get(aliases.get(name, name))
        if c is None:
            missing.append(name)
            continue
        try:
            rarity = int(str(c["rarity"]).removeprefix("TIER_"))
            ids = {PROFESSION_TAG[c["profession"]], POSITION_TAG[c["position"]]}
            if rarity in RARITY_TAG:
                ids.add(RARITY_TAG[rarity])
            for text in c["tagList"]:
                if text not in by_text:
                    raise KeyError(f"標籤「{text}」")
                ids.add(by_text[text])
        except (KeyError, ValueError, TypeError) as e:
            broken.append(f"{name}（{e}）")
            continue
        operators.append({"name": name, "rarity": rarity, "tags": sorted(ids)})
    problems = []
    if missing:
        problems.append("招募池裡這些名字在幹員表找不到：" + "、".join(missing))
    if broken:
        problems.append("這些幹員缺欄位或欄位不認得：" + "、".join(broken))
    if problems:
        raise ToolError("；".join(problems) + "。快照沒有產生（上游改了字面時，"
                        "在 pool.py 的 NAME_ALIASES 補對照）")
    if not operators:
        raise ToolError("recruitDetail 裡沒有任何幹員名字（格式可能改了）")
    return {
        "server": server,
        "source": {
            "gacha_table": raw_url(server, "gacha_table"),
            "character_table": raw_url(server, "character_table"),
            "upstream_updated": upstream_updated,
            "fetched_at": fetched_at or _now(),
        },
        "tags": tags,
        "operators": operators,
    }


def tag_names(snapshot):
    """快照 → {tagId: 字面}."""
    return {t["id"]: t["name"] for t in snapshot["tags"]}


def load_pool(path_or_server):
    """讀快照: 給伺服器代號 (tw/cn) 讀工具資料夾裡的, 或給路徑."""
    p = (snapshot_path(path_or_server) if path_or_server in SOURCES
         else Path(path_or_server))
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise ToolError(f"讀不到招募池快照 {p}（{e}）；先跑 fetch-pool") from None


def save_pool(snapshot, path=None):
    p = Path(path) if path else snapshot_path(snapshot["server"])
    p.parent.mkdir(parents=True, exist_ok=True)

    def rows(items):   # 一個標籤 / 一位幹員一行: 新幹員進池時 diff 好讀
        return ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in items)

    head = json.dumps({"server": snapshot["server"], "source": snapshot["source"]},
                      ensure_ascii=False, indent=1)[:-2]
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(f'{head},\n "tags": [\n{rows(snapshot["tags"])}\n ],\n'
                f' "operators": [\n{rows(snapshot["operators"])}\n ]\n}}\n')
    return p

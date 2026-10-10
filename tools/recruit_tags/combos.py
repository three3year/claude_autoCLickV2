"""保底組合: 照 arkntools 的公開招募計算 (src/views/Hr.vue 的 combinations / guarantees).

- 列舉辨識出的標籤的 1–3 子集; 候選 = 招募池中標籤集合包含子集全部標籤的幹員;
  子集不含「高級資深幹員」時剔除 6★
- 最低稀有度只看 3★ 以上的候選 (沒有 3★ 以上時看全部——機器人組合就落在這裡);
  含高資的子集候選只有 6★、含資深的只有 5★, 所以等級自然是 6 / 5
- 最低稀有度 ≥ 4 才是`保底組合`, 等級 = 最低稀有度
- 去冗餘: 真子集已是同等級以上的保底組合時不列 (機器人組合同理)
- 排序: 標籤數少者前、等級高者前
- 機器人: 子集含「支援機械」且候選有 1★ → 另列 (要設 3:50 以下時限), 不混進保底
"""
from __future__ import annotations

from itertools import combinations

from .pool import ROBOT, SENIOR_PLUS, tag_names


def _candidates(comb, operators):
    need = set(comb)
    chars = [o for o in operators if need <= set(o["tags"])]
    if SENIOR_PLUS not in need:
        chars = [o for o in chars if o["rarity"] != 6]
    return chars


def _entry(comb, names, chars, **extra):
    chars = sorted(chars, key=lambda o: (-o["rarity"], o["name"]))
    return {"tags": [{"id": t, "name": names[t]} for t in comb], **extra,
            "operators": [{"name": o["name"], "rarity": o["rarity"]} for o in chars]}


def guarantees(tags, pool):
    """辨識出的標籤 (tagId, 依格子順序) → {"combos": [...], "robots": [...]}."""
    names = tag_names(pool)
    tags = list(dict.fromkeys(tags))
    combos, robots = [], []
    for k in (1, 2, 3):
        for comb in combinations(tags, k):
            chars = _candidates(comb, pool["operators"])
            if not chars:
                continue
            counted = [o for o in chars if o["rarity"] >= 3] or chars
            level = min(o["rarity"] for o in counted)
            sub = set(comb)
            if level >= 4 and not any(set(c[0]) < sub and c[1] >= level for c in combos):
                combos.append((comb, level, counted))
            if (ROBOT in sub and any(o["rarity"] == 1 for o in chars)
                    and not any(set(c[0]) < sub for c in robots)):
                robots.append((comb, chars))
    combos.sort(key=lambda c: (len(c[0]), -c[1]))
    return {"combos": [_entry(c, names, chars, level=lv) for c, lv, chars in combos],
            "robots": [_entry(c, names, chars) for c, chars in robots]}

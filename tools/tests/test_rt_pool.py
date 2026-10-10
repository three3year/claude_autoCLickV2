"""公開招募 票 01 — 建池入口: 迷你 gacha_table / character_table → 招募池快照."""
import pytest

import recruit_tags
from rt_synth import TAG_ID, TAGS_CN, TAGS_TW, char, character_table, gacha_table

T = TAG_ID


def ops(snapshot):
    return {o["name"]: o for o in snapshot["operators"]}


def mini_tw():
    gacha = gacha_table(TAGS_TW, [
        (1, ["<@rc.eml>Lancet-2</>"]),
        (3, ["芬", "<@rc.eml>香草</>"]),
        (5, ["獅蠍"]),
    ])
    chars = character_table(
        char("Lancet-2", 1, "MEDIC", "RANGED", ["支援機械", "治療"], key="char_285_medic2"),
        char("芬", 3, "PIONEER", "MELEE", ["費用回復"], key="char_123_fang"),
        char("香草", 3, "PIONEER", "MELEE", ["費用回復"], key="char_124_kroos"),
        char("獅蠍", 5, "SPECIAL", "MELEE", ["輸出", "生存"], key="char_215_mantic"),
        # 同名的召喚物: 不是幹員, 不能被當成獅蠍
        char("獅蠍", 1, "TRAP", "NONE", [], key="trap_470_tmantic"),
    )
    return gacha, chars


def test_建池取出29個標籤與招募池幹員的稀有度和標籤集合():
    gacha, chars = mini_tw()

    snap = recruit_tags.build_pool(gacha, chars, "tw")

    assert [(t["id"], t["name"]) for t in snap["tags"]] == list(enumerate(TAGS_TW, 1))
    o = ops(snap)
    assert set(o) == {"Lancet-2", "芬", "香草", "獅蠍"}
    assert o["Lancet-2"]["rarity"] == 1
    assert set(o["Lancet-2"]["tags"]) == {T["支援機械"], T["治療"], T["醫療幹員"], T["遠程位"]}
    assert o["獅蠍"]["rarity"] == 5
    assert set(o["獅蠍"]["tags"]) == {T["輸出"], T["生存"], T["特種幹員"], T["近戰位"],
                                    T["資深幹員"]}


def test_五星帶資深幹員六星帶高級資深幹員():
    gacha = gacha_table(TAGS_TW, [(5, ["五星"]), (6, ["六星"])])
    chars = character_table(char("五星", 5, "SNIPER", "RANGED", [], key="char_5_a"),
                            char("六星", 6, "SNIPER", "RANGED", [], key="char_6_a"))

    o = ops(recruit_tags.build_pool(gacha, chars, "tw"))

    assert T["資深幹員"] in o["五星"]["tags"] and T["高級資深幹員"] not in o["五星"]["tags"]
    assert T["高級資深幹員"] in o["六星"]["tags"] and T["資深幹員"] not in o["六星"]["tags"]


@pytest.mark.parametrize("profession,tag", [
    ("WARRIOR", "近衛幹員"), ("SNIPER", "狙擊幹員"), ("TANK", "重裝幹員"),
    ("MEDIC", "醫療幹員"), ("SUPPORT", "輔助幹員"), ("CASTER", "術師幹員"),
    ("SPECIAL", "特種幹員"), ("PIONEER", "先鋒幹員")])
@pytest.mark.parametrize("position,ptag", [("MELEE", "近戰位"), ("RANGED", "遠程位")])
def test_職業與位置轉成對應的標籤(profession, tag, position, ptag):
    gacha = gacha_table(TAGS_TW, [(4, ["某人"])])
    chars = character_table(char("某人", 4, profession, position, ["輸出"], key="char_1_a"))

    snap = recruit_tags.build_pool(gacha, chars, "tw")

    assert set(snap["operators"][0]["tags"]) == {T["輸出"], T[tag], T[ptag]}


def test_名字對不上時失敗並列出全部對不上的名字():
    gacha = gacha_table(TAGS_TW, [(3, ["芬", "查無此人"]), (4, ["也查無此人"])])
    chars = character_table(char("芬", 3, "PIONEER", "MELEE", [], key="char_1_fang"))

    with pytest.raises(recruit_tags.ToolError) as e:
        recruit_tags.build_pool(gacha, chars, "tw")

    assert "查無此人" in str(e.value) and "也查無此人" in str(e.value)


def test_幹員缺欄位時失敗並列出名字():
    gacha = gacha_table(TAGS_TW, [(3, ["芬"])])
    chars = {"char_1_fang": {"name": "芬", "rarity": "TIER_3", "position": "MELEE",
                             "tagList": []}}   # 沒有 profession

    with pytest.raises(recruit_tags.ToolError, match="芬"):
        recruit_tags.build_pool(gacha, chars, "tw")


def test_幹員帶不認得的標籤字面時失敗():
    gacha = gacha_table(TAGS_TW, [(3, ["芬"])])
    chars = character_table(char("芬", 3, "PIONEER", "MELEE", ["高空"], key="char_1_fang"))

    with pytest.raises(recruit_tags.ToolError, match="高空"):
        recruit_tags.build_pool(gacha, chars, "tw")


def test_台服招募說明的奧斯塔對到幹員表的奥斯塔():
    # 上游台服資料: recruitDetail 寫「奧」(U+5967), character_table 寫「奥」(U+5965)
    gacha = gacha_table(TAGS_TW, [(5, ["奧斯塔"])])
    chars = character_table(char("奥斯塔", 5, "SNIPER", "RANGED", ["群攻"],
                                 key="char_346_aosta"))

    snap = recruit_tags.build_pool(gacha, chars, "tw")

    assert ops(snap)["奧斯塔"]["rarity"] == 5


def test_快照記下伺服器來源網址上游更新時間與抓取時間():
    gacha, chars = mini_tw()

    snap = recruit_tags.build_pool(gacha, chars, "tw", upstream_updated="2026-10-08T08:13:01Z",
                                   fetched_at="2026-10-10T08:00:00Z")

    assert snap["server"] == "tw"
    src = snap["source"]
    assert "arknights-data-tw-for-maa" in src["gacha_table"]
    assert "arknights-data-tw-for-maa" in src["character_table"]
    assert src["upstream_updated"] == "2026-10-08T08:13:01Z"
    assert src["fetched_at"] == "2026-10-10T08:00:00Z"


def test_沒給抓取時間時記下現在():
    gacha, chars = mini_tw()

    snap = recruit_tags.build_pool(gacha, chars, "tw")

    assert snap["source"]["fetched_at"].startswith("20")


def test_國服字面不同但tagId一致且接受字面反斜線換行():
    gacha = gacha_table(TAGS_CN + ["男性干员"], [(5, ["狮蝎"])], newline="\\n")
    gacha["gachaTags"][-1]["tagId"] = 1012       # 國服多出的性別標籤: 不是招募標籤
    chars = character_table(char("狮蝎", 5, "SPECIAL", "MELEE", ["输出", "生存"],
                                 key="char_215_mantic"))

    snap = recruit_tags.build_pool(gacha, chars, "cn")

    assert [t["id"] for t in snap["tags"]] == list(range(1, 30))
    assert snap["tags"][0]["name"] == "近卫干员"
    assert "Kengxxiao" in snap["source"]["gacha_table"]
    assert set(snap["operators"][0]["tags"]) == {T["輸出"], T["生存"], T["特種幹員"], T["近戰位"],
                                                 T["資深幹員"]}


def test_不認得的伺服器拒絕():
    gacha, chars = mini_tw()

    with pytest.raises(recruit_tags.ToolError):
        recruit_tags.build_pool(gacha, chars, "jp")

"""公開招募 票 03 — 保底組合: 透過辨識入口以迷你快照打 (不另開接縫).

假畫面上的五格都選辨識會通過的字面 (見 test_rt_recognize 的說明); 「資深幹員」
在同族範本前會混淆, 測資深 5★ 時把 tagId 14 的字面換成「前輩」——組合只認 tagId。
"""
import pytest

import recruit_tags
from rt_synth import TAGS_CN, TAGS_TW, fake_screen, pool

SENIOR = {"資深幹員": "前輩"}
OPS = [
    ("六星", 6, ["高級資深幹員", "輸出"]),
    ("五星", 5, ["資深幹員", "輸出"]),
    ("四星控", 4, ["控場", "輸出"]),
    ("四星控二", 4, ["控場"]),
    ("三星輸", 3, ["輸出"]),
    ("機器人", 1, ["支援機械", "輸出"]),
]
FIVE = ["高級資深幹員", "前輩", "控場", "輸出", "支援機械"]


@pytest.fixture(scope="module")
def result(engine):
    return recruit_tags.recognize(fake_screen(FIVE), pool(OPS, rename=SENIOR), engine=engine)


def tags(combo):
    return [t["name"] for t in combo["tags"]]


def by_tags(res):
    return {tuple(tags(c)): c for c in res["combos"]}


def test_五格都認得(result):
    assert [c["tag"]["name"] for c in result["cells"]] == FIVE


def test_含高資的組合保底6星(result):
    c = by_tags(result)[("高級資深幹員",)]
    assert c["level"] == 6
    assert [o["name"] for o in c["operators"]] == ["六星"]


def test_資深單標籤保底5星(result):
    assert by_tags(result)[("前輩",)]["level"] == 5


def test_只有4星的標籤保底4星並附候選幹員(result):
    c = by_tags(result)[("控場",)]
    assert c["level"] == 4
    assert sorted((o["name"], o["rarity"]) for o in c["operators"]) == [
        ("四星控", 4), ("四星控二", 4)]


def test_靠3星拉低的組合不保底且不含高資時剔除6星(result):
    assert ("輸出",) not in by_tags(result)


def test_真子集已達同等級的冗餘組合不列並依標籤數與等級排序(result):
    assert [tags(c) for c in result["combos"]] == [["高級資深幹員"], ["前輩"], ["控場"]]


def test_機器人組合另列不混進保底(result):
    assert [tags(c) for c in result["robots"]] == [["支援機械"]]
    assert result["robots"][0]["operators"][0] == {"name": "機器人", "rarity": 1}
    assert all("支援機械" not in tags(c) for c in result["combos"])


def test_兩標籤保底排在單標籤之後(engine):
    ops = [("甲", 5, ["治療"]), ("乙", 5, ["輸出", "生存"]), ("丙", 4, ["輸出", "生存"]),
           ("丁", 3, ["輸出"]), ("戊", 3, ["生存"])]

    res = recruit_tags.recognize(fake_screen(["新手", "輸出", "生存", "治療", "支援"]),
                                 pool(ops), engine=engine)

    assert [(tags(c), c["level"]) for c in res["combos"]] == [
        (["治療"], 5), (["輸出", "生存"], 4)]


def test_混淆或未辨識的格子不參與組合(engine):
    ops = [("甲", 4, ["重裝幹員", "控場"]), ("乙", 5, ["控場"])]

    res = recruit_tags.recognize(fake_screen(["重裝幹員", "招募預算", "新手", "輸出", "生存"]),
                                 pool(ops), engine=engine)

    assert res["cells"][0]["status"] == "confused"
    assert res["combos"] == [] and res["robots"] == []


def test_兩服字面不同但tagId相同結果一致(engine, result):
    cn_names = dict(zip(TAGS_TW, TAGS_CN))
    ops_cn = [(n, r, [cn_names[t] for t in ts]) for n, r, ts in OPS]
    five_cn = ["高级资深干员", "前輩", "控场", "输出", "支援机械"]
    from recruit_tags import render
    cn = render.default_settings("cn")

    res = recruit_tags.recognize(fake_screen(five_cn, settings=cn),
                                 pool(ops_cn, server="cn", rename={"资深干员": "前輩"}),
                                 engine=engine, client="cn")

    def key(r):
        return ([([t["id"] for t in c["tags"]], c["level"], c["operators"]) for c in r["combos"]],
                [([t["id"] for t in c["tags"]], c["operators"]) for c in r["robots"]])
    assert key(res) == key(result)

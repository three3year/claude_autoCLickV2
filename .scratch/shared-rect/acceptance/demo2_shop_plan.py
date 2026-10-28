import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "v2f-rules-agent-docs" / "acceptance"))
import demo2_plan  # noqa: E402

GOODS = ("採購_招聘許可", "採購_裝置", "採購_初級作戰記錄", "採購_破損裝置", "採購_赤金")

PLAN = copy.deepcopy(demo2_plan.PLAN)
PLAN["shared_rects"] = {
    "商品區": {"frame": 2784, "box": [20, 268, 1542, 608],
              "why": "信用交易所的商品每天換格子，上下兩排都可能出現"}}


def _use_shared(items):
    n = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if "repeat" in item:
            n += _use_shared(item["steps"])
        for arm in item.get("branch", []):
            cond = arm["if"]
            if cond.get("find_click") in GOODS:
                assert cond.pop("scroll") == "horizontal"
                cond["rect"] = "商品區"
                n += 1
            n += _use_shared(arm.get("then", []))
    return n


assert _use_shared(PLAN["steps"]) == len(GOODS)
PLAN["report"]["notes"] = [
    t for t in PLAN["report"]["notes"] if "horizontal" not in t]

if __name__ == "__main__":
    with open(sys.argv[1], "w", encoding="utf-8") as fp:
        json.dump(PLAN, fp, ensure_ascii=False, indent=1)
    print(sys.argv[1])

"""shared-rect 票 06 驗收: demo2 計畫的商店改用一個共用矩形「商品區」.

    .venv/Scripts/python .scratch/shared-rect/acceptance/demo2_shop_plan.py <輸出 plan.json>

沿用 v2f-rules-agent-docs 驗收② 的計畫 (demo2_plan.py), 只改商店: 五個購買分支的條件引用
「商品區」、拿掉各自的 horizontal; 容器框在第 2784 幀量 (十張商品卡兩排全在、沒有彈窗):
卡片 x 22–1560、y 270–874。
"""
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

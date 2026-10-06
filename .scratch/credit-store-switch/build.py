"""把早班流程的採購區塊改成「重複區段 ×10 包一個 23 分支的分岔」(見 spec.md).

    .venv/Scripts/python.exe .scratch/credit-store-switch/build.py --lang tw
    .venv/Scripts/python.exe .scratch/credit-store-switch/build.py --lang cn
    .venv/Scripts/python.exe .scratch/credit-store-switch/build.py --lang tw --out 試做.autoclickpack

可以重跑: 已改過的流程再跑一次結果相同 (商品的買法從區塊裡第一個商品分支取)。
- 收取信用那個分岔原樣不動; 它之後到「導航 → 公開招募」之前的步驟整段換掉。
- 每個分支: 條件步驟 (找圖 採購_X〔由上到下第 1、比色〕→ 點到購買物品出現, 逾時與
  其餘欄位沿用原本的商品條件步驟, 找不到時改成跳出) + 原本商品分支裡條件步驟之後的
  購買步驟原樣複製。
- 範本從採購中心範本資料夾 (`繁中\\`、`簡中\\`) 匯入, 名稱一律 `採購_X` (去掉
  `待重拍_`)。存檔只寫被引用的範本 (flowfile.write), 沒人用的舊商品範本自然離開存檔。
- 流程存檔只經 app/flowfile.py 讀寫。
"""
from __future__ import annotations

import argparse
import copy
import os
import sys

import common
from common import NO_COLOR, PRIORITY, ROUNDS, template_name

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402


def load_templates(lang):
    """{採購_X: PNG bytes}; 檔名帶 `待重拍_` 的照用, 名稱去掉前綴."""
    folder = os.path.join(common.TEMPLATE_SRC, common.LANGS[lang]["folder"])
    out = {}
    for item in PRIORITY:
        name = template_name(item)
        for fn in (name + ".png", common.RETAKE + name + ".png"):
            p = os.path.join(folder, fn)
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    out[name] = f.read()
                break
        else:
            raise SystemExit(f"範本資料夾裡沒有 {name}: {folder}")
    return out


def condition(base, item):
    """一種商品的條件步驟: 沿用原本商品條件步驟的欄位, 換找圖目標、找不到時跳出."""
    s = copy.deepcopy(base)
    s[findtarget.TARGET] = findtarget.make_target(
        template_name(item), pick={"kind": "top", "n": 1}, color=item not in NO_COLOR)
    s["onNotFound"] = "break"
    return s


def purchase_block(base, tail):
    """重複區段 ×10 { 分岔 { 23 個分支 } 跳出後連外層一起跳出 }."""
    block = [{"type": "loop_start", "count": ROUNDS}, {"type": "branch_start"}]
    for i, item in enumerate(PRIORITY):
        if i:
            block.append({"type": "branch_or"})
        block.append(condition(base, item))
        block += copy.deepcopy(tail)
    block += [{"type": "branch_end", "onBreak": "break"}, {"type": "loop_end"}]
    return block


def rebuild(data):
    """就地改寫 data 的採購區塊; 回傳 (新 steps, 被換掉的舊區塊)."""
    steps = data["steps"]
    start, nav = common.purchase_span(steps)
    old = steps[start:nav]
    base, tail = common.buy_tail(old)
    data["steps"] = steps[:start] + purchase_block(base, tail) + steps[nav:]
    return data["steps"], old


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(common.LANGS), required=True)
    ap.add_argument("--flow", help="流程名 (預設依語系)")
    ap.add_argument("--out", help="另存到這個路徑 (預設覆寫原檔)")
    args = ap.parse_args(argv)

    path = common.flow_path(args.lang, args.flow)
    r = flowfile.read(path)
    data, images = r["data"], dict(r["images"])
    before_refs = set(flowfile.flow_refs(data))
    new_tmpl = load_templates(args.lang)
    images.update(new_tmpl)

    n_before = len(data["steps"])
    steps, old = rebuild(data)
    out = args.out or path
    missing = flowfile.write(out, data, images, r["pos"])
    if missing:
        raise SystemExit(f"存檔引用了不存在的範本: {'、'.join(missing)}")

    # 完整性: 讀回來, 每個引用的範本都在存檔裡
    back = flowfile.read(out)
    refs = set(flowfile.flow_refs(back["data"]))
    lost = refs - set(back["images"])
    if lost:
        raise SystemExit(f"讀回後缺範本: {'、'.join(sorted(lost))}")
    dropped = sorted(before_refs - refs)
    added = sorted(refs - before_refs)
    print(f"{os.path.basename(out)}: 步驟 {n_before} → {len(back['data']['steps'])}"
          f"（舊採購區塊 {len(old)} 步換成 {len(steps) - n_before + len(old)} 步）")
    print(f"範本 {len(before_refs)} → {len(refs)}；新增 {len(added)} 張、移出 {len(dropped)} 張")
    print("移出:", "、".join(dropped) or "無")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
    s = copy.deepcopy(base)
    s[findtarget.TARGET] = findtarget.make_target(
        template_name(item), pick={"kind": "top", "n": 1}, color=item not in NO_COLOR)
    s["onNotFound"] = "break"
    return s


def purchase_block(base, tail):
    block = [{"type": "loop_start", "count": ROUNDS}, {"type": "branch_start"}]
    for i, item in enumerate(PRIORITY):
        if i:
            block.append({"type": "branch_or"})
        block.append(condition(base, item))
        block += copy.deepcopy(tail)
    block += [{"type": "branch_end", "onBreak": "break"}, {"type": "loop_end"}]
    return block


def rebuild(data):
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

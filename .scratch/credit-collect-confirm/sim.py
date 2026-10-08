"""接縫一: 無頭執行器跑收取信用分岔到公開招募, 看事件序列 (見 spec.md「接縫一」).

    .venv/Scripts/python.exe .scratch/credit-collect-confirm/sim.py --lang tw|cn [--flows 目錄] [--orig 目錄]

從存檔切出信用交易所之後 (收取信用分岔) 到公開招募的步驟, 照存檔的搜尋範圍、忙碌指示、
補做間隔, 交給 app 測試用的無頭 harness (假畫面、假輸入、虛擬時鐘)。畫面是
credit-store-switch 的商店模擬器, 加上收取信用按鈕與它的物資彈窗。四個劇本:

- 正常: 點一下 → 物資彈窗出現 → 關掉 → 採購。收取信用只點一下。
- 第一下被吃掉: 第一下沒反應, 之後的有效 → 補做一次後物資彈窗出現 → 關掉 → 採購。
- 按鈕不在: 分岔約 3 秒逾時跳過 → 採購; 沒點收取信用。
- 物資彈窗始終不出現: 補做到逾時 → 約 3 秒跳出分岔 → 採購; 沒跑等物資彈窗那步 (8 秒)。

每個劇本也用改動前的存檔 (--orig, 預設本功能的備份) 跑一次: 從採購開始 (第一次查商品範本)
之後的事件序列要和改動前相同。結果寫 results/sim_<lang>.json; 任一劇本不符時結束碼 1。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import collect
from collect import bp

css = collect.css_sim()
hz, pytest, runner_mod = css.hz, css.pytest, css.runner_mod

import flowfile  # noqa: E402
from automation import findtarget  # noqa: E402

CARDS = (("招聘許可", (300, 450)), ("糖", (800, 450)))   # 採購段買兩件, 劇本間不變 (在商品的限定範圍內)
BRANCH_SECS = 3.0      # 收取信用的逾時 (spec: 維持 3 秒)


class CreditShop(css.Shop):
    """商店模擬器加上收取信用: 按鈕在商店頁右上, 點了 (沒被吃、會出彈窗時) 出物資彈窗.

    eaten: 前幾下點擊被吃掉 (頁面還沒載好); popup: 點了會不會出物資彈窗。
    收過之後按鈕消失。第一次查商品範本時記下採購從事件序列的哪裡開始。
    """

    def __init__(self, cards, credit_at, events, clock, button=True, eaten=0, popup=True):
        super().__init__(cards)
        self.credit_at = credit_at
        self.button, self.eaten, self.popup = button, eaten, popup
        self.events, self.clock = events, clock
        self.credit_clicks = 0
        self.credit_times = []       # 每一下點到收取信用的虛擬時間
        self.collected = False
        self.purchase_at = None      # (story 索引, events 索引, 虛擬時間)
        self.branch_t = None         # 第一次查收取信用的虛擬時間

    def lookup(self, name):
        if name.startswith(css.common.PREFIX) and self.purchase_at is None:
            self.purchase_at = (len(self.story), len(self.events), self.clock.t)
        if name == collect.CREDIT:
            if self.branch_t is None:
                self.branch_t = self.clock.t
            return self.credit_at if self.button and self.phase == "shop" else None
        return super().lookup(name)

    def _click(self, x, y):
        cx, cy = self.credit_at
        if (self.button and self.phase == "shop"
                and abs(cx - x) <= css.NEAR and abs(cy - y) <= css.NEAR):
            self.credit_clicks += 1
            self.credit_times.append(self.clock.t)
            if self.eaten > 0:
                self.eaten -= 1
                return "收取信用（被吃）"
            if not self.popup:
                return "收取信用（沒出彈窗）"
            self.button, self.collected, self.phase = False, True, "got"
            return "收取信用"
        return super()._click(x, y)


COND = 1   # 片段裡收取信用的索引 (片段從它所屬的分岔開頭起算)


def slice_steps(data, lang):
    """信用交易所之後 (收取信用分岔開頭) 到公開招募的步驟."""
    steps = data["steps"]
    i = collect.credit_index(steps, lang)
    end = collect.recruit_index(steps, i)
    return steps[i - 1:end + 1]


def center(data, tgt):
    """找圖目標限定範圍的中心 (搜尋範圍照存檔); 不限定時 None."""
    if not (tgt.get("limit") or {}):
        return None
    x, y, w, h = findtarget.limit_rect(tgt, data["scanRegion"], None)
    return (int(x + w / 2), int(y + h / 2))


def layout(data, steps):
    """商店畫面上各個元素的位置: 放在存檔裡那一步限定範圍的中心.

    credit-store-switch 的模擬器座標是 10/07 加固定矩形之前定的, 現在會落在限定範圍外,
    所以購買物品、物資彈窗、導航、公開招募都照存檔重放 (只放得進限定範圍時才換)。
    """
    def first(names, key=findtarget.target):
        s = next((s for s in steps if s.get("type") == "find_click"
                  and key(s).get("template", "").startswith(names)), None)
        return None if s is None else center(data, key(s))
    out = {"BUY_AT": first(css.common.BUY), "GOT_AT": first(collect.GOT),
           "NAV_AT": first(css.common.NAV), "RECRUIT_AT": first(collect.RECRUIT)}
    return {k: v for k, v in out.items() if v is not None}


def run(data, lang, shop_cfg):
    steps = slice_steps(data, lang)
    with pytest.MonkeyPatch.context() as mp:
        for name, at in layout(data, steps).items():
            mp.setattr(css, name, at)
        h = hz.Harness(mp)
        shop = CreditShop([css.Card(n, p) for n, p in CARDS],
                          center(data, findtarget.target(steps[COND])),
                          events=h.events, clock=h.clock, **shop_cfg)
        h.vision = css.ShopVision(shop, h.clock)
        mp.setattr(runner_mod.capture, "grab", h.vision.grab)

        def click(x, y, button="left", clicks=1, **kw):
            h.input.click(x, y, button, clicks, **kw)
            shop.click(int(x), int(y))
        mp.setattr(runner_mod.win, "click", click)
        r = h.run(steps, timeout=60.0, scan_region=data["scanRegion"],
                  avoid_hover=bool(data.get("avoidHover")),
                  retry_interval=flowfile.retry_interval_ms(data) / 1000.0,
                  busy=flowfile.busy_target(data))
    # 片段裡的步驟編號 → 存檔裡的編號
    base = collect.credit_index(data["steps"], lang) - COND
    recs = [dict(x, step=x["step"] + base) for x in h.filelog.of("find.target")]
    if shop.purchase_at is None:
        story_i, ev_i, t = len(shop.story), len(h.events), None
    else:
        story_i, ev_i, t = shop.purchase_at
    return {
        "ended": r.ended,
        "story": list(shop.story),
        "credit_clicks": shop.credit_clicks,
        "collected": shop.collected,
        "secs_to_purchase": (None if t is None or shop.branch_t is None
                             else round(t - shop.branch_t, 2)),
        "after_purchase": [list(e) for e in h.events[ev_i:]],
        "story_after_purchase": shop.story[story_i:],
        "story_before_purchase": shop.story[:story_i],
        "credit_gaps": [round(b - a, 2) for a, b in zip(shop.credit_times, shop.credit_times[1:])],
        "records": recs,
        "log": h.logs(r)[-8:],
    }


def purchases():
    seq = []
    for n, p in CARDS:
        seq += [f"{n}{p}", "購買物品", "關獲得物資"]
    return seq + ["導航", "公開招募"]


DEAD = "收取信用（沒出彈窗）"

# 每個劇本: 標題、說明、商店設定、新版的預期——
# before: 開始採購之前的點擊經過 (None＝另由 dead 判: 全是沒出彈窗的收取信用, 至少 2 下);
# confirm: 收取信用那一步的確認紀錄 (role, result, clicks; clicks None＝不看); 沒點就是 None;
# secs: 到開始採購的秒數要接近收取信用的逾時 (跳過或跳出, 沒有等物資彈窗那步的 8 秒)。
SCENARIOS = [
    {"title": "正常", "desc": "點一下 → 物資彈窗出現 → 關掉 → 開始採購；收取信用只點一下",
     "shop": {"button": True, "eaten": 0, "popup": True},
     "before": ["收取信用", "關獲得物資"], "confirm": ("confirm_appear", "found", 1),
     "secs": False},
    {"title": "第一下被吃掉", "desc": "第一下沒反應 → 補做一次後物資彈窗出現 → 關掉 → 開始採購",
     "shop": {"button": True, "eaten": 1, "popup": True},
     "before": ["收取信用（被吃）", "收取信用", "關獲得物資"],
     "confirm": ("confirm_appear", "found", 2), "secs": False},
    {"title": "按鈕不在", "desc": "收取信用找不到 → 約 3 秒跳過分岔 → 開始採購；沒點收取信用",
     "shop": {"button": False, "eaten": 0, "popup": True},
     "before": [], "confirm": None, "secs": True},
    {"title": "物資彈窗始終不出現", "desc": "補做到逾時 → 約 3 秒跳出分岔 → 開始採購；沒有等物資彈窗那步的 8 秒",
     "shop": {"button": True, "eaten": 0, "popup": False},
     "before": None, "confirm": ("confirm_appear", "timeout", None), "secs": True},
]


def judge(scen, res, credit_no, got_no, retry_s):
    """新版的預期 (只看外部行為). 回傳 (通過, 說明)."""
    cred = [x for x in res["records"] if x["step"] == credit_no and x["role"] != "branch"]
    got = [x for x in res["records"] if x["step"] == got_no]
    last = cred[-1] if cred else None
    secs = res["secs_to_purchase"]
    before = res["story_before_purchase"]
    checks = [res["ended"] == "done", res["story_after_purchase"] == purchases(), secs is not None,
              # 補做的間隔: 兩下收取信用之間至少隔流程的補做間隔
              all(g >= retry_s - 1e-6 for g in res["credit_gaps"])]
    if scen["before"] is None:
        checks.append(len(before) >= 2 and all(x == DEAD for x in before))
    else:
        checks.append(before == scen["before"])
    want = scen["confirm"]
    if want is None:
        checks.append(last is None)
    else:
        checks.append(last is not None and (last["role"], last["result"]) == want[:2]
                      and (want[2] is None or last.get("clicks") == want[2]))
    if scen["secs"]:
        checks.append(not got and secs is not None
                      and BRANCH_SECS - 0.1 <= secs <= BRANCH_SECS + 0.6)
    last = last or {}
    note = (f"收取信用點 {res['credit_clicks']} 下（間隔 {res['credit_gaps'] or '-'}s）、"
            f"第 {credit_no} 步 {last.get('role', '-')}={last.get('result', '-')}、"
            f"第 {got_no} 步{'有' if got else '沒有'}執行、到採購 {secs}s")
    return all(checks), note


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(collect.LANGS), required=True)
    ap.add_argument("--flows", default=bp.FLOWS)
    ap.add_argument("--orig", help="改動前的流程資料夾 (預設本功能的備份)")
    args = ap.parse_args(argv)
    args.orig = args.orig or collect.orig_flows(args.lang)
    cfg = collect.LANGS[args.lang]
    data = flowfile.read(bp.flow_path(cfg["flow"], args.flows))["data"]
    orig = flowfile.read(bp.flow_path(cfg["flow"], args.orig))["data"]
    steps = slice_steps(data, args.lang)
    retry_s = flowfile.retry_interval_ms(data) / 1000.0
    print(f"{cfg['flow']}: 片段第 {cfg['credit_no'] - 1}–{cfg['credit_no'] - 2 + len(steps)} 步"
          f"（{len(steps)} 步，收取信用分岔 → 採購 → 公開招募）")
    out, failed = [], 0
    for scen in SCENARIOS:
        title, desc = scen["title"], scen["desc"]
        new, old = run(data, args.lang, scen["shop"]), run(orig, args.lang, scen["shop"])
        ok, note = judge(scen, new, cfg["credit_no"], cfg["got_no"], retry_s)
        same = new["after_purchase"] == old["after_purchase"] and bool(new["after_purchase"])
        ok = ok and same
        failed += not ok
        out.append({"title": title, "desc": desc, "ok": ok, "note": note,
                    "same_after_purchase": same,
                    "new": {k: new[k] for k in ("ended", "story", "credit_clicks", "credit_gaps",
                                                "secs_to_purchase", "log")},
                    "old": {k: old[k] for k in ("ended", "story", "credit_clicks",
                                                "secs_to_purchase")}})
        print(f"[{'通過' if ok else '失敗'}] {title}：{desc}")
        print(f"    新版：{note}")
        print(f"    　　　{' → '.join(new['story'])}")
        print(f"    改前：收取信用點 {old['credit_clicks']} 下、到採購 {old['secs_to_purchase']}s")
        print(f"    採購開始後的事件序列與改前{'相同' if same else '**不同**'}")
        if not ok:
            print("    紀錄尾端：", *new["log"], sep="\n      ")
    os.makedirs(collect.RESULTS, exist_ok=True)
    with open(os.path.join(collect.RESULTS, f"sim_{args.lang}.json"), "w", encoding="utf-8") as f:
        json.dump({"flow": cfg["flow"], "results": out}, f, ensure_ascii=False, indent=1)
    print(f"{len(out) - failed}/{len(out)} 通過")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

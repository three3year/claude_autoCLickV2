"""接縫一: 無頭執行器跑改好的採購區塊, 驗流程控制 (見 spec.md「Testing Decisions」).

    .venv/Scripts/python.exe .scratch/credit-store-switch/sim.py --lang tw
    .venv/Scripts/python.exe .scratch/credit-store-switch/sim.py --lang cn [--flow 早_簡中]

從流程存檔讀出收取信用之後到公開招募的步驟, 交給 app 測試用的無頭 harness
(app/tests/harness.py: 假畫面、假輸入、虛擬時鐘) 執行。辨識走執行器的偵測接縫,
這裡換成一個商店模擬器: 卡片、購買物品、獲得物資會隨點擊變化。斷言只看事件序列
——點了哪裡、依什麼順序、何時離開區段。

商品範本每查一次推進虛擬時鐘 0.14 秒 (本機實測一張約 0.13 秒), 所以分岔一輪
要把 23 張都找過一遍才看逾時, 和實機一樣每輪只比對一張截圖。

結果寫到 results/sim_<lang>.json (報告用); 任一劇本不符預期時結束碼 1。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import common
from common import PRIORITY, template_name

sys.path.insert(0, os.path.join(common.APP, "tests"))

import pytest  # noqa: E402  (只借 MonkeyPatch 給 harness 用, 不跑 pytest)

import flowfile  # noqa: E402
import harness as hz  # noqa: E402
from automation import runner as runner_mod  # noqa: E402

QUERY_COST = 0.14      # 商品範本每查一次的虛擬秒數
NEAR = 25              # 點擊落在卡片中心這個距離內＝點到那張卡

BUY_AT = (1500, 850)   # 購買物品鈕
GOT_AT = (960, 150)    # 獲得物資彈窗的標題
NAV_AT = (200, 100)
RECRUIT_AT = (1200, 200)


class Card:
    def __init__(self, name, pos, affordable=True, sold=False):
        self.name, self.pos = name, pos
        self.affordable, self.sold = affordable, sold

    @property
    def label(self):
        return f"{self.name}{self.pos}"


class Shop:
    """商店畫面的狀態機: shop (商店頁) → buy (購買物品) → got (獲得物資) → shop.

    - 點未售完、買得起的卡 → buy; 買不起的卡點了沒反應。
    - 點購買物品 → 那張卡售罄; got_fails 時獲得物資永遠不出現 (limbo)。
    - got 時任何點擊都關掉彈窗 (繁中點它本身、簡中點它下方)。
    - 點導航之後公開招募才出現。
    """

    def __init__(self, cards, got_fails=False):
        self.cards = cards
        self.got_fails = got_fails
        self.phase = "shop"
        self.selected = None
        self.navigated = False
        self.story = []      # 每一下點擊點到什麼 (給人看、也拿來斷言)

    def lookup(self, name):
        if name.startswith(common.PREFIX):
            if self.phase != "shop":
                return None
            item = name[len(common.PREFIX):]
            hits = [c.pos for c in self.cards if c.name == item and not c.sold]
            return hits or None
        if name in common.BUY:
            return BUY_AT if self.phase == "buy" else None
        if name in ("獲得物資", "获得物资"):
            return GOT_AT if self.phase == "got" else None
        if name.startswith(common.NAV):
            return NAV_AT
        if name in common.RECRUIT:
            return RECRUIT_AT if self.navigated else None
        return None      # 忙碌指示等: 不在畫面上

    def click(self, x, y):
        self.story.append(self._click(x, y))

    def _click(self, x, y):
        def near(p):
            return abs(p[0] - x) <= NEAR and abs(p[1] - y) <= NEAR
        if self.phase == "got":
            self.phase = "shop"
            return "關獲得物資"
        if self.phase == "buy" and near(BUY_AT):
            self.selected.sold = True
            self.phase = "limbo" if self.got_fails else "got"
            return "購買物品"
        if near(NAV_AT):
            self.navigated = True
            return "導航"
        if self.navigated and near(RECRUIT_AT):
            return "公開招募"
        if self.phase == "shop":
            card = next((c for c in self.cards if near(c.pos)), None)
            if card is not None:
                if card.affordable and not card.sold:
                    self.selected, self.phase = card, "buy"
                return card.label
        return f"?({x},{y})"


class ShopVision(hz.Vision):
    """harness 的假偵測器, 未安排 (plan) 的範本改問商店模擬器."""

    def __init__(self, shop, clock):
        super().__init__(clock=clock)
        self.shop = shop

    def _next(self, name):
        if name in self._plans:      # 開頭校準的那對
            return super()._next(name)
        return self.shop.lookup(name)

    def query(self, name, search_region, color_check=False, expected_scale=None):
        r = super().query(name, search_region, color_check, expected_scale)
        if name.startswith(common.PREFIX):
            self.clock.t += QUERY_COST
        return r


def grid(names, cols=6, x0=250, y0=200, dx=250, dy=220):
    """依序把商品排成格子 (左上起逐列), 回傳 Card list."""
    return [Card(n, (x0 + dx * (i % cols), y0 + dy * (i // cols)))
            for i, n in enumerate(names)]


def run(flow, cards, got_fails=False):
    """在模擬商店上跑一次採購區塊; 回傳 (story, harness, runner)."""
    data = flow["data"]
    steps = flow["steps"]
    shop = Shop(cards, got_fails)
    with pytest.MonkeyPatch.context() as mp:
        h = hz.Harness(mp)
        h.vision = ShopVision(shop, h.clock)
        mp.setattr(runner_mod.capture, "grab", h.vision.grab)

        def click(x, y, button="left", clicks=1, **kw):
            h.input.click(x, y, button, clicks, **kw)
            shop.click(int(x), int(y))
        mp.setattr(runner_mod.win, "click", click)
        r = h.run(steps, timeout=60.0,
                  scan_region=data.get("scanRegion"),
                  avoid_hover=bool(data.get("avoidHover")),
                  retry_interval=flowfile.retry_interval_ms(data) / 1000.0,
                  busy=flowfile.busy_target(data))
    return shop.story, h, r


def squash(story):
    """連續重複的同一下 (補做重送) 併成一個."""
    out = []
    for s in story:
        if not out or out[-1] != s:
            out.append(s)
    return out


def bought(story):
    """實際買到的商品: 緊接著點了購買物品的那張卡."""
    st = squash(story)
    return [st[i - 1] for i, s in enumerate(st) if s == "購買物品" and i > 0]


def purchases(cards):
    """預期的事件序列: 每件 [卡, 購買物品, 關獲得物資], 最後導航 → 公開招募."""
    seq = []
    for c in cards:
        seq += [c.label, "購買物品", "關獲得物資"]
    return seq + ["導航", "公開招募"]


# ---------------------------------------------------------------- 劇本

def scenarios():
    """(名稱, 說明, 建構函式) ; 建構函式回傳 (cards, got_fails, 預期序列, 額外檢查)."""

    def s1():
        # 優先第 2、5、20; 擺放位置故意跟優先順序反過來
        cards = grid(["基礎作戰記錄", "赤金", "招聘許可"])
        by = {c.name: c for c in cards}
        return cards, False, purchases([by["招聘許可"], by["赤金"], by["基礎作戰記錄"]]), None

    def s2():
        low = Card("初級作戰記錄", (1300, 560))
        top = Card("初級作戰記錄", (550, 300))
        return [low, top], False, purchases([top, low]), None

    def s3():
        cards = [Card("加急許可", (300, 300), affordable=False), Card("糖", (800, 300))]
        return cards, False, [cards[0].label, "導航", "公開招募"], None

    def s4():
        cards = [Card("傢俱零件", (300, 300)), Card("招聘許可", (800, 300), sold=True)]

        def extra(h, r):
            n = sum(1 for x in h.lookups() if x.startswith(common.PREFIX))
            timeouts = h.log_text().count("沒有任何分支成立")
            return (n == len(PRIORITY) and timeouts == 1,
                    f"商品範本查詢 {n} 次（一輪 {len(PRIORITY)} 張）、分岔逾時 {timeouts} 次")
        return cards, False, ["導航", "公開招募"], extra

    def s5():
        cards = [Card("招聘許可", (300, 300)), Card("糖", (800, 300))]
        return cards, True, [cards[0].label, "購買物品", "導航", "公開招募"], None

    def s6():
        names = ["糖", "糖", "糖", "裝置", "裝置", "聚酸酯", "聚酸酯", "異鐵", "異鐵",
                 "碳", "碳", "碳"]
        cards = grid(names)

        def extra(h, r):
            ok = "重複區段完成（10 次）" in h.log_text()
            left = [c.label for c in cards if not c.sold]
            return ok and len(left) == 2, f"10 輪後還剩 {len(left)} 張沒買：{'、'.join(left)}"
        # 預期: 依優先順序, 同種由上到下 (同列由左到右)
        order = sorted(cards, key=lambda c: (PRIORITY.index(c.name), c.pos[1], c.pos[0]))
        exp = purchases(order[:10])
        return cards, False, exp, extra

    return [
        ("優先順序", "畫面上有優先第 2、5、20 的商品 → 依序買 2、5、20，之後全部逾時 → 離開區段、點公開招募", s1),
        ("同種兩格", "同一種商品兩格 → 兩輪各買一格，先買上面那格", s2),
        ("買不起", "點了商品沒出現購買物品 → 不再買其他商品，直接離開區段", s3),
        ("沒有商品", "一開始畫面上沒有白名單商品（只有傢俱零件與售完卡）→ 一輪逾時後離開區段", s4),
        ("獲得物資等不到", "點購買物品後獲得物資不出現 → 離開區段，不再點任何商品", s5),
        ("10 輪上限", "每輪都有商品可買（12 張）→ 剛好 10 輪後離開區段", s6),
    ] + priority_scenarios()


def priority_scenarios():
    """完整優先順序: 23 種全上 → 買前 10; 再上第 11–20 種 → 買那 10 種; 再上第 21–23 種."""
    out = []
    for lo, hi in ((0, 10), (10, 20), (20, 23)):
        def build(lo=lo, hi=hi):
            names = PRIORITY[lo:]
            cards = grid(list(reversed(names)))   # 擺放跟優先順序反過來
            by = {c.name: c for c in cards}
            return cards, False, purchases([by[n] for n in PRIORITY[lo:hi]]), None
        out.append((f"完整順序 {lo + 1}–{hi}",
                    f"畫面上有第 {lo + 1}–23 種各一張 → 依序買第 {lo + 1}–{hi} 種", build))
    return out


def load(lang, name=None):
    path = common.flow_path(lang, name)
    r = flowfile.read(path)
    steps = r["data"]["steps"]
    start, nav = common.purchase_span(steps)
    return {"path": path, "data": r["data"], "steps": steps[start:nav + 2]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(common.LANGS), required=True)
    ap.add_argument("--flow", help="流程名 (預設依語系)")
    args = ap.parse_args(argv)

    flow = load(args.lang, args.flow)
    print(f"{os.path.basename(flow['path'])}: 採購區塊 {len(flow['steps'])} 步（含導航 → 公開招募）")
    results, failed = [], 0
    for title, desc, build in scenarios():
        cards, got_fails, expected, extra = build()
        story, h, r = run(flow, cards, got_fails)
        got = squash(story)
        ok = got == expected and r.ended == "done"
        note = ""
        if extra is not None:
            ok2, note = extra(h, r)
            ok = ok and ok2
        # 結束購買的那一輪: 最後一次關獲得物資 (或區塊開頭) 到點導航的虛擬秒數
        results.append({"title": title, "desc": desc, "ok": ok, "ended": r.ended,
                        "expected": expected, "got": got, "note": note,
                        "secs": round(h.clock.t - 1000.0, 1)})
        failed += not ok
        print(f"[{'通過' if ok else '失敗'}] {title}: {desc}")
        if not ok:
            print("   預期:", " → ".join(expected))
            print("   實際:", " → ".join(got), f"(ended={r.ended})")
            tail = [m for m in h.logs()[-8:]]
            print("   紀錄尾端:", *tail, sep="\n     ")
        if note:
            print("   ", note)
    os.makedirs(os.path.join(common.HERE, "results"), exist_ok=True)
    with open(os.path.join(common.HERE, "results", f"sim_{args.lang}.json"), "w",
              encoding="utf-8") as f:
        json.dump({"flow": os.path.basename(flow["path"]), "results": results}, f,
                  ensure_ascii=False, indent=1)
    print(f"{len(results) - failed}/{len(results)} 通過")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

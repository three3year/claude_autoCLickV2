from __future__ import annotations

import argparse
import json
import os
import sys

import clue
from clue import bp

import pytest  # noqa: E402

import flowfile  # noqa: E402
import harness as hz  # noqa: E402
from automation import findtarget  # noqa: E402
from automation import runner as runner_mod  # noqa: E402

NEAR = 30


class Board:
    def __init__(self, lang, steps, region, have, eaten=None, label_broken=False):
        cfg = clue.LANGS[lang]
        self.lang, self.cfg = lang, cfg
        sx = lambda xy: clue.screen_xy(lang, xy)  # noqa: E731
        self.open_at = sx(clue.center(cfg["boxes"][cfg["open"]][1]))
        self.marker_at = sx(clue.center(cfg["boxes"][cfg["marker"]][1]))
        self.label_at = sx(clue.center(cfg["boxes"][clue.LABEL[lang]][1]))
        self.quick_at = sx(clue.center(cfg["quick_box"]))
        self.buttons = {n: sx((cfg["buttons"][n - 1], cfg["button_y"])) for n in clue.NUMS}
        self.panel_left = sx((cfg["panel_left"], 0))[0]
        self.r = cfg["button_r"]
        self.have, self.eaten = set(have), dict(eaten or {})
        self.label_broken = label_broken
        self.panel, self.sel, self.placed = False, None, False
        self.gone = set()
        self.story = []
        self.static = {}
        for s in steps:
            for _, t in findtarget.step_targets(s):
                n = t.get("template")
                if n and n not in self.static:
                    x, y, w, h = findtarget.limit_rect(t, region, None) or region
                    self.static[n] = (int(x + w / 2), int(y + h / 2))
        self.selected = {clue.selected_name(lang, n): n for n in clue.NUMS}

    def lookup(self, name):
        cfg = self.cfg
        if name == cfg["open"]:
            return None if self.panel else self.open_at
        if name == cfg["marker"]:
            return self.marker_at if self.panel else None
        if name in self.selected:
            n = self.selected[name]
            return self.buttons[n] if self.panel and self.sel == n else None
        if name == clue.LABEL[self.lang]:
            has = (self.have if self.sel == "all" else {self.sel} & self.have)
            return self.label_at if self.panel and has and not self.label_broken else None
        if name == cfg["quick"]:
            return None if self.panel else self.quick_at
        if name == cfg["unlock"]:
            return self.static[name] if self.placed and name not in self.gone else None
        if name in self.gone:
            return None
        return self.static.get(name)

    @staticmethod
    def _near(a, x, y, d=NEAR):
        return a is not None and abs(a[0] - x) <= d and abs(a[1] - y) <= d

    def click(self, x, y):
        cfg = self.cfg
        if self.panel:
            if x < self.panel_left:
                self.panel = False
                return self.story.append("關面板")
            for n, at in self.buttons.items():
                if self._near(at, x, y, self.r):
                    if self.eaten.get(n, 0) > 0:
                        self.eaten[n] -= 1
                        return self.story.append(f"篩選{n}（被吃）")
                    self.sel = n
                    return self.story.append(f"篩選{n}")
            return self.story.append(f"面板上({x},{y})")
        if self._near(self.open_at, x, y):
            self.panel, self.sel = True, "all"
            return self.story.append("開面板")
        if self._near(self.quick_at, x, y):
            self.placed = True
            return self.story.append("快速置入")
        for name in (cfg["unlock"], cfg["send_close"]):
            if self.lookup(name) is not None and self._near(self.static[name], x, y):
                self.gone.add(name)
                return self.story.append(name)
        for name, at in self.static.items():
            if self.lookup(name) is not None and self._near(at, x, y):
                return self.story.append(name)
        self.story.append(f"({x},{y})")


class BoardVision(hz.Vision):
    def __init__(self, board, clock):
        super().__init__(clock=clock)
        self.board = board

    def _next(self, name):
        if name in self._plans:
            return super()._next(name)
        return self.board.lookup(name)


def slice_steps(steps, lang):
    cfg = clue.LANGS[lang]
    lay = clue.new_layout(steps, lang)
    end = clue.one_step(steps, cfg["send_close"], cfg["flow"])
    if end + 1 < len(steps) and steps[end + 1].get("type") == "branch_end":
        end += 1
    return lay["recv"][0], steps[lay["recv"][0]:end + 1]


def run(data, lang, scen):
    start, steps = slice_steps(data["steps"], lang)
    region = data["scanRegion"]
    board = Board(lang, steps, region, **scen["board"])
    busy = flowfile.busy_target(data)
    with pytest.MonkeyPatch.context() as mp:
        h = hz.Harness(mp)
        h.vision = BoardVision(board, h.clock)
        mp.setattr(runner_mod.capture, "grab", h.vision.grab)
        if busy:
            h.vision.plan(busy["template"], [None])

        def click(x, y, button="left", clicks=1, **kw):
            h.input.click(x, y, button, clicks, **kw)
            board.click(int(x), int(y))
        mp.setattr(runner_mod.win, "click", click)
        r = h.run(steps, timeout=60.0, scan_region=region,
                  avoid_hover=bool(data.get("avoidHover")),
                  retry_interval=flowfile.retry_interval_ms(data) / 1000.0, busy=busy)
    recs = [dict(x, step=x["step"] + start) for x in h.filelog.of("find.target")]
    confirms = [dict(x, step=x["step"] + start) for x in h.filelog.of("input.confirm")]
    return {"ended": r.ended, "story": board.story, "records": recs, "confirms": confirms,
            "log": h.logs(r)[-8:], "t_end": round(h.clock.t - 1000.0, 2)}


CLUE = ("開面板", "關面板", "快速置入")


def clue_story(story, lang):
    unlock = clue.LANGS[lang]["unlock"]
    return [s for s in story if s in CLUE or s.startswith("篩選") or s == unlock]


def scenarios(lang):
    unlock = clue.LANGS[lang]["unlock"]
    seq = lambda k: [f"篩選{n}" for n in range(1, k + 1)]  # noqa: E731
    out = [{"title": "7 號都有", "board": {"have": clue.NUMS},
            "want": ["開面板", *seq(7), "關面板", "快速置入", unlock], "close": "check"}]
    for n in (1, 4, 7):
        out.append({"title": f"第 {n} 號空", "board": {"have": set(clue.NUMS) - {n}},
                    "want": ["開面板", *seq(n), "關面板"], "close": "leftover", "stop": n})
    out += [
        {"title": "卡片標籤判不出", "board": {"have": clue.NUMS, "label_broken": True},
         "want": ["開面板", "篩選1", "關面板"], "close": "leftover", "stop": 1},
        {"title": "3 號第一下被吃", "board": {"have": clue.NUMS, "eaten": {3: 1}},
         "want": ["開面板", "篩選1", "篩選2", "篩選3（被吃）", *seq(7)[2:], "關面板", "快速置入",
                  unlock], "close": "check"},
        {"title": "3 號一直沒選中", "board": {"have": clue.NUMS, "eaten": {3: 99}},
         "want": None, "close": "leftover", "stop": 3},
    ]
    return out


def judge(scen, res, lang, lay):
    cfg = clue.LANGS[lang]
    story = res["story"]
    cs = clue_story(story, lang)
    want = scen["want"]
    if want is None:
        eaten = cs[3:-1]
        ok_seq = (cs[:3] == ["開面板", "篩選1", "篩選2"] and cs[-1:] == ["關面板"]
                  and len(eaten) >= 2 and all(x == "篩選3（被吃）" for x in eaten))
    else:
        ok_seq = cs == want
    i_open = story.index("開面板") if "開面板" in story else -1
    recv_first = (i_open > 0 and cfg["receive"] in story[:i_open]
                  and "全部收取" in story[:i_open])
    sent = cfg["send_close"] in story and story.index(cfg["send_close"]) > i_open
    a, b = lay["check"]
    la, lb = lay["leftover"]
    closes = [x for x in res["confirms"] if x.get("mode") == "gone" and x["result"] == "gone"]
    where = ["check" if a < x["step"] - 1 < b else "leftover" if la < x["step"] - 1 < lb
             else "?" for x in closes]
    ok_close = where == [scen["close"]]
    labels = [x for x in res["records"] if x["template"] == clue.LABEL[lang]]
    fast = all(x.get("polls") == 1 for x in labels if x["result"] == "found")
    stop = scen.get("stop")
    ok = (res["ended"] == "done" and ok_seq and recv_first and sent and ok_close and fast)
    note = (f"{' → '.join(cs)}；關面板在{'檢查區段' if where == ['check'] else '補關分岔' if where == ['leftover'] else where}"
            f"；卡片標籤 {sum(x['result'] == 'found' for x in labels)} 次找到"
            f"（都第一輪：{'是' if fast else '否'}）"
            + (f"、{sum(x['result'] == 'timeout' for x in labels)} 次逾時" if stop else "")
            + f"；先接收：{'是' if recv_first else '否'}；傳遞：{'有' if sent else '沒有'}；"
              f"結束：{res['ended']}；虛擬 {res['t_end']}s")
    return ok, note


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(clue.LANGS), required=True)
    ap.add_argument("--flows", default=bp.FLOWS)
    args = ap.parse_args(argv)
    cfg = clue.LANGS[args.lang]
    data = flowfile.read(bp.flow_path(cfg["flow"], args.flows))["data"]
    if not clue.is_new(data["steps"], args.lang):
        raise SystemExit(f"{cfg['flow']}: 還沒改 (先跑 build.py --apply)")
    lay = clue.new_layout(data["steps"], args.lang)
    start, steps = slice_steps(data["steps"], args.lang)
    print(f"{cfg['flow']}: 片段第 {start + 1}–{start + len(steps)} 步（接收 → 查 1–7 → 解鎖 → 傳遞）")
    out, failed = [], 0
    for scen in scenarios(args.lang):
        res = run(data, args.lang, scen)
        ok, note = judge(scen, res, args.lang, lay)
        failed += not ok
        out.append({"title": scen["title"], "ok": ok, "note": note, "ended": res["ended"],
                    "story": res["story"], "t_end": res["t_end"], "log": res["log"]})
        print(f"[{'通過' if ok else '失敗'}] {scen['title']}：{note}")
        if not ok:
            print("    全部點擊：", " → ".join(res["story"]))
            print("    紀錄尾端：", *res["log"], sep="\n      ")
    os.makedirs(clue.RESULTS, exist_ok=True)
    with open(os.path.join(clue.RESULTS, f"sim_{args.lang}.json"), "w", encoding="utf-8") as f:
        json.dump({"flow": cfg["flow"], "slice": [start + 1, start + len(steps)], "results": out},
                  f, ensure_ascii=False, indent=1)
    print(f"{len(out) - failed}/{len(out)} 通過")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

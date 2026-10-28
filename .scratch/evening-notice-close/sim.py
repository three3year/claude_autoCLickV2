from __future__ import annotations

import argparse
import json
import os
import sys

import notice
from notice import bp

import pytest  # noqa: E402

import flowfile  # noqa: E402
import harness as hz  # noqa: E402
from automation import findtarget  # noqa: E402
from automation import runner as runner_mod  # noqa: E402

BASE_AT = (1000, 500)


class Screen(hz.Vision):
    def __init__(self, clock):
        super().__init__(clock=clock)
        self.timeline = []

    def query(self, name, search_region, color_check=False, expected_scale=None):
        self.timeline.append((round(self.clock.t, 2), name))
        return super().query(name, search_region, color_check, expected_scale)


def notice_at(lang):
    _video, _n, (x, y, w, h) = notice.LANGS[lang]["positive"][0]
    ox, oy = bp.LANGS[lang]["offset"]
    return (x + ox + w // 2, y + oy + h // 2)


def run_once(lang, data, shown):
    steps = data["steps"][:2]
    tmpl = findtarget.template(steps[0])
    base = findtarget.template(steps[1])
    busy = flowfile.busy_target(data)
    with pytest.MonkeyPatch.context() as mp:
        h = hz.Harness(mp)
        h.vision = Screen(h.clock)
        mp.setattr(runner_mod.capture, "grab", h.vision.grab)
        h.vision.plan(tmpl, [notice_at(lang), None] if shown else [None])
        h.vision.plan(base, [BASE_AT, None])
        h.vision.plan(busy["template"], [None])
        r = h.run(steps, busy=busy, timeout=30, scan_region=data["scanRegion"],
                  retry_interval=flowfile.retry_interval_ms(data) / 1000.0)
        recs = h.filelog.of("find.target")
        tl = h.vision.timeline
        t_first = next((t for t, n in tl if n == tmpl), None)
        t_base = next((t for t, n in tl if n == base), None)
        return {
            "ended": r.ended,
            "events": [list(e) for e in h.events],
            "step1": [{k: x[k] for k in ("role", "result", "polls", "clicks", "picked")
                       if k in x} for x in recs if x["step"] == 1],
            "step2": [{k: x[k] for k in ("role", "result", "clicks", "picked")
                       if k in x} for x in recs if x["step"] == 2],
            "step1_secs": None if None in (t_first, t_base) else round(t_base - t_first, 2),
            "notice_lookups": h.lookups().count(tmpl),
            "log": h.logs(r)[-6:],
        }


def judge(shown, res, at):
    clicks = [tuple(e[1:3]) for e in res["events"] if e[0] == "click"]
    s1 = res["step1"][-1] if res["step1"] else {}
    s2 = res["step2"][-1] if res["step2"] else {}
    base_ok = (s2.get("role") == "confirm_gone" and s2.get("result") == "gone"
               and clicks[-1:] == [BASE_AT])
    if shown:
        return (res["ended"] == "done" and base_ok and clicks == [at, BASE_AT]
                and s1.get("role") == "confirm_gone" and s1.get("result") == "gone"
                and s1.get("clicks") == 1)
    return (res["ended"] == "done" and base_ok and clicks == [BASE_AT]
            and s1.get("role") == "find" and s1.get("result") == "timeout"
            and res["step1_secs"] is not None
            and notice.TIMEOUT - 0.1 <= res["step1_secs"] <= notice.TIMEOUT + 0.5)


def after_base(events):
    i = next((k for k, e in enumerate(events)
              if e[0] == "click" and tuple(e[1:3]) == BASE_AT), None)
    return None if i is None else events[i:]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default=bp.FLOWS)
    args = ap.parse_args(argv)
    results, bad = {}, []
    for lang, cfg in notice.LANGS.items():
        data = flowfile.read(bp.flow_path(cfg["flow"], args.flows))["data"]
        if not notice.is_notice_step(data["steps"][0], lang):
            raise SystemExit(f"{cfg['flow']}: 第 1 步不是關公告那步 (先跑 build.py --apply)")
        at = notice_at(lang)
        shown, hidden = run_once(lang, data, True), run_once(lang, data, False)
        rec = {"notice_at": list(at), "base_at": list(BASE_AT),
               "shown": dict(shown, ok=judge(True, shown, at)),
               "hidden": dict(hidden, ok=judge(False, hidden, at)),
               "same_after_base": (after_base(shown["events"]) is not None
                                   and after_base(shown["events"]) == after_base(hidden["events"]))}
        rec["ok"] = rec["shown"]["ok"] and rec["hidden"]["ok"] and rec["same_after_base"]
        results[cfg["flow"]] = rec
        print(f"== {cfg['flow']}")
        print(f"  公告在：點擊 {[tuple(e[1:3]) for e in shown['events'] if e[0] == 'click']}，"
              f"第 1 步 {shown['step1'][-1]}，{shown['step1_secs']}s"
              + ("" if rec["shown"]["ok"] else "  ← 不符預期"))
        print(f"  公告不在：點擊 {[tuple(e[1:3]) for e in hidden['events'] if e[0] == 'click']}，"
              f"第 1 步 {hidden['step1'][-1]}，{hidden['step1_secs']}s"
              + ("" if rec["hidden"]["ok"] else "  ← 不符預期"))
        print(f"  點基建入口起的事件序列{'相同' if rec['same_after_base'] else '**不同**'}")
        if not rec["ok"]:
            bad.append(cfg["flow"])
    os.makedirs(notice.RESULTS, exist_ok=True)
    with open(os.path.join(notice.RESULTS, "sim.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("全部符合預期" if not bad else f"**不符預期**: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

"""接縫二: 無頭執行器跑晚班開頭 (新的第 1 步到找基建入口), 看事件序列 (見 spec.md「接縫二」).

    .venv/Scripts/python.exe .scratch/evening-notice-close/sim.py [--flows 目錄]

從改好的存檔切出第 1–2 步 (關公告 → 找基建入口), 照存檔的搜尋範圍、忙碌指示、補做間隔,
交給 app 測試用的無頭 harness (app/tests/harness.py: 假畫面、假輸入、虛擬時鐘) 跑兩個劇本:

- 公告在: 公告 X 在影片上量到的位置 (固定矩形內), 點一下之後消失。
  預期: 點 X 一次 → 確認消失 → 找到基建入口並點擊 → 確認消失, 流程跑完。
- 公告不在: 公告 X 一直找不到。
  預期: 約 2 秒 (虛擬時間) 逾時、跳過 → 找到基建入口並點擊, 流程跑完; 點基建前沒有任何點擊。
兩個劇本從「點基建入口」起的事件序列要相同。忙碌指示兩個劇本都不出現。
結果寫 results/sim.json; 任一劇本不符預期時結束碼 1。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import notice
from notice import bp

import pytest  # noqa: E402  (只借 MonkeyPatch 給 harness 用)

import flowfile  # noqa: E402
import harness as hz  # noqa: E402
from automation import findtarget  # noqa: E402
from automation import runner as runner_mod  # noqa: E402

BASE_AT = (1000, 500)    # 基建入口 (不限定範圍; 搜尋範圍內任一處)


class Screen(hz.Vision):
    """依劇本回答查詢; 每次查詢記下 (虛擬時間, 範本名)."""

    def __init__(self, clock):
        super().__init__(clock=clock)
        self.timeline = []

    def query(self, name, search_region, color_check=False, expected_scale=None):
        self.timeline.append((round(self.clock.t, 2), name))
        return super().query(name, search_region, color_check, expected_scale)


def notice_at(lang):
    """公告 X 在實機螢幕上的中心: 有公告的影格上量到的框 + 影片偏移."""
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

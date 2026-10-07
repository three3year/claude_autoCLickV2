"""票 05 驗證: 無頭執行器跑「拿掉忙碌等待之後」的換班片段, 看事件序列.

    .venv/Scripts/python.exe .scratch/busy-pause-fixed-rect/sim_busy.py [--flows 目錄]

每個拿掉的位置切一段: 從它前面最近一個會更新原點、本身不需要原點的找圖步驟, 到它後面第一個
找圖步驟 (下一步＝改由`忙碌暫停`接手的那一步)。交給 app 測試用的無頭 harness
(app/tests/harness.py: 假畫面、假輸入、虛擬時鐘) 跑兩個劇本:

- 有忙碌: 片段最後一次點擊之後, 忙碌指示出現 BUSY_SECS 秒 (比下一步的逾時長),
  這段時間下一步的圖不出現。預期下一步等到忙碌結束才找到 (`忙碌暫停`), 流程照常走完。
- 沒忙碌: 圖一直都在。預期一路直接走, 一次都不查忙碌指示。
兩個劇本的事件序列 (點到哪裡、依什麼順序) 必須完全相同——忙碌只改變時間。

另外記下片段裡「點擊後緊接點擊」的地方: 那裡現在不等忙碌 (座標點擊沒有找圖等待)。
結果寫 results/sim_busy.json; 任一劇本不符預期時結束碼 1。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import common

import pytest  # noqa: E402  (只借 MonkeyPatch 給 harness 用)

import flowfile  # noqa: E402
import harness as hz  # noqa: E402
from automation import findtarget  # noqa: E402
from automation import runner as runner_mod  # noqa: E402

BUSY_AT = (1300, 1000)   # 搜尋範圍 (0,0,1920,1080) 的九宮格 8、9 之內
BUSY_SECS = 15.0


class Net(hz.Vision):
    """片段最後一次點擊之後忙碌 busy_secs 秒; 這段時間 target 不出現."""

    def __init__(self, clock, events, busy_name, target, n_clicks, busy_secs):
        super().__init__(clock=clock)
        self.events, self.busy_name, self.target = events, busy_name, target
        self.n_clicks, self.busy_secs = n_clicks, busy_secs
        self.t_busy = None

    def _busy_on(self):
        if self.t_busy is None:
            if sum(1 for e in self.events if e[0] == "click") < self.n_clicks:
                return False
            self.t_busy = self.clock.t
        return self.clock.t < self.t_busy + self.busy_secs

    def query(self, name, search_region, color_check=False, expected_scale=None):
        on = bool(self.busy_secs) and self._busy_on()
        if name == self.busy_name:
            self.plan(name, [BUSY_AT if on else None])
        elif name == self.target:
            self.plan(name, [None if on else self.default])
        return super().query(name, search_region, color_check, expected_scale)


def windows(steps, removed_nos):
    """每個拿掉的位置 → (片段起, 片段迄(含), 下一步索引); 索引是改後的 steps."""
    out = []
    for k, no in enumerate(sorted(removed_nos)):
        site = no - 1 - k              # 改後的位置: 前面每拿掉一步就往前一格
        # 起點不能以原點為基準 (片段開頭沒有原點, 那一步會被跳過)
        start = max(j for j in range(site) if steps[j].get("type") == "find_click"
                    and steps[j].get("updateOrigin", True)
                    and not findtarget.needs_origin(findtarget.target(steps[j])))
        nxt = min(j for j in range(site, len(steps))
                  if steps[j].get("type") == "find_click")
        seg = steps[start:nxt + 1]
        if any(s["type"] in ("loop_start", "loop_end", "branch_or") for s in seg):
            raise SystemExit(f"第 {no} 步附近的片段含重複區段或多分支, 不認得的寫法")
        out.append((no, start, nxt))
    return out


def run_once(seg, busy, busy_secs):
    target = findtarget.template(seg[-1])
    n_clicks = sum(1 for s in seg if s["type"] == "click")
    with pytest.MonkeyPatch.context() as mp:
        h = hz.Harness(mp)
        h.vision = Net(h.clock, h.events, busy["template"], target, n_clicks,
                       busy_secs)
        mp.setattr(runner_mod.capture, "grab", h.vision.grab)
        r = h.run(seg, busy=busy, timeout=30)
        recs = [x for x in h.filelog.of("find.target")
                if x["step"] == len(seg) and x["role"] == "find"]
        clicks = [e for e in h.events if e[0] == "click"]
        return {
            "events": [list(e) for e in h.events],
            "ended": r.ended,
            "clicks": len(clicks),
            "next": target,
            "next_result": recs[-1]["result"] if recs else None,
            "busy_pause": recs[-1].get("busy_pause") if recs else None,
            "busy_lookups": h.lookups().count(busy["template"]),
            "log": h.logs(r)[-3:],
        }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default=common.FLOWS)
    args = ap.parse_args(argv)
    with open(os.path.join(common.RESULTS, "remove_busy_waits.json"),
              encoding="utf-8") as f:
        removed = json.load(f)

    results, bad = {}, []
    for name in common.FLOW_NAMES:
        data = flowfile.read(common.flow_path(name, args.flows))["data"]
        steps, busy = data["steps"], flowfile.busy_target(data)
        if any(common.is_busy_wait(s, busy) for s in steps):
            raise SystemExit(f"{name}: 還有忙碌等待步驟 (先跑 remove_busy_waits.py)")
        nos = [x["no"] for x in removed[name]["removed"]]
        results[name] = []
        print(f"== {name}")
        for no, start, nxt in windows(steps, nos):
            seg = steps[start:nxt + 1]
            back_to_back = [start + i + 1 for i in range(len(seg) - 1)
                            if seg[i]["type"] == "click"
                            and seg[i + 1]["type"] == "click"]
            with_busy = run_once(seg, busy, BUSY_SECS)
            no_busy = run_once(seg, busy, 0.0)
            ok = (with_busy["ended"] == "done" and with_busy["next_result"] == "found"
                  and float(with_busy["busy_pause"]) >= BUSY_SECS - 0.5
                  and no_busy["ended"] == "done" and no_busy["next_result"] == "found"
                  and no_busy["busy_lookups"] == 0
                  and with_busy["events"] == no_busy["events"])
            rec = {"removed_no": no, "segment": [start + 1, nxt + 1],
                   "next_step": nxt + 1, "click_then_click": back_to_back,
                   "with_busy": with_busy, "no_busy": no_busy, "ok": ok}
            results[name].append(rec)
            print(f"  原第 {no} 步 → 片段 {start + 1}–{nxt + 1}，下一步 {nxt + 1}"
                  f"「{with_busy['next']}」：有忙碌 {with_busy['next_result']}"
                  f"（暫停 {with_busy['busy_pause']}s）／沒忙碌 {no_busy['next_result']}"
                  f"（查忙碌 {no_busy['busy_lookups']} 次）"
                  + (f"；點擊緊接點擊於第 {back_to_back} 步" if back_to_back else "")
                  + ("" if ok else "  ← 不符預期"))
            if not ok:
                bad.append((name, no))
    os.makedirs(common.RESULTS, exist_ok=True)
    with open(os.path.join(common.RESULTS, "sim_busy.json"), "w",
              encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    if bad:
        print("不符預期:", bad)
        return 1
    print("全部符合預期")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""量主畫面那一對的停穩基準距離 (票 05).

用法: .venv/Scripts/python .scratch/calibration-settle/measure_baseline.py <流程名稱> [--delay 秒] [--out 路徑]

遊戲開著、停在主畫面。腳本先載入引擎, 倒數 --delay 秒 (讓你切到遊戲), 然後:
  1. 不動游標, 截流程的搜尋範圍一次, 主畫面那一對和標題列對四張圖都要找得到;
     任一張找不到 (畫面上沒有遊戲、不是主畫面、被別的視窗擋住) 就中止, 游標完全沒動過。
  2. 用跟執行器一樣的`等停穩再量` (calibration.settle) 和停點 (Runner._avoid_cursor:
     搜尋範圍左下角外), 每 1 秒量一次兩對, 連續兩次四張圖中心各差 ≤1px 才定案, 最多 10 秒。
  3. 印出主畫面那一對的停穩距離、標題列對的倍率、新基準距離 ＝ 停穩距離 ÷ 標題列倍率,
     寫成 json; 游標移回原位。

哪一對是「主畫面那一對」照流程檔決定: 兩張範本名都以「標題列」/「标题栏」開頭的那一對
是標題列對, 另一對 (主對或備用對) 就是主畫面那一對。晚班主對是主畫面那一對,
早班主畫面那一對是備用校準對。只移動游標, 不按任何鍵; Ctrl+C 可中斷。
"""
import argparse
import datetime
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (os.path.join(ROOT, "src"), os.path.join(ROOT, "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import calibration as calib  # noqa: E402

TITLE_PREFIXES = ("標題列", "标题栏")


class Abort(Exception):
    """量不了: 訊息說明原因; 在移動游標前丟出時游標沒動過."""


def is_title_pair(pair):
    return all(str(n).startswith(TITLE_PREFIXES) for n in pair)


def pick_pairs(cal):
    """從流程的校準資料挑出 (主畫面那一對, 標題列對), 各為
    {"pair", "baseline", "key"}; key 是 flow.yaml 裡那個基準距離的位置."""
    if not calib.valid(cal):
        raise Abort("這份流程沒有成形的校準對")
    fb = calib.fallback_pair(cal)
    if fb is None:
        raise Abort("這份流程沒有備用校準對, 湊不出主畫面那一對＋標題列對")
    groups = [
        {"pair": list(cal["pair"]), "baseline": float(cal["baseline"]),
         "key": "calibration.baseline"},
        {"pair": list(fb["pair"]), "baseline": float(fb["baseline"]),
         "key": "calibration.fallback.baseline"},
    ]
    titles = [g for g in groups if is_title_pair(g["pair"])]
    if len(titles) != 1:
        raise Abort("分不出哪一對是標題列對 (要剛好一對的兩張範本名都以"
                    f"「標題列」/「标题栏」開頭): {[g['pair'] for g in groups]}")
    title = titles[0]
    main = next(g for g in groups if g is not title)
    return main, title


def measure_both(query, screen, origin, main, title):
    return {"main": calib.measure(query, screen, main["pair"], origin),
            "title": calib.measure(query, screen, title["pair"], origin)}


def both_reading(ms):
    """兩對一起的停穩比對: 四張圖中心都要各差 ≤1px; 量不到時比原因與缺的圖."""
    bad = tuple((tag, m.problem, tuple(m.missing)) for tag, m in ms.items() if not m.ok)
    if bad:
        return calib.Reading(ms, failure=bad)
    points = {n: m.centers[n] for m in ms.values() for n in m.pair}
    return calib.Reading(ms, points, group="both")


def describe(ms):
    return "；".join(f"{'主畫面那一對' if tag == 'main' else '標題列對'}：{m.describe()}"
                    for tag, m in ms.items() if not m.ok)


def run(cal, query, peek, grab, wait, say=print):
    """量一次 → (結果 dict, 停穩那次的 Settled).

    peek() → (截圖, 左上角): 不動游標的截圖, 先確認畫面上有遊戲;
    grab() → (截圖, 左上角): 先`避開游標`再截 (會移動游標), 確認過才會呼叫;
    wait(秒): 兩次量測之間的等待。
    """
    main, title = pick_pairs(cal)
    say(f"主畫面那一對：{main['pair']}（{main['key']} = {main['baseline']:.1f}）")
    say(f"標題列對：{title['pair']}（基準 {title['baseline']:.1f}）")
    screen, origin = peek()
    pre = measure_both(query, screen, origin, main, title)
    if any(not m.ok for m in pre.values()):
        raise Abort("游標移動前的檢查沒過，沒有移動游標："
                    f"{describe(pre)}。請確認遊戲停在主畫面、搜尋範圍沒被其他視窗擋住")
    say("檢查通過：四張圖都找得到，開始移開游標、等停穩（約 1–10 秒）")
    s = calib.settle(
        grab,
        lambda sc, og: both_reading(measure_both(query, sc, og, main, title)),
        wait)
    ms = s.value
    if any(not m.ok for m in ms.values()):
        e = Abort(f"移開游標後量不到（量了 {s.reads} 次）：{describe(ms)}")
        e.screen = s.screen  # 給呼叫端存檔, 看移開游標後畫面變成什麼樣
        raise e
    m_main, m_title = ms["main"], ms["title"]
    k_title = m_title.distance / title["baseline"]
    new_baseline = round(m_main.distance / k_title, 1)
    result = {
        "settle": "timeout" if s.timed_out else "stable",
        "reads": s.reads,
        "main_screen_pair": {
            "pair": main["pair"], "flow_key": main["key"],
            "centers": {n: list(m_main.centers[n]) for n in main["pair"]},
            "settled_distance": round(m_main.distance, 2),
            "old_baseline": main["baseline"],
            "scale_with_old_baseline": round(m_main.distance / main["baseline"], 4),
        },
        "title_pair": {
            "pair": title["pair"],
            "centers": {n: list(m_title.centers[n]) for n in title["pair"]},
            "distance": round(m_title.distance, 2),
            "baseline": title["baseline"],
            "scale": round(k_title, 4),
            "scale_snapped": round(calib.snap_identity(k_title), 4),
        },
        "new_baseline": new_baseline,
        "formula": "new_baseline = settled_distance / title_pair.scale",
    }
    return result, s


def report(r, say=print):
    mp, tp = r["main_screen_pair"], r["title_pair"]
    if r["settle"] == "timeout":
        say(f"警告：畫面 {r['reads'] - 1} 秒都沒停穩，用的是最後一次的值，建議重跑")
    else:
        say(f"停穩：量了 {r['reads']} 次")
    say(f"主畫面那一對停穩距離：{mp['settled_distance']:.2f}px"
        f"（舊基準 {mp['old_baseline']:.1f} → ×{mp['scale_with_old_baseline']:.4f}）")
    say(f"標題列對倍率：×{tp['scale']:.4f}（距離 {tp['distance']:.2f} ÷ 基準 {tp['baseline']:.1f}；"
        f"貼齊後 ×{tp['scale_snapped']:.4f}）")
    say(f"新基準距離：{mp['settled_distance']:.2f} ÷ {tp['scale']:.4f} = {r['new_baseline']:.1f}"
        f"（改 flow.yaml 的 {mp['flow_key']}）")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="量主畫面那一對的停穩基準距離（票 05）。遊戲要停在主畫面；"
                    "畫面上找不到兩對校準圖時，在移動游標前就中止。")
    ap.add_argument("flow", help="流程資料夾名稱，例如 晚_繁中、早_繁中")
    ap.add_argument("--delay", type=float, default=5,
                    help="引擎載入後倒數幾秒才開始（讓你切到遊戲畫面；預設 5）")
    ap.add_argument("--out", help="結果 json 路徑（預設 .scratch/calibration-settle/baseline_<流程>.json）")
    a = ap.parse_args(argv)

    import applog
    import flowfile
    tmp = os.path.join(HERE, "tmp")
    os.makedirs(tmp, exist_ok=True)
    applog.set_path(os.path.join(tmp, "measure_baseline.log"))

    folder = os.path.join(ROOT, "flows", a.flow)
    if not os.path.isfile(os.path.join(folder, flowfile.FLOW_YAML)):
        names = sorted(d for d in os.listdir(os.path.join(ROOT, "flows"))
                       if os.path.isfile(os.path.join(ROOT, "flows", d, flowfile.FLOW_YAML)))
        sys.exit(f"找不到流程「{a.flow}」；可用的：{'、'.join(names)}")
    flow = flowfile.read_flow(folder)
    cal = flow.get("calibration")
    region = flow.get("scan_region")
    try:
        main_pair, title_pair = pick_pairs(cal)
    except Abort as e:
        sys.exit(f"中止：{e}")
    print(f"流程 {a.flow}　搜尋範圍 {region}")

    from automation import capture, win
    from automation.runner import Runner
    import enginehub
    from subject_detection.library import load_default_config
    win.set_dpi_aware()

    t0 = time.perf_counter()
    print("載入引擎…")
    hub = enginehub.EngineHub()
    hub.load()
    if not hub.ready or hub.coarse_only:
        sys.exit(f"中止：引擎載入失敗或只有粗篩（{hub.error}）")
    cfg = load_default_config()
    cfg.update(flow.get("engine") or {})
    tdir = os.path.join(folder, flowfile.TEMPLATES_DIR)
    imgs = {fn[:-4]: os.path.join(tdir, fn) for fn in os.listdir(tdir)
            if fn.lower().endswith(".png")}
    need = main_pair["pair"] + title_pair["pair"]
    lacking = [n for n in need if n not in imgs]
    if lacking:
        sys.exit(f"中止：流程的 templates 裡沒有 {lacking}")
    hub.bind(imgs, cfg, os.path.join(folder, flowfile.CACHE_DIR, flowfile.REGISTERED_DIR))
    hub.preload(need)
    print(f"引擎就緒（{time.perf_counter() - t0:.1f}s）")

    for left in range(int(a.delay), 0, -1):
        print(f"{left} 秒後開始，請切到遊戲主畫面…", flush=True)
        time.sleep(1)

    # 停點與執行器相同: 直接借用執行器的避開游標 (搜尋範圍左下角外, 夾在該螢幕內)
    parker = type("Parker", (), {"_sleep": staticmethod(time.sleep)})()
    moved = []

    def grab():
        moved.append(True)
        Runner._avoid_cursor(parker, region)
        if win.cursor_pos() == home:
            # 遊戲以系統管理員執行時, 非管理員程序的 SetCursorPos 會被 UIPI 擋掉, 量到的是游標沒移開的畫面
            raise Abort(f"游標移不動（還在 {home}）：遊戲可能以系統管理員執行，請用系統管理員身分跑這支腳本")
        return capture.grab(region)

    home = win.cursor_pos()
    t_move = None
    try:
        t_move = time.perf_counter()
        r, s = run(cal, hub.query, lambda: capture.grab(region), grab, time.sleep)
        park = win.cursor_pos()
    except Abort as e:
        if getattr(e, "screen", None) is not None:
            import cv2
            os.makedirs(tmp, exist_ok=True)
            fail = os.path.join(tmp, f"baseline_{a.flow}_failed.png")
            ok, buf = cv2.imencode(".png", e.screen)
            if ok:
                buf.tofile(fail)
                print(f"最後一次的截圖：{fail}")
        sys.exit(f"中止：{e}")
    finally:
        if moved:
            win.park(*home)
            print(f"游標已移回 {home}（移開約 {time.perf_counter() - t_move:.1f}s）")
    r = {"flow": a.flow, "measured_at": datetime.datetime.now().isoformat(timespec="seconds"),
         "scan_region": region, "park_point": list(park), **r}
    report(r)
    out = a.out or os.path.join(HERE, f"baseline_{a.flow}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    shot = os.path.join(tmp, f"baseline_{a.flow}.png")
    import cv2
    ok, buf = cv2.imencode(".png", s.screen)
    if ok:
        buf.tofile(shot)
    print(f"結果：{out}\n停穩那張截圖：{shot}")


if __name__ == "__main__":
    main()

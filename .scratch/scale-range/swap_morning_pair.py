"""早班開頭簽到／公告彈窗開著時整個主畫面被模糊 (demo6、demo2 第 0 幀), 遊戲內沒有一個清楚的
固定元件, 「主畫面設定鈕 × 主畫面倉庫」量不到, 每趟都退到備用對; 彈窗下只有標題列一直在。
"""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile

import srcommon as sr
from srcommon import bp

import calibration  # noqa: E402
import flowfile  # noqa: E402
from automation import flowfmt  # noqa: E402

BACKUP = os.path.join(bp.APP, "dist", "profiles-backup-2026-10-10-morning-pair")
FLOWS_TO_SWAP = ("早_繁中", "早_簡中")
POPUP_FRAME = {"cn": ("demo6", 0), "tw": ("demo2", 0)}


def swap(data, pos):
    old = calibration.flow_pair(data)
    fb = calibration.fallback_pair(old)
    assert old and fb, "沒有主對或備用對"
    off = (int(fb["offset"][0]), int(fb["offset"][1]))
    old_anchor, new_anchor = (0, 0), (-off[0], -off[1])
    moved = flowfmt.shift_flow(data, old_anchor, new_anchor, 1.0)
    for n, xy in list(pos.items()):
        pos[n] = list(flowfmt.from_screen(flowfmt.to_screen(xy, old_anchor, 1.0), new_anchor, 1.0))
    cal = calibration.make(fb["pair"], fb["baseline"])
    cal[calibration.FALLBACK_KEY] = calibration.make_fallback(
        old["pair"], old["baseline"], calibration.fallback_offset(new_anchor, old_anchor, 1.0))
    data[calibration.FLOW_KEY] = cal
    return moved, cal


def do_swap():
    if bp.autoclick_running():
        raise SystemExit("AutoClick 正在執行: 請先關掉")
    if not os.path.isdir(BACKUP):
        shutil.copytree(os.path.dirname(sr.PROFILE), BACKUP)
        print(f"已備份 profiles 到 {BACKUP}")
    for name in FLOWS_TO_SWAP:
        path = bp.flow_path(name, sr.FLOWS)
        r = flowfile.read(path)
        data, images, pos = r["data"], r["images"], dict(r["pos"])
        before = calibration.flow_pair(data)
        moved, cal = swap(data, pos)
        data.pop("flowFormat", None)
        missing = flowfile.write(path, data, images, pos)
        assert not missing, f"{name}: 缺圖 {missing}"
        back = flowfile.read(path)
        refs = set(flowfile.flow_refs(back["data"]))
        assert refs <= set(back["images"]), refs - set(back["images"])
        assert back["data"]["calibration"] == cal
        print(f"[{name}] 主對 {before['pair']} → {cal['pair']} (基準距離 {cal['baseline']:.1f}); "
              f"備用 {cal['fallback']['pair']} 偏移 {cal['fallback']['offset']}; "
              f"平移 {moved} 個座標、{len(pos)} 個拍攝位置; {len(back['data']['steps'])} 步、"
              f"{len(back['images'])} 張範本")
    synced = []
    for n in FLOWS_TO_SWAP:
        path = bp.flow_path(n, sr.FLOWS)
        if bp.sync_draft(path):
            flowfile.Workspace(sr.PROFILE).load_flow(path)
            synced.append(n)
    print("草稿與工作區同步:", synced or "草稿不屬於早班, 不動")


def verify():
    ok = True
    for name in FLOWS_TO_SWAP:
        lang = sr.FLOW_LANG[name]
        new = flowfile.read(bp.flow_path(name, sr.FLOWS))
        old = flowfile.read(bp.flow_path(name, os.path.join(BACKUP, "arknights", "flows")))
        region = new["data"]["scanRegion"]
        ncal, ocal = new["data"]["calibration"], old["data"]["calibration"]
        names = [*ncal["pair"], *ncal["fallback"]["pair"]]
        tmp = tempfile.mkdtemp(prefix="sr_swap_")
        try:
            hub = bp.make_hub(new["images"], names, tmp)
            placer = sr.place(lang, region)
            canvas, org = placer(sr.frame(*POPUP_FRAME[lang]))
            c = calibration.calibrate(hub.query, canvas, org, ncal)
            print(f"[{name}] 彈窗影格 {POPUP_FRAME[lang]}: ok={c.ok} used={c.used} pair={c.pair} "
                  f"scale={c.scale if c.ok else None} anchor={c.anchor if c.ok else None}"
                  + ("" if c.ok else " " + c.describe()))
            ok &= bool(c.ok and c.used == "main" and c.scale == 1.0)
            canvas, org = placer(sr.frame(*sr.LANGS[lang]["menu"]))
            cn = calibration.calibrate(hub.query, canvas, org, ncal)
            co = calibration.calibrate(hub.query, canvas, org, ocal)
            print(f"[{name}] 主畫面影格 {sr.LANGS[lang]['menu']}: 新 used={cn.used} anchor={cn.anchor} "
                  f"scale={cn.scale}; 舊 used={co.used} anchor={co.anchor} scale={co.scale}")
            ok &= bool(cn.ok and co.ok and cn.used == "main" and co.used == "main")
            if cn.ok and co.ok:
                d = (co.anchor[0] - cn.anchor[0], co.anchor[1] - cn.anchor[1])
                want = tuple(-v for v in ncal["fallback"]["offset"])
                jitter = max(abs(d[0] - want[0]), abs(d[1] - want[1]))
                print(f"    舊基準點−新基準點 = {d}, 應為 −新備用偏移 = {want}, 抖動 {jitter}px")
                ok &= jitter <= 3
                fb = ncal["fallback"]
                fm = calibration.measure(hub.query, canvas, fb["pair"], org)
                fk = calibration.snap_identity(fm.distance / fb["baseline"]) if fm.ok else None
                fba = calibration.fallback_anchor(fm.anchor, fb["offset"], fk) if fm.ok else None
                print(f"    新存檔只用備用對 (齒輪×倉庫): ok={fm.ok} scale={fk} 算回基準點 {fba} "
                      f"(主對量到 {cn.anchor})")
                ok &= bool(fm.ok and max(abs(fba[0] - cn.anchor[0]),
                                         abs(fba[1] - cn.anchor[1])) <= 3)
                ns, os_ = new["data"]["steps"], old["data"]["steps"]
                for (i, s), (_, so) in zip(flowfmt.abs_steps(ns)[:2], flowfmt.abs_steps(os_)[:2]):
                    kx, ky = flowfmt._ABS_KEYS[s["type"]][0]
                    pn = flowfmt.to_screen((s[kx], s[ky]), cn.anchor, cn.scale)
                    po = flowfmt.to_screen((so[kx], so[ky]), co.anchor, co.scale)
                    print(f"    第 {i} 步 {s['type']} 新 {pn} 舊 {po}")
                    ok &= max(abs(pn[0] - po[0]), abs(pn[1] - po[1])) <= 3
                for s, so in zip(ns, os_):
                    lim = (s.get("target") or {}).get("limit")
                    if isinstance(lim, dict) and lim.get("kind") == "rect":
                        rn = flowfmt.rect_to_screen(lim, cn.anchor, cn.scale)
                        ro = flowfmt.rect_to_screen(so["target"]["limit"], co.anchor, co.scale)
                        print(f"    固定矩形 {s['target'].get('template')} 新 {rn} 舊 {ro}")
                        ok &= max(abs(a - b) for a, b in zip(rn, ro)) <= 3
                        break
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("驗證", "通過" if ok else "失敗")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    if args.verify:
        raise SystemExit(0 if verify() else 1)
    do_swap()


if __name__ == "__main__":
    main()

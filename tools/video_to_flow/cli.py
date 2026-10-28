"""命令列介面 (skill 呼叫用)::

    python tools/video_to_flow scan <影片> --out <輸出目錄> [--sample <特效樣本.json>]
                                   [--frames 120,130,...]
    python tools/video_to_flow learn-cursor <影片> --at "幀:x,y;幀:x,y;..." --out <樣本.json>
    python tools/video_to_flow assemble <轉換計畫.json> [--out <輸出位置>]
    python tools/video_to_flow insert <補充計畫.json> <流程資料夾>

結果摘要印在 stdout (UTF-8); 拒絕時把原因印在 stderr 並以 1 結束。
"""
from __future__ import annotations

import argparse
import sys

from .errors import ToolError


def _utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _frames(text):
    try:
        return [int(v) for v in text.split(",") if v.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError("--frames 要是逗號分隔的影格編號") from None


def _points(text):
    """「幀:x,y;幀:x,y」→ [(幀, (x, y)), ...]."""
    out = []
    try:
        for part in text.split(";"):
            if not part.strip():
                continue
            f, xy = part.split(":")
            x, y = xy.split(",")
            out.append((int(f), (int(x), int(y))))
    except ValueError:
        raise argparse.ArgumentTypeError(
            "--at 要寫成「幀:x,y;幀:x,y;...」（游標尖端的影片像素位置）") from None
    return out


def _shared(res):
    for name, info in res["shared_rects"].items():
        members = "、".join(text for _, text in info["members"])
        print(f"共用矩形「{name}」：固定矩形 {info['within']}，成員 {members}"
              + (f"（沿用{info['source']}那一步）" if info["source"] else ""))


def _loosened(res):
    from .labels import label
    from .report import loosened_text
    steps = res["step_list"]
    base = res["position"] - 1 if "position" in res else 0
    for i, kind, value in res["loosened"]:
        print(f"固定矩形放寬：{label(steps[base + i])}：{loosened_text(kind, value)}")


def _lists(res):
    for name, why in res["retake"].items():
        print(f"待重拍：{name}：{'；'.join(why)}")
    for name, info in (res.get("existing") or {}).items():
        print(f"待確認（既有範本）：{name}：{'；'.join(info['reasons'])}——流程裡共 "
              f"{info['steps']} 步引用它（{'、'.join(info['files'])}），重截會一起影響")
    for _, text in res["scroll_confirm"]:
        print(f"待確認（捲動）：{text}——同一段有拖曳，沒宣告捲動軸或停點差")
    for _, text in res["busy_unseen"]:
        print(f"待確認（忙碌）：{text} 勾了忙碌檢查，之後沒看到忙碌指示")
    for _, text in res["busy_unchecked"]:
        print(f"待確認（忙碌）：{text} 沒勾忙碌檢查，之後看到忙碌指示")


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(prog="video_to_flow",
                                 description="影片轉流程：掃描示範影片、組裝流程存檔")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="示範影片 → 候選點擊清單與縮圖")
    sc.add_argument("video")
    sc.add_argument("--out", required=True, help="候選清單與縮圖的輸出目錄（不要放 repo 裡）")
    sc.add_argument("--sample", help="點擊特效樣本 JSON（沒有就用退路偵測）")
    sc.add_argument("--frames", type=_frames, default=[],
                    help="另外輸出這些影格的原尺寸圖（含座標格線版），逗號分隔")
    lc = sub.add_parser("learn-cursor",
                        help="遊戲自繪游標 → 游標樣本（從游標停在不同背景上的幾幀學）")
    lc.add_argument("video")
    lc.add_argument("--at", type=_points, required=True,
                    help="游標尖端位置，「幀:x,y;幀:x,y;...」，至少 4 幀、背景各不相同")
    lc.add_argument("--out", required=True, help="樣本 JSON（游標圖寫在旁邊同名 .png）")
    asm = sub.add_parser("assemble", help="轉換計畫 → 自我驗證 → 新的流程資料夾 + 交付報告")
    asm.add_argument("plan")
    asm.add_argument("--out", help="輸出位置：流程資料夾建在它底下"
                                   "（預設計畫的 out，再沒有就是流程存放區：repo 的 flows\\）")
    ins = sub.add_parser("insert", help="補充計畫 → 量好的步驟插進既有流程（直接改寫，不備份）")
    ins.add_argument("plan")
    ins.add_argument("folder", help="既有流程資料夾（有 flow.yaml 的那一層）")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "scan":
            from .scan import scan
            res = scan(args.video, args.out, sample=args.sample, frames=args.frames)
            print(f"候選點擊 {len(res['candidates'])} 個（{res['mode']}）"
                  f"→ {res['candidates_path']}")
            for c in res["candidates"]:
                print(f"  #{c['id']:03d} 幀 {c['frame']} ({c['time']:.2f}s) "
                      f"@ {c['x']},{c['y']} 信心 {c['confidence']:.2f} {c['kind']}"
                      + (f" {c['cue']}" if "cue" in c else ""))
        elif args.cmd == "learn-cursor":
            from . import learn_cursor
            res = learn_cursor(args.video, args.at, args.out)
            print(f"游標樣本：{res['sample_path']}（圖 {res['template_path']}）")
            print(f"  大小 {res['size'][0]}×{res['size'][1]}、熱點 {res['hotspot']}、"
                  f"不透明 {res['cover']:.0%}")
            print("  各幀相似度：" + "、".join(f"{f}={v}" for f, v in res["fits"].items()))
            for w in res["warnings"]:
                print(f"提醒：{w}")
        elif args.cmd == "insert":
            from .insert import insert
            res = insert(args.plan, args.folder)
            print(f"已插入 {res['inserted']} 步（從步驟 {res['position']} 起）→ {res['flow_path']}")
            print(f"影片倍率 ×{res['video_scale']:.3f}（{res['scale_from']}）")
            aligned = res["align"]
            if aligned:
                dx, dy = aligned["shift"]
                print(f"對齊位移 ({dx}, {dy}) px（影片裡 {aligned['video']}、執行時 "
                      f"{aligned['runtime']}）" + (
                          "；第一次拖曳 {} → {} px".format(*aligned["drag"])
                          if aligned["drag"] else ""))
            _shared(res)
            _loosened(res)
            _lists(res)
            for n, e in res["similar"].items():
                print(f"建議：新範本「{n}」跟既有的「{e}」幾乎一樣，考慮改用既有的")
            print(f"交付報告更新：{'、'.join(res['report_files'])}")
        else:
            from .assemble import assemble
            res = assemble(args.plan, out_dir=args.out)
            print(f"流程資料夾：{res['flow_path']}")
            print(f"交付報告：{res['report_path']}（{'、'.join(res['report_files'])}）")
            if res.get("fallback_problem"):
                print(f"警告：備用校準對量不到（{res['fallback_problem']}）——流程不帶備用對")
            if res["verification"] == "coarse":
                print("警告：驗證不完整——深度驗證模型無法載入，只做了粗篩")
            _shared(res)
            _loosened(res)
            _lists(res)
            print(f"步驟 {res['steps']}、範本 {res['templates']}")
    except ToolError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 1
    return 0

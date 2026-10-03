"""命令列介面 (skill 呼叫用)::

    python tools/video_to_flow scan <影片> --out <輸出目錄> [--sample <特效樣本.json>]
                                   [--frames 120,130,...]
    python tools/video_to_flow learn-cursor <影片> --at "幀:x,y;幀:x,y;..." --out <樣本.json>
    python tools/video_to_flow assemble <轉換計畫.json> [--report <報告.md>]

結果摘要印在 stdout (UTF-8); 拒絕時把原因印在 stderr 並以 1 結束。
"""
from __future__ import annotations

import argparse
import json
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
    asm = sub.add_parser("assemble", help="轉換計畫 → 自我驗證 → 流程存檔 + 交付報告")
    asm.add_argument("plan")
    asm.add_argument("--report", help="交付報告位置（預設與存檔同名並排）")
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
        else:
            from .assemble import assemble
            res = assemble(args.plan, report_path=args.report)
            print(f"流程存檔：{res['flow_path']}")
            print(f"交付報告：{res['report_path']}")
            for w in res["warnings"]:
                print(f"提醒：{w}")
            if res["verification"] == "coarse":
                print("警告：驗證不完整——深度驗證模型無法載入，只做了粗篩")
            for name, why in res["retake"].items():
                print(f"待重拍：{name}：{'；'.join(why)}")
            summary = {k: v for k, v in res.items()
                       if k not in ("flow_path", "report_path", "found", "step_list",
                                    "warnings")}
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    except ToolError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 1
    return 0

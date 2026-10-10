"""命令列介面::

    python tools/recruit_tags fetch-pool --server tw|cn [--out <快照.json>]
    python tools/recruit_tags recognize <截圖> [--client tw|cn] [--pool <快照.json>]
                                       [--font <字型>] [--weight N] [--size N]
                                       [--cells <JSON>] [--json <結果.json>]

結果摘要印在 stdout (UTF-8); 拒絕時把原因印在 stderr 並以 1 結束。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import ToolError


def _utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _fetch_pool(args):
    from . import fetch
    from .pool import build_pool, save_pool
    gacha = fetch.table(args.server, "gacha_table")
    character = fetch.table(args.server, "character_table")
    snap = build_pool(gacha, character, args.server,
                      upstream_updated=fetch.upstream_updated(args.server))
    path = save_pool(snap, args.out)
    src = snap["source"]
    print(f"招募池快照（{args.server}）：{path}")
    print(f"  標籤 {len(snap['tags'])} 個、幹員 {len(snap['operators'])} 位")
    print(f"  上游更新 {src['upstream_updated'] or '（查不到）'}、抓取 {src['fetched_at']}")


def _cells(text):
    """--cells: JSON 字串或 JSON 檔, 五個 [x, y, w, h] (1.0 尺度)."""
    try:
        data = json.loads(Path(text).read_text(encoding="utf-8")
                          if Path(text).is_file() else text)
        cells = [tuple(int(v) for v in c) for c in data]
        if any(len(c) != 4 for c in cells):   # 個數由 layout.scaled_cells 檢查
            raise ValueError
    except (ValueError, TypeError, OSError):
        raise argparse.ArgumentTypeError(
            "--cells 要是五個 [x, y, w, h] 的 JSON（1.0 尺度、1920 寬客戶區座標）") from None
    return cells


def _f(v):
    return "—" if v is None else f"{v:.3f}"


def summary(res):
    """辨識結果 → 給人看的摘要 (多行字串)."""
    from .recognize import STATUS_TEXT
    out = [f"截圖 {res['size'][0]}×{res['size'][1]}（尺度 ×{res['scale']}）、客戶端 {res['client']}"]
    for c in res["cells"]:
        b, r = c["best"], c["runner_up"]
        line = (f"  格 {c['index']}：{STATUS_TEXT[c['status']]:　<4} "
                f"{(c['tag'] or b)['name']}（粗篩 {_f(b['coarse'])}、驗證 {_f(b['verify'])}）"
                f" 次高 {r['name']} {_f(r['coarse'])}、差距 {c['margin']:+.3f}")
        if c["status"] == "confused":
            names = {s["id"]: s["name"] for s in c["scores"]}
            line += "；過門檻：" + "、".join(names[t] for t in c["found"])
        out.append(line)
    out.append(f"嚴格標準：{'通過' if res['passed'] else '不通過'}"
               f"（每格恰一張範本過門檻、粗篩差距 ≥ {res['engine']['min_margin']}）")

    def names(c):
        return "＋".join(t["name"] for t in c["tags"])

    def ops(c):
        return "、".join(f"{o['name']}{o['rarity']}★" for o in c["operators"])

    out.append("保底組合：" + ("（沒有）" if not res["combos"] else ""))
    out += [f"  {c['level']}★ {names(c)}：{ops(c)}" for c in res["combos"]]
    if res["robots"]:
        out.append("機器人組合（時限設 3:50 以下）：")
        out += [f"  {names(c)}：{ops(c)}" for c in res["robots"]]
    r, e, p = res["render"], res["engine"], res["pool"]
    out.append(f"渲染：{r['font']} 字級 {r['size']} 字重 {r['weight']} 邊 {r['margin']}"
               f" 字色 {tuple(r['fg'])} 底色 {tuple(r['bg'])}")
    out.append(f"引擎：粗篩門檻 {e['match_threshold']}、驗證門檻 {e['verify_threshold']}"
               f"（{'完整' if e['verification'] == 'full' else '只有粗篩'}）")
    out.append(f"招募池：{p['server']}，上游更新 {p.get('upstream_updated') or '—'}、"
               f"抓取 {p.get('fetched_at') or '—'}")
    return "\n".join(out)


def _recognize(args):
    from . import render
    from .pool import load_pool
    from .recognize import recognize
    pool = load_pool(args.pool or args.client)
    settings = render.default_settings(args.client, font=args.font, size=args.size,
                                       weight=args.weight)
    res = recognize(args.image, pool, client=args.client, cells=args.cells,
                    render_settings=settings)
    print(summary(res))
    if args.json:
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"JSON：{args.json}")


def main(argv=None):
    _utf8()
    ap = argparse.ArgumentParser(prog="recruit_tags",
                                 description="公開招募標籤辨識：建招募池快照、辨識截圖的五個標籤格")
    sub = ap.add_subparsers(dest="cmd", required=True)
    fp = sub.add_parser("fetch-pool", help="抓上游資料表、建招募池快照")
    fp.add_argument("--server", choices=["tw", "cn"], required=True)
    fp.add_argument("--out", help="快照位置（預設工具資料夾 data/pool_<伺服器>.json）")
    rc = sub.add_parser("recognize", help="截圖 → 五格標籤、嚴格判定、保底組合")
    rc.add_argument("image", help="公開招募畫面截圖（整個遊戲客戶區）")
    rc.add_argument("--client", choices=["tw", "cn"], default="tw")
    rc.add_argument("--pool", help="招募池快照（預設工具資料夾裡該客戶端的）")
    rc.add_argument("--font", help="字型檔名或路徑（預設 tw: NotoSansTC-VF、cn: 微軟雅黑）")
    rc.add_argument("--size", type=int, help="1.0 尺度的字級 px（預設 24）")
    rc.add_argument("--weight", type=int, help="可變字型的字重（預設 500）")
    rc.add_argument("--cells", type=_cells, help="整組覆寫五格版面：五個 [x,y,w,h] 的 JSON 或 JSON 檔")
    rc.add_argument("--json", help="結果另存 JSON")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "fetch-pool":
            _fetch_pool(args)
        else:
            _recognize(args)
    except ToolError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 1
    return 0

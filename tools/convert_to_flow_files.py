"""一次性轉換: 舊的「流程 JSON + profile 範本庫」→ 自包自足的流程存檔 (ADR 0006).

轉換完成即功成身退——app 只讀新格式, 這不是內建的長期遷移路徑。

每份舊流程 JSON 變成一個 `.autoclickpack`, 收進它引用到的每一張範本圖 (含
`確認圖`); 多截圖範本取`登錄基準張` (排序後第一張), 其餘丟棄; 範本名拉平
(去掉子路徑前綴), 撞名加序號並同步改寫步驟引用。`校準對`的兩張圖落到 profile
自存的位置。轉換完成後刪掉舊的範本庫與登錄產物目錄。

步驟草稿 (`flows/_autosave.json`) 也一起轉: 引用改寫之後, 它引用到的圖解進
工作區——當機重開時草稿與工作區的圖一起復原, 未存檔的編輯不會白做。

用法::

    python tools/convert_to_flow_files.py <profiles 根目錄> [選項]

      --library DIR   範本庫位置的覆寫 (預設 <profile>/templates)。repo 的開發
                      用資料把範本庫搬去了 benchmark 素材, 用這個指過去。
      --backup DIR    動手之前把整個 profiles 根目錄複製一份備份到這裡
      --report FILE   轉換報告寫到這個檔 (預設只印在畫面上)
      --dry-run       只算不寫
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

import calibration  # noqa: E402
import flowfile  # noqa: E402


def profile_dirs(profiles_root: Path) -> list[Path]:
    """profiles 根目錄下的 profile (有引擎參數設定檔的就算)."""
    if not profiles_root.is_dir():
        return []
    return [d for d in sorted(profiles_root.iterdir())
            if d.is_dir() and (d / "config.yaml").is_file()]


def legacy_flows(profile: Path) -> list[Path]:
    """舊的流程 JSON (草稿不算一份流程, 另外處理)."""
    flows = profile / "flows"
    if not flows.is_dir():
        return []
    return [p for p in sorted(flows.iterdir())
            if p.suffix.lower() == ".json" and p.name != flowfile.DRAFT_NAME]


def _load(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def convert_profile(profile: Path, library_dir: Path, dry_run=False) -> dict:
    """轉換一個 profile; 回傳報告 dict (不寫任何報告檔)."""
    lib = flowfile.scan_templates(library_dir)
    pos_in = flowfile._legacy_meta_pos(str(library_dir))
    cal = calibration.load(str(profile))

    report = {
        "profile": profile.name, "library": str(library_dir),
        "library_templates": len(lib), "flows": [], "draft": None,
        "downgraded": {}, "renamed": {}, "orphans": [], "missing": {},
        "calibration": None, "removed": [],
    }
    referenced: set[str] = set()
    draft = _load(profile / flowfile.DRAFT_NAME) or _load(
        profile / "flows" / flowfile.DRAFT_NAME)
    draft_steps_before = json.dumps((draft or {}).get("steps") or [],
                                    ensure_ascii=False, sort_keys=True)
    draft_twin = None   # 草稿與哪一份流程內容相同 (工作區的當前流程就指它)

    for src in legacy_flows(profile):
        data = _load(src)
        if data is None:
            report["flows"].append({"file": src.name, "error": "讀不出 JSON"})
            continue
        steps_before = json.dumps(data.get("steps") or [], ensure_ascii=False,
                                  sort_keys=True)
        notes = flowfile.migrate_flow(data)
        referenced |= set(flowfile.used_templates(data.get("steps") or []))
        r = flowfile.collect_flow_templates(data.get("steps") or [], lib)
        pos = {new: pos_in[old] for old, new in r["mapping"].items()
               if old in pos_in}
        dest = profile / "flows" / (src.stem + flowfile.EXT)
        cal_payload, cal_images = _calibration_payload(cal, lib)
        if not dry_run:
            flowfile.write(str(dest), data, r["images"], pos,
                           cal=cal_payload, cal_images=cal_images)
            src.unlink()
        if steps_before == draft_steps_before and draft_twin is None:
            draft_twin = dest
        report["flows"].append({
            "file": src.name, "dest": dest.name,
            "steps": len(data.get("steps") or []),
            "templates": len(r["images"]), "notes": notes,
            "renamed": r["renamed"], "downgraded": r["downgraded"],
            "missing": r["missing"]})
        report["renamed"].update(r["renamed"])
        for n in r["downgraded"]:
            report["downgraded"][n] = True
        if r["missing"]:
            report["missing"][src.name] = r["missing"]

    # 草稿: 引用改寫 + 它引用到的圖解進工作區
    ws = flowfile.Workspace(str(profile))
    if draft is not None:
        flowfile.migrate_flow(draft)
        referenced |= set(flowfile.used_templates(draft.get("steps") or []))
        r = flowfile.collect_flow_templates(draft.get("steps") or [], lib)
        if not dry_run:
            ws.clear()
            for name, src_img in r["images"].items():
                ws.add(name, src_img,
                       pos=pos_in.get(_key_of(r["mapping"], name)))
            ws.set_flow_path(str(draft_twin) if draft_twin else None)
            flowfile.write_draft(str(profile), draft)
        report["draft"] = {"steps": len(draft.get("steps") or []),
                           "templates": len(r["images"]),
                           "renamed": r["renamed"],
                           "flow": draft_twin.name if draft_twin else None}
        report["renamed"].update(r["renamed"])
    elif not dry_run:
        ws.ensure()

    if cal is not None:
        pair = _flat_pair(cal)
        images = {n: flowfile.baseline_capture(lib[o])
                  for o, n in zip(cal["pair"], pair) if o in lib}
        if not dry_run:
            flowfile.store_calibration_images(str(profile), images)
            calibration.save(str(profile), dict(cal, pair=pair))
        report["calibration"] = {
            "pair": pair, "baseline": cal["baseline"], "scale": cal.get("scale"),
            "images_found": sorted(images)}

    report["orphans"] = sorted(set(lib) - referenced)

    # 舊的範本庫與登錄產物目錄退場 (留著只會有人/程式再去讀它們)
    for stale in (profile / "templates", profile / "registered"):
        if stale.is_dir():
            report["removed"].append(stale.name)
            if not dry_run:
                shutil.rmtree(stale, ignore_errors=True)
    return report


def _key_of(mapping: dict, new_name: str):
    for old, new in mapping.items():
        if new == new_name:
            return old
    return new_name


def _flat_pair(cal) -> list[str]:
    """`校準對`名稱拉平 (與流程引用同一條拉平規則); 兩張撞名時加序號.

    校準對與流程的範本是兩套獨立的名字空間 (校準圖由 profile 自存), 所以
    只要這一對彼此不撞名就夠。
    """
    pair = []
    for old in cal["pair"]:
        pair.append(flowfile.free_name(flowfile.flatten_name(old), pair))
    return pair


def _calibration_payload(cal, lib):
    """每份存檔攜帶的校準資料與那兩張圖 (拉平後的名稱)."""
    if cal is None:
        return None, {}
    pair = _flat_pair(cal)
    images = {new: flowfile.baseline_capture(lib[old])
              for old, new in zip(cal["pair"], pair) if old in lib}
    return {"pair": pair, "baseline": cal["baseline"]}, images


def format_report(reports: list[dict]) -> str:
    out = ["# 流程存檔自包自足 — 一次性轉換報告", ""]
    for r in reports:
        out.append(f"## profile `{r['profile']}`")
        out.append("")
        out.append(f"- 範本庫來源：`{r['library']}`（{r['library_templates']} 個範本）")
        out.append(f"- 轉換流程：{len(r['flows'])} 份")
        out.append("")
        out.append("| 舊檔 | 新存檔 | 步驟數 | 範本數 |")
        out.append("|---|---|---|---|")
        for f in r["flows"]:
            if "error" in f:
                out.append(f"| {f['file']} | （{f['error']}） | - | - |")
            else:
                out.append(f"| {f['file']} | {f['dest']} | {f['steps']} "
                           f"| {f['templates']} |")
        out.append("")
        if r["draft"]:
            d = r["draft"]
            out.append(f"- 步驟草稿：{d['steps']} 步、{d['templates']} 個範本解進"
                       f"工作區（對應流程：{d['flow'] or '（新流程）'}）")
        if r["downgraded"]:
            out.append(f"- **降為單張的範本**（原本是多截圖，取登錄基準張）"
                       f"共 {len(r['downgraded'])} 個：")
            out.append("  " + "、".join(f"`{n}`" for n in
                                       sorted(r["downgraded"])))
        if r["renamed"]:
            out.append(f"- **被改名的範本**（名稱拉平／撞名加序號）"
                       f"共 {len(r['renamed'])} 個：")
            for old, new in sorted(r["renamed"].items()):
                out.append(f"  - `{old}` → `{new}`")
        if r["orphans"]:
            out.append(f"- **沒有被任何流程引用而消失的範本**"
                       f"共 {len(r['orphans'])} 個：")
            out.append("  " + "、".join(f"`{n}`" for n in r["orphans"]))
        if r["missing"]:
            out.append("- **被引用卻在範本庫裡找不到的範本**：")
            for fn, names in sorted(r["missing"].items()):
                out.append(f"  - {fn}: " + "、".join(f"`{n}`" for n in names))
        if r["calibration"]:
            c = r["calibration"]
            out.append(f"- 校準：校準對 `{c['pair'][0]}` × `{c['pair'][1]}`、"
                       f"基準距離 {c['baseline']}、倍率 {c['scale']}；"
                       f"自存圖 {len(c['images_found'])}/2 張")
        if r["removed"]:
            out.append("- 已刪除的舊目錄：" +
                       "、".join(f"`{n}/`" for n in r["removed"]))
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("profiles_root")
    ap.add_argument("--library", default=None,
                    help="範本庫位置的覆寫 (預設 <profile>/templates)")
    ap.add_argument("--backup", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.profiles_root).resolve()
    profiles = profile_dirs(root)
    if not profiles:
        print(f"找不到任何 profile: {root}")
        return 1

    backup_note = None
    if args.backup and not args.dry_run:
        dest = Path(args.backup).resolve()
        if dest.exists():
            print(f"備份目的地已存在，請換一個: {dest}")
            return 1
        shutil.copytree(root, dest)
        backup_note = str(dest)
        print(f"已備份 {root} → {dest}")

    reports = [convert_profile(p, Path(args.library) if args.library
                               else p / "templates", dry_run=args.dry_run)
               for p in profiles]
    text = format_report(reports)
    if backup_note:
        text = text.replace("", "", 1)
        text += f"\n## 備份\n\n轉換前的完整備份：`{backup_note}`\n"
    print(text)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
        print(f"報告已寫入 {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

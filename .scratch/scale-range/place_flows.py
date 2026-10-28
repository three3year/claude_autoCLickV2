from __future__ import annotations

import os
import shutil

import srcommon as sr
from srcommon import bp

import flowfile  # noqa: E402


def main():
    if bp.autoclick_running():
        raise SystemExit("AutoClick 正在執行: 請先關掉")
    if not os.path.isdir(sr.BACKUP):
        raise SystemExit(f"還沒備份: {sr.BACKUP}")
    for name in ("早_繁中", "晚_繁中", "早_簡中", "晚_簡中"):
        src = bp.flow_path(name, sr.CONVERTED)
        dst = bp.flow_path(name, sr.FLOWS)
        r = flowfile.read(src)
        shutil.copyfile(src, dst)
        print(f"放回 {name}: {len(r['data']['steps'])} 步、{len(r['images'])} 張範本")
    synced = [n for n in ("早_繁中", "晚_繁中", "早_簡中", "晚_簡中")
              if bp.sync_draft(bp.flow_path(n, sr.FLOWS))]
    print("草稿同步:", synced or "草稿不屬於這四份, 不動")


if __name__ == "__main__":
    main()

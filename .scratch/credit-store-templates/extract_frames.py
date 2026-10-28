import json
import os
import shutil

import cv2

from build import HERE, SRC, write


def main():
    with open(os.path.join(HERE, "annotations.json"), encoding="utf-8") as f:
        ann = json.load(f)
    out = os.path.join(HERE, "frames")
    os.makedirs(out, exist_ok=True)
    caps = {}
    try:
        for fr in ann["frames"]:
            src, dst = fr["source"], os.path.join(out, fr["id"] + ".png")
            if "pic" in src:
                shutil.copyfile(os.path.join(SRC, src["pic"] + ".png"), dst)
                continue
            cap = caps.get(src["video"])
            if cap is None:
                cap = caps[src["video"]] = cv2.VideoCapture(
                    os.path.join(SRC, src["video"] + ".mp4"))
            cap.set(cv2.CAP_PROP_POS_FRAMES, src["frame"])
            ok, img = cap.read()
            if not ok:
                raise SystemExit(f"讀不到 {src['video']} 第 {src['frame']} 幀")
            write(dst, img)
            print(fr["id"], img.shape[1], "x", img.shape[0])
    finally:
        for cap in caps.values():
            cap.release()


if __name__ == "__main__":
    main()

import json
import os

import cv2
import numpy as np

from build import GRID, HERE, read

RADIUS = {"tw": (62, 82), "cn": (54, 72)}
COLS = 5


def main():
    path = os.path.join(HERE, "annotations.json")
    with open(path, encoding="utf-8") as f:
        ann = json.load(f)
    for fr in ann["frames"]:
        img = read(os.path.join(HERE, "frames", fr["id"] + ".png"))
        g = cv2.medianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 5)
        rmin, rmax = RADIUS[fr["set"]]
        cs = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, dp=1, minDist=rmin * 2,
                              param1=100, param2=40, minRadius=rmin, maxRadius=rmax)
        cs = [] if cs is None else cs[0].tolist()
        # 只留未售完卡上的圓 (售完卡的斜帶讓偵測不可靠)
        px, py = GRID[fr["set"]]
        good = []
        for x, y, _r in cs:
            col, row = int(x // px), int(y > 0.56 * img.shape[0])
            if col < COLS and not fr["cards"][row * COLS + col]["soldOut"]:
                good.append((x, y, col, row))
        bx = float(np.mean([x - px * col for x, _y, col, _row in good]))
        by = float(np.mean([y - py * row for _x, y, _col, row in good]))
        for i, card in enumerate(fr["cards"]):
            col, row = i % COLS, i // COLS
            card["center"] = [round(bx + px * col, 1), round(by + py * row, 1)]
        resid = max(max(abs(x - (bx + px * col)), abs(y - (by + py * row)))
                    for x, y, col, row in good)
        print(f"{fr['id']}: 欄距 {px:.1f} 列距 {py:.1f} 原點 {bx:.1f},{by:.1f} "
              f"用 {len(good)} 個圓, 最大殘差 {resid:.1f}px")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ann, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

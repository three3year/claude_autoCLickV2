"""量驗證影格上每張卡的圓圈中心, 寫回 annotations.json 的 center.

卡片是 2 列 × 5 欄的等距格子, 格距是同一客戶端的固定值 (build.GRID): 以霍夫圓
偵測未售完卡的圓圈, 擬合格子原點 (售完卡的斜帶會讓偵測漏掉或偏掉, 由格子補上)。
量完要跑 build.py --overlays 疊框目視核對。

    .venv/Scripts/python.exe .scratch/credit-store-templates/measure_centers.py
"""
import json
import os

import cv2
import numpy as np

from build import GRID, HERE, read

RADIUS = {"tw": (62, 82), "cn": (54, 72)}   # 霍夫圓的半徑範圍 (px)
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
        # 圓分到格子: 第一欄的圓心 x 都小於一個格距, 上下列以畫面高度 56% 分開;
        # 只留未售完卡上的圓 (售完卡的斜帶讓偵測不可靠)
        px, py = GRID[fr["set"]]
        good = []
        for x, y, _r in cs:
            col, row = int(x // px), int(y > 0.56 * img.shape[0])
            if col < COLS and not fr["cards"][row * COLS + col]["soldOut"]:
                good.append((x, y, col, row))
        # 以未售完卡的圓擬合原點 (售完多的畫面圓太少, 連格距一起擬合會發散)
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

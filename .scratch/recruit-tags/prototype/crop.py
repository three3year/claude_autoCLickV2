"""找五個標籤按鈕的精確邊界 (深色底框) 與文字邊界, 輸出兩組裁切."""
import json, sys, cv2, numpy as np
SP = sys.argv[1]
im = cv2.imread(SP + "/images/1.png")
gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
rough = {"guard": (563,432,720,487), "novice": (744,432,900,487),
         "cost": (925,432,1082,487), "dps": (563,512,720,566),
         "surv": (744,512,900,566)}
out = {}
for name, (x1,y1,x2,y2) in rough.items():
    pad = 12
    sub = gray[y1-pad:y2+pad, x1-pad:x2+pad]
    dark = sub < 90                      # 深色底
    rows = np.where(dark.mean(1) > 0.5)[0]; cols = np.where(dark.mean(0) > 0.5)[0]
    bx1, by1 = x1-pad+cols[0], y1-pad+rows[0]
    bx2, by2 = x1-pad+cols[-1]+1, y1-pad+rows[-1]+1
    btn = gray[by1:by2, bx1:bx2]
    white = btn > 160
    r = np.where(white.any(1))[0]; c = np.where(white.any(0))[0]
    tx1, ty1 = bx1+c[0]-2, by1+r[0]-2; tx2, ty2 = bx1+c[-1]+3, by1+r[-1]+3
    out[name] = {"button": [int(bx1),int(by1),int(bx2),int(by2)],
                 "text": [int(tx1),int(ty1),int(tx2),int(ty2)]}
    cv2.imwrite(f"{SP}/scratchpad/recruit_tags/btn_{name}.png", im[by1:by2, bx1:bx2])
    cv2.imwrite(f"{SP}/scratchpad/recruit_tags/txt_{name}.png", im[ty1:ty2, tx1:tx2])
    print(name, out[name], "button size", bx2-bx1, by2-by1, "text size", tx2-tx1, ty2-ty1)
json.dump(out, open(SP + "/scratchpad/recruit_tags/crops.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

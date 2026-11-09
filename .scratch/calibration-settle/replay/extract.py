"""依序讀影片 (變動幀率, 不跳轉), 每 stride 格存一張到 tmp/frames/<影片>/f#####.png。

用法: python extract.py <影片名不含 .mp4> <stride> [最後一格]
"""
import os, sys, shutil, tempfile
import cv2

VIDEO_DIR = r"C:\Users\three\我的電腦\oCam Video"
HERE = os.path.dirname(os.path.abspath(__file__))

name, stride = sys.argv[1], int(sys.argv[2])
last = int(sys.argv[3]) if len(sys.argv) > 3 else None
out = os.path.join(HERE, "tmp", "frames", name)
os.makedirs(out, exist_ok=True)
src = os.path.join(VIDEO_DIR, name + ".mp4")
cap = cv2.VideoCapture(src)
tmpcopy = None
if not cap.isOpened():
    tmpcopy = os.path.join(tempfile.gettempdir(), "replay_" + name + ".mp4")
    shutil.copyfile(src, tmpcopy)
    cap = cv2.VideoCapture(tmpcopy)
assert cap.isOpened(), src
n = saved = 0
while cap.grab():
    if last is not None and n > last:
        break
    if n % stride == 0:
        ok, img = cap.retrieve()
        if ok:
            cv2.imencode(".png", img)[1].tofile(os.path.join(out, f"f{n:05d}.png"))
            saved += 1
    n += 1
cap.release()
if tmpcopy:
    os.remove(tmpcopy)
print(name, "frames read", n, "saved", saved)

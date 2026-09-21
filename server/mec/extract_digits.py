#!/usr/bin/env python3
# extract_digits.py
import os, json, cv2
from tqdm import tqdm
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--video", required=True)
ap.add_argument("--rois", required=True)
ap.add_argument("--out", default="digit_crops/raw")
ap.add_argument("--frame_step", type=int, default=2, help="Skip frames to reduce redundancy")
args = ap.parse_args()

os.makedirs(args.out, exist_ok=True)
with open(args.rois, "r") as f:
    rois = json.load(f).get("rois", [])
if not rois:
    raise RuntimeError("No ROIs in rois JSON")

cap = cv2.VideoCapture(args.video)
frame_idx = 0
saved = 0
pbar = tqdm(total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
while True:
    ret, frame = cap.read()
    if not ret:
        break
    if frame_idx % args.frame_step == 0:
        for roi_idx, r in enumerate(rois[:18]):
            x,y,w,h = map(int, r)
            crop = frame[y:y+h, x:x+w]
            if crop.size == 0:
                continue
            # split into 4 equal columns (digits)
            dw = w // 4
            for d in range(4):
                x0 = d*dw
                x1 = (d+1)*dw if d<3 else w
                d_crop = crop[:, x0:x1]
                fname = os.path.join(args.out, f"{frame_idx:06d}_{roi_idx:02d}_{d}.png")
                cv2.imwrite(fname, d_crop)
                saved += 1
    frame_idx += 1
    pbar.update(1)
pbar.close()
cap.release()
print(f"Saved {saved} crops to {args.out}")

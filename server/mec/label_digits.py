#!/usr/bin/env python3
# label_digits.py
import cv2, os, argparse, glob, shutil
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--crops_dir", default="digit_crops/raw")
ap.add_argument("--out_dir", default="digit_crops/labeled")
args = ap.parse_args()

os.makedirs(args.out_dir, exist_ok=True)
img_list = sorted(glob.glob(os.path.join(args.crops_dir, "*.png")))
i = 0
print("Keys: 0-9 = label, s = skip and save to 'skip', q = quit")
while i < len(img_list):
    p = img_list[i]
    img = cv2.imread(p)
    if img is None:
        i += 1
        continue
    disp = cv2.resize(img, (img.shape[1]*2, img.shape[0]*2))
    cv2.imshow("label", disp)
    key = cv2.waitKey(0) & 0xFF
    if key == ord('q'):
        break
    if key == ord('s'):
        dst = os.path.join(args.out_dir, "skip")
        os.makedirs(dst, exist_ok=True)
        shutil.copy(p, dst)
        i += 1
        continue
    if 48 <= key <= 57:
        lbl = chr(key)
        dst = os.path.join(args.out_dir, lbl)
        os.makedirs(dst, exist_ok=True)
        shutil.copy(p, dst)
        i += 1
        continue
    # any other key: skip
    i += 1

cv2.destroyAllWindows()
print("Labeling finished.")

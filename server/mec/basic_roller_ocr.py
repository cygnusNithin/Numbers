#!/usr/bin/env python3
import argparse, json, cv2, time
from datetime import datetime
import pandas as pd
from digit_reader import read_roller_number   # <-- using CNN model

# Draw helper
def draw_rects(img, rois, nums=None):
    out = img.copy()
    for i,(x,y,w,h) in enumerate(rois):
        cv2.rectangle(out,(x,y),(x+w,y+h),(0,255,0),2)
        if nums and i < len(nums):
            cv2.putText(out, nums[i], (x, y-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,(0,255,0),2)
    return out

# OCR all ROIs
def ocr_all(frame, rois):
    nums = []
    for x,y,w,h in rois:
        crop = frame[y:y+h, x:x+w]
        nums.append(read_roller_number(crop))
    return nums

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--rois", required=True)
    ap.add_argument("--out", default="mapping.csv")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--prize_csv", required=True)
    args = ap.parse_args()

    # Load ROIs
    with open(args.rois,"r") as f:
        rois = json.load(f)["rois"]

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print("❌ Cannot open video")
        return

    paused = False
    last_frame = None
    print("\n🎥 Controls: SPACE=Pause/Resume | C=Capture | Q=Quit\n")

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                print("🔚 End of video.")
                break
            last_frame = frame.copy()

        # show preview with NO OCR until paused
        disp = draw_rects(last_frame, rois)
        cv2.imshow("🎯 Roller OCR Test", disp)

        key = cv2.waitKey(30) & 0xFF

        if key == ord(' '):
            paused = not paused
            print("⏸️ PAUSED" if paused else "▶ PLAYING")

        elif key == ord('c') and paused:
            nums = ocr_all(last_frame, rois)
            print("\n📌 CAPTURED:", nums)

            row = {"date": args.date}
            for i, n in enumerate(nums):
                row[f"rollerset{i+1}"] = n
            pd.DataFrame([row]).to_csv(args.out, index=False)
            print(f"💾 Saved → {args.out}\n")

        elif key == ord('q'):
            print("👋 Exit.")
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

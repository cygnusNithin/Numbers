#!/usr/bin/env python3
"""
Live Roller Pickup + CNN OCR (Stable Freeze Detection)
"""

import argparse, json, time, cv2, pandas as pd, numpy as np
from datetime import datetime
from digit_reader import read_roller_number


# ==== DRAW ROIS + TEXT ====
def draw_rects(img, rois, texts=None):
    out = img.copy()
    for i,(x,y,w,h) in enumerate(rois):
        cv2.rectangle(out,(x,y),(x+w,y+h),(0,255,0),2)
        if texts:
            cv2.putText(out, texts[i], (x,y-5),
                        cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,255,0),2)
    return out

# ==== PROCESS VIDEO ====
def process_video(video_path, roi_json, prize_csv, out_csv, date, start_mode, delay):

    # Load ROI boxes
    with open(roi_json,"r") as f:
        rois = json.load(f)["rois"]

    # Open video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("❌ Cannot open video.")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    print(f"\nVideo opened: FPS={fps:.1f}, total frames={int(total)}\n")

    # OPTION: Skip seconds
    if start_mode in (1,3):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps*delay))
        print(f"⏳ Skipped {delay} seconds")

    # OPTIONAL: WAIT until user sees rollers
    if start_mode in (2,3):
        print("\n▶ Preview started. Press ENTER (in console) when rollers are clearly visible & aligned.")
        print("   While previewing, you can also press 'q' in the preview window to abort.\n")

        while True:
            ret, f = cap.read()
            if not ret: break
            cv2.imshow("Preview - Press ENTER in console", f)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                cv2.destroyAllWindows(); return
            try:
                if input() == "":
                    break
            except:
                break
        cv2.destroyAllWindows()

    print("\n🔍 Waiting for freeze (rollers must stop)...")

    last_gray = None
    stable = 0
    NEED_STABLE = 6
    captured = []

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Video ended.")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if last_gray is not None:
            diff = np.mean(cv2.absdiff(gray, last_gray))
            stable = stable + 1 if diff < 4.0 else 0
        last_gray = gray

        # ALWAYS Preview Live + Text
        texts = []
        for (x,y,w,h) in rois:
            crop = frame[y:y+h, x:x+w]
            number = read_roller_number(crop)
            texts.append(number)

        view = draw_rects(frame, rois, texts)
        cv2.imshow("📌 Live Roller OCR (CNN)", view)

        if stable >= NEED_STABLE:
            captured = texts
            print("\n💾 Captured numbers:", captured)
            time.sleep(1)
            break

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("❌ Aborted.")
            break

    cap.release()
    cv2.destroyAllWindows()

    # SAVE CSV
    if captured:
        row = {"date": date}
        for i,n in enumerate(captured):
            row[f"rollerset{i+1}"] = n
        pd.DataFrame([row]).to_csv(out_csv,index=False)
        print(f"📁 Saved → {out_csv}\n")


# ==== MAIN ====
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--rois", required=True)
    ap.add_argument("--prize_csv", required=True)
    ap.add_argument("--out", default="mapping.csv")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--start_mode", type=int, default=1,
                    help="1=delay skip, 2=keypress wait, 3=both")
    ap.add_argument("--delay", type=float, default=2.0)
    args = ap.parse_args()

    process_video(args.video, args.rois, args.prize_csv,
                  args.out, args.date,
                  args.start_mode, args.delay)

if __name__ == "__main__":
    main()

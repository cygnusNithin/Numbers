# video_debug_ocr.py
"""
Interactive video OCR using the trained digit CNN.

Controls (preview window):
 - SPACE : OCR current frame (capture and save mapping CSV)
 - p     : play/pause
 - ← / → : step backward / forward one frame (when paused)
 - s     : save current ROI crops to folder 'debug_crops' (for labeling/debug)
 - q     : quit

Run:
 python video_debug_ocr.py --video /mnt/data/sample_video.mp4 --rois rois.json --model digit_model.h5 --out mapping.csv --model_img_size 40
"""
import argparse, json, os, time
from datetime import datetime
import cv2
import numpy as np
import pandas as pd
from digit_reader import load_digit_model, read_roller_number

def load_rois(rois_path):
    with open(rois_path, "r") as f:
        js = json.load(f)
    rois = js.get("rois", [])
    # normalize tuples
    rois_norm = []
    for r in rois:
        if isinstance(r, list) and len(r) >= 4:
            rois_norm.append(tuple(map(int, r[:4])))
    return rois_norm

def draw_overlay(frame, rois, texts=None):
    out = frame.copy()
    for i, (x,y,w,h) in enumerate(rois):
        cv2.rectangle(out, (x,y),(x+w,y+h),(0,255,0),2)
        label = str(i+1)
        if texts and i < len(texts):
            label = f"{i+1}:{texts[i]}"
        cv2.putText(out, label, (x, y-6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
    return out

def save_crops(frame, rois, folder="debug_crops"):
    os.makedirs(folder, exist_ok=True)
    for i,(x,y,w,h) in enumerate(rois):
        crop = frame[y:y+h, x:x+w]
        fn = os.path.join(folder, f"crop_{i+1:02d}_{int(time.time())}.png")
        cv2.imwrite(fn, crop)
    print(f"Saved {len(rois)} crops to {folder}")

def ocr_frame(frame, rois, model, model_img_size):
    texts = []
    confs = []
    for (x,y,w,h) in rois:
        crop = frame[y:y+h, x:x+w]
        txt, conf = None, None
        try:
            txt, conf = read_roller_number(crop, model_tuple=(model, model_img_size), model_input_size=model_img_size, return_conf=True)
        except TypeError:
            # read_roller_number may not accept return_conf depending on version; fallback
            txt = read_roller_number(crop, model_tuple=(model, model_img_size), model_input_size=model_img_size)
            conf = [None]*4
        texts.append(txt)
        confs.append(conf)
    return texts, confs

def run(video_path, rois_path, model_path, out_csv, date_str, model_img_size=40):
    rois = load_rois(rois_path)
    if not rois:
        raise RuntimeError("No ROIs loaded. Run pick_rois first.")

    model, _ = load_digit_model(model_path, model_img_size)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Cannot open video: " + video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    print(f"Loaded model: {model_path}")
    print(f"Video opened: FPS={fps}, total frames={total}")
    paused = False
    frame_idx = 0

    # Start preview loop
    saved_once = False
    texts = [""]*len(rois)
    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                print("End of video.")
                break
            frame_idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        # draw overlay
        view = draw_overlay(frame, rois, texts)
        cv2.putText(view, f"Frame: {frame_idx}/{total}  (space=OCR, p=play/pause, s=save crops, q=quit)", (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)
        cv2.imshow("Roller OCR Debug", view)
        key = cv2.waitKey(0 if paused else int(1000/fps)) & 0xFF

        if key == ord('q'):
            print("Quit.")
            break
        if key == ord('p'):
            paused = not paused
            print("Paused." if paused else "Playing.")
            continue
        if key == 81 or key == ord('a'):  # left arrow or 'a'
            # step back one frame
            new_pos = max(0, frame_idx-2)
            cap.set(cv2.CAP_PROP_POS_FRAMES, new_pos)
            paused = True
            continue
        if key == 83 or key == ord('d'):  # right arrow or 'd'
            # step forward one frame (when paused)
            paused = True
            ret, frame = cap.read()
            continue
        if key == ord(' '):  # SPACE -> run OCR for current frame and save mapping row
            print("Running OCR on current frame...")
            texts, confs = ocr_frame(frame, rois, model, model_img_size)
            print("CAPTURED:", texts)
            # Save mapping single-row CSV
            row = {"date": date_str}
            for i, t in enumerate(texts):
                row[f"rollerset{i+1}"] = t
            pd.DataFrame([row]).to_csv(out_csv, index=False)
            print(f"Saved → {out_csv}")
            saved_once = True
            # continue playing or remain paused as before
            continue
        if key == ord('s'):
            save_crops(frame, rois)
            continue
        # otherwise loop

    cap.release()
    cv2.destroyAllWindows()
    if not saved_once:
        print("No mapping saved (press SPACE during preview to OCR/save).")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--rois", required=True)
    ap.add_argument("--model", required=True, help="path to digit_model.h5")
    ap.add_argument("--out", default="mapping.csv")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--model_img_size", type=int, default=40)
    args = ap.parse_args()

    run(args.video, args.rois, args.model, args.out, args.date, args.model_img_size)

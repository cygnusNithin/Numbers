#!/usr/bin/env python3
"""
rollerset_capture_and_map.py

1) Run once to create ROI config for the 18 roller windows (interactive).
   python rollerset_capture_and_map.py --mode pick_rois --video sample_video.mp4 --out rois.json

2) Run to process a video and map roller-sets to prize numbers for a given draw date and prize lists:
   python rollerset_capture_and_map.py --mode process --video sample_video.mp4 --rois rois.json --date 2025-11-14 --out mapping_2025-11-14.csv

Dependencies:
 - OpenCV (cv2)
 - pytesseract (Tesseract must be installed separately on system)
 - numpy, pandas
 - tqdm (optional)
Install examples:
 pip install opencv-python pytesseract numpy pandas tqdm

On Windows you must install Tesseract OCR and set pytesseract.pytesseract.tesseract_cmd path.

Notes:
 - ROI picking: click and drag a rectangle for each roller in order 1..18 on a reference frame.
 - The script detects stable frames (low difference between consecutive frames).
 - OCR uses config '--psm 7 -c tessedit_char_whitelist=0123456789' to focus on digits.
"""

import argparse, json, time, os
from collections import defaultdict, Counter
from datetime import datetime
import cv2
import numpy as np
import pytesseract
import pandas as pd
from tqdm import tqdm

# If needed, set explicit tesseract path:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ---------------------------
# Helper utilities
# ---------------------------
def draw_rects_on_img(img, rois):
    out = img.copy()
    for i, r in enumerate(rois):
        x,y,w,h = r
        cv2.rectangle(out, (x,y), (x+w,y+h), (0,255,0), 2)
        cv2.putText(out, str(i+1), (x+2,y+18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
    return out

def preprocess_crop_for_ocr(crop):
    # Convert to gray, resize, adaptive threshold
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    # upscale to improve OCR
    h, w = g.shape
    scale = max(1, int(160.0 / max(h,w)))
    if scale > 1:
        g = cv2.resize(g, (w*scale, h*scale), interpolation=cv2.INTER_CUBIC)
    # Blur then adaptive threshold
    g = cv2.GaussianBlur(g, (3,3), 0)
    th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY_INV, 15, 8)
    # morphological close to join digit strokes
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=1)
    # invert back for tesseract (tesseract expects black text on white bg normally)
    th_inv = cv2.bitwise_not(th)
    return th_inv

def ocr_digits_from_crop(crop):
    img_for_ocr = preprocess_crop_for_ocr(crop)
    # config: single line, digits only
    conf = "--psm 7 -c tessedit_char_whitelist=0123456789"
    txt = pytesseract.image_to_string(img_for_ocr, config=conf)
    txt = txt.strip()
    # keep only digits
    digits = "".join(ch for ch in txt if ch.isdigit())
    # If OCR yields >4 digits, try to pick best 4 (e.g., center substring) or first 4
    if len(digits) > 4:
        # try heuristics: longest group of 4 contiguous digits
        import re
        m = re.findall(r"\d{4}", digits)
        if m:
            digits = m[0]
        else:
            digits = digits[:4]
    # return digits and rudimentary confidence measure (length-based)
    conf_score = len(digits) / 4.0
    return digits.zfill(4) if digits else "", conf_score

# ---------------------------
# Interactive ROI picker
# ---------------------------
def pick_rois_interactive(video_path, out_json, n_rois=18):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Cannot open video: " + video_path)
    # grab a nice reference frame near start
    cap.set(cv2.CAP_PROP_POS_FRAMES, min(60, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)-1)))
    ret, frame = cap.read()
    if not ret:
        cap.release()
        raise RuntimeError("Cannot read reference frame from video.")
    rois = []
    clone = frame.copy()
    cur = {"ix":-1,"iy":-1,"drawing":False,"start":None,"rects":rois}
    win = "Pick ROIs - draw rectangle for each rollerset in order 1..18 - press 'n' when finished"
    cv2.namedWindow(win)
    def mouse_cb(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            cur["drawing"] = True
            cur["start"] = (x,y)
        elif event == cv2.EVENT_MOUSEMOVE and cur["drawing"]:
            img = clone.copy()
            sx,sy = cur["start"]
            cv2.rectangle(img, (sx,sy), (x,y), (0,255,0), 2)
            # draw already picked
            img = draw_rects_on_img(img, rois)
            cv2.imshow(win, img)
        elif event == cv2.EVENT_LBUTTONUP:
            cur["drawing"] = False
            sx,sy = cur["start"]
            x1,y1 = min(x,sx), min(y,sy)
            w,h = abs(x-sx), abs(y-sy)
            # enforce minimum
            if w < 10 or h < 10:
                return
            rois.append((x1,y1,w,h))
            img = draw_rects_on_img(clone, rois)
            cv2.imshow(win, img)
    cv2.setMouseCallback(win, mouse_cb)
    print("Draw rectangles. Press 'n' to finish, 'r' to reset, 's' to save current and exit.")
    while True:
        img = draw_rects_on_img(clone, rois)
        cv2.imshow(win, img)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('n') or key == ord('s'):
            break
        if key == ord('r'):
            rois.clear()
            print("Reset ROIs.")
        if key == 27:
            break
    cv2.destroyWindow(win)
    cap.release()
    if len(rois) < n_rois:
        print(f"Warning: only {len(rois)} ROIs picked (expected {n_rois}). You can still proceed.")
    # save json
    with open(out_json, "w") as f:
        json.dump({"rois": rois}, f, indent=2)
    print("Saved ROIs to", out_json)
    return rois

# ---------------------------
# Stable frame detection & capture
# ---------------------------
def find_stable_frames(video_path, diff_threshold=50, stable_frame_count=3, max_frames=None):
    """
    Return indices of frames that are 'stable' (small difference to previous frames).
    diff_threshold: threshold of mean absolute diff to consider movement low
    stable_frame_count: require this many consecutive low-diff frames to declare a stable period
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Cannot open video: " + video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    last_gray = None
    stable_idxs = []
    consec = 0
    frame_no = 0
    print("Scanning video for stable frames (this can be fast)...")
    pbar = tqdm(total=total if max_frames is None else max_frames)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if last_gray is None:
            last_gray = gray
            frame_no += 1
            pbar.update(1)
            if max_frames and frame_no >= max_frames:
                break
            continue
        diff = cv2.absdiff(gray, last_gray)
        mean_diff = float(np.mean(diff))
        if mean_diff < diff_threshold:
            consec += 1
        else:
            consec = 0
        if consec >= stable_frame_count:
            stable_frame_idx = frame_no
            stable_idxs.append(stable_frame_idx)
            # skip ahead to avoid many duplicates of same stable period
            # advance by stable_frame_count*5 frames
            skip = stable_frame_count * 5
            for _ in range(skip):
                ret2, _ = cap.read()
                if not ret2:
                    break
                frame_no += 1
            last_gray = None
            consec = 0
            pbar.update(skip+1)
            continue
        last_gray = gray
        frame_no += 1
        pbar.update(1)
        if max_frames and frame_no >= max_frames:
            break
    pbar.close()
    cap.release()
    return stable_idxs

# ---------------------------
# Process video and map roller outputs to prize lists
# ---------------------------
def process_video_and_map(video_path, rois_json, out_csv, prize_lists_by_section, draw_date_str):
    """
    prize_lists_by_section: dict e.g.
      {5000: [...list of strings 4-digit...], 2000: [...], 1000: [...], 500: [...], ...}
    The function will:
     - detect stable frames
     - for each stable frame, extract 18 rollers digits
     - group stable frames into rounds and assemble revealed numbers in order
     - attempt to map revealed numbers to prize lists (for the prize sections present)
     - write mapping CSV with columns: date, rollerset1..rollerset18 (final confirmed)
    """
    with open(rois_json, "r") as f:
        roiconf = json.load(f)
    rois = roiconf.get("rois", [])
    if len(rois) < 18:
        print("Warning: fewer than 18 ROIs. Proceeding but results may be wrong.")
    # find stable frames
    stable_frames = find_stable_frames(video_path, diff_threshold=30, stable_frame_count=3, max_frames=None)
    if not stable_frames:
        print("No stable frames found. Try lowering diff_threshold or increasing stable_frame_count.")
        return
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # collect extracted numbers per stable frame (list of lists)
    frames_data = []
    print("Extracting digits from stable frames...")
    for idx in stable_frames:
        if idx >= total_frames:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, idx-1))
        ret, frame = cap.read()
        if not ret:
            continue
        # For each ROI, crop and OCR
        frame_numbers = []
        frame_conf = []
        for r in rois[:18]:
            x,y,w,h = map(int, r)
            crop = frame[y:y+h, x:x+w]
            digits, conf = ocr_digits_from_crop(crop)
            frame_numbers.append(digits)
            frame_conf.append(conf)
        frames_data.append({"frame_idx": idx, "numbers": frame_numbers, "conf": frame_conf})
    cap.release()

    # Now group frames into rounds: we'll treat each stable frame as one reveal snapshot.
    # Build reveal order: sequential frames_data correspond to reveal order (round1, round2,...)
    revealed_numbers_seq = []  # flattened sequence in reveal order (rollerset-wise)
    # For each frame snapshot, append numbers for roller positions in ROI order (1..n)
    for snap in frames_data:
        nums = snap["numbers"]
        # keep as list of 18 (if missing, pad "")
        nums_padded = [(n if n else "") for n in nums]
        revealed_numbers_seq.append(nums_padded)

    # Flatten into per-round order: Round1 = revealed_numbers_seq[0], Round2=revealed_numbers_seq[1], ...
    # The actual visible order of numbers within a round is the ROI order
    # Build candidate sequence per prize section by concatenating rounds until we have at least needed count
    mapping_result = {}  # final mapping rollerset_id (1..18) -> confirmed number
    details = []

    # Build combined list of revealed numbers in reveal-order (each round adds up to 18 numbers)
    flat_reveals = []
    for r_idx, roundnums in enumerate(revealed_numbers_seq):
        # each round is a list of up to 18 numbers in ROI order
        for pos, num in enumerate(roundnums):
            flat_reveals.append({"round": r_idx+1, "pos": pos+1, "number": num})

    # We will now iterate through prize sections in their observed order and pick numbers from flat_reveals sequentially, performing duplicate replacement logic
    # Determine prize order and counts
    prize_order = sorted(prize_lists_by_section.keys(), key=lambda x: -1)  # we'll use the order passed; user should pass in desired order
    # But better: accept the sequence as they usually occur: 5000 → 2000 → 1000 → 500 → 200 → 100
    observed_order = [5000,2000,1000,500,200,100]
    prize_order = [p for p in observed_order if p in prize_lists_by_section]

    # flat pointer
    ptr = 0
    total_flat = len(flat_reveals)
    print(f"Total revealed cells captured: {total_flat} (rounds: {len(revealed_numbers_seq)})")
    # For each prize section:
    final_confirmed = {}  # prize->list of confirmed numbers in reveal order
    used_numbers=set()
    for prize in prize_order:
        needed = len(prize_lists_by_section[prize])
        confirmed = []
        # pull numbers sequentially from flat_reveals until we have 'needed' unique numbers (respect reveal order)
        attempts = 0
        while len(confirmed) < needed and ptr < total_flat and attempts < total_flat:
            candidate = flat_reveals[ptr]["number"]
            ptr += 1
            attempts += 1
            if not candidate or candidate == "":  # skip empty OCR misses
                continue
            if candidate in confirmed:
                # duplicate within same prize → will be later replaced by subsequent reveals; skip
                continue
            # If candidate is in the prize list for this prize (the DB list), accept
            if candidate in prize_lists_by_section[prize] and candidate not in confirmed:
                confirmed.append(candidate)
                used_numbers.add(candidate)
            else:
                # Candidate may be in other prize sections; sometimes earlier rounds show numbers not for this prize (rare).
                # Add to confirmed only if we still need numbers and candidate not yet used anywhere (best-effort)
                if candidate not in used_numbers:
                    confirmed.append(candidate)
                    used_numbers.add(candidate)
        # if still fewer than needed, attempt to fill by searching remaining flat_reveals (this handles replacement logic)
        if len(confirmed) < needed:
            for i in range(ptr, total_flat):
                candidate = flat_reveals[i]["number"]
                if not candidate: continue
                if candidate in prize_lists_by_section[prize] and candidate not in confirmed:
                    confirmed.append(candidate)
                    used_numbers.add(candidate)
                if len(confirmed) >= needed:
                    break
        # if still missing, fill with placeholders
        while len(confirmed) < needed:
            confirmed.append("")  # unknown
        final_confirmed[prize] = confirmed[:needed]

    # Now we have confirmed lists per prize. The main objective: map rollerset (1..18) to the numbers they produced (from round1 primarily).
    # We'll build mapping from ROI position (1..18) using first-round numbers where OCR succeeded, but if first-round had duplicates replaced later,
    # we will use the replacement number from later round that matches prize_list.
    # Build mapping by scanning rounds per ROI:
    roi_to_final_number = [""]*18
    # First pass: try to map using round1 (frames_data[0]) where that number appears in any prize_list
    if len(revealed_numbers_seq) > 0:
        round1 = revealed_numbers_seq[0]
        for i, num in enumerate(round1[:18]):
            # find which prize list contains this number (if any)
            found_prize = None
            for pr, plist in prize_lists_by_section.items():
                if num in plist:
                    found_prize = pr
                    break
            if found_prize:
                roi_to_final_number[i] = num

    # second pass: for any ROI with empty mapping, look through subsequent rounds to find a matching number that belongs to some prize_list and isn't already assigned
    assigned = set([n for n in roi_to_final_number if n])
    for roundnums in revealed_numbers_seq[1:]:
        for i, num in enumerate(roundnums[:18]):
            if roi_to_final_number[i]:
                continue
            if not num: continue
            # accept if the number exists in any prize_list and not already assigned
            belongs=False
            for pr, plist in prize_lists_by_section.items():
                if num in plist:
                    belongs=True; break
            if belongs and num not in assigned:
                roi_to_final_number[i] = num
                assigned.add(num)

    # as fallback, where still empty, fill with first-round OCR numbers (even if not matched)
    if len(revealed_numbers_seq) > 0:
        round1 = revealed_numbers_seq[0]
        for i in range(18):
            if not roi_to_final_number[i]:
                if i < len(round1) and round1[i]:
                    roi_to_final_number[i] = round1[i]

    # Build output CSV: a single row for the draw date with columns rollerset1...rollerset18
    out_row = {"date": draw_date_str}
    for i in range(18):
        out_row[f"rollerset{i+1}"] = roi_to_final_number[i]

    df_out = pd.DataFrame([out_row])
    df_out.to_csv(out_csv, index=False)
    print("Saved mapping CSV ->", out_csv)

    # Also save details per round for manual check
    rounds_detail = []
    for r, nums in enumerate(revealed_numbers_seq, start=1):
        row = {"round": r}
        for i, num in enumerate(nums[:18]):
            row[f"r{i+1}"] = num
        rounds_detail.append(row)
    pd.DataFrame(rounds_detail).to_csv(out_csv.replace(".csv","_rounds.csv"), index=False)
    print("Saved per-round raw OCR ->", out_csv.replace(".csv","_rounds.csv"))

    return df_out, revealed_numbers_seq

# ---------------------------
# Main CLI
# ---------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pick_rois","process"], required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--rois", help="ROI JSON file (used in process mode)")
    ap.add_argument("--out", help="output csv path", default="rollerset_mapping.csv")
    ap.add_argument("--date", help="draw date string (yyyy-mm-dd)", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--prize_csv", help="optional CSV with prize lists per section", default=None)
    ap.add_argument("--n_rois", type=int, default=18)
    args = ap.parse_args()

    if args.mode == "pick_rois":
        pick_rois_interactive(args.video, args.out, n_rois=args.n_rois)
        return

    if args.mode == "process":
        if not args.rois:
            raise RuntimeError("Process mode requires --rois file produced by pick_rois.")
        # Load prize lists: either load from prize_csv (two columns: prize,number) or ask user to edit inline
        if args.prize_csv:
            df = pd.read_csv(args.prize_csv, dtype=str)
            # Expect columns: prize, number (4-digit)
            prize_lists = {}
            for _, r in df.iterrows():
                p = int(r['prize'])
                num = str(r['number']).zfill(4)
                prize_lists.setdefault(p, []).append(num)
        else:
            # USER MUST EDIT these prize lists below to match the draw you want to confirm
            # Replace the example lists with the ones you gave for this special day.
            prize_lists = {
                5000: [
                    # put your 5000 list here, e.g. '0191','0234',...
                ],
                2000: [
                    # 2000 list here
                ],
                1000: [
                    # 1000 list here
                ],
                500: [
                    # 500 list here
                ],
                # add 200 or 100 if needed
            }
            # NOTE: For production replace this with reading a CSV or DB.
            print("No prize_csv provided: edit 'prize_lists' dict in script or pass --prize_csv")
            return

        process_video_and_map(args.video, args.rois, args.out, prize_lists, args.date)

if __name__ == "__main__":
    main()

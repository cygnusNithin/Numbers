import cv2
import numpy as np
import pandas as pd
import os
import argparse
from tqdm import tqdm
import matplotlib.pyplot as plt

# Optional OCR
try:
    import pytesseract
    PYTESSACT_AVAILABLE = True
except Exception:
    PYTESSACT_AVAILABLE = False

# -----------------------
# Utility: simple template matcher for digits 0-9
# -----------------------
def load_templates(folder):
    """
    Load templates named 0.png,1.png,...9.png (grayscale).
    Returns dict of digit -> image.
    """
    templates = {}
    for d in range(10):
        p = os.path.join(folder, f"{d}.png")
        if os.path.exists(p):
            img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                templates[str(d)] = img
    return templates

def best_match_template(img_gray, templates):
    """Return best matching digit (string) and score using cv2.matchTemplate (TM_CCOEFF_NORMED)."""
    best_digit, best_score = None, -1.0
    # resize ROI to template scale if needed? We assume similar sizes.
    for d, tpl in templates.items():
        try:
            # If template larger than image, skip
            if tpl.shape[0] > img_gray.shape[0] or tpl.shape[1] > img_gray.shape[1]:
                # try resizing template to ROI height
                scale = img_gray.shape[0] / tpl.shape[0]
                tpl_resized = cv2.resize(tpl, (int(tpl.shape[1]*scale), img_gray.shape[0]))
            else:
                tpl_resized = tpl
            res = cv2.matchTemplate(img_gray, tpl_resized, cv2.TM_CCOEFF_NORMED)
            _, maxv, _, _ = cv2.minMaxLoc(res)
            if maxv > best_score:
                best_score = maxv
                best_digit = d
        except Exception:
            continue
    return best_digit, best_score

# -----------------------
# OCR helper (slower, sometimes better)
# -----------------------
def ocr_digit(img_gray, psm=10, oem=3):
    if not PYTESSACT_AVAILABLE:
        return None, 0.0
    # Preprocess: threshold
    img = cv2.resize(img_gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_LINEAR)
    _, thr = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    config = f'--oem {oem} --psm {psm} -c tessedit_char_whitelist=0123456789'
    txt = pytesseract.image_to_string(thr, config=config)
    txt = txt.strip()
    # find first digit
    for ch in txt:
        if ch.isdigit():
            return ch, 1.0
    return None, 0.0

# -----------------------
# Main analyzer
# -----------------------
def analyze_rotation(video_path, t0, t1, roi, fps_sample=None, templates_folder=None, use_ocr=False, out_csv="wheel_results.csv"):
    """
    video_path: local file path
    t0, t1: seconds start and end
    roi: (x,y,w,h)
    fps_sample: None => use video fps; or specify integer sample fps for speed
    templates_folder: path to digit templates (optional)
    use_ocr: fallback to pytesseract if templates missing
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Cannot open video")

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total_frames / video_fps if total_frames>0 else None

    start_frame = int(max(0, round(t0 * video_fps)))
    end_frame = int(min(total_frames-1, round(t1 * video_fps))) if t1 is not None else total_frames-1

    # choose sampling interval
    if fps_sample is None:
        step = 1
    else:
        # sample at fps_sample frames per second
        step = max(1, int(round(video_fps / fps_sample)))

    # load templates
    templates = {}
    if templates_folder:
        templates = load_templates(templates_folder)

    results = []
    frame_idx = start_frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    pbar = tqdm(total=(end_frame - start_frame + 1)//step + 1, desc="Frames")
    while frame_idx <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break
        # extract ROI
        x,y,w,h = roi
        h_frame, w_frame = frame.shape[:2]
        # clip ROI
        x2 = min(x + w, w_frame)
        y2 = min(y + h, h_frame)
        x = max(0, x); y = max(0, y)
        if x >= x2 or y >= y2:
            raise ValueError("ROI outside frame")
        patch = frame[y:y2, x:x2]
        gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)

        timestamp = frame_idx / video_fps

        digit, score = None, 0.0
        # try template matching first
        if templates:
            digit, score = best_match_template(gray, templates)
        # fallback to OCR if requested or templates missing/low score
        if (not digit or score < 0.6) and use_ocr and PYTESSACT_AVAILABLE:
            digit, ocrm = ocr_digit(gray)
            if ocrm > 0:
                score = max(score, ocrm)

        results.append({"frame": frame_idx, "time_s": timestamp, "digit": digit, "score": float(score)})
        # skip frames by step
        frame_idx += step
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        pbar.update(1)
    pbar.close()
    cap.release()

    # Build DataFrame
    df = pd.DataFrame(results)
    # Clean: propagate last known digit forward for consecutive unrecognized frames to avoid overcounting noise
    df['digit_filled'] = df['digit'].ffill().bfill()  # forward/backward fill
    # detect transitions: count when digit_filled changes
    df['transition'] = df['digit_filled'] != df['digit_filled'].shift(1)
    # ignore first row transition
    df.loc[df.index[0], 'transition'] = False

    # Count digit transitions (when digit changes and new digit is not None)
    trans_events = df[(df['transition']) & (df['digit_filled'].notna())]
    transitions = len(trans_events)

    # Because there are 10 digits per roll, total rotations = transitions / 10
    rotations = transitions / 10.0

    elapsed_time = (df['time_s'].iloc[-1] - df['time_s'].iloc[0]) if len(df) > 1 else 0.0
    rps = rotations / elapsed_time if elapsed_time > 0 else np.nan
    rpm = rps * 60.0
    deg_per_sec = rps * 360.0

    # Additional: compute per-transition intervals
    trans_times = trans_events['time_s'].values
    inter_transition_intervals = np.diff(trans_times) if len(trans_times) > 1 else np.array([])
    # average time per digit-change:
    avg_digit_change_sec = inter_transition_intervals.mean() if inter_transition_intervals.size>0 else np.nan
    std_digit_change_sec = inter_transition_intervals.std() if inter_transition_intervals.size>0 else np.nan

    # Save CSV
    df.to_csv(out_csv, index=False)

    summary = {
        "video": video_path,
        "roi": roi,
        "frames_sampled": len(df),
        "transitions": transitions,
        "rotations": rotations,
        "elapsed_time_s": float(elapsed_time),
        "rps": float(rps),
        "rpm": float(rpm),
        "deg_per_sec": float(deg_per_sec),
        "avg_digit_change_s": float(avg_digit_change_sec) if not np.isnan(avg_digit_change_sec) else None,
        "std_digit_change_s": float(std_digit_change_sec) if not np.isnan(std_digit_change_sec) else None
    }
    return summary, df

# -----------------------
# CLI
# -----------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, help="path to video file")
    parser.add_argument("--start", type=float, required=True, help="start time (s)")
    parser.add_argument("--end", type=float, required=True, help="end time (s)")
    parser.add_argument("--roi", required=True, help="ROI as x,y,w,h (integers)")
    parser.add_argument("--templates", default=None, help="folder with digit templates named 0.png ... 9.png")
    parser.add_argument("--fps_sample", type=float, default=None, help="sample fps (e.g. 10)")
    parser.add_argument("--use_ocr", action="store_true", help="use pytesseract OCR fallback")
    parser.add_argument("--out", default="wheel_results.csv", help="where to save per-frame CSV")
    args = parser.parse_args()

    x,y,w,h = [int(v) for v in args.roi.split(",")]
    summary, df = analyze_rotation(args.video, args.start, args.end, (x,y,w,h),
                                   fps_sample=args.fps_sample,
                                   templates_folder=args.templates,
                                   use_ocr=args.use_ocr,
                                   out_csv=args.out)
    print("=== SUMMARY ===")
    for k,v in summary.items():
        print(f"{k}: {v}")

    # quick plot: digit timeline
    try:
        plt.figure(figsize=(10,3))
        times = df['time_s']
        # map digit_filled to numeric (None -> -1)
        digits_mapped = df['digit_filled'].fillna("-1").apply(lambda s: int(s) if str(s).isdigit() else -1)
        plt.plot(times, digits_mapped, marker='o', linestyle='-')
        plt.ylabel("digit")
        plt.xlabel("time (s)")
        plt.title("Detected digits over time")
        plt.grid(True)
        png_out = args.out.replace(".csv", "_digits.png")
        plt.savefig(png_out, dpi=150)
        print("Saved digit timeline plot to", png_out)
    except Exception as e:
        print("Plot failed:", e)

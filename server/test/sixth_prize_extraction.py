"""
sixth_prize_extraction.py - SIMPLIFIED VERSION (NO DATABASE)

Based on stable DB version but removes MongoDB dependency.
Extracts 6th prize numbers and shows raw OCR results with confidence.
"""

import csv
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np


# ============================================================
# CONFIG
# ============================================================
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OCR_ENGINE = "auto"  # "auto", "easyocr", or "tesseract"
EASYOCR_GPU = False

ROLLER_FILE = "roller_groups.json"
OUTPUT_CSV = "sixth_prize_extracted.csv"
OUTPUT_JSON = "sixth_prize_extracted.json"
OUTPUT_IMAGE = "sixth_prize_annotated.png"
DEBUG_DIR = "debug_6th"

TIMESTAMP_SEC = 17 * 60 + 42  # 17:42
SAMPLE_OFFSETS_SEC = [-1.0, 0.0, 1.0]

DIGITS = 4
DIGIT_CHARS = "0123456789"
GLYPH_SCALE = 6
WHOLE_BOX_WEIGHT = 0.5
EPS = 0.2

SHOW_UI = True
UI_WIN = "6th Prize - Direct Extraction"
ROWS_PER_COLUMN = 6
PANEL_H = 260

COLORS = {
    "pending":   (110, 110, 110),
    "reading":   (255, 200, 0),
    "good":      (0, 220, 0),      # Green - high confidence
    "fair":      (0, 165, 255),    # Orange - medium confidence
    "poor":      (0, 0, 220),      # Red - low confidence
    "partial":   (0, 255, 255),    # Cyan - unreadable digit
}


# ============================================================
# SMALL HELPERS
# ============================================================

def put(img, text, org, scale=0.5, color=(230, 230, 230), thick=1):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def fit(img, max_w, max_h):
    if img is None or img.size == 0:
        return None
    h, w = img.shape[:2]
    s = min(max_w / w, max_h / h)
    return cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))),
                      interpolation=cv2.INTER_CUBIC)


def place(canvas, img, x, y):
    if img is None or img.size == 0:
        return
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h = min(img.shape[0], canvas.shape[0] - y)
    w = min(img.shape[1], canvas.shape[1] - x)
    if h > 0 and w > 0:
        canvas[y:y + h, x:x + w] = img[:h, :w]


def pad(img, m=40):
    return cv2.copyMakeBorder(img, m, m, m, m, cv2.BORDER_CONSTANT, value=255)


def weight(conf):
    return max(0.1, float(conf) / 100.0)


def get_status(number, avg_conf):
    """Get status based on confidence and readability"""
    if "?" in number:
        return {"icon": "⚠️", "text": "PARTIAL", "color": "partial"}
    elif avg_conf >= 70:
        return {"icon": "✓", "text": "GOOD", "color": "good"}
    elif avg_conf >= 50:
        return {"icon": "~", "text": "FAIR", "color": "fair"}
    else:
        return {"icon": "✗", "text": "POOR", "color": "poor"}


# ============================================================
# VIDEO
# ============================================================

def find_video():
    """Find video file"""
    import glob
    patterns = [
        "Kerala Lottery*SAMRUDHI*.mp4",
        "*.mp4"
    ]
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    raise FileNotFoundError("No video file found")


def load_rollers(json_path):
    """Load roller box coordinates"""
    if not os.path.exists(json_path):
        print(f"⚠️  Roller config not found: {json_path}")
        print("📍 Generating default 18 roller positions...\n")
        
        # Generate default 18 boxes in 2 rows of 9
        rollers = []
        box_w, box_h = 80, 120
        spacing_x = 100
        spacing_y = 160
        start_x, start_y = 50, 50
        
        for row in range(2):
            for col in range(9):
                x = start_x + col * spacing_x
                y = start_y + row * spacing_y
                rollers.append({"x": x, "y": y, "width": box_w, "height": box_h})
        
        # Save it
        with open(json_path, 'w') as f:
            json.dump({"roller_groups": rollers}, f, indent=2)
        
        print(f"✅ Created {json_path} with {len(rollers)} default positions")
        print("⚠️  IMPORTANT: Adjust coordinates based on your video!\n")
        return rollers
    
    # Load existing file
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    # Handle both "rollers" and "roller_groups" keys
    rollers = data.get("roller_groups") or data.get("rollers", [])
    if not rollers:
        raise ValueError("No rollers defined in config")
    
    return rollers


def load_frames(video_path, t0):
    """Load frames around timestamp"""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = []
    
    for off in sorted(SAMPLE_OFFSETS_SEC, key=lambda o: (abs(o), o)):
        t = t0 + off
        if t < 0:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
        ok, frame = cap.read()
        if ok:
            frames.append((off, frame))
    
    cap.release()
    
    if not frames:
        raise SystemExit("Could not read any video frames")
    
    H, W = frames[0][1].shape[:2]
    offsets_str = ", ".join([f"{o:+.0f}s" for o, _ in frames])
    print(f"📹 Frames loaded: {offsets_str} | size {W}x{H}\n")
    
    return frames


def crop_roi(frame, roi):
    """Crop region of interest from frame"""
    if frame is None:
        return None
    
    H, W = frame.shape[:2]
    x, y = int(roi["x"]), int(roi["y"])
    w, h = int(roi["width"]), int(roi["height"])
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    
    if x1 <= x0 or y1 <= y0:
        return None
    
    return frame[y0:y1, x0:x1]


# ============================================================
# OCR
# ============================================================

def tess_read(img, psm):
    """Tesseract OCR"""
    if img is None or img.size == 0:
        return "", 0.0
    
    tmp = tempfile.mkdtemp(prefix="sixth_")
    try:
        in_path = os.path.join(tmp, "in.png")
        out_base = os.path.join(tmp, "out")
        cv2.imwrite(in_path, img)
        
        cmd = [TESSERACT_CMD, in_path, out_base, "--psm", str(psm), "--dpi", "300",
               "-c", f"tessedit_char_whitelist={DIGIT_CHARS}", "tsv"]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return "", 0.0
        
        best_text, best_conf = "", 0.0
        tsv = out_base + ".tsv"
        
        if os.path.exists(tsv):
            with open(tsv, "r", encoding="utf-8", errors="ignore") as f:
                for line in f.read().splitlines()[1:]:
                    parts = line.split("\t")
                    if len(parts) >= 12 and parts[0] == "5":
                        try:
                            digits = re.sub(r"\D", "", parts[11])
                            conf = float(parts[10])
                            if digits and conf > best_conf:
                                best_text, best_conf = digits, conf
                        except (ValueError, IndexError):
                            continue
        
        return best_text, best_conf
    
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class OcrEngine:
    """OCR wrapper - EasyOCR or Tesseract"""
    
    def __init__(self):
        self.kind = None
        self.reader = None
        
        # Try EasyOCR first
        if OCR_ENGINE in ("auto", "easyocr"):
            try:
                import easyocr
                print("⏳ Loading EasyOCR (first run downloads models)...")
                self.reader = easyocr.Reader(["en"], gpu=EASYOCR_GPU, verbose=False)
                self.kind = "easyocr"
                print("✓ EasyOCR loaded\n")
                return
            except Exception as e:
                if OCR_ENGINE == "easyocr":
                    raise SystemExit(f"❌ EasyOCR failed: {e}\nInstall with: pip install easyocr")
                print(f"⚠️  EasyOCR unavailable, trying Tesseract...\n")
        
        # Fall back to Tesseract
        if not os.path.exists(TESSERACT_CMD):
            raise SystemExit(f"❌ Tesseract not found: {TESSERACT_CMD}")
        
        self.kind = "tesseract"
        print("🔍 OCR Engine: tesseract\n")
    
    def read(self, img, mode="char"):
        """Read image and return (text, confidence)"""
        if img is None or img.size == 0:
            return "", 0.0
        
        if self.kind == "easyocr":
            try:
                results = self.reader.readtext(img, allowlist=DIGIT_CHARS,
                                               detail=True, paragraph=False)
                best_text, best_conf = "", 0.0
                
                for _bbox, text, conf in results:
                    digits = re.sub(r"\D", "", text)
                    if digits and float(conf) * 100 > best_conf:
                        best_text, best_conf = digits, float(conf) * 100
                
                return best_text, best_conf
            
            except Exception as e:
                print(f"⚠️  EasyOCR error: {e}")
                return "", 0.0
        
        else:
            return tess_read(img, 10 if mode == "char" else 7)


# ============================================================
# DIGIT SPLITTING AND PREPROCESSING
# ============================================================

def split_digits(box_bgr):
    """Split box into individual digit regions"""
    if box_bgr is None or box_bgr.size == 0:
        return [], "failed"
    
    gray = cv2.cvtColor(box_bgr, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    
    if H < 20 or W < 20:
        return [], "too_small"
    
    ty = max(1, int(H * 0.08))
    tx = max(1, int(W * 0.02))
    inner = gray[ty:H - ty, tx:W - tx]
    ih, iw = inner.shape
    
    if ih < 10 or iw < 20:
        return [], "too_small"

    _, ink = cv2.threshold(inner, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)

    cands = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if w < 1 or h < 1:
            continue
        if not (0.40 * ih <= h <= 0.92 * ih):
            continue
        if not (0.06 * iw <= w <= 0.30 * iw):
            continue
        if not (1.1 <= h / w <= 4.0):
            continue
        if a / float(w * h) < 0.12:
            continue
        cands.append((int(x), int(y), int(w), int(h), int(a)))

    if len(cands) >= DIGITS:
        cands.sort(key=lambda c: -c[4])
        cands = sorted(cands[:DIGITS], key=lambda c: c[0])
        boxes = [(x, y, x + w, y + h) for x, y, w, h, _ in cands]
        method = "components"
    else:
        slot = iw / DIGITS
        boxes = [(int(i * slot + 0.12 * slot), int(0.05 * ih),
                  int((i + 1) * slot - 0.12 * slot), int(0.95 * ih))
                 for i in range(DIGITS)]
        method = "slots"

    glyphs = []
    for x0, y0, x1, y1 in boxes:
        glyphs.append(inner[max(0, y0 - 3):min(ih, y1 + 3),
                            max(0, x0 - 3):min(iw, x1 + 3)])
    return glyphs, method


def glyph_variants(g):
    """Generate preprocessing variants of digit glyph"""
    if g is None or g.size == 0:
        return []
    
    big = cv2.resize(g, None, fx=GLYPH_SCALE, fy=GLYPH_SCALE, interpolation=cv2.INTER_CUBIC)
    big = cv2.GaussianBlur(big, (3, 3), 0)
    _, otsu = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    p = pad(otsu, 40)
    return [("otsu", p), ("inv", cv2.bitwise_not(p)), ("gray", pad(big, 40))]


def box_variants(bgr):
    """Generate preprocessing variants of whole box"""
    if bgr is None or bgr.size == 0:
        return []
    
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, otsu = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    p = pad(otsu, 30)
    return [("otsu", p), ("inv", cv2.bitwise_not(p))]


# ============================================================
# EXTRACTION (NO MATCHING)
# ============================================================

def read_box(frames, roi, ocr):
    """Extract 4-digit number from roller box (NO DATABASE MATCHING)"""
    votes = [defaultdict(float) for _ in range(DIGITS)]
    box_crop = None
    glyph_sample = None
    method = ""
    last_pre = None
    calls = 0

    for _off, frame in frames:
        crop = crop_roi(frame, roi)
        if crop is None:
            continue
        
        if box_crop is None:
            box_crop = crop.copy()

        # Split into individual digits
        glyphs, m = split_digits(crop)
        if glyph_sample is None and glyphs:
            glyph_sample, method = glyphs, m

        # Vote on each glyph
        for pos in range(min(len(glyphs), DIGITS)):
            g = glyphs[pos]
            if g is None or g.size == 0:
                continue
            
            for _name, img in glyph_variants(g):
                text, conf = ocr.read(img, "char")
                calls += 1
                last_pre = img
                if text:
                    votes[pos][text[0]] += weight(conf)

        # Vote on whole box
        for _name, img in box_variants(crop):
            text, conf = ocr.read(img, "line")
            calls += 1
            last_pre = img
            if len(text) == DIGITS:
                for pos, ch in enumerate(text):
                    if ch in DIGIT_CHARS:
                        votes[pos][ch] += WHOLE_BOX_WEIGHT

    # Extract best digit + confidence for each position
    extracted = ""
    per_digit_conf = []
    argmax = ""
    
    for pos in range(DIGITS):
        d = votes[pos]
        if not d:
            extracted += "?"
            per_digit_conf.append(0.0)
            argmax += "?"
        else:
            best_digit = max(d, key=d.get)
            best_score = d[best_digit]
            total_score = sum(d.values())
            confidence = (best_score / total_score * 100) if total_score > 0 else 0
            
            extracted += best_digit
            per_digit_conf.append(confidence)
            argmax += best_digit
    
    avg_confidence = sum(per_digit_conf) / len(per_digit_conf) if per_digit_conf else 0
    
    return {
        "number": extracted,
        "per_digit_conf": per_digit_conf,
        "avg_confidence": avg_confidence,
        "argmax": argmax,
        "crop": box_crop,
        "glyphs": glyph_sample,
        "method": method,
        "pre": last_pre,
        "calls": calls,
        "votes": votes
    }


def digit_summary(votes):
    """Summarize digit voting results"""
    out = []
    for d in votes:
        if d:
            k = max(d, key=d.get)
            out.append(f"{k}({d[k] / sum(d.values()):.0%})")
        else:
            out.append("-")
    return " ".join(out)


# ============================================================
# DRAWING
# ============================================================

def draw_canvas(frame, rollers, results, cur, header):
    """Draw results on canvas"""
    H, W = frame.shape[:2]
    canvas = np.full((H + PANEL_H, W, 3), 28, np.uint8)
    img = frame.copy()

    for i, roi in enumerate(rollers):
        if i >= len(results):
            continue
        
        r = results[i]
        status_info = get_status(r["number"], r["avg_confidence"])
        color = COLORS.get(status_info["color"], COLORS["pending"])
        
        x, y = int(roi["x"]), int(roi["y"])
        w, h = int(roi["width"]), int(roi["height"])
        
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 3 if i == cur else 1)
        put(img, f"R{i + 1} {r['number'] or '----'}", (x, max(14, y - 6)), 0.5, color, 1)
    
    canvas[:H, :W] = img
    put(canvas, header, (10, H + 24), 0.6, (255, 255, 255), 1)

    # Show results in panel
    col_w = W // 3
    for i in range(len(results)):
        if i >= 18:  # Limit display
            break
        c_i, r_i = i // ROWS_PER_COLUMN, i % ROWS_PER_COLUMN
        r = results[i]
        x = 10 + c_i * col_w
        y = H + 60 + r_i * 32
        
        status_info = get_status(r["number"], r["avg_confidence"])
        color = COLORS.get(status_info["color"], COLORS["pending"])
        
        per_digit_str = " ".join([f"{int(c)}%" for c in r["per_digit_conf"]])
        txt = f"R{i + 1:<2} {r['number'] or '----'}  {status_info['text']:<8} {status_info['icon']} | {per_digit_str}"
        put(canvas, txt, (x, y), 0.45, color, 1)

    return canvas


# ============================================================
# MAIN
# ============================================================

def main():
    """Main extraction pipeline"""
    print("\n" + "="*100)
    print("6TH PRIZE NUMBER EXTRACTION - DIRECT (NO DATABASE MATCHING)")
    print("="*100 + "\n")
    
    # Find video
    video_path = find_video()
    print(f"🎬 Video: {Path(video_path).name}\n")
    
    # Load roller coordinates
    rollers = load_rollers(ROLLER_FILE)
    print(f"📦 Loaded {len(rollers)} roller boxes\n")
    
    # Initialize OCR
    ocr = OcrEngine()
    
    # Load frames
    frames = load_frames(video_path, TIMESTAMP_SEC)
    
    # Process each roller
    results = []
    base_frame = frames[0][1].copy()
    boxes = []
    
    print("="*100)
    print("PROCESSING BOXES")
    print("="*100)
    print(f"{'Box':<5}{'Number':<8}{'Avg Conf':<10}{'Per-Digit Conf':<40}{'Method':<12}{'Calls':<7}{'Status'}")
    print("-"*100)
    
    if SHOW_UI:
        cv2.namedWindow(UI_WIN, cv2.WINDOW_AUTOSIZE)
    
    for i, roi in enumerate(rollers):
        if SHOW_UI:
            canvas = draw_canvas(base_frame, rollers, results, i,
                                f"Processing R{i+1}/{len(rollers)}")
            cv2.imshow(UI_WIN, canvas)
            cv2.waitKey(1)
        
        t0 = time.time()
        result = read_box(frames, roi, ocr)
        boxes.append(result)
        results.append({
            "number": result["number"],
            "avg_confidence": result["avg_confidence"],
            "per_digit_conf": result["per_digit_conf"],
            "argmax": result["argmax"],
        })
        
        elapsed = time.time() - t0
        
        # Print result
        number = result["number"]
        avg_conf = result["avg_confidence"]
        per_digit_str = " ".join([f"{int(c)}%" for c in result["per_digit_conf"]])
        status_info = get_status(number, avg_conf)
        method = result["method"] or "-"
        calls = result["calls"]
        
        print(f"R{i+1:<4}{number:<8}{avg_conf:<10.0f}{per_digit_str:<40}{method:<12}{calls:<7}{status_info['icon']} {status_info['text']}")
        
        # Save debug images
        tag = f"{DEBUG_DIR}/roller_{i+1:02d}"
        if result["crop"] is not None:
            cv2.imwrite(tag + "_box.png", result["crop"])
        for k, g in enumerate(result["glyphs"] or []):
            if g is not None:
                cv2.imwrite(f"{tag}_glyph{k+1}.png", g)
        if result["pre"] is not None:
            cv2.imwrite(tag + "_last_pre.png", result["pre"])

    print("="*100 + "\n")
    
    # Save outputs
    print("💾 Saving results...\n")
    
    # CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        fields = ["box", "number", "avg_confidence", "per_digit_confidence", "method", "calls", "status"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        
        for i, (r, out) in enumerate(zip(results, boxes), 1):
            status_info = get_status(r["number"], r["avg_confidence"])
            per_digit_str = " ".join([f"{int(c)}" for c in r["per_digit_conf"]])
            w.writerow({
                "box": i,
                "number": r["number"],
                "avg_confidence": f"{r['avg_confidence']:.1f}",
                "per_digit_confidence": per_digit_str,
                "method": out["method"],
                "calls": out["calls"],
                "status": f"{status_info['icon']} {status_info['text']}",
            })
    
    # JSON
    payload = {
        "extraction": {
            "timestamp": TIMESTAMP_SEC // 60,
            "video": Path(video_path).name,
            "total_boxes": len(results),
        },
        "boxes": [{
            "box": i + 1,
            "number": r["number"],
            "avg_confidence": round(r["avg_confidence"], 1),
            "per_digit_confidence": [round(c, 1) for c in r["per_digit_conf"]],
            "argmax": r["argmax"],
            "method": boxes[i]["method"],
            "calls": boxes[i]["calls"],
        } for i, r in enumerate(results)],
    }
    
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    
    # Annotated image
    annotated = draw_canvas(base_frame, rollers, results, -1, "6th Prize - Extraction Complete")
    cv2.imwrite(OUTPUT_IMAGE, annotated)
    
    print(f"✅ Saved outputs:")
    print(f"   - {OUTPUT_CSV}")
    print(f"   - {OUTPUT_JSON}")
    print(f"   - {OUTPUT_IMAGE}")
    print(f"   - Debug images in {DEBUG_DIR}/\n")
    
    # Summary
    print("="*100)
    print("EXTRACTION SUMMARY")
    print("="*100)
    
    good = sum(1 for r in results if get_status(r["number"], r["avg_confidence"])["color"] == "good")
    fair = sum(1 for r in results if get_status(r["number"], r["avg_confidence"])["color"] == "fair")
    poor = sum(1 for r in results if get_status(r["number"], r["avg_confidence"])["color"] == "poor")
    partial = sum(1 for r in results if "?" in r["number"])
    
    print(f"\n✓ GOOD    (≥70% avg):  {good:2d} boxes")
    print(f"~ FAIR    (50-69%):    {fair:2d} boxes")
    print(f"✗ POOR    (<50%):      {poor:2d} boxes")
    print(f"⚠️  PARTIAL (has ?):    {partial:2d} boxes")
    print(f"\nTotal:                 {len(results):2d} boxes")
    
    print("\n" + "="*100 + "\n")
    
    # Show final frame
    if SHOW_UI:
        canvas = draw_canvas(base_frame, rollers, results, -1,
                            f"✅ COMPLETE - All {len(results)} boxes extracted")
        cv2.imshow(UI_WIN, canvas)
        print("🎉 Press any key to exit...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    os.makedirs(DEBUG_DIR, exist_ok=True)
    main()
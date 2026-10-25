"""
sixth_prize_matcher.py - STABLE VERSION WITH DUPLICATE PREVENTION

Improvements:
1. Prevents duplicate extractions (same number in multiple boxes)
2. Better terminal reporting with detailed explanations
3. Recheck markers for suspicious extractions
4. Memory efficient (no threading issues)
5. Detailed confidence breakdown
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
from pymongo import MongoClient


# ============================================================
# CONFIG
# ============================================================
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OCR_ENGINE = "auto"
EASYOCR_GPU = False

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "absolute_data"
TARGET_SERIAL = None

TARGET_TIER = 6
PRIZE_TIERS = [4, 5, 6, 7, 8, 9]
PRIZE_MAX_AMOUNT = 5000

ROLLER_FILE = "roller_groups.json"
OUTPUT_CSV = "sixth_prize_matches.csv"
OUTPUT_JSON = "sixth_prize_matches.json"
OUTPUT_IMAGE = "sixth_prize_annotated.png"
DEBUG_DIR = "debug_6th"

TIMESTAMP_SEC = 17 * 60 + 42
SAMPLE_OFFSETS_SEC = [-1.0, 0.0, 1.0]

DIGITS = 4
DIGIT_CHARS = "0123456789"
GLYPH_SCALE = 6
WHOLE_BOX_WEIGHT = 0.5
EPS = 0.2
MIN_MARGIN = 2.5

SHOW_UI = True
UI_WIN = "6th Prize Matcher"
ROWS_PER_COLUMN = 6
PANEL_H = 260

COLORS = {
    "pending":   (110, 110, 110),
    "reading":   (255, 200, 0),
    "match":     (0, 220, 0),
    "unsure":    (0, 255, 255),
    "not_6th":   (255, 0, 255),
    "recheck":   (0, 165, 255),  # Changed from "duplicate"
    "no_read":   (0, 0, 220),
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


def serial_from_filename(filename):
    m = re.search(r"\b([A-Za-z]{2,})[-\s]?(\d{1,4})\b", filename)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def date_from_filename(filename):
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", filename)
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else None


# ============================================================
# DATABASE
# ============================================================

def find_draw(coll, video_path):
    filename = Path(video_path).name
    serial = TARGET_SERIAL or serial_from_filename(filename)
    draw_date = date_from_filename(filename)
    print(f"Video serial: {serial}   Video date: {draw_date}")

    if serial:
        m = re.match(r"([A-Za-z]+)[-\s]?(\d+)$", serial.strip())
        if m:
            pattern = rf"^{m.group(1)}[-\s]?{m.group(2)}$"
            draw = coll.find_one({"serialNumber": {"$regex": pattern, "$options": "i"}})
            if draw:
                return draw, "serialNumber"

    if draw_date:
        draw = coll.find_one({"date": draw_date})
        if draw:
            return draw, "date"
    return None, None


def load_target_numbers(video_path):
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    coll = client[DB_NAME][COLLECTION]

    draw, how = find_draw(coll, video_path)
    if draw is None:
        print("No draw matched this video. Last 10 serials in the database:")
        for d in coll.find({}, {"serialNumber": 1, "date": 1, "fileName": 1}) \
                     .sort("recordNumber", -1).limit(10):
            print(f"  {d.get('serialNumber')!r:12}  {d.get('date')}  {d.get('fileName')}")
        client.close()
        raise SystemExit(1)

    info = {"serialNumber": draw.get("serialNumber"), "date": draw.get("date"),
            "fileName": draw.get("fileName")}
    print(f"Matched by {how}: {info}")

    series = draw.get("series", [])
    small = sorted([s for s in series if 0 < s.get("prize", 0) <= PRIZE_MAX_AMOUNT],
                   key=lambda s: -s["prize"])
    print("\nSmall-amount tiers in DB (largest amount = 4th):")
    for tier, s in zip(PRIZE_TIERS, small):
        print(f"  {tier}th: amount={s['prize']}  count={len(s.get('numbers', []))}")

    idx = TARGET_TIER - PRIZE_TIERS[0]
    if idx >= len(small):
        client.close()
        raise SystemExit(f"Only {len(small)} small tiers in DB, cannot find {TARGET_TIER}th")

    target = small[idx]
    numbers = sorted({n["number"] for n in target.get("numbers", [])
                      if re.fullmatch(r"\d{4}", str(n.get("number", "")))})
    print(f"\n{TARGET_TIER}th Prize: amount={target['prize']}, {len(numbers)} numbers")
    print("  " + " ".join(numbers))
    return client, numbers, info


# ============================================================
# VIDEO
# ============================================================

def load_frames(video_path, t0):
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
        raise SystemExit("Could not read any video frame")
    H, W = frames[0][1].shape[:2]
    print(f"Frames loaded: {[f'{o:+.0f}s' for o, _ in frames]}  size {W}x{H}")
    return frames


def crop_roi(frame, roi):
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
                    p = line.split("\t")
                    if len(p) == 12 and p[0] == "5" and p[11].strip():
                        digits = re.sub(r"\D", "", p[11])
                        try:
                            conf = float(p[10])
                        except ValueError:
                            conf = 0.0
                        if digits and conf > best_conf:
                            best_text, best_conf = digits, conf
        return best_text, best_conf
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class OcrEngine:
    def __init__(self):
        self.kind = None
        self.reader = None

        if OCR_ENGINE in ("auto", "easyocr"):
            try:
                import easyocr
                print("Loading EasyOCR (first run downloads models)...")
                self.reader = easyocr.Reader(["en"], gpu=EASYOCR_GPU, verbose=False)
                self.kind = "easyocr"
            except Exception as e:
                if OCR_ENGINE == "easyocr":
                    raise SystemExit(f"EasyOCR failed to load: {e}\n"
                                     "Install with: pip install easyocr")
                print(f"EasyOCR not available ({type(e).__name__}: {e}); using Tesseract.")

        if self.kind is None:
            if not os.path.exists(TESSERACT_CMD):
                raise SystemExit(f"Tesseract not found: {TESSERACT_CMD}")
            self.kind = "tesseract"

        print(f"OCR engine: {self.kind}")

    def read(self, img, mode):
        if self.kind == "easyocr":
            try:
                results = self.reader.readtext(img, allowlist=DIGIT_CHARS,
                                               detail=1, paragraph=False)
            except Exception as e:
                print(f"EasyOCR error: {e}")
                return "", 0.0
            best_text, best_conf = "", 0.0
            for _bbox, text, conf in results:
                digits = re.sub(r"\D", "", text)
                if digits and float(conf) * 100 > best_conf:
                    best_text, best_conf = digits, float(conf) * 100
            return best_text, best_conf
        return tess_read(img, 10 if mode == "char" else 7)


# ============================================================
# DIGIT SPLITTING AND PREPROCESSING
# ============================================================

def split_digits(box_bgr):
    gray = cv2.cvtColor(box_bgr, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    ty, tx = max(1, int(H * 0.08)), max(1, int(W * 0.02))
    inner = gray[ty:H - ty, tx:W - tx]
    ih, iw = inner.shape
    if ih < 10 or iw < 20:
        return [], "too small"

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
    if g is None or g.size == 0:
        return []
    big = cv2.resize(g, None, fx=GLYPH_SCALE, fy=GLYPH_SCALE, interpolation=cv2.INTER_CUBIC)
    big = cv2.GaussianBlur(big, (3, 3), 0)
    _, otsu = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    p = pad(otsu, 40)
    return [("otsu", p), ("inv", cv2.bitwise_not(p)), ("gray", pad(big, 40))]


def box_variants(bgr):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, otsu = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    p = pad(otsu, 30)
    return [("otsu", p), ("inv", cv2.bitwise_not(p))]


# ============================================================
# MATCHING (6th prize only)
# ============================================================

def score_candidates(votes, candidates):
    total = sum(sum(d.values()) for d in votes)
    if total <= 0 or not candidates:
        return {"status": "no_read", "number": None, "margin": 0.0,
                "hamming": None, "argmax": "", "log_lik": None}

    probs, argmax = [], ""
    for d in votes:
        s = sum(d.values()) + len(DIGIT_CHARS) * EPS
        probs.append({k: (d.get(k, 0.0) + EPS) / s for k in DIGIT_CHARS})
        argmax += max(DIGIT_CHARS, key=lambda k: d.get(k, 0.0)) if d else "?"

    ranked = sorted(
        ((sum(math.log(probs[p][c[p]]) for p in range(DIGITS)), c) for c in candidates),
        reverse=True,
    )
    best_ll, best = ranked[0]
    runner_ll = ranked[1][0] if len(ranked) > 1 else best_ll - 99.0
    margin = best_ll - runner_ll
    hd = sum(1 for a, b in zip(argmax, best) if a != b)

    if hd == 0:
        status = "match"
    elif hd == 1 and margin >= MIN_MARGIN:
        status = "match"
    elif hd <= 2:
        status = "unsure"
    else:
        status = "not_6th"

    return {"status": status, "number": best, "margin": round(margin, 2),
            "hamming": hd, "argmax": argmax, "log_lik": round(best_ll, 2)}


# ============================================================
# READING ONE BOX
# ============================================================

def read_box(frames, roi, ocr, candidates):
    votes = [defaultdict(float) for _ in range(DIGITS)]
    box_crop = None
    glyph_sample, method = None, ""
    last_pre = None
    calls = 0

    for _off, frame in frames:
        crop = crop_roi(frame, roi)
        if crop is None:
            continue
        if box_crop is None:
            box_crop = crop

        glyphs, m = split_digits(crop)
        if glyph_sample is None and glyphs:
            glyph_sample, method = glyphs, m

        for pos, g in enumerate(glyphs[:DIGITS]):
            for _name, img in glyph_variants(g):
                text, conf = ocr.read(img, "char")
                calls += 1
                last_pre = img
                if text:
                    votes[pos][text[0]] += weight(conf)

        for _name, img in box_variants(crop):
            text, conf = ocr.read(img, "line")
            calls += 1
            last_pre = img
            if len(text) == DIGITS:
                for pos, ch in enumerate(text):
                    votes[pos][ch] += WHOLE_BOX_WEIGHT

    res = score_candidates(votes, candidates)
    return {"result": res, "votes": votes, "crop": box_crop,
            "glyphs": glyph_sample, "method": method, "pre": last_pre,
            "calls": calls}


def digit_summary(votes):
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
    H, W = frame.shape[:2]
    canvas = np.full((H + PANEL_H, W, 3), 28, np.uint8)
    img = frame.copy()

    for i, roi in enumerate(rollers):
        r = results[i]
        col = COLORS.get(r["status"], COLORS["pending"])
        x, y = int(roi["x"]), int(roi["y"])
        w, h = int(roi["width"]), int(roi["height"])
        cv2.rectangle(img, (x, y), (x + w, y + h), col, 3 if i == cur else 1)
        put(img, f"R{i + 1} {r['number'] or '----'}", (x, max(14, y - 6)), 0.5, col, 1)
    canvas[:H] = img

    put(canvas, header, (10, H + 24), 0.6, (255, 255, 255), 1)

    col_w = W // 3
    for i in range(len(rollers)):
        c_i, r_i = i // ROWS_PER_COLUMN, i % ROWS_PER_COLUMN
        r = results[i]
        x = 10 + c_i * col_w
        y = H + 60 + r_i * 32
        hd = "-" if r["hamming"] is None else str(r["hamming"])
        txt = (f"R{i + 1:<2} {r['number'] or '----'}  {r['status']:<9} "
               f"m={r['margin']:.1f} hd={hd}")
        put(canvas, txt, (x, y), 0.5, COLORS.get(r["status"], COLORS["pending"]), 1)

    return canvas


# ============================================================
# DUPLICATE PREVENTION & HANDLING
# ============================================================

def handle_duplicates(results):
    """
    Detect duplicates (same 6th prize number in multiple boxes).
    Only the FIRST occurrence is kept as primary.
    Additional occurrences are marked as RECHECK.
    This prevents false duplicates when numbers genuinely appear only once per day.
    """
    # Track which numbers we've seen and where
    number_boxes = defaultdict(list)
    
    for i, r in enumerate(results):
        if r["status"] in ("match", "unsure") and r["number"]:
            number_boxes[r["number"]].append(i)
    
    duplicates = []
    
    # Find numbers that appear more than once
    for num, box_indices in number_boxes.items():
        if len(box_indices) > 1:
            # Mark all but the first as recheck
            for idx in box_indices[1:]:
                duplicates.append({
                    "number": num,
                    "first_box": box_indices[0] + 1,
                    "duplicate_box": idx + 1,
                    "is_duplicate": True
                })
                results[idx]["status"] = "recheck"
                results[idx]["previous_number"] = num
                results[idx]["recheck_reason"] = f"Duplicate of Box {box_indices[0] + 1}"
                results[idx]["original_status"] = results[idx].get("status", "unknown")
    
    return results, duplicates


# ============================================================
# DETAILED TERMINAL REPORTING
# ============================================================

def print_detailed_report(results, boxes, candidates, missing, duplicates):
    """Print comprehensive terminal report with all details and explanations."""
    
    print("\n" + "=" * 130)
    print("DETAILED EXTRACTION REPORT - 6TH PRIZE MATCHER")
    print("=" * 130)
    
    # Summary Statistics
    match_count = sum(1 for r in results if r['status'] == 'match')
    unsure_count = sum(1 for r in results if r['status'] == 'unsure')
    not_6th_count = sum(1 for r in results if r['status'] == 'not_6th')
    recheck_count = sum(1 for r in results if r['status'] == 'recheck')
    no_read_count = sum(1 for r in results if r['status'] == 'no_read')
    
    print(f"\n📊 OVERALL STATISTICS:")
    print(f"   Total boxes processed: {len(results)}")
    print(f"   ✓ MATCH (Perfect/1-digit with high margin):  {match_count:2d}")
    print(f"   ~ UNSURE (2-digit differences):             {unsure_count:2d}")
    print(f"   ✗ NOT_6TH (Not in 6th prize list):          {not_6th_count:2d}")
    print(f"   ⟳ RECHECK (Duplicate detections):           {recheck_count:2d}")
    print(f"   ○ NO_READ (No OCR reads):                   {no_read_count:2d}")
    
    found = {r["number"] for r in results if r["status"] in ("match", "unsure") and r["number"]}
    print(f"\n📈 COVERAGE ANALYSIS:")
    print(f"   Boxes with valid extraction: {len(found)}/{len(results)} ({len(found)*100/len(results):.1f}%)")
    print(f"   Unique numbers extracted:    {len(found)}/{len(candidates)}")
    print(f"   Numbers NOT found on video:  {len(missing)}/{len(candidates)}")
    if missing:
        print(f"   Missing numbers: {' '.join(missing)}")
    
    print(f"\n🔄 DUPLICATE ANALYSIS:")
    if duplicates:
        print(f"   Duplicates detected: {len(duplicates)}")
        for dup in duplicates:
            print(f"   - '{dup['number']}' found in Box {dup['first_box']} AND Box {dup['duplicate_box']}")
            print(f"     → Box {dup['first_box']} kept as primary")
            print(f"     → Box {dup['duplicate_box']} marked as RECHECK")
    else:
        print(f"   No duplicates detected (each number extracted only once)")
    
    print(f"\n📋 DETAILED BOX-BY-BOX ANALYSIS:")
    print("-" * 130)
    print(f"{'Box':<5}{'Number':<8}{'Status':<11}{'Margin':<10}{'Hamming':<10}{'Argmax':<10}{'Method':<12}{'Calls':<7}{'Assessment'}")
    print("-" * 130)
    
    for i, r in enumerate(results, 1):
        out = boxes[i-1]
        hd = "-" if r["hamming"] is None else str(r["hamming"])
        margin_str = f"{r['margin']:.2f}" if r['margin'] else "-"
        
        # Create assessment string
        assessment = ""
        if r["status"] == "match":
            assessment = "✓ Reliable - High confidence match"
        elif r["status"] == "unsure":
            assessment = "~ Review needed - Some digit uncertainty"
        elif r["status"] == "not_6th":
            assessment = "✗ Likely error - Check video quality or box location"
        elif r["status"] == "recheck":
            dup_box = r.get("recheck_reason", "?").split()[-1]
            assessment = f"⟳ Duplicate of Box {dup_box} - First occurrence is primary"
        elif r["status"] == "no_read":
            assessment = "○ No OCR reads - Unrecognizable box"
        
        status_symbol = {
            "match": "✓",
            "unsure": "~",
            "not_6th": "✗",
            "recheck": "⟳",
            "no_read": "○"
        }.get(r['status'], "?")
        
        method = out['method'] or "-"
        calls = out['calls']
        
        print(f"R{i:<4}{r['number'] or '----':<8}{status_symbol} {r['status']:<9} "
              f"{margin_str:<10}{hd:<10}{r['argmax'] or '----':<10}"
              f"{method:<12}{calls:<7}{assessment}")
    
    print("\n" + "=" * 130)
    print("LEGEND & EXPLANATIONS:")
    print("-" * 130)
    
    print("\n📌 STATUS MEANINGS:")
    print("   ✓ MATCH     : Extracted number matches 6th prize list perfectly")
    print("                 - Hamming = 0 (all digits correct)")
    print("                 - OR Hamming = 1 with margin >= 2.5 (1 digit off but very confident)")
    print("                 - Action: ACCEPT - Ready for validation")
    print()
    print("   ~ UNSURE    : Extracted number in 6th prize list but with some uncertainty")
    print("                 - Hamming = 2 (2 digits different from best match)")
    print("                 - OR Hamming = 1 with margin < 2.5 (close to another number)")
    print("                 - Action: REVIEW - Check OCR quality and video box location")
    print()
    print("   ✗ NOT_6TH   : No match found in 6th prize list")
    print("                 - Hamming >= 3 (too many differences)")
    print("                 - Action: CHECK - Verify box position or video timestamp")
    print()
    print("   ⟳ RECHECK   : Same number appeared in multiple boxes (duplicate detection)")
    print("                 - Indicates first extraction is primary, this one is duplicate")
    print("                 - Action: INVESTIGATE - Why was same number read twice?")
    print()
    print("   ○ NO_READ   : OCR couldn't read the box at all")
    print("                 - No digit votes received from any OCR attempt")
    print("                 - Action: SKIP - Box is unreadable/corrupted")
    
    print("\n🔢 HAMMING DISTANCE:")
    print("   Shows how many digits differ between OCR reading and best match")
    print("   0 = All 4 digits correct")
    print("   1 = One digit wrong (1234 → 1235)")
    print("   2 = Two digits wrong (1234 → 1564)")
    print("   3+ = Too many differences, not a match")
    
    print("\n📊 MARGIN (Log-Likelihood Gap):")
    print("   Confidence gap between best match and runner-up number")
    print("   Higher margin = more confident choice")
    print("   Margin > 2.5  = Very confident (high threshold)")
    print("   Margin 1.5-2.5 = Good confidence")
    print("   Margin < 1.5  = Close call, could be wrong")
    print("   Margin = 0.0  = Best match and runner-up equally likely")
    
    print("\n📱 ARGMAX:")
    print("   OCR's raw reading before matching against candidates")
    print("   ? indicates unreadable digit position")
    print("   Compare this with 'Number' to see what changed during matching")
    
    print("\n🎯 RECOMMENDATIONS:")
    print("   1. Accept all MATCH status boxes - they're reliable")
    print("   2. Review UNSURE boxes - check video quality and position")
    print("   3. Investigate NOT_6TH boxes - might indicate wrong box location")
    print("   4. For RECHECK boxes - the FIRST occurrence is the correct one")
    print("   5. Note any MISSING numbers - might need different timestamp")
    
    print("=" * 130 + "\n")


# ============================================================
# MAIN RUN
# ============================================================

def run(rollers, frames, ocr, candidates, info, video_path):
    n = len(rollers)
    results = [{"status": "pending", "number": None, "margin": 0.0,
                "hamming": None, "argmax": "", "log_lik": None} for _ in range(n)]
    boxes = [None] * n
    os.makedirs(DEBUG_DIR, exist_ok=True)

    H, W = frames[0][1].shape[:2]
    base = frames[0][1]

    if SHOW_UI:
        cv2.namedWindow(UI_WIN, cv2.WINDOW_AUTOSIZE)

    # Process each box
    for i, roi in enumerate(rollers):
        results[i]["status"] = "reading"
        if SHOW_UI:
            cv2.imshow(UI_WIN, draw_canvas(base, rollers, results, i,
                                           f"Reading R{i + 1}/{n} ({TARGET_TIER}th prize only)"))
            cv2.waitKey(1)

        t0 = time.time()
        out = read_box(frames, roi, ocr, candidates)
        boxes[i] = out
        r = out["result"]
        results[i].update(r)

        tag = f"{DEBUG_DIR}/roller_{i + 1:02d}"
        if out["crop"] is not None:
            cv2.imwrite(tag + "_box.png", out["crop"])
        for k, g in enumerate(out["glyphs"] or []):
            cv2.imwrite(f"{tag}_glyph{k + 1}.png", g)
        if out["pre"] is not None:
            cv2.imwrite(tag + "_last_pre.png", out["pre"])

        elapsed = time.time() - t0
        print(f"R{i + 1:02d} | split {out['method'] or '-':<11} | argmax {r['argmax'] or '-':<5} "
              f"| best {r['number'] or '-':<5} hd {r['hamming'] if r['hamming'] is not None else '-'} "
              f"margin {r['margin']:>6.1f} | {r['status'].upper():<8} | "
              f"digits {digit_summary(out['votes'])} | calls {out['calls']:>3d} ({elapsed:>6.1f}s)")

        if SHOW_UI:
            cv2.imshow(UI_WIN, draw_canvas(base, rollers, results, i,
                                           f"Done R{i + 1}/{n}"))
            cv2.waitKey(1)

    # Handle duplicates
    print("\n" + "=" * 130)
    print("DUPLICATE DETECTION & PREVENTION")
    print("=" * 130)
    results, duplicates = handle_duplicates(results)
    
    if duplicates:
        print(f"\nDuplicate(s) detected: {len(duplicates)}")
        for dup in duplicates:
            print(f"  ⚠️  Number '{dup['number']}' appears in:")
            print(f"      - Box {dup['first_box']} (PRIMARY - kept)")
            print(f"      - Box {dup['duplicate_box']} (SECONDARY - marked as RECHECK)")
    else:
        print("\n✓ No duplicates detected - each 6th prize number appears only once")

    # Calculate summary
    found = {r["number"] for r in results
             if r["status"] in ("match", "unsure") and r["number"]}
    missing = [c for c in candidates if c not in found]

    # Print detailed report
    print_detailed_report(results, boxes, candidates, missing, duplicates)

    # Save outputs
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        fields = ["box", "x", "y", "width", "height", "status", "number",
                  "hamming", "margin", "argmax", "digits", "calls", "notes"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i, (roi, r, out) in enumerate(zip(rollers, results, boxes), 1):
            notes = ""
            if r["status"] == "recheck":
                notes = f"Duplicate - {r.get('recheck_reason', '')}"
            w.writerow({
                "box": i, "x": roi["x"], "y": roi["y"],
                "width": roi["width"], "height": roi["height"],
                "status": r["status"], "number": r["number"] or "",
                "hamming": "" if r["hamming"] is None else r["hamming"],
                "margin": r["margin"], "argmax": r["argmax"],
                "digits": digit_summary(out["votes"]), "calls": out["calls"],
                "notes": notes,
            })

    payload = {
        "draw": info,
        "tier": TARGET_TIER,
        "candidates": candidates,
        "not_seen": missing,
        "duplicates_found": len(duplicates),
        "duplicate_details": duplicates,
        "boxes": [{
            "box": i + 1,
            "status": r["status"],
            "number": r["number"],
            "margin": r["margin"],
            "hamming": r["hamming"],
            "argmax": r["argmax"],
            "digit_votes": [dict(d) for d in boxes[i]["votes"]],
        } for i, r in enumerate(results)],
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    annotated = draw_canvas(base, rollers, results, -1,
                            f"{TARGET_TIER}th prize matches - {info.get('serialNumber')}")
    cv2.imwrite(OUTPUT_IMAGE, annotated)
    print(f"\n✓ Saved: {OUTPUT_CSV}, {OUTPUT_JSON}, {OUTPUT_IMAGE}")

    if SHOW_UI:
        cv2.imshow(UI_WIN, draw_canvas(base, rollers, results, -1,
                                       "Finished. Press any key to close."))
        cv2.waitKey(0)
        cv2.destroyAllWindows()


# ============================================================
# MAIN
# ============================================================

def main():
    videos = sorted(Path(".").glob("*.mp4"))
    if not videos:
        raise SystemExit("No .mp4 file found in this folder")
    video = str(videos[0])
    print(f"🎬 Video: {videos[0].name}\n")

    with open(ROLLER_FILE, "r", encoding="utf-8") as f:
        rollers = json.load(f).get("roller_groups", [])
    print(f"📦 Loaded {len(rollers)} roller boxes\n")

    client, candidates, info = load_target_numbers(video)
    try:
        if not candidates:
            raise SystemExit(f"No {TARGET_TIER}th prize numbers in the database for this draw")
        ocr = OcrEngine()
        frames = load_frames(video, TIMESTAMP_SEC)
        print("\n▶️  Starting extraction...\n")
        run(rollers, frames, ocr, candidates, info, video)
    finally:
        client.close()


if __name__ == "__main__":
    os.makedirs(DEBUG_DIR, exist_ok=True)
    main()
"""
roller_ocr_live.py  (v4, full)

- Loads the 4-digit prize tiers (4th..9th) for this video's draw from MongoDB
  (numbergrid.absolute_data, matched by serialNumber taken from the video filename).
- Reads the on-screen prize label ("6 PRIZE") from the rectangle in prize_location.json.
  It is read on several frames and voted. That vote is the expected tier.
- Splits each of the 18 roller boxes into 4 digit glyphs and reads each glyph alone.
  A whole-box pass adds extra evidence.
- The final number is always a database number, chosen by per-digit likelihood.
  The margin to the runner-up is reported.
- Live window + roller_analysis.csv + roller_reads.json + debug images.
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

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "absolute_data"
TARGET_SERIAL = None                    # None = read serial from video filename

ROLLER_FILE = "roller_groups.json"
LABEL_FILE = "prize_location.json"      # the "6 PRIZE" rectangle
OUTPUT_CSV = "roller_analysis.csv"
OUTPUT_JSON = "roller_reads.json"
DEBUG_DIR = "debug"

TIMESTAMP_SEC = 17 * 60 + 42
SAMPLE_OFFSETS_SEC = [0.0, -1.0, 1.0]  # frames pooled around the timestamp

PRIZE_TIERS = [4, 5, 6, 7, 8, 9]
PRIZE_MAX_AMOUNT = 5000                 # 1st-3rd prizes are above this
DIGITS = 4
DIGIT_CHARS = "0123456789"

GLYPH_SCALE = 6
GLYPH_PSM = 10                          # single character
WHOLE_BOX_PSM = 7                       # single line
WHOLE_BOX_WEIGHT = 0.5                  # vote weight of a whole-box read per digit

MIN_MARGIN = 3.0                        # log-likelihood gap to runner-up for "match"
EPS = 0.2                               # smoothing for digit votes

ROWS_PER_COLUMN = 6                     # grid layout in the viewer only
STEP_MS = 60                            # UI tick delay
HOLD_SEC = 1.0                          # pause on a finished roller

# ============================================================
# UI
# ============================================================
WIN = "Roller OCR - Live"
CANVAS_W, CANVAS_H = 1600, 900
FRAME_W, FRAME_H = 960, 540
FONT = cv2.FONT_HERSHEY_SIMPLEX

STATUS_COLORS = {                       # BGR
    "pending":    (110, 110, 110),
    "reading":    (255, 200, 0),
    "match":      (0, 220, 0),
    "unsure":     (0, 255, 255),
    "other_tier": (255, 0, 255),
    "no_read":    (0, 0, 220),
}


# ============================================================
# SMALL HELPERS
# ============================================================

def put(img, text, org, scale=0.5, color=(230, 230, 230), thick=1):
    cv2.putText(img, text, org, FONT, scale, color, thick, cv2.LINE_AA)


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


def fmt_time(t):
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


def serial_from_filename(filename):
    """'... SAMRUDHI - SM-70 - 30.08.2026.mp4' -> 'SM-70'"""
    m = re.search(r"\b([A-Za-z]{2,})[-\s]?(\d{1,4})\b", filename)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def date_from_filename(filename):
    """'... 30.08.2026.mp4' -> '30/08/2026'"""
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", filename)
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else None


def clip_roi(roi, W, H):
    """Clip (x, y, w, h) to the frame. w or h can be 0 if the ROI is outside."""
    x, y, w, h = [int(v) for v in roi]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


def pad_roi(roi, p):
    x, y, w, h = roi
    return (x - p, y - p, w + 2 * p, h + 2 * p)


def read_frame(video_path, t):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def weight(conf):
    return max(0.1, float(conf) / 100.0)


def first_digit(words):
    for text, conf in words:
        d = re.sub(r"\D", "", text)
        if d:
            return d[0], conf
    return "", 0.0


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


def load_prizes(video_path):
    """Returns (client, {tier: set_of_4digit_numbers}, draw_info)."""
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
    if len(small) != len(PRIZE_TIERS):
        print(f"WARNING: {len(small)} small-amount tiers found, expected {len(PRIZE_TIERS)}")

    prize_numbers = {}
    for tier, s in zip(PRIZE_TIERS, small):
        prize_numbers[tier] = {n["number"] for n in s.get("numbers", [])}

    print("\nPrize tiers in DB:")
    for tier in PRIZE_TIERS:
        nums = sorted(prize_numbers.get(tier, []))
        print(f"  {tier}th: {len(nums)} numbers  {nums[:6]}")
    return client, prize_numbers, info


# ============================================================
# OCR
# ============================================================

def tess(img, psm, whitelist=None, dpi=300):
    """
    One Tesseract call using TSV output.
    Returns (words, returncode, stderr, ms), where words = [(text, conf)].
    """
    tmp = tempfile.mkdtemp(prefix="rocr_")
    try:
        in_path = os.path.join(tmp, "in.png")
        out_base = os.path.join(tmp, "out")
        if not cv2.imwrite(in_path, img):
            return [], -3, "imwrite failed", 0

        cmd = [TESSERACT_CMD, in_path, out_base, "--psm", str(psm), "--dpi", str(dpi)]
        if whitelist:
            cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
        cmd.append("tsv")

        t0 = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return [], -2, "timeout", 20000
        ms = int((time.time() - t0) * 1000)

        words = []
        tsv_path = out_base + ".tsv"
        if os.path.exists(tsv_path):
            with open(tsv_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f.read().splitlines()[1:]:
                    p = line.split("\t")
                    if len(p) == 12 and p[0] == "5" and p[11].strip():
                        try:
                            conf = max(0.0, float(p[10]))
                        except ValueError:
                            conf = 0.0
                        words.append((p[11].strip(), conf))
        return words, proc.returncode, proc.stderr.strip()[:80], ms
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ocr_label_crop(crop):
    """Returns (tier or None, text). Tries several preprocessings."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, th = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    texts = []
    for img in (big, th, cv2.bitwise_not(th)):
        img = pad(img, 20)
        for psm in (7, 6):
            words, _, _, _ = tess(img, psm)
            text = " ".join(t for t, _ in words)
            if text:
                texts.append(text)
            tier = label_tier_from_text(text)
            if tier is not None:
                return tier, text
    return None, " | ".join(texts)


def label_tier_from_text(text):
    """'6 PRIZE', '6th PRIZE', '16 EPRIZE' -> 6"""
    m = re.search(r"(\d)(?:ST|ND|RD|TH)?\s*[A-Z]{0,2}\s*PRIZE", text.upper())
    if m and int(m.group(1)) in PRIZE_TIERS:
        return int(m.group(1))
    return None


def read_label(frame, roi):
    """Returns (tier, crop, text). Tries the marked ROI, then a padded version."""
    H, W = frame.shape[:2]
    crop_out = None
    texts = []
    for cand in (roi, pad_roi(roi, 30)):
        x, y, w, h = clip_roi(cand, W, H)
        if w <= 0 or h <= 0:
            continue
        crop = frame[y:y + h, x:x + w]
        if crop_out is None:
            crop_out = crop
        tier, text = ocr_label_crop(crop)
        if text:
            texts.append(text)
        if tier is not None:
            return tier, crop, text
    return None, crop_out, " | ".join(texts)


def read_label_multi(frames, roi):
    votes = Counter()
    crop_out = None
    texts = []
    for off, frame in frames:
        tier, crop, text = read_label(frame, roi)
        if crop_out is None and crop is not None and crop.size:
            crop_out = crop
        if text:
            texts.append(f"{off:+.0f}s:{text[:50]}")
        if tier is not None:
            votes[tier] += 1
    tier = votes.most_common(1)[0][0] if votes else None
    return tier, crop_out, " || ".join(texts[:3]), votes


def split_digits(box_bgr):
    """
    Split a roller box into DIGITS glyphs (grayscale, dark digit on light).
    Returns (glyphs, method).
    """
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
        aspect = h / w
        if not (1.1 <= aspect <= 4.0):
            continue
        if a / float(w * h) < 0.12:          # outlines are thin, digits are filled
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
        g = inner[max(0, y0 - 3):min(ih, y1 + 3), max(0, x0 - 3):min(iw, x1 + 3)]
        glyphs.append(g)
    return glyphs, method


def glyph_variants(g):
    """[(name, image)] for one glyph. Dark digits on white, padded."""
    if g is None or g.size == 0:
        return []
    big = cv2.resize(g, None, fx=GLYPH_SCALE, fy=GLYPH_SCALE, interpolation=cv2.INTER_CUBIC)
    big = cv2.GaussianBlur(big, (3, 3), 0)
    _, otsu = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    p = pad(otsu, 40)
    return [("otsu", p), ("inv", cv2.bitwise_not(p)), ("gray", pad(big, 40))]


def box_variants(bgr):
    """[(name, image)] for the whole box."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, otsu = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    p = pad(otsu, 30)
    return [("otsu", p), ("inv", cv2.bitwise_not(p))]


# ============================================================
# MATCHING
# ============================================================

def evaluate(votes, all_numbers, label_tier):
    """
    votes: list (per digit position) of {digit: weight}
    all_numbers: {number_string: tier}
    Ranks every database number by per-digit log-likelihood.
    """
    res = {"status": "no_read", "number": None, "tier": None,
           "margin": 0.0, "exact": False, "argmax": ""}
    if not all_numbers or sum(sum(d.values()) for d in votes) <= 0:
        return res

    probs, argmax = [], ""
    for d in votes:
        s = sum(d.values()) + 10 * EPS
        probs.append({k: (d.get(k, 0.0) + EPS) / s for k in DIGIT_CHARS})
        argmax += (max(DIGIT_CHARS, key=lambda k: d.get(k, 0.0)) if d else "?")

    ranked = sorted(
        ((sum(math.log(probs[p][num[p]]) for p in range(DIGITS)), num, tier)
         for num, tier in all_numbers.items()),
        reverse=True,
    )
    best_ll, best_num, best_tier = ranked[0]
    runner_ll = ranked[1][0] if len(ranked) > 1 else best_ll - 99.0
    margin = best_ll - runner_ll

    if label_tier is not None and best_tier != label_tier:
        status = "other_tier"
    elif margin >= MIN_MARGIN:
        status = "match"
    else:
        status = "unsure"

    res.update(status=status, number=best_num, tier=best_tier,
               margin=round(margin, 2), exact=argmax in all_numbers, argmax=argmax)
    return res


# ============================================================
# VIEWER
# ============================================================

class Viewer:
    def __init__(self, video_path, rollers, prize_numbers, draw_info, label_roi):
        self.video_path = video_path
        self.rollers = rollers
        self.n = len(rollers)
        self.prize_numbers = prize_numbers
        self.all_numbers = {num: tier for tier, nums in prize_numbers.items() for num in nums}
        self.draw_info = draw_info
        self.label_roi = label_roi

        self.base_t = TIMESTAMP_SEC
        self.cur = 0
        self.auto = True
        self.delay = STEP_MS
        self.gen = None
        self.done = [False] * self.n
        self.done_at = 0.0
        self.canvas = None

        self.load_frames()
        self.views = [self.blank_view() for _ in range(self.n)]

    # ---------- state ----------

    def blank_view(self):
        return {
            "status": "pending", "number": None, "tier": None, "margin": 0.0,
            "exact": False, "argmax": "",
            "votes": [defaultdict(float) for _ in range(DIGITS)],
            "glyphs": None, "split": "", "crop": None,
            "pre": None, "pre_label": "", "log": [], "calls": 0,
        }

    def load_frames(self):
        self.frames = []
        for off in sorted(SAMPLE_OFFSETS_SEC, key=lambda o: (abs(o), o)):
            t = self.base_t + off
            if t < 0:
                continue
            f = read_frame(self.video_path, t)
            if f is not None:
                self.frames.append((off, f))
        if not self.frames:
            raise SystemExit("Could not read any video frame")
        self.frame = self.frames[0][1]

        H, W = self.frame.shape[:2]
        print(f"Frame {W}x{H}. Label ROI requested={self.label_roi} "
              f"clipped={clip_roi(self.label_roi, W, H)}")

        (self.label_tier, self.label_crop,
         self.label_text, self.label_votes) = read_label_multi(self.frames, self.label_roi)

        os.makedirs(DEBUG_DIR, exist_ok=True)
        if self.label_crop is not None and self.label_crop.size:
            cv2.imwrite(f"{DEBUG_DIR}/prize_label.png", self.label_crop)
        print(f"On-screen label votes: {dict(self.label_votes)}  -> tier {self.label_tier}")
        print(f"Label OCR: {self.label_text[:160] or '-'}")

    def reset(self, idx=None):
        if self.gen is not None:
            self.gen.close()
            self.gen = None
        for i in (range(self.n) if idx is None else [idx]):
            self.done[i] = False
            self.views[i] = self.blank_view()

    def goto(self, idx):
        if self.gen is not None:
            self.gen.close()
            self.gen = None
        if not self.done[self.cur]:
            self.views[self.cur] = self.blank_view()
        self.cur = max(0, min(idx, self.n - 1))

    def scrub(self, seconds):
        self.base_t = max(0, self.base_t + seconds)
        self.load_frames()
        self.reset()
        print(f"\nFrames moved to {fmt_time(self.base_t)}")

    # ---------- OCR (one tesseract call per yield) ----------

    def note(self, v, label, rc, ms, result, conf, err, img):
        v["pre"], v["pre_label"] = img, label
        v["calls"] += 1
        line = f"{label:<22} rc{rc:>3} {ms:>5}ms '{(result or '-')[:8]}' {conf:>4.0f}"
        if rc != 0 and err:
            line += f" {err[:18]}"
        v["log"] = (v["log"] + [line])[-10:]

        res = evaluate(v["votes"], self.all_numbers, self.label_tier)
        v.update(res)
        if res["status"] == "no_read":
            v["status"] = "reading"

    def run_roller(self, idx):
        v = self.views[idx]
        roi = self.rollers[idx]
        x, y = int(roi["x"]), int(roi["y"])
        w, h = int(roi["width"]), int(roi["height"])
        v["status"] = "reading"

        for off, frame in self.frames:
            H, W = frame.shape[:2]
            crop = frame[max(0, y):min(H, y + h), max(0, x):min(W, x + w)]
            if crop.size == 0:
                continue
            if v["crop"] is None:
                v["crop"] = crop

            glyphs, method = split_digits(crop)
            if v["glyphs"] is None and glyphs:
                v["glyphs"], v["split"] = glyphs, method

            for pos, g in enumerate(glyphs):
                for vname, img in glyph_variants(g):
                    words, rc, err, ms = tess(img, GLYPH_PSM, DIGIT_WHITELIST)
                    digit, conf = first_digit(words)
                    if digit:
                        v["votes"][pos][digit] += weight(conf)
                    self.note(v, f"{off:+.0f}s g{pos + 1} {vname}",
                              rc, ms, digit, conf, err, img)
                    yield

            for vname, img in box_variants(crop):
                words, rc, err, ms = tess(img, WHOLE_BOX_PSM, DIGIT_WHITELIST)
                text = re.sub(r"\D", "", " ".join(t for t, _ in words))
                if len(text) == DIGITS:
                    for pos, ch in enumerate(text):
                        v["votes"][pos][ch] += WHOLE_BOX_WEIGHT
                self.note(v, f"{off:+.0f}s box {vname}",
                          rc, ms, text, 0, err, img)
                yield

        if v["calls"] == 0 or sum(sum(d.values()) for d in v["votes"]) == 0:
            v["status"] = "no_read"

    # ---------- per-roller finish ----------

    def on_finish(self, idx):
        v = self.views[idx]
        os.makedirs(DEBUG_DIR, exist_ok=True)
        tag = f"{DEBUG_DIR}/roller_{idx + 1:02d}"
        if v["crop"] is not None:
            cv2.imwrite(tag + "_box.png", v["crop"])
        for k, g in enumerate(v["glyphs"] or []):
            cv2.imwrite(f"{tag}_glyph{k + 1}.png", g)
        if v["pre"] is not None:
            cv2.imwrite(tag + "_last_pre.png", v["pre"])

        tier_s = f"{v['tier']}th" if v["tier"] else "-"
        print(f"R{idx + 1:02d} | split {v['split'] or '-'} | best {v['number'] or '-'} "
              f"tier {tier_s} margin {v['margin']:.1f} | {v['status'].upper()} | "
              f"digits {digit_summary(v['votes'])} | calls {v['calls']}")

    # ---------- main loop ----------

    def tick(self):
        if not self.done[self.cur]:
            if self.gen is None:
                self.gen = self.run_roller(self.cur)
            try:
                next(self.gen)
            except StopIteration:
                self.gen = None
                self.done[self.cur] = True
                self.done_at = time.time()
                self.on_finish(self.cur)
        elif self.auto and time.time() - self.done_at > HOLD_SEC:
            if self.cur < self.n - 1:
                self.goto(self.cur + 1)
            else:
                self.auto = False
                self.print_summary()

    # ---------- drawing ----------

    def draw(self):
        c = np.full((CANVAS_H, CANVAS_W, 3), 28, np.uint8)
        v = self.views[self.cur]
        H, W = self.frame.shape[:2]

        # Left top: frame with all boxes
        disp = cv2.resize(self.frame, (FRAME_W, FRAME_H))
        sx, sy = FRAME_W / W, FRAME_H / H
        for i, roi in enumerate(self.rollers):
            col = STATUS_COLORS[self.views[i]["status"]]
            x0, y0 = int(roi["x"] * sx), int(roi["y"] * sy)
            x1 = int((roi["x"] + roi["width"]) * sx)
            y1 = int((roi["y"] + roi["height"]) * sy)
            cv2.rectangle(disp, (x0, y0), (x1, y1), col, 3 if i == self.cur else 1)
            put(disp, f"R{i + 1}", (x0 + 2, max(12, y0 - 4)), 0.4, col)
        lx, ly, lw, lh = clip_roi(self.label_roi, W, H)
        if lw > 0 and lh > 0:
            cv2.rectangle(disp, (int(lx * sx), int(ly * sy)),
                          (int((lx + lw) * sx), int((ly + lh) * sy)), (255, 255, 255), 1)
        c[0:FRAME_H, 0:FRAME_W] = disp

        # Status lines under the frame
        offs = ", ".join(f"{o:+.0f}s" for o, _ in self.frames)
        lab = f"{self.label_tier}th" if self.label_tier else "not read"
        put(c, f"Video {fmt_time(self.base_t)}  frames [{offs}]  Roller {self.cur + 1}/{self.n}  "
               f"on-screen prize: {lab}  auto {'ON' if self.auto else 'OFF'}  step {self.delay}ms",
            (10, 560), 0.45, (255, 255, 255))
        tier_s = f"{v['tier']}th" if v["tier"] else "-"
        put(c, f"Status: {v['status'].upper()}   Best: {v['number'] or '-'}   tier {tier_s}   "
               f"margin {v['margin']:.1f}   exact {'yes' if v['exact'] else 'no'}   "
               f"argmax {v['argmax'] or '-'}",
            (10, 586), 0.45, STATUS_COLORS[v["status"]])
        put(c, f"Attempt: {v['pre_label'] or '-'}   calls {v['calls']}   "
               f"digits: {digit_summary(v['votes'])}", (10, 612), 0.42, (200, 200, 200))

        # Bottom-left: results grid
        for i in range(self.n):
            col_i, row = i // ROWS_PER_COLUMN, i % ROWS_PER_COLUMN
            vv = self.views[i]
            x = 10 + col_i * 320
            yy = 650 + row * 36
            if i == self.cur:
                cv2.rectangle(c, (x - 4, yy - 16), (x + 310, yy + 10), (0, 255, 255), 1)
            t_s = f"{vv['tier']}th" if vv["tier"] else "-"
            txt = (f"R{i + 1:<2} {vv['number'] or '----'}  tier {t_s:<4} "
                   f"m {vv['margin']:>4.1f}  {vv['status']}")
            put(c, txt, (x, yy), 0.42, STATUS_COLORS[vv["status"]])

        # Right: source crop
        put(c, f"Source crop (split: {v['split'] or '-'})", (980, 22), 0.5, (255, 255, 255))
        place(c, fit(v["crop"], 600, 180), 980, 30)

        # Right: four glyphs, each read separately
        put(c, "Digit glyphs (each read separately)", (980, 228), 0.5, (255, 255, 255))
        for pos in range(DIGITS):
            gx = 980 + pos * 150
            if v["glyphs"] and pos < len(v["glyphs"]):
                place(c, fit(v["glyphs"][pos], 130, 110), gx, 240)
            if v["votes"][pos]:
                k = max(v["votes"][pos], key=v["votes"][pos].get)
                share = v["votes"][pos][k] / sum(v["votes"][pos].values())
                put(c, f"pos{pos + 1}: {k} ({share:.0%})", (gx, 370), 0.42)
            else:
                put(c, f"pos{pos + 1}: -", (gx, 370), 0.42)

        # Right: last preprocessed image sent to Tesseract
        put(c, "Last preprocessed image sent to Tesseract", (980, 392), 0.45, (255, 255, 255))
        place(c, fit(v["pre"], 600, 100), 980, 402)

        # Right: on-screen label
        put(c, "On-screen prize label", (980, 524), 0.5, (255, 255, 255))
        place(c, fit(self.label_crop, 400, 60), 980, 534)
        put(c, f"label -> tier {self.label_tier or '-'}   votes {dict(self.label_votes)}",
            (980, 612), 0.4, (200, 200, 200))

        # Right: attempt log
        put(c, "Attempts (live)", (980, 636), 0.5, (255, 255, 255))
        for k, line in enumerate(v["log"]):
            put(c, line[:90], (980, 656 + k * 16), 0.37, (200, 200, 200))

        # Right: summary
        counts = Counter(x["status"] for x in self.views)
        put(c, f"match {counts['match']}  unsure {counts['unsure']}  "
               f"other tier {counts['other_tier']}  no read {counts['no_read']}  "
               f"pending {counts['pending'] + counts['reading']}",
            (980, 834), 0.42, (255, 255, 255))
        put(c, "SPACE auto  n/p next/prev  r retry  a run all  +/- speed",
            (980, 852), 0.38, (180, 180, 180))
        put(c, ".  ,  shift frames +1s/-1s   s snapshot   q quit",
            (980, 870), 0.38, (180, 180, 180))

        self.canvas = c
        return c

    # ---------- input ----------

    def handle_key(self, key):
        if key in (ord("q"), 27):
            return False
        if key == ord(" "):
            self.auto = not self.auto
        elif key == ord("n"):
            self.goto(self.cur + 1)
        elif key == ord("p"):
            self.goto(self.cur - 1)
        elif key == ord("r"):
            self.reset(self.cur)
        elif key == ord("a"):
            self.reset()
            self.goto(0)
            self.auto = True
        elif key in (ord("+"), ord("=")):
            self.delay = min(2000, self.delay + 50)
        elif key == ord("-"):
            self.delay = max(20, self.delay - 50)
        elif key == ord("."):
            self.scrub(+1)
        elif key == ord(","):
            self.scrub(-1)
        elif key == ord("s"):
            os.makedirs(DEBUG_DIR, exist_ok=True)
            path = f"{DEBUG_DIR}/ui_roller_{self.cur + 1:02d}.png"
            cv2.imwrite(path, self.canvas)
            print(f"Snapshot saved: {path}")
        return True

    def run(self):
        cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)
        print("Keys: SPACE auto | n/p next/prev | r retry | a run all | "
              "+/- speed | ./, frame | s snapshot | q quit")
        while True:
            self.tick()
            cv2.imshow(WIN, self.draw())
            key = cv2.waitKey(max(1, self.delay)) & 0xFF
            if not self.handle_key(key):
                break
        cv2.destroyAllWindows()

    # ---------- output ----------

    def print_summary(self):
        print("\n" + "=" * 80)
        print(f"RESULTS   on-screen prize: {self.label_tier or 'not read'}")
        print("=" * 80)
        tiers = Counter(v["tier"] for v in self.views if v["tier"])
        print(f"Tier distribution of best reads: {dict(tiers)}\n")
        print(f"{'R#':<4}{'Best':<7}{'Tier':<7}{'Margin':<8}{'Exact':<7}{'Status':<12}Digits")
        print("-" * 80)
        for i, v in enumerate(self.views, 1):
            t_s = f"{v['tier']}th" if v["tier"] else "-"
            print(f"{i:<4}{v['number'] or '-':<7}{t_s:<7}{v['margin']:<8.1f}"
                  f"{'yes' if v['exact'] else 'no':<7}{v['status'].upper():<12}"
                  f"{digit_summary(v['votes'])}")

    def finish(self):
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            fields = ["roller_id", "x", "y", "width", "height", "onscreen_tier",
                      "best_number", "best_tier", "margin", "exact", "status",
                      "argmax", "digits", "calls"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for i, v in enumerate(self.views):
                roi = self.rollers[i]
                w.writerow({
                    "roller_id": i + 1, "x": roi["x"], "y": roi["y"],
                    "width": roi["width"], "height": roi["height"],
                    "onscreen_tier": self.label_tier or "",
                    "best_number": v["number"] or "",
                    "best_tier": v["tier"] or "",
                    "margin": v["margin"], "exact": v["exact"],
                    "status": v["status"], "argmax": v["argmax"],
                    "digits": digit_summary(v["votes"]), "calls": v["calls"],
                })

        payload = {
            "draw": self.draw_info,
            "onscreen_tier": self.label_tier,
            "label_votes": dict(self.label_votes),
            "rollers": [{
                "roller_id": i + 1,
                "best_number": v["number"],
                "best_tier": v["tier"],
                "margin": v["margin"],
                "exact": v["exact"],
                "status": v["status"],
                "split": v["split"],
                "digit_votes": [dict(d) for d in v["votes"]],
            } for i, v in enumerate(self.views)],
        }
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\nSaved {OUTPUT_CSV} and {OUTPUT_JSON}")


# ============================================================
# MAIN
# ============================================================

DIGIT_WHITELIST = DIGIT_CHARS


def main():
    videos = sorted(Path(".").glob("*.mp4"))
    if not videos:
        raise SystemExit("No .mp4 file found in this folder")
    video = str(videos[0])
    print(f"Video: {videos[0].name}")

    if not os.path.exists(TESSERACT_CMD):
        raise SystemExit(f"Tesseract not found: {TESSERACT_CMD}")
    ver = subprocess.run([TESSERACT_CMD, "--version"], capture_output=True, text=True)
    print(f"Tesseract: {(ver.stdout or ver.stderr).splitlines()[0]}")

    with open(ROLLER_FILE, "r", encoding="utf-8") as f:
        rollers = json.load(f).get("roller_groups", [])
    print(f"Loaded {len(rollers)} roller boxes")

    with open(LABEL_FILE, "r", encoding="utf-8") as f:
        label_json = json.load(f)
    print(f"{LABEL_FILE} roi: {label_json.get('roi')}")
    r = label_json["roi"]
    label_roi = (int(r["x"]), int(r["y"]), int(r["width"]), int(r["height"]))

    client, prize_numbers, draw_info = load_prizes(video)
    try:
        viewer = Viewer(video, rollers, prize_numbers, draw_info, label_roi)
        viewer.run()
        viewer.finish()
    finally:
        client.close()


if __name__ == "__main__":
    os.makedirs(DEBUG_DIR, exist_ok=True)
    main()
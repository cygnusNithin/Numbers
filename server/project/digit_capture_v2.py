"""
font_capture.py
Capture the 0-9 digit font from a stopped one-roller close-up.

Mark a digit and the check runs at the same time: saved fonts and OCR.
Your key press is the label that gets saved. The guess is not saved.
Or type all four digits you see (e.g. 7484) and press Enter to save the 4 boxes.

The full board is rejected. Digits there are too small.
Saved to digit_fonts/0 .. digit_fonts/9.

No threading. No cv2.imshow. No debug images outside digit_fonts.
Run: python font_capture.py
"""
import csv
from itertools import combinations
from pathlib import Path
from tkinter import (Tk, Frame, Label, Button, Canvas, Text, Entry, StringVar,
                     DoubleVar, messagebox, filedialog, END, DISABLED, NORMAL)
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

FONT_W, FONT_H = 32, 48
ANALYSIS_W = 640
CANVAS_W, CANVAS_H = 900, 506
HOUSE_W, HOUSE_H = 500, 250
NUM_DIGITS = 4
MATCH_MIN = 0.50

YELLOW_LO = (15, 90, 120)
YELLOW_HI = (40, 255, 255)
CLOSEUP_MIN_FRAC = 0.008
CLOSEUP_DOMINANT = 2.5
MULTI_TAGS = 4
HOUSING_WHITE_MIN = 0.22

HERE = Path(__file__).resolve().parent
FONT_DIR = HERE / "digit_fonts"


# --------------------------------------------------------------------------- helpers
def fmt_hms(sec):
    sec = max(0, int(sec))
    return "%02d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


def parse_time(s):
    try:
        sec = 0.0
        for p in str(s).strip().split(":"):
            sec = sec * 60 + float(p)
        return max(0.0, sec)
    except Exception:
        return 0.0


def to_gray(img):
    if img is None or getattr(img, "size", 0) == 0:
        return None
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def resize_w(img, w):
    h = max(1, int(img.shape[0] * w / img.shape[1]))
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)


def upscale_to_height(gray, target_h):
    f = target_h / float(max(1, gray.shape[0]))
    return cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)


def imread_gray(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)


def imread_color(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def clean_board(img):
    """Remove yellow aging tint and soft shadows from a crop.

    Brightest-channel projection erases colored stains (yellowed plastic is
    bright in R/G, dark in B; black ink is dark in every channel, so it stays).
    Flat-field division by a large-scale blur then evens out shadows and
    uneven yellowing: background -> ~white, strokes survive untouched.
    Returns grayscale.
    """
    if img is None or getattr(img, "size", 0) == 0:
        return None
    if img.ndim == 3:
        b, g, r = cv2.split(img)
        gray = cv2.max(cv2.max(b, g), r)     # yellow/red stains vanish, ink stays dark
    else:
        gray = img
    h = gray.shape[0]
    sigma = max(3.0, h / 8.0)                # bigger than a stroke, smaller than a shadow
    bg = cv2.GaussianBlur(gray, (0, 0), sigma, sigma)
    return cv2.divide(gray, bg, scale=255)   # slow shading -> white, ink stays dark


def imwrite_png(path, img):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(str(path))
    return bool(ok)


def box_iou(a, b):
    ax, ay, aw, ah = a[:4]
    bx, by, bw, bh = b[:4]
    iw = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / float(union) if union > 0 else 0.0


# --------------------------------------------------------------------------- glyph cleaning
def remove_frame_lines(inv):
    """Remove long border lines near the crop edges. A centred 1 is not a frame line."""
    h, w = inv.shape
    if h < 8 or w < 8:
        return inv
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(w * 0.68)), 1))
    horiz = cv2.morphologyEx(inv, cv2.MORPH_OPEN, hk)
    hmask = np.zeros_like(inv)
    hmask[:max(1, int(h * 0.14)), :] = 255
    hmask[min(h - 1, int(h * 0.86)):, :] = 255
    horiz = cv2.bitwise_and(horiz, hmask)
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(3, int(h * 0.68))))
    vert = cv2.morphologyEx(inv, cv2.MORPH_OPEN, vk)
    vmask = np.zeros_like(inv)
    vmask[:, :max(1, int(w * 0.14))] = 255
    vmask[:, min(w - 1, int(w * 0.86)):] = 255
    vert = cv2.bitwise_and(vert, vmask)
    return cv2.subtract(inv, cv2.dilate(horiz | vert, np.ones((2, 2), np.uint8)))


def pick_glyph(ink):
    """Keep only the main, central digit. Thin straight bars (cell borders),
    edge blobs and shadows are dropped. Returns (mask, clean)."""
    h, w = ink.shape
    n, labels, stats, cents = cv2.connectedComponentsWithStats(ink, connectivity=8)
    best, best_score = None, 0.0
    for i in range(1, n):
        x, y, cw, ch, a = [int(v) for v in stats[i]]
        if ch < 0.30 * h or a < 0.004 * h * w:
            continue
        if cw >= 0.96 * w:                       # band across the whole crop
            continue
        if cw < 0.13 * ch and a > 0.70 * cw * ch:  # straight vertical bar = border
            continue
        cx, cy = cents[i]
        off = abs(cx - w / 2.0) / w + 0.5 * abs(cy - h / 2.0) / h
        score = a * max(0.05, 1.0 - 1.6 * off)
        if x <= 0 or x + cw >= w:                # touches left/right edge
            score *= 0.3
        if score > best_score:
            best, best_score = i, score
    if best is None:
        return None, False
    bx, by, bw, bh, ba = [int(v) for v in stats[best]]
    keep = [best]
    for i in range(1, n):                        # broken strokes of the same digit
        if i == best:
            continue
        x, y, cw, ch, a = [int(v) for v in stats[i]]
        if a < 0.03 * ba:
            continue
        ov = min(x + cw, bx + bw) - max(x, bx)
        if ov >= 0.6 * cw and y >= by - 0.1 * bh and y + ch <= by + bh + 0.1 * bh:
            keep.append(i)
    mask = np.isin(labels, keep).astype(np.uint8) * 255
    clean = bx > 0 and bx + bw < w and bh >= 0.40 * h
    return mask, clean


def normalize_font(img):
    gray = clean_board(img)
    if gray is None or gray.shape[0] < 8 or gray.shape[1] < 4:
        return None
    if gray.shape[0] < 96:
        gray = upscale_to_height(gray, 96)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    t_otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    chosen = None
    for t in (t_otsu, t_otsu * 0.85, t_otsu * 0.70, t_otsu * 0.55):
        ink = (gray < t).astype(np.uint8) * 255
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        ink = remove_frame_lines(ink)
        mask, clean = pick_glyph(ink)
        if mask is None:
            continue
        if chosen is None or clean:
            chosen = mask
        if clean:
            break
    if chosen is None:
        return None
    ys, xs = np.where(chosen > 0)
    if len(xs) == 0:
        return None
    glyph = chosen[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    gh, gw = glyph.shape
    if gh < 6 or gw < 2:
        return None
    nh = FONT_H - 8
    nw = max(1, min(FONT_W - 8, int(round(gw * nh / float(gh)))))
    resized = cv2.resize(glyph, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.full((FONT_H, FONT_W), 255, np.uint8)
    x0 = (FONT_W - nw) // 2
    canvas[4:4 + nh, x0:x0 + nw] = 255 - resized
    dark = int(np.count_nonzero(canvas < 128))
    if dark < 8 or dark > 0.62 * canvas.size:
        return None
    return canvas


def score_pair(a, b):
    if a is None or b is None or a.size == 0 or b.size == 0:
        return -1.0
    aa = cv2.resize(a, (FONT_W, FONT_H), interpolation=cv2.INTER_AREA)
    bb = cv2.resize(b, (FONT_W, FONT_H), interpolation=cv2.INTER_AREA)
    try:
        s = float(cv2.matchTemplate(aa, bb, cv2.TM_CCOEFF_NORMED)[0, 0])
    except Exception:
        return -1.0
    return -1.0 if np.isnan(s) else s


# --------------------------------------------------------------------------- font store
class DigitStore:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.index_csv = self.folder / "index.csv"
        self.samples = {str(i): [] for i in range(10)}
        self.paths = {str(i): [] for i in range(10)}
        self.last = []
        self.reload()

    def reload(self):
        self.samples = {str(i): [] for i in range(10)}
        self.paths = {str(i): [] for i in range(10)}
        if not self.folder.exists():
            return 0
        n = 0
        for d in range(10):
            sub = self.folder / str(d)
            if not sub.exists():
                continue
            for p in sorted(sub.glob("*.png")):
                if p.name.endswith("_raw.png"):
                    continue
                img = imread_gray(p)
                if img is None:
                    continue
                img = cv2.resize(img, (FONT_W, FONT_H), interpolation=cv2.INTER_AREA)
                self.samples[str(d)].append(img)
                self.paths[str(d)].append(p)
                n += 1
        return n

    def counts(self):
        return {d: len(self.samples[d]) for d in self.samples}

    def total(self):
        return sum(len(v) for v in self.samples.values())

    def match(self, img):
        norm = img if (img is not None and img.shape[:2] == (FONT_H, FONT_W)) else normalize_font(img)
        best, second = ("", -1.0), ("", -1.0)
        if norm is None or self.total() == 0:
            return "", -1.0, "", -1.0, norm
        per_digit = {}
        for digit, samples in self.samples.items():
            for sample in samples:
                s = score_pair(norm, sample)
                if s > per_digit.get(digit, -1.0):
                    per_digit[digit] = s
        for digit, s in per_digit.items():
            if s > best[1]:
                second, best = best, (digit, s)
            elif s > second[1]:
                second = (digit, s)
        return best[0], best[1], second[0], second[1], norm

    def save(self, digit, raw, norm, meta):
        digit = str(digit)
        sub = self.folder / digit
        sub.mkdir(parents=True, exist_ok=True)
        n = 1
        while (sub / ("%04d.png" % n)).exists():
            n += 1
        norm_path = sub / ("%04d.png" % n)
        raw_path = sub / ("%04d_raw.png" % n)
        imwrite_png(norm_path, norm)
        if raw is not None and getattr(raw, "size", 0) > 0:
            imwrite_png(raw_path, raw)
        new = not self.index_csv.exists()
        with open(self.index_csv, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["digit", "file", "time", "video"])
            w.writerow([digit, norm_path.name, meta.get("time", ""), meta.get("video", "")])
        self.samples[digit].append(cv2.resize(norm, (FONT_W, FONT_H)))
        self.paths[digit].append(norm_path)
        self.last.append((digit, norm_path, raw_path))
        return norm_path

    def rebuild_index(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        rows = []
        for digit in map(str, range(10)):
            for path in sorted((self.folder / digit).glob("*.png")):
                if not path.name.endswith("_raw.png"):
                    rows.append((digit, path.name, "", ""))
        with open(self.index_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["digit", "file", "time", "video"])
            writer.writerows(rows)

    def undo(self):
        if not self.last:
            return None
        digit, norm_path, raw_path = self.last.pop()
        for p in (norm_path, raw_path):
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        self.reload()
        self.rebuild_index()
        return digit

    def renormalize_all(self):
        """Rebuild every saved font from its _raw.png with the current pipeline."""
        ok, failed = 0, []
        for d in range(10):
            sub = self.folder / str(d)
            if not sub.exists():
                continue
            for raw in sorted(sub.glob("*_raw.png")):
                img = imread_color(raw)
                norm = normalize_font(img) if img is not None else None
                if norm is None:
                    failed.append("%d/%s" % (d, raw.name))
                    continue
                imwrite_png(raw.with_name(raw.name.replace("_raw", "")), norm)
                ok += 1
        self.reload()
        return ok, failed

    def self_check(self):
        """Leave-one-out: every sample must match its own digit best."""
        errors, total = [], 0
        for d, samples in self.samples.items():
            for idx, s in enumerate(samples):
                best = ("", -1.0)
                for d2, others in self.samples.items():
                    for j, t in enumerate(others):
                        if d2 == d and j == idx:
                            continue
                        sc = score_pair(s, t)
                        if sc > best[1]:
                            best = (d2, sc)
                total += 1
                if best[0] and best[0] != d:
                    errors.append((d, self.paths[d][idx].name, best[0], best[1]))
        return total, errors


# --------------------------------------------------------------------------- scene detection
def find_yellow_labels(small):
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    mask = cv2.morphologyEx(cv2.inRange(hsv, YELLOW_LO, YELLOW_HI), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    W = mask.shape[1]
    labels = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 30 or w > 0.45 * W:
            continue
        if not 0.55 <= w / max(1, h) <= 1.9 or a / float(w * h) < 0.45:
            continue
        labels.append((int(x), int(y), int(w), int(h)))
    return labels


def similar_tag_count(labels):
    if len(labels) < 3:
        return 0
    areas = np.array([w * h for _, _, w, h in labels], float)
    med = float(np.median(areas))
    return int(np.sum((areas > 0.45 * med) & (areas < 2.2 * med)))


def housing_box(label, W, H):
    x, y, w, h = label
    cy = y + h / 2.0
    x1, x2 = int(x + w * 0.85), int(min(W - 1, x + w * 7.2))
    y1, y2 = int(max(0, cy - h * 1.7)), int(min(H - 1, cy + h * 1.7))
    if x2 - x1 < w * 2 or y2 - y1 < h:
        return None
    return x1, y1, x2, y2


def white_fraction(img, box):
    x1, y1, x2, y2 = box
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    m = cv2.inRange(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV), (0, 0, 140), (180, 80, 255))
    return float(np.count_nonzero(m)) / float(m.size)


def refine_housing_box(img, estimate, label):
    """Snap the tag-based estimate to the large white roller enclosure."""
    ex1, ey1, ex2, ey2 = estimate
    _lx, _ly, lw, lh = label
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, (0, 0, 140), (180, 100, 255))
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
    contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < lw * 2.5 or h < lh * 1.2 or not 1.25 <= w / float(max(1, h)) <= 3.8:
            continue
        overlap_w = max(0, min(x + w, ex2) - max(x, ex1))
        overlap_h = max(0, min(y + h, ey2) - max(y, ey1))
        if overlap_w * overlap_h < 0.55 * w * h:
            continue
        score = cv2.contourArea(contour)
        if best is None or score > best[0]:
            best = (score, (x, y, x + w, y + h))
    return best[1] if best is not None else estimate


def classify_frame(frame):
    small = resize_w(frame, ANALYSIS_W)
    H, W = small.shape[:2]
    labels = find_yellow_labels(small)
    multi = similar_tag_count(labels)
    close = None
    if multi < MULTI_TAGS:
        big = [l for l in labels if l[2] * l[3] >= CLOSEUP_MIN_FRAC * W * H]
        big.sort(key=lambda l: l[2] * l[3], reverse=True)
        if big and (len(big) == 1 or big[0][2] * big[0][3] >= CLOSEUP_DOMINANT * big[1][2] * big[1][3]):
            hb = housing_box(big[0], W, H)
            if hb and white_fraction(small, hb) >= HOUSING_WHITE_MIN:
                close = {"label": big[0], "housing": refine_housing_box(small, hb, big[0])}
    if multi >= MULTI_TAGS:
        scene = "multi"
    elif close is not None:
        scene = "closeup"
    else:
        scene = "other"
    return {"scene": scene, "labels": labels, "multi": multi, "close": close}


# --------------------------------------------------------------------------- digit boxes
def fallback_boxes(shape):
    h, w = shape[:2]
    x0, x1 = int(w * 0.05), int(w * 0.95)
    y0, y1 = int(h * 0.20), int(h * 0.82)
    cell_w = max(4, x1 - x0) / 4.0
    boxes = []
    for i in range(4):
        xa = int(x0 + i * cell_w + cell_w * 0.16)
        xb = int(x0 + (i + 1) * cell_w - cell_w * 0.16)
        ya = int(y0 + (y1 - y0) * 0.08)
        yb = int(y1 - (y1 - y0) * 0.06)
        if xb - xa >= 4 and yb - ya >= 8:
            boxes.append((xa, ya, xb - xa, yb - ya))
    return boxes


def digit_candidates(gray):
    """Dark blobs shaped like a digit. The opening cuts thin cell borders
    away from the thick digit strokes so they do not merge."""
    h, w = gray.shape[:2]
    k = max(3, int(round(h * 0.012)))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    found = []
    for t in (55, 70, 85, 100, 115, 130):
        dark = (gray < t).astype(np.uint8) * 255
        dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel)
        n, _l, stats, _c = cv2.connectedComponentsWithStats(dark, connectivity=8)
        for i in range(1, n):
            x, y, bw, bh, area = [int(v) for v in stats[i]]
            if not (0.14 * h <= bh <= 0.55 * h):
                continue
            if not (0.02 * w <= bw <= 0.17 * w):
                continue
            if not (0.18 <= bw / float(bh) <= 0.95):
                continue
            if area < 0.22 * bw * bh:
                continue
            cx, cy = x + bw / 2.0, y + bh / 2.0
            if not (0.05 * w <= cx <= 0.95 * w and 0.18 * h <= cy <= 0.82 * h):
                continue
            found.append((x, y, bw, bh, area, t))
    found.sort(key=lambda b: abs(b[5] - 90))   # prefer the threshold that usually works
    uniq = []
    for b in found:
        if all(box_iou(b, u) < 0.6 for u in uniq):
            uniq.append(b)
    uniq.sort(key=lambda b: b[4], reverse=True)
    return uniq[:16]


def select_four(cands, h):
    """Best set of 4: same height, same baseline, even spacing, no overlap."""
    best, best_cost = None, None
    for combo in combinations(cands, NUM_DIGITS):
        sel = sorted(combo, key=lambda b: b[0])
        hs = np.array([b[3] for b in sel], float)
        mh = float(np.median(hs))
        if hs.max() / hs.min() > 1.30:
            continue
        cys = np.array([b[1] + b[3] / 2.0 for b in sel])
        if cys.max() - cys.min() > 0.22 * mh:
            continue
        if any(sel[i][0] + sel[i][2] > sel[i + 1][0] for i in range(3)):
            continue
        cxs = np.array([b[0] + b[2] / 2.0 for b in sel])
        gaps = np.diff(cxs)
        if gaps.min() < 0.6 * mh or gaps.max() / gaps.min() > 1.45:
            continue
        cost = hs.std() / mh + cys.std() / mh + gaps.std() / gaps.mean() - 0.6 * (mh / h)
        if best_cost is None or cost < best_cost:
            best, best_cost = sel, cost
    return best


def propose_boxes(housing):
    """Returns (boxes, detected). detected=False means grid fallback."""
    if housing is None or getattr(housing, "size", 0) == 0:
        return [], False
    gray = clean_board(housing)
    h, w = gray.shape[:2]
    if h < 20 or w < 40:
        return fallback_boxes(gray.shape), False
    sel = select_four(digit_candidates(gray), h)
    if sel is None:
        return fallback_boxes(gray.shape), False
    mh = float(np.median([b[3] for b in sel]))
    maxw = max(b[2] for b in sel)
    cxs = [b[0] + b[2] / 2.0 for b in sel]
    cy = float(np.median([b[1] + b[3] / 2.0 for b in sel]))
    gaps = np.diff(cxs)
    box_w = min(max(maxw, 0.55 * mh) + 0.30 * mh, 0.95 * float(gaps.min()))
    box_h = mh * 1.22
    boxes = []
    for cx in cxs:
        xa = int(round(max(0, cx - box_w / 2.0)))
        ya = int(round(max(0, cy - box_h / 2.0)))
        xb = int(round(min(w, cx + box_w / 2.0)))
        yb = int(round(min(h, cy + box_h / 2.0)))
        boxes.append((xa, ya, xb - xa, yb - ya))
    return boxes, True


# --------------------------------------------------------------------------- app
class FontApp:
    def __init__(self, root):
        self.root = root
        root.title("Digit font capture — close-ups only")
        root.geometry("1480x980")
        root.configure(bg="#f0f0f0")
        self.cap = None
        self.video_path = None
        self.fps = 30.0
        self.total = 1
        self.frame = None
        self.frame_idx = 0
        self.photo = None
        self.house_photo = None
        self.norm_photo = None
        self.crop_photo = None
        self.strip_photos = []
        self.playing = False
        self.after_id = None
        self.seek_after = None
        self.slider_guard = False
        self.analysis = None
        self.housing = None
        self.housing_rect = None
        self.h_scale = 1.0
        self.h_off = (0, 0)
        self.v_scale = 1.0
        self.v_off = (0, 0)
        self.proposals = []
        self.detected = False
        self.box_reads = []
        self.selected = None
        self.manual = None
        self.drag = None
        self.drag_target = None
        self.last_live = 0.0
        self.current_crop = None
        self.current_norm = None
        self.store = DigitStore(FONT_DIR)
        self.reader = None
        self.ocr_error = ""
        self.build_ui()
        self.refresh_counts()
        self.log("Fonts folder: %s" % FONT_DIR)
        self.log("Loaded samples: %s" % self.count_text())
        self.log("Pause on a CLOSE-UP. Click a cyan box, or type all 4 digits and press Enter.")
        self.log("Old fonts with border lines? Click 'Re-normalize from raw'.")
        root.bind("<Key>", self.on_key)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ UI
    def build_ui(self):
        left = Frame(self.root, bg="#f0f0f0")
        left.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        right = Frame(self.root, bg="#ffffff", width=520, relief="solid", bd=1)
        right.pack(side="right", fill="y", padx=(0, 8), pady=8)
        right.pack_propagate(False)

        top = Frame(left, bg="#f0f0f0")
        top.pack(fill="x")
        Button(top, text="Open Video", command=self.open_video, bg="#4CAF50", fg="white",
               font=("Arial", 10, "bold")).pack(side="left")
        self.play_btn = Button(top, text="Play", command=self.toggle_play, bg="#607D8B", fg="white",
                               font=("Arial", 10, "bold"), width=8)
        self.play_btn.pack(side="left", padx=4)
        for txt, sec in [("-10s", -10), ("-1s", -1), ("+1s", 1), ("+10s", 10)]:
            Button(top, text=txt, width=5, command=lambda s=sec: self.skip(s)).pack(side="left", padx=1)
        Label(top, text="Jump", bg="#f0f0f0").pack(side="left", padx=(8, 2))
        self.jump_var = StringVar(value="00:09:50")
        jump_entry = Entry(top, textvariable=self.jump_var, width=10, font=("Courier", 10))
        jump_entry.pack(side="left")
        jump_entry.bind("<Return>", lambda e: self.jump_to())
        Button(top, text="Go", command=self.jump_to, width=4).pack(side="left", padx=2)

        self.video_label = Label(left, text="No video", bg="#f0f0f0", fg="#555", anchor="w")
        self.video_label.pack(fill="x")
        self.canvas = Canvas(left, width=CANVAS_W, height=CANVAS_H, bg="black", highlightthickness=0)
        self.canvas.pack(pady=4)
        self.canvas.bind("<Button-1>", lambda e: self.press(e, "video"))
        self.canvas.bind("<B1-Motion>", lambda e: self.drag_move(e, "video"))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self.release(e, "video"))
        self.pos_var = DoubleVar()
        self.slider = ttk.Scale(left, from_=0, to=1, orient="horizontal", variable=self.pos_var,
                                command=self.on_slider)
        self.slider.pack(fill="x")
        self.time_label = Label(left, text="00:00:00 / 00:00:00", font=("Courier", 12, "bold"), bg="#f0f0f0")
        self.time_label.pack()
        Label(left, bg="#f0f0f0", fg="#333", anchor="w", font=("Arial", 9),
              text="Green banner = one-roller close-up, the only place a font may be saved. "
                   "Board digits are rejected.").pack(fill="x")

        Label(right, text="Close-up housing — click a digit", font=("Arial", 12, "bold"),
              bg="#fff").pack(anchor="w", padx=8, pady=(8, 0))
        self.house_canvas = Canvas(right, width=HOUSE_W, height=HOUSE_H, bg="black", highlightthickness=0)
        self.house_canvas.pack(padx=8, pady=4)
        self.house_canvas.bind("<Button-1>", lambda e: self.press(e, "house"))
        self.house_canvas.bind("<B1-Motion>", lambda e: self.drag_move(e, "house"))
        self.house_canvas.bind("<ButtonRelease-1>", lambda e: self.release(e, "house"))

        self.read_label = Label(right, text="Font read: ----", bg="#fff", fg="#2E7D32",
                                font=("Courier", 12, "bold"), anchor="w")
        self.read_label.pack(fill="x", padx=8)

        four = Frame(right, bg="#fff")
        four.pack(fill="x", padx=8, pady=2)
        Label(four, text="All 4 digits you see:", bg="#fff", font=("Arial", 9)).pack(side="left")
        self.four_var = StringVar()
        self.four_entry = Entry(four, textvariable=self.four_var, width=6, font=("Courier", 14, "bold"))
        self.four_entry.pack(side="left", padx=4)
        self.four_entry.bind("<Return>", self.save_four)
        Button(four, text="Save 4", command=self.save_four, bg="#1976D2", fg="white").pack(side="left")

        self.check_label = Label(right, text="Open a video and pause on a close-up.", bg="#fff", fg="#222",
                                 justify="left", anchor="w", font=("Courier", 10), wraplength=490)
        self.check_label.pack(fill="x", padx=8, pady=4)

        prev = Frame(right, bg="#fff")
        prev.pack(fill="x", padx=8)
        Label(prev, text="Crop", bg="#fff", font=("Arial", 8)).pack(side="left")
        self.crop_label = Label(prev, bg="#ddd")
        self.crop_label.pack(side="left", padx=4)
        Label(prev, text="Saved as", bg="#fff", font=("Arial", 8)).pack(side="left", padx=(8, 0))
        self.norm_label = Label(prev, bg="#ddd")
        self.norm_label.pack(side="left", padx=4)

        Label(right, text="Press the digit you see. The guess above is only a check.", bg="#fff",
              fg="#333", font=("Arial", 9)).pack(anchor="w", padx=8, pady=(6, 2))
        keys = Frame(right, bg="#fff")
        keys.pack(fill="x", padx=8)
        for d in "0123456789":
            Button(keys, text=d, width=3, font=("Arial", 14, "bold"),
                   command=lambda n=d: self.save_digit(n)).pack(side="left", padx=1)

        tools = Frame(right, bg="#fff")
        tools.pack(fill="x", padx=8, pady=4)
        Button(tools, text="Undo last save", command=self.undo, bg="#f44336", fg="white").pack(side="left")
        Button(tools, text="Re-normalize from raw", command=self.renormalize).pack(side="left", padx=4)
        Button(tools, text="Check font set", command=self.check_fonts).pack(side="left")

        self.count_label = Label(right, text="", bg="#fff", fg="#1565C0", justify="left", anchor="w",
                                 font=("Courier", 10), wraplength=490)
        self.count_label.pack(fill="x", padx=8)
        strip = Frame(right, bg="#fff")
        strip.pack(fill="x", padx=8, pady=2)
        self.strip_labels = []
        for d in "0123456789":
            box = Frame(strip, bg="#fff")
            box.pack(side="left", padx=1)
            Label(box, text=d, bg="#fff", font=("Arial", 8, "bold")).pack()
            lab = Label(box, bg="#eee")
            lab.pack()
            self.strip_labels.append(lab)

        self.log_box = Text(right, height=6, font=("Courier", 8), bg="#fafafa", state=DISABLED)
        self.log_box.pack(fill="both", expand=True, padx=8, pady=(4, 8))

    def log(self, msg):
        self.log_box.config(state=NORMAL)
        self.log_box.insert(END, str(msg) + "\n")
        self.log_box.see(END)
        self.log_box.config(state=DISABLED)
        try:
            print(msg, flush=True)
        except Exception:
            print(str(msg).encode("ascii", "replace").decode("ascii"), flush=True)

    def count_text(self):
        c = self.store.counts()
        return "  ".join("%s:%d" % (d, c[d]) for d in "0123456789")

    def refresh_counts(self):
        c = self.store.counts()
        need = [d for d in "0123456789" if c[d] < 2]
        text = self.count_text()
        text += "\nNeed 2 samples of: " + (" ".join(need) if need else "none — ready to scan")
        self.count_label.config(text=text)
        self.strip_photos = []
        for i, d in enumerate("0123456789"):
            imgs = self.store.samples[d]
            if not imgs:
                self.strip_labels[i].config(image="")
                continue
            ph = ImageTk.PhotoImage(Image.fromarray(imgs[-1]).resize((42, 63)))
            self.strip_photos.append(ph)
            self.strip_labels[i].config(image=ph)

    # ------------------------------------------------------------------ OCR (optional)
    def get_reader(self):
        if self.reader is None:
            try:
                import easyocr
                self.check_label.config(text="Loading OCR for the live check...")
                self.root.update_idletasks()
                self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            except Exception as e:
                self.ocr_error = str(e)
                self.reader = False
                self.log("OCR not available (%s). Font check still works." % e)
        return self.reader

    def ocr_one(self, img):
        gray = to_gray(img)
        if gray is None:
            return "", 0.0
        reader = self.get_reader()
        if not reader:
            return "", 0.0
        if gray.shape[0] < 24:
            gray = upscale_to_height(gray, 48)
        try:
            res = reader.recognize(gray, allowlist="0123456789", detail=1)
            if not res:
                res = reader.readtext(gray, allowlist="0123456789", detail=1, paragraph=False)
        except Exception as e:
            self.ocr_error = str(e)
            return "", 0.0
        best, conf = "", 0.0
        for item in res or []:
            if len(item) < 3:
                continue
            d = "".join(ch for ch in str(item[1]) if ch.isdigit())
            c = float(item[2])
            if len(d) == 1 and c >= conf:
                best, conf = d, c
        return best, conf

    # ------------------------------------------------------------------ video
    def open_video(self):
        path = filedialog.askopenfilename(title="Select video",
                                          filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv"), ("All", "*.*")])
        if not path:
            return
        self.stop_play()
        if self.cap:
            self.cap.release()
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            messagebox.showerror("Error", "Cannot open this video.")
            return
        self.cap = cap
        self.video_path = path
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if self.fps < 1:
            self.fps = 30.0
        self.total = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.slider.config(to=self.total - 1)
        self.video_label.config(text=Path(path).name)
        self.log("Opened %s" % Path(path).name)
        self.seek(0)

    def t_now(self):
        return self.frame_idx / self.fps if self.fps else 0.0

    def read_current(self):
        ok, f = self.cap.read()
        if not ok:
            return False
        self.frame = f
        pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        self.frame_idx = pos if pos >= 0 else self.frame_idx + 1
        return True

    def seek(self, idx):
        if not self.cap:
            return
        idx = max(0, min(int(idx), self.total - 1))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        if not self.read_current():
            return
        self.analysis = classify_frame(self.frame)
        self.show_frame()
        self.load_housing()

    def skip(self, sec):
        if self.cap and not self.playing:
            self.seek(self.frame_idx + sec * self.fps)

    def jump_to(self):
        if self.cap and not self.playing:
            self.seek(parse_time(self.jump_var.get()) * self.fps)
            self.canvas.focus_set()

    def on_slider(self, value):
        if self.slider_guard or not self.cap or self.playing:
            return
        if self.seek_after:
            self.root.after_cancel(self.seek_after)
        self.seek_after = self.root.after(80, lambda: self.seek(float(value)))

    def update_time(self):
        self.slider_guard = True
        self.pos_var.set(self.frame_idx)
        self.slider_guard = False
        self.time_label.config(text="%s / %s" % (fmt_hms(self.t_now()), fmt_hms(self.total / self.fps)))

    def show_frame(self):
        if self.frame is None:
            return
        h, w = self.frame.shape[:2]
        s = min(CANVAS_W / float(w), CANVAS_H / float(h))
        dw, dh = int(w * s), int(h * s)
        ox, oy = (CANVAS_W - dw) // 2, (CANVAS_H - dh) // 2
        self.v_scale, self.v_off = s, (ox, oy)
        rgb = cv2.cvtColor(cv2.resize(self.frame, (dw, dh), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, image=self.photo, anchor="nw")
        scene = (self.analysis or {}).get("scene", "")
        close = (self.analysis or {}).get("close")
        if close:
            k = s * w / float(ANALYSIS_W)
            lab = close["label"]
            hx1, hy1, hx2, hy2 = close["housing"]
            self.canvas.create_rectangle(ox + lab[0] * k, oy + lab[1] * k,
                                         ox + (lab[0] + lab[2]) * k, oy + (lab[1] + lab[3]) * k,
                                         outline="#FFEB3B", width=3)
            self.canvas.create_rectangle(ox + hx1 * k, oy + hy1 * k, ox + hx2 * k, oy + hy2 * k,
                                         outline="#00E5FF", width=3)
        banner = {"closeup": "CLOSE-UP — font capture allowed",
                  "multi": "BOARD — too small, capture refused",
                  "other": "NOT A CLOSE-UP — capture refused"}.get(scene, "")
        color = {"closeup": "#00E676", "multi": "#FFB300", "other": "#FF5252"}.get(scene, "#FFFFFF")
        if banner:
            self.canvas.create_rectangle(ox, oy, ox + 560, oy + 30, fill="#000000", outline="")
            self.canvas.create_text(ox + 8, oy + 15, anchor="w", fill=color,
                                    font=("Courier", 12, "bold"), text=banner)
        self.update_time()

    # ------------------------------------------------------------------ housing
    def housing_from_analysis(self):
        if self.frame is None or not self.analysis or not self.analysis.get("close"):
            return None, None
        h, w = self.frame.shape[:2]
        sc = w / float(ANALYSIS_W)
        hx1, hy1, hx2, hy2 = self.analysis["close"]["housing"]
        pad = 8
        x1, y1 = max(0, int(hx1 * sc) - pad), max(0, int(hy1 * sc) - pad)
        x2, y2 = min(w, int(hx2 * sc) + pad), min(h, int(hy2 * sc) + pad)
        crop = self.frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None, None
        return crop, (x1, y1, x2 - x1, y2 - y1)

    def load_housing(self):
        self.selected = None
        self.manual = None
        self.current_crop = None
        self.box_reads = []
        if not self.analysis or self.analysis.get("scene") != "closeup":
            self.housing = None
            self.housing_rect = None
            self.proposals = []
            self.detected = False
            self.house_canvas.delete("all")
            self.house_canvas.create_text(20, 20, anchor="nw", fill="#FFAB40", font=("Arial", 12, "bold"),
                                          text="Not a close-up. Capture is refused here.")
            self.read_label.config(text="Font read: ----")
            return
        self.housing, self.housing_rect = self.housing_from_analysis()
        if self.housing is not None:
            self.proposals, self.detected = propose_boxes(self.housing)
        else:
            self.proposals, self.detected = [], False
        if not self.playing:
            self.read_all_boxes()
        self.redraw_housing()

    def read_all_boxes(self):
        """Font-match all 4 boxes so you can see what a scan would read."""
        self.box_reads = []
        for box in self.proposals:
            d, s, _d2, _s2, norm = self.store.match(self.crop_housing_box(box))
            if norm is None:
                self.box_reads.append(("x", s))
            elif d and s >= MATCH_MIN:
                self.box_reads.append((d, s))
            else:
                self.box_reads.append(("?", s))
        txt = "".join(r[0] for r in self.box_reads) or "----"
        how = "digits found" if self.detected else "GRID FALLBACK — drag boxes by hand"
        conf = min([r[1] for r in self.box_reads], default=-1.0)
        self.read_label.config(text="Font read: %s   (min %.2f, %s)" % (txt, conf, how),
                               fg="#2E7D32" if self.detected else "#E65100")

    def redraw_housing(self):
        self.house_canvas.delete("all")
        if self.housing is None:
            return
        h, w = self.housing.shape[:2]
        s = min(HOUSE_W / float(w), HOUSE_H / float(h))
        dw, dh = int(w * s), int(h * s)
        ox, oy = (HOUSE_W - dw) // 2, (HOUSE_H - dh) // 2
        self.h_scale, self.h_off = s, (ox, oy)
        rgb = cv2.cvtColor(cv2.resize(self.housing, (dw, dh), interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2RGB)
        self.house_photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.house_canvas.create_image(ox, oy, image=self.house_photo, anchor="nw")
        for i, (x, y, bw, bh) in enumerate(self.proposals):
            color = "#FFEB3B" if self.selected == ("prop", i) else "#00E5FF"
            self.house_canvas.create_rectangle(ox + x * s, oy + y * s, ox + (x + bw) * s, oy + (y + bh) * s,
                                               outline=color, width=2)
            guess = self.box_reads[i][0] if i < len(self.box_reads) else ""
            ty = max(8, oy + y * s - 9)
            self.house_canvas.create_text(ox + (x + bw / 2.0) * s, ty, fill=color,
                                          font=("Arial", 11, "bold"), text="%d:%s" % (i + 1, guess))
        if self.manual:
            x, y, bw, bh = self.manual
            self.house_canvas.create_rectangle(ox + x * s, oy + y * s, ox + (x + bw) * s, oy + (y + bh) * s,
                                               outline="#FF5252", width=2)
        box = self.drag_box()
        if box and self.drag_target == "house":
            self.house_canvas.create_rectangle(*box, outline="#FF5252", dash=(3, 2))

    # ------------------------------------------------------------------ mouse
    def press(self, event, target):
        if self.playing:
            return
        self.canvas.focus_set()   # so digit keys work again after typing in an entry
        self.drag_target = target
        self.drag = (event.x, event.y, event.x, event.y)

    def drag_move(self, event, target):
        if not self.drag or self.drag_target != target:
            return
        self.drag = (self.drag[0], self.drag[1], event.x, event.y)
        if target == "house":
            self.redraw_housing()
        else:
            self.show_frame()
            box = self.drag_box()
            if box:
                self.canvas.create_rectangle(*box, outline="#FF5252", width=2)

    def drag_box(self):
        if not self.drag:
            return None
        x1, y1, x2, y2 = self.drag
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    def release(self, event, target):
        if not self.drag or self.playing:
            self.drag = None
            return
        x1, y1, _x2, _y2 = self.drag
        self.drag = None
        moved = abs(event.x - x1) + abs(event.y - y1) > 8
        if self.analysis is None or self.analysis.get("scene") != "closeup":
            self.check_label.config(text="Not a close-up. Font capture is refused.\nGo to a one-roller close-up.")
            return
        if target == "house":
            box = self.canvas_box_to_housing(x1, y1, event.x, event.y) if moved else None
            if box is None:                       # click or tiny drag = select a box
                self.select_proposal(event.x, event.y)
                return
            self.manual = box
            self.selected = ("manual", 0)
            self.redraw_housing()
            self.inspect(self.crop_housing_box(box), ocr=True)
            return
        if not moved:
            self.show_frame()
            return
        box = self.canvas_box_to_frame(x1, y1, event.x, event.y)
        if box is None:
            self.show_frame()
            return
        x, y, bw, bh = box
        self.selected = None
        self.inspect(self.frame[y:y + bh, x:x + bw], ocr=True)

    def select_proposal(self, x, y):
        if self.housing is None or not self.proposals:
            return
        ix = (x - self.h_off[0]) / self.h_scale
        iy = (y - self.h_off[1]) / self.h_scale
        best, best_d = None, None
        for i, (bx, by, bw, bh) in enumerate(self.proposals):
            if bx <= ix <= bx + bw and by <= iy <= by + bh:
                best = i
                break
            d = abs(ix - (bx + bw / 2.0))
            if best_d is None or d < best_d:
                best, best_d = i, d
        if best is None:
            return
        self.selected = ("prop", best)
        self.manual = None
        self.redraw_housing()
        self.inspect(self.crop_housing_box(self.proposals[best]), ocr=True)

    def canvas_box_to_housing(self, x1, y1, x2, y2):
        if self.housing is None:
            return None
        xa = int((min(x1, x2) - self.h_off[0]) / self.h_scale)
        ya = int((min(y1, y2) - self.h_off[1]) / self.h_scale)
        xb = int((max(x1, x2) - self.h_off[0]) / self.h_scale)
        yb = int((max(y1, y2) - self.h_off[1]) / self.h_scale)
        h, w = self.housing.shape[:2]
        xa, ya, xb, yb = max(0, xa), max(0, ya), min(w, xb), min(h, yb)
        if xb - xa < 6 or yb - ya < 10:
            return None
        return xa, ya, xb - xa, yb - ya

    def canvas_box_to_frame(self, x1, y1, x2, y2):
        if self.frame is None:
            return None
        xa = int((min(x1, x2) - self.v_off[0]) / self.v_scale)
        ya = int((min(y1, y2) - self.v_off[1]) / self.v_scale)
        xb = int((max(x1, x2) - self.v_off[0]) / self.v_scale)
        yb = int((max(y1, y2) - self.v_off[1]) / self.v_scale)
        h, w = self.frame.shape[:2]
        xa, ya, xb, yb = max(0, xa), max(0, ya), min(w, xb), min(h, yb)
        if xb - xa < 6 or yb - ya < 10:
            self.check_label.config(text="Mark is too small. Draw around the whole digit.")
            return None
        return xa, ya, xb - xa, yb - ya

    def crop_housing_box(self, box):
        x, y, w, h = box
        return self.housing[y:y + h, x:x + w]

    # ------------------------------------------------------------------ check & save
    def show_small(self, img, label, key_name, size):
        if img is None or getattr(img, "size", 0) == 0:
            label.config(image="")
            return
        if img.ndim == 3:
            im = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        else:
            im = Image.fromarray(img)
        ph = ImageTk.PhotoImage(im.resize(size))
        setattr(self, key_name, ph)
        label.config(image=ph)

    def inspect(self, crop, ocr):
        self.current_crop = crop
        digit, score, second, second_s, norm = self.store.match(crop)
        self.current_norm = norm
        self.show_small(crop, self.crop_label, "crop_photo", (90, 120))
        self.show_small(norm, self.norm_label, "norm_photo", (64, 96))
        if norm is None:
            self.check_label.config(text="No digit ink in this mark.\n"
                                         "Draw around the black number, not the screw or the frame.")
            return
        lines = ["CHECK — not saved yet", ""]
        if score < 0:
            lines.append("Saved fonts: none yet")
        else:
            lines.append("Saved fonts: %s  (%.2f)" % (digit or "?", score))
            if second:
                lines.append("Second:      %s  (%.2f)" % (second, second_s))
        if ocr:
            od, oc = self.ocr_one(norm)
            if od:
                lines.append("OCR sees:    %s  (%d%%)" % (od, int(oc * 100)))
                if digit and od != digit and score >= 0.45:
                    lines.append("Font and OCR disagree. Trust your eyes.")
            elif self.reader is not False:
                lines.append("OCR sees:    nothing")
        lines.append("")
        lines.append("Check the 'Saved as' image is ONLY the digit, then press 0-9.")
        self.check_label.config(text="\n".join(lines))

    def current_box_crop(self):
        if self.selected and self.selected[0] == "prop" and self.selected[1] < len(self.proposals):
            return self.crop_housing_box(self.proposals[self.selected[1]])
        if self.selected and self.selected[0] == "manual" and self.manual and self.housing is not None:
            return self.crop_housing_box(self.manual)
        return self.current_crop

    def can_save(self):
        if self.playing:
            self.check_label.config(text="Pause the video before saving.")
            return False
        if not self.analysis or self.analysis.get("scene") != "closeup":
            self.check_label.config(text="Refused. This frame is not a one-roller close-up.")
            return False
        return True

    def meta(self):
        return {"time": fmt_hms(self.t_now()),
                "video": Path(self.video_path).name if self.video_path else ""}

    def save_digit(self, digit):
        if not self.can_save():
            return
        crop = self.current_box_crop()
        if crop is None or getattr(crop, "size", 0) == 0:
            self.check_label.config(text="Mark a digit first.")
            return
        norm = normalize_font(crop)
        if norm is None:
            self.check_label.config(text="Refused. This mark has no clean digit.")
            return
        path = self.store.save(digit, crop, norm, self.meta())
        again_d, again_s, _a, _b, _n = self.store.match(norm)
        self.log("Saved %s/%s. Recheck sees %s (%.2f)." % (digit, path.name, again_d or "?", again_s))
        self.check_label.config(text="SAVED digit %s\nRecheck against saved fonts: %s (%.2f)\nMark the next digit."
                                     % (digit, again_d or "?", again_s))
        self.refresh_counts()
        self.read_all_boxes()
        if self.selected and self.selected[0] == "prop" and self.selected[1] + 1 < len(self.proposals):
            nxt = self.selected[1] + 1
            self.selected = ("prop", nxt)
            self.inspect(self.crop_housing_box(self.proposals[nxt]), ocr=True)
        self.redraw_housing()

    def save_four(self, _event=None):
        txt = self.four_var.get().strip()
        if len(txt) != NUM_DIGITS or not txt.isdigit():
            self.check_label.config(text="Type exactly 4 digits (what you see), e.g. 7484.")
            return
        if not self.can_save():
            return
        if len(self.proposals) != NUM_DIGITS:
            self.check_label.config(text="Need 4 digit boxes on the housing.")
            return
        items = []
        for i, (digit, box) in enumerate(zip(txt, self.proposals)):
            crop = self.crop_housing_box(box)
            norm = normalize_font(crop)
            if norm is None:
                self.check_label.config(text="Box %d has no clean digit. Nothing saved.\n"
                                             "Drag that digit by hand instead." % (i + 1))
                return
            items.append((digit, crop, norm))
        for digit, crop, norm in items:
            path = self.store.save(digit, crop, norm, self.meta())
            self.log("Saved %s/%s" % (digit, path.name))
        self.four_var.set("")
        self.canvas.focus_set()
        self.refresh_counts()
        self.read_all_boxes()
        self.redraw_housing()
        self.check_label.config(text="SAVED 4 digits: %s\nRead-back now: %s" %
                                     (txt, "".join(r[0] for r in self.box_reads)))

    def undo(self):
        digit = self.store.undo()
        if digit is None:
            self.log("Nothing to undo.")
            return
        self.log("Removed last saved digit %s." % digit)
        self.refresh_counts()
        if self.housing is not None:
            self.read_all_boxes()
            self.redraw_housing()

    def renormalize(self):
        ok, failed = self.store.renormalize_all()
        self.log("Re-normalized %d fonts from raw crops." % ok)
        for f in failed:
            self.log("  could not clean %s - delete it and capture again" % f)
        self.refresh_counts()
        if self.housing is not None:
            self.read_all_boxes()
            self.redraw_housing()

    def check_fonts(self):
        total, errors = self.store.self_check()
        if not errors:
            self.log("Font set check: %d samples, all match their own digit." % total)
            return
        self.log("Font set check: %d of %d samples look like another digit:" % (len(errors), total))
        for d, name, other, s in errors:
            self.log("  %s/%s looks like %s (%.2f) - check or delete it" % (d, name, other, s))

    def on_key(self, event):
        if isinstance(self.root.focus_get(), Entry):
            return
        if event.char and event.char in "0123456789":
            self.save_digit(event.char)

    # ------------------------------------------------------------------ playback
    def stop_play(self):
        self.playing = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.play_btn.config(text="Play")

    def toggle_play(self):
        if not self.cap:
            messagebox.showwarning("No video", "Open a video first.")
            return
        if self.playing:
            self.stop_play()
            self.load_housing()
            return
        self.playing = True
        self.play_btn.config(text="Pause")
        self.play_tick()

    def play_tick(self):
        if not self.playing or not self.cap:
            return
        if not self.read_current():
            self.stop_play()
            return
        self.analysis = classify_frame(self.frame)
        self.show_frame()
        if abs(self.t_now() - self.last_live) >= 0.25:
            self.load_housing()
            self.last_live = self.t_now()
        self.after_id = self.root.after(max(1, int(1000 / self.fps)), self.play_tick)

    def on_close(self):
        self.playing = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
        if self.cap:
            self.cap.release()
        self.root.destroy()


if __name__ == "__main__":
    root = Tk()
    FontApp(root)
    root.mainloop()
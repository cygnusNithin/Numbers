"""
scan_gui.py
4th-prize reader.

The 18 marked tags only identify the machine. They are never read.
A number is read only from a later one-roller close-up, and only after
the digit band has stopped moving.

digit_fonts/0..9, made by font_capture.py, is checked first.
EasyOCR is used only when a digit has no confident font match.
A saved number must be exactly 4 digits.
The result list is checked only after 19 reads. It does not change a read.

No threading. No cv2.imshow. No images written except the export files.
Run: python scan_gui.py
"""
import csv
import json
import re
import time
from collections import Counter
from pathlib import Path
from tkinter import (Tk, Frame, Label, Button, Canvas, Text, Entry, StringVar,
                     DoubleVar, messagebox, filedialog, END, DISABLED, NORMAL,
                     Listbox, SINGLE)
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

PRIZE = 4
EXPECTED = 19
NUM_PER_SPIN = 18
NUMBER_DIGITS = 4
OFFICIAL_NUMBERS = [
    "2023", "2340", "2353", "2368", "2566",
    "3158", "3366", "3740", "4213", "4380",
    "4395", "4481", "5240", "5622", "6851",
    "6972", "7484", "8338", "8925",
]

ANALYSIS_W = 640
MACHINE_MIN_HITS = 8
YELLOW_FRAC = 0.30
CLOSEUP_MIN_FRAC = 0.008
CLOSEUP_DOMINANT = 2.5
MULTI_TAGS = 4
HOUSING_WHITE_MIN = 0.22
CLOSEUP_MISS_SEC = 0.55
FREEZE_DIFF = 0.055
FREEZE_HOLD_SEC = 0.22
STILL_ACCEPT = 0.10

YELLOW_LO = (15, 90, 120)
YELLOW_HI = (40, 255, 255)
FONT_W, FONT_H = 32, 48
UPSCALE_HOUSING_H = 220
FONT_SCORE = 0.58
FONT_MARGIN = 0.07
CANVAS_W, CANVAS_H = 960, 540

HERE = Path(__file__).resolve().parent
FONT_DIR = HERE / "digit_fonts"
OUT_JSON = HERE / "4th_prize_extracted.json"
OUT_CSV = HERE / "4th_prize_extracted.csv"


def roi_path():
    for p in (HERE / "roller_boxes.json", Path.cwd() / "roller_boxes.json"):
        if p.exists():
            return p
    return HERE / "roller_boxes.json"


ROI_FILE = roi_path()


def fmt_hms(sec):
    sec = max(0, int(sec))
    return "%02d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


def fmt_mmss(sec):
    sec = max(0, int(round(sec)))
    return "%02d:%02d" % (sec // 60, sec % 60)


def parse_time(s):
    try:
        sec = 0.0
        for p in str(s).strip().split(":"):
            sec = sec * 60 + float(p)
        return max(0.0, sec)
    except Exception:
        return 0.0


def four(text):
    d = re.sub(r"\D", "", text or "")
    return d if len(d) == NUMBER_DIGITS else ""


def to_gray(img):
    if img is None or getattr(img, "size", 0) == 0:
        return None
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def resize_w(img, w):
    h = max(1, int(img.shape[0] * w / img.shape[1]))
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)


def upscale_to_height(gray, target_h):
    f = target_h / max(1, gray.shape[0])
    return cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)


def imread_gray(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)


def yellow_fraction(bgr):
    if bgr is None or bgr.size == 0 or bgr.ndim != 3:
        return 0.0
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return float(np.count_nonzero(cv2.inRange(hsv, YELLOW_LO, YELLOW_HI))) / float(hsv.shape[0] * hsv.shape[1])


def sharpness(gray):
    if gray is None or gray.size == 0:
        return 0.0
    g = gray if gray.shape[0] <= 160 else upscale_to_height(gray, 120)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def binary_diff(a, b, size):
    if a is None or b is None or a.size == 0 or b.size == 0:
        return 1.0

    def prep(im):
        g = cv2.resize(to_gray(im), size, interpolation=cv2.INTER_AREA)
        g = cv2.GaussianBlur(g, (3, 3), 0)
        _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return bw

    return float(np.mean(prep(a) != prep(b)))


def digit_band(house):
    if house is None or house.size == 0:
        return None
    h, w = house.shape[:2]
    y1, y2 = int(h * 0.22), int(h * 0.82)
    x1, x2 = int(w * 0.06), int(w * 0.94)
    if y2 - y1 < 8 or x2 - x1 < 12:
        return house
    return house[y1:y2, x1:x2]


def remove_frame_lines(inv):
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


def normalize_font(img):
    gray = to_gray(img)
    if gray is None or gray.shape[0] < 8 or gray.shape[1] < 4:
        return None
    if gray.shape[0] < 48:
        gray = upscale_to_height(gray, 80)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    inv = remove_frame_lines(inv)
    h, w = inv.shape
    n, labels, stats, cents = cv2.connectedComponentsWithStats(inv, connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, cw, ch, a = stats[i]
        if a < 0.008 * h * w or ch < 0.22 * h:
            continue
        if not (0.08 * w <= cents[i][0] <= 0.92 * w):
            continue
        comps.append(i)
    if not comps:
        return None
    largest = max(stats[i][4] for i in comps)
    keep = [i for i in comps if stats[i][4] >= 0.15 * largest]
    mask = np.isin(labels, keep).astype(np.uint8) * 255
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None
    glyph = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    gh, gw = glyph.shape
    if gh < 6 or gw < 2:
        return None
    scale = (FONT_H - 8) / float(gh)
    nw = max(1, min(FONT_W - 8, int(round(gw * scale))))
    nh = FONT_H - 8
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
    if np.isnan(s):
        return -1.0
    return s


class DigitFonts:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.samples = {str(i): [] for i in range(10)}
        self.count = 0
        self.reload()

    def reload(self):
        self.samples = {str(i): [] for i in range(10)}
        self.count = 0
        if not self.folder.exists():
            return 0
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
                self.samples[str(d)].append(cv2.resize(img, (FONT_W, FONT_H), interpolation=cv2.INTER_AREA))
                self.count += 1
        return self.count

    def match(self, img):
        norm = normalize_font(img)
        best, second = ("", -1.0), ("", -1.0)
        if norm is None or self.count == 0:
            return "", 0.0, 0.0
        for digit, samples in self.samples.items():
            for sample in samples:
                s = score_pair(norm, sample)
                if s > best[1]:
                    second = best
                    best = (digit, s)
                elif s > second[1]:
                    second = (digit, s)
        margin = best[1] - max(second[1], 0.0)
        return best[0], best[1], margin


def load_boxes(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return []
    boxes = []
    for b in data.get("boxes", []):
        tag = b.get("tag") or {}
        if not all(k in tag for k in ("x", "y", "w", "h")):
            continue
        item = {"roller": int(b.get("roller", len(boxes) + 1)),
                "tag": {k: int(tag[k]) for k in ("x", "y", "w", "h")}}
        housing = b.get("housing") or {}
        if all(k in housing for k in ("x", "y", "w", "h")):
            item["housing"] = {k: int(housing[k]) for k in ("x", "y", "w", "h")}
        boxes.append(item)
    return boxes


def housing_ratio(boxes):
    dx, dy, dw, dh = [], [], [], []
    for b in boxes:
        t, h = b.get("tag"), b.get("housing")
        if not t or not h or t["w"] < 5 or t["h"] < 5:
            continue
        dx.append((h["x"] - t["x"]) / float(t["w"]))
        dy.append((h["y"] - t["y"]) / float(t["h"]))
        dw.append(h["w"] / float(t["w"]))
        dh.append(h["h"] / float(t["h"]))
    if len(dx) < 3:
        return None
    ratio = {"dx": float(np.median(dx)), "dy": float(np.median(dy)),
             "dw": float(np.median(dw)), "dh": float(np.median(dh))}
    if ratio["dx"] < 0.4 or ratio["dw"] < 1.5 or ratio["dh"] < 0.4:
        return None
    return ratio


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


def housing_from_tag(label, ratio):
    if not ratio:
        return None
    x, y, w, h = label
    x1, y1 = int(x + ratio["dx"] * w), int(y + ratio["dy"] * h)
    x2, y2 = int(x1 + ratio["dw"] * w), int(y1 + ratio["dh"] * h)
    if x2 <= x1 + 4 or y2 <= y1 + 4:
        return None
    return x1, y1, x2, y2


def white_fraction(img, box):
    x1, y1, x2, y2 = box
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    m = cv2.inRange(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV), (0, 0, 140), (180, 80, 255))
    return float(np.count_nonzero(m)) / float(m.size)


def refine_housing(crop):
    if crop is None or crop.size == 0:
        return crop
    white = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), (0, 0, 140), (180, 80, 255))
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    if n <= 1:
        return crop
    i = 1 + int(np.argmax(stats[1:, 4]))
    x, y, w, h, a = stats[i]
    if a < 0.08 * crop.shape[0] * crop.shape[1]:
        return crop
    pad = 2
    return crop[max(0, y - pad):min(crop.shape[0], y + h + pad),
                max(0, x - pad):min(crop.shape[1], x + w + pad)]


def find_closeup(labels, W, H, small, ratio):
    if similar_tag_count(labels) >= MULTI_TAGS:
        return None
    big = [l for l in labels if l[2] * l[3] >= CLOSEUP_MIN_FRAC * W * H]
    if not big:
        return None
    big.sort(key=lambda l: l[2] * l[3], reverse=True)
    best = big[0]
    if len(big) > 1 and best[2] * best[3] < CLOSEUP_DOMINANT * big[1][2] * big[1][3]:
        return None
    candidates = []
    scaled = housing_from_tag(best, ratio)
    if scaled:
        candidates.append(scaled)
    heur = housing_box(best, W, H)
    if heur:
        candidates.append(heur)
    for box in candidates:
        x1, y1, x2, y2 = max(0, box[0]), max(0, box[1]), min(W - 1, box[2]), min(H - 1, box[3])
        if x2 - x1 < 8 or y2 - y1 < 8:
            continue
        wf = white_fraction(small, (x1, y1, x2, y2))
        if wf >= HOUSING_WHITE_MIN:
            return {"label": best, "housing": (x1, y1, x2, y2), "white": wf}
    return None


def classify(frame, boxes):
    h, w = frame.shape[:2]
    hits, hit_count, valid = {}, 0, 0
    for b in boxes:
        tag = b["tag"]
        x, y, tw, th = tag["x"], tag["y"], tag["w"], tag["h"]
        if x >= w or y >= h or x + tw <= 0 or y + th <= 0:
            hits[b["roller"]] = False
            continue
        x1, y1, x2, y2 = max(0, x), max(0, y), min(w, x + tw), min(h, y + th)
        if x2 - x1 < 3 or y2 - y1 < 3:
            hits[b["roller"]] = False
            continue
        valid += 1
        ok = yellow_fraction(frame[y1:y2, x1:x2]) >= YELLOW_FRAC
        hits[b["roller"]] = ok
        hit_count += int(ok)
    small = resize_w(frame, ANALYSIS_W)
    sh, sw = small.shape[:2]
    labels = find_yellow_labels(small)
    multi = similar_tag_count(labels)
    is_machine = valid > 0 and hit_count >= MACHINE_MIN_HITS
    close = None if (is_machine or multi >= MULTI_TAGS) else find_closeup(
        labels, sw, sh, small, housing_ratio(boxes))
    if is_machine:
        scene = "machine"
    elif multi >= MULTI_TAGS:
        scene = "multi"
    elif close is not None:
        scene = "closeup"
    else:
        scene = "other"
    return {"scene": scene, "hits": hits, "hit_count": hit_count, "valid": valid,
            "labels": labels, "multi": multi, "close": close}


def inset_crop(img, frac=0.12):
    if img is None or img.size == 0:
        return img
    h, w = img.shape[:2]
    dx, dy = int(w * frac), int(h * frac)
    if w - 2 * dx < 4 or h - 2 * dy < 6:
        return img
    return img[dy:h - dy, dx:w - dx]


def find_digit_cells(gray):
    H, W = gray.shape
    _, dark = cv2.threshold(cv2.GaussianBlur(gray, (3, 3), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, _, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    cands = []
    for i in range(1, n):
        x, y, w, h, _a = stats[i]
        if h < 0.25 * H or not (0.04 * W <= w <= 0.35 * W) or not (0.7 <= h / max(1, w) <= 5.0):
            continue
        cands.append((int(x), int(y), int(x + w), int(y + h)))

    def area(b):
        return (b[2] - b[0]) * (b[3] - b[1])

    outer = []
    for i, a in enumerate(cands):
        inside = False
        for j, b in enumerate(cands):
            if j != i and b[0] <= a[0] and b[1] <= a[1] and b[2] >= a[2] and b[3] >= a[3] and area(b) > area(a):
                inside = True
                break
        if not inside:
            outer.append(a)
    if len(outer) < NUMBER_DIGITS:
        return None
    hs = np.array([b[3] - b[1] for b in outer], float)
    ycs = np.array([(b[1] + b[3]) / 2.0 for b in outer], float)
    mh, myc = float(np.median(hs)), float(np.median(ycs))
    sel = [b for b, hh, yc in zip(outer, hs, ycs) if 0.7 * mh <= hh <= 1.4 * mh and abs(yc - myc) < 0.25 * H]
    if len(sel) < NUMBER_DIGITS:
        return None
    sel = sorted(sorted(sel, key=area, reverse=True)[:NUMBER_DIGITS], key=lambda b: b[0])
    steps = [sel[i + 1][0] - sel[i][0] for i in range(len(sel) - 1)]
    if not steps or min(steps) <= 0 or max(steps) > 1.8 * min(steps):
        return None
    crops = []
    for x1, y1, x2, y2 in sel:
        crops.append(inset_crop(gray[max(0, y1):min(H, y2), max(0, x1):min(W, x2)], 0.12))
    return crops


def ink_four(gray):
    H, W = gray.shape
    if H < 12 or W < 24:
        return None
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, inv = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    inv = remove_frame_lines(inv)
    active = (inv > 0).mean(axis=0) > 0.045
    runs, i = [], 0
    while i < W:
        if not active[i]:
            i += 1
            continue
        j = i
        while j < W and active[j]:
            j += 1
        if j - i >= 2:
            runs.append((i, j))
        i = j
    if len(runs) < NUMBER_DIGITS:
        return None
    if len(runs) > NUMBER_DIGITS:
        runs = sorted(sorted(runs, key=lambda r: r[1] - r[0], reverse=True)[:NUMBER_DIGITS])
    crops = []
    for x1, x2 in runs:
        xa, xb = max(0, x1 - 1), min(W, x2 + 1)
        ys = np.where((inv[:, xa:xb] > 0).any(axis=1))[0]
        if len(ys) < 4:
            return None
        crops.append(gray[max(0, ys[0] - 1):min(H, ys[-1] + 2), xa:xb])
    return crops if len(crops) == NUMBER_DIGITS else None


def equal_four(gray):
    H, W = gray.shape
    if H < 12 or W < 24:
        return None
    band = gray[int(H * 0.16):int(H * 0.86), int(W * 0.04):int(W * 0.96)]
    w = band.shape[1] // NUMBER_DIGITS
    if w < 6:
        return None
    crops = []
    for i in range(NUMBER_DIGITS):
        cell = band[:, i * w:(i + 1) * w]
        crops.append(inset_crop(cell, 0.14))
    return crops


class NumberReader:
    def __init__(self):
        self.reader = None
        self.error = ""

    def get(self):
        if self.reader is None:
            import easyocr
            self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return self.reader

    def one_digit(self, img):
        gray = to_gray(img)
        if gray is None or gray.size == 0:
            return "", 0.0
        if gray.shape[0] < 24:
            gray = upscale_to_height(gray, 48)
        reader = self.get()
        try:
            res = reader.recognize(gray, allowlist="0123456789", detail=1)
        except Exception:
            res = None
        if not res:
            try:
                res = reader.readtext(gray, allowlist="0123456789", detail=1, paragraph=False)
            except Exception as e:
                self.error = str(e)
                return "", 0.0
        best, conf = "", 0.0
        for item in res or []:
            if len(item) < 3:
                continue
            d = re.sub(r"\D", "", str(item[1]))
            c = float(item[2])
            if len(d) == 1 and c >= conf:
                best, conf = d, c
        return best, conf


class Reader:
    def __init__(self, fonts):
        self.fonts = fonts
        self.ocr = NumberReader()

    def classify_cell(self, crop):
        d, score, margin = self.fonts.match(crop)
        if d and score >= FONT_SCORE and margin >= FONT_MARGIN:
            return d, score, "font"
        od, oc = "", 0.0
        if not (d and score >= 0.72):
            od, oc = self.ocr.one_digit(crop)
        if d and score >= 0.50 and (not od or score >= oc):
            return d, score, "font"
        if len(od) == 1:
            return od, oc, "ocr"
        if d:
            return d, score, "font-weak"
        return "", 0.0, ""

    def read(self, house):
        if house is None or house.size == 0:
            return "", 0.0, {}
        gray = upscale_to_height(to_gray(house), UPSCALE_HOUSING_H)
        splits = []
        for name, crops in (("cells", find_digit_cells(gray)), ("ink", ink_four(gray)), ("equal", equal_four(gray))):
            if crops and len(crops) == NUMBER_DIGITS:
                splits.append((name, crops))
        best = None
        alts = []
        for name, crops in splits:
            digits, scores, sources = [], [], []
            ok = True
            for crop in crops:
                d, sc, src = self.classify_cell(crop)
                if len(d) != 1:
                    ok = False
                    break
                digits.append(d)
                scores.append(float(sc))
                sources.append(src)
            if not ok:
                continue
            num = "".join(digits)
            alts.append(num)
            strong = sum(1 for s in sources if s in ("font", "ocr"))
            font_n = sources.count("font")
            mean = float(np.mean(scores))
            item = (strong, font_n, mean, num, scores, sources, name)
            if best is None or item[:3] > best[:3]:
                best = item
        if best is None:
            return "", 0.0, {"alts": alts}
        _strong, font_n, mean, num, scores, sources, name = best
        if font_n == 4:
            method = "font"
        elif font_n == 0:
            method = "ocr"
        else:
            method = "hybrid"
        return num, mean, {"method": method, "split": name, "scores": [round(s, 3) for s in scores],
                           "sources": sources, "alts": [a for a in alts if a != num]}


class VisitTracker:
    def __init__(self):
        self.visit = None

    def reset(self):
        self.visit = None

    def _new(self, tag, house, frame_idx, t):
        return {
            "start": t, "last": t, "samples": 1, "frame": frame_idx, "time": t,
            "best_house": None if house is None else house.copy(),
            "best_tag": None if tag is None or tag.size == 0 else tag.copy(),
            "prev_band": None, "motion": 1.0, "stable_since": None, "motion_state": "",
            "best_still_motion": 9.0, "best_still_house": None, "best_still_frame": frame_idx,
            "best_still_time": t, "final": "", "final_conf": 0.0, "final_meta": {},
            "attempts": 0, "saved": False,
        }

    def update(self, is_close, tag, house, frame_idx, t):
        if is_close and house is not None and house.size > 0:
            if self.visit is None:
                self.visit = self._new(tag, house, frame_idx, t)
            band = digit_band(house)
            if self.visit.get("prev_band") is not None:
                motion = binary_diff(self.visit["prev_band"], band, (96, 32))
            else:
                motion = 1.0
            self.visit["motion"] = motion
            self.visit["prev_band"] = None if band is None else band.copy()
            if motion <= FREEZE_DIFF:
                if self.visit["stable_since"] is None:
                    self.visit["stable_since"] = t
            else:
                self.visit["stable_since"] = None
            if motion < self.visit.get("best_still_motion", 9.0):
                self.visit["best_still_motion"] = motion
                self.visit["best_still_house"] = house.copy()
                self.visit["best_still_frame"] = frame_idx
                self.visit["best_still_time"] = t
                self.visit["best_house"] = house.copy()
                if tag is not None and tag.size > 0:
                    self.visit["best_tag"] = tag.copy()
            self.visit["last"] = t
            self.visit["samples"] += 1
            return None
        if self.visit is not None and (t - self.visit["last"]) >= CLOSEUP_MISS_SEC:
            done = self.visit
            self.reset()
            return done
        return None

    @staticmethod
    def frozen(visit, t):
        since = visit.get("stable_since")
        return since is not None and (t - since) >= FREEZE_HOLD_SEC and visit.get("motion", 1) <= FREEZE_DIFF


def compare_both(entries):
    pool = Counter(OFFICIAL_NUMBERS)
    matched, not_in_result, duplicates, short = [], [], [], []
    for e in entries:
        n = e.get("number") or ""
        e["match"] = ""
        if len(n) != NUMBER_DIGITS:
            e["match"] = "short"
            short.append({"roller": e["roller"], "number": n})
            continue
        if pool[n] > 0:
            pool[n] -= 1
            e["match"] = "ok"
            matched.append({"roller": e["roller"], "number": n})
        elif n in OFFICIAL_NUMBERS:
            e["match"] = "duplicate"
            duplicates.append({"roller": e["roller"], "number": n})
        else:
            e["match"] = "wrong"
            not_in_result.append({"roller": e["roller"], "number": n})
    missing = [n for n in OFFICIAL_NUMBERS if pool[n] > 0]
    return {"ready": len(entries) == EXPECTED, "matched_count": len(matched), "matched": matched,
            "missing_from_extraction": missing, "not_in_result": not_in_result,
            "duplicates": duplicates, "short": short}


def validation_text(report):
    lines = [
        "Checked both lists. Reads were not changed.",
        "Matched %d. Not in result %d. Duplicate %d. Short %d. Missing %d." % (
            report["matched_count"], len(report["not_in_result"]), len(report["duplicates"]),
            len(report["short"]), len(report["missing_from_extraction"])),
        "Missing: " + (", ".join(report["missing_from_extraction"]) or "none"),
        "Not in result: " + (", ".join("r%d=%s" % (x["roller"], x["number"]) for x in report["not_in_result"]) or "none"),
    ]
    if report["duplicates"]:
        lines.append("Duplicates: " + ", ".join("r%d=%s" % (x["roller"], x["number"]) for x in report["duplicates"]))
    if report["short"]:
        lines.append("Not 4 digits: " + ", ".join("r%d" % x["roller"] for x in report["short"]))
    if report["ready"] and not any(report[k] for k in ("missing_from_extraction", "not_in_result", "duplicates", "short")):
        lines.append("All 19 match the result list.")
    return "\n".join(lines)


class ScanApp:
    def __init__(self, root):
        self.root = root
        root.title("4th prize — read after the digits stop")
        root.geometry("1460x960")
        root.configure(bg="#f0f0f0")
        self.cap = None
        self.video_path = None
        self.fps = 30.0
        self.total = 1
        self.frame = None
        self.frame_idx = 0
        self.photo = None
        self.thumbs = {}
        self.playing = False
        self.scanning = False
        self.after_id = None
        self.seek_after = None
        self.slider_guard = False
        self.boxes = load_boxes(ROI_FILE)
        self.fonts = DigitFonts(FONT_DIR)
        self.reader = Reader(self.fonts)
        self.tracker = VisitTracker()
        self.analysis = None
        self.machine_seen = False
        self.entries = []
        self.selected = None
        self.beat = -1
        self.validation = None
        self.freeze_text = ""
        self.build_ui()
        self.log("ROI: %s (%d tags)" % (ROI_FILE, len(self.boxes)))
        self.log("Fonts: %d samples in %s" % (self.fonts.count, FONT_DIR))
        if self.fonts.count < 10:
            self.log("Capture 0-9 with font_capture.py before expecting a clean scan.")
        self.log("Play speed. No read until the digit band stops.")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        left = Frame(self.root, bg="#f0f0f0")
        left.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        right = Frame(self.root, bg="#ffffff", width=460, relief="solid", bd=1)
        right.pack(side="right", fill="y", padx=(0, 8), pady=8)
        right.pack_propagate(False)
        top = Frame(left, bg="#f0f0f0")
        top.pack(fill="x")
        Button(top, text="Open Video", command=self.open_video, bg="#4CAF50", fg="white",
               font=("Arial", 10, "bold")).pack(side="left", padx=(0, 4))
        self.play_btn = Button(top, text="Play", command=self.toggle_play, bg="#607D8B", fg="white",
                               font=("Arial", 10, "bold"), width=8)
        self.play_btn.pack(side="left", padx=2)
        Label(top, text="Start", bg="#f0f0f0").pack(side="left", padx=(8, 2))
        self.start_var = StringVar(value="00:09:30")
        Entry(top, textvariable=self.start_var, width=10, font=("Courier", 10)).pack(side="left")
        Button(top, text="Set Start", command=self.set_start_here).pack(side="left", padx=3)
        self.scan_btn = Button(top, text="START SCAN", command=self.start_scan, bg="#2196F3", fg="white",
                               font=("Arial", 10, "bold"))
        self.scan_btn.pack(side="left", padx=3)
        self.stop_btn = Button(top, text="Stop", command=self.stop_scan, bg="#f44336", fg="white",
                               font=("Arial", 10, "bold"), state=DISABLED)
        self.stop_btn.pack(side="left", padx=2)
        Button(top, text="Validate", command=self.validate_clicked, bg="#6A1B9A", fg="white",
               font=("Arial", 10, "bold")).pack(side="left", padx=2)
        Button(top, text="Export", command=self.export, bg="#FF9800", fg="white",
               font=("Arial", 10, "bold")).pack(side="left", padx=2)
        self.video_label = Label(left, text="No video", bg="#f0f0f0", fg="#555", anchor="w")
        self.video_label.pack(fill="x")
        self.canvas = Canvas(left, width=CANVAS_W, height=CANVAS_H, bg="black", highlightthickness=0)
        self.canvas.pack(pady=4)
        self.pos_var = DoubleVar()
        self.slider = ttk.Scale(left, from_=0, to=1, orient="horizontal", variable=self.pos_var, command=self.on_slider)
        self.slider.pack(fill="x")
        self.time_label = Label(left, text="00:00:00 / 00:00:00", font=("Courier", 12, "bold"), bg="#f0f0f0")
        self.time_label.pack()
        nav = Frame(left, bg="#f0f0f0")
        nav.pack(pady=4)
        for txt, sec in [("-60s", -60), ("-10s", -10), ("-1s", -1), ("+1s", 1), ("+10s", 10), ("+60s", 60)]:
            Button(nav, text=txt, width=6, command=lambda s=sec: self.skip(s)).pack(side="left", padx=2)
        Button(nav, text="Test Frame", command=self.test_frame, bg="#7B1FA2", fg="white",
               font=("Arial", 10, "bold")).pack(side="left", padx=8)
        Button(nav, text="Reload Fonts", command=self.reload_fonts).pack(side="left", padx=4)
        self.hint = Label(left, bg="#f0f0f0", fg="#333", font=("Arial", 9), anchor="w",
                          text="Green = machine ID, not a read. A read happens only after a close-up digit band stops.")
        self.hint.pack(fill="x")
        Label(right, text="What this frame is", font=("Arial", 12, "bold"), bg="#fff").pack(anchor="w", padx=10, pady=(8, 0))
        self.status = Label(right, text="Open the video.", bg="#fff", fg="#222", justify="left",
                            font=("Courier", 9), wraplength=430)
        self.status.pack(anchor="w", padx=10, pady=4)
        self.found_label = Label(right, text="Close-ups read: 0 / 19", bg="#fff", fg="#1565C0", font=("Arial", 13, "bold"))
        self.found_label.pack(anchor="w", padx=10)
        self.gate_label = Label(right, text="Machine: not seen yet", bg="#fff", fg="#E65100", font=("Arial", 10, "bold"))
        self.gate_label.pack(anchor="w", padx=10)
        self.font_label = Label(right, text="", bg="#fff", fg="#455A64", font=("Arial", 9), justify="left", wraplength=430)
        self.font_label.pack(anchor="w", padx=10)
        self.valid_label = Label(right, text="Validation: waits for 19 reads", bg="#fff", fg="#6A1B9A",
                                 font=("Arial", 9, "bold"), justify="left", wraplength=430)
        self.valid_label.pack(anchor="w", padx=10, pady=(2, 4))
        self.refresh_font_label()
        crops = Frame(right, bg="#fff")
        crops.pack(fill="x", padx=10)
        self.house_thumb = Label(crops, bg="#eee")
        self.house_thumb.pack(side="left")
        self.tag_thumb = Label(crops, bg="#eee")
        self.tag_thumb.pack(side="left", padx=6)
        Label(right, text="Log", font=("Arial", 11, "bold"), bg="#fff").pack(anchor="w", padx=10)
        self.log_box = Text(right, height=8, font=("Courier", 8), bg="#fafafa", state=DISABLED)
        self.log_box.pack(fill="x", padx=10)
        Label(right, text="Close-up reads (click a row to jump)", font=("Arial", 11, "bold"), bg="#fff").pack(anchor="w", padx=10, pady=(6, 0))
        self.listbox = Listbox(right, font=("Courier", 9), height=11, selectmode=SINGLE)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=4)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        edit = Frame(right, bg="#fff")
        edit.pack(fill="x", padx=10, pady=(0, 8))
        Label(edit, text="Correct", bg="#fff").pack(side="left")
        self.edit_var = StringVar()
        Entry(edit, textvariable=self.edit_var, width=6, font=("Courier", 14)).pack(side="left", padx=4)
        Button(edit, text="Save", command=self.save_correction, bg="#4CAF50", fg="white").pack(side="left", padx=2)
        Button(edit, text="Delete", command=self.delete_selected, bg="#f44336", fg="white").pack(side="left", padx=2)
        Button(edit, text="Clear", command=self.clear_results).pack(side="left", padx=2)

    def log(self, msg):
        self.log_box.config(state=NORMAL)
        self.log_box.insert(END, str(msg) + "\n")
        self.log_box.see(END)
        self.log_box.config(state=DISABLED)
        try:
            print(msg, flush=True)
        except Exception:
            print(str(msg).encode("ascii", "replace").decode("ascii"), flush=True)

    def refresh_font_label(self):
        self.font_label.config(text="Fonts: %d samples. A confident font overrides OCR." % self.fonts.count)

    def reload_fonts(self):
        n = self.fonts.reload()
        self.refresh_font_label()
        self.log("Reloaded %d font samples." % n)

    def frame_delay_ms(self):
        fps = self.fps if self.fps and self.fps > 1 else 30.0
        return max(1, int(round(1000.0 / fps)))

    def open_video(self):
        path = filedialog.askopenfilename(title="Select video",
                                          filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv"), ("All", "*.*")])
        if not path:
            return
        self.stop_playback()
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
        self.boxes = load_boxes(ROI_FILE)
        self.machine_seen = False
        self.gate_label.config(text="Machine: not seen yet", fg="#E65100")
        self.log("Opened %s  fps=%.2f" % (Path(path).name, self.fps))
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
        self.analysis = classify(self.frame, self.boxes)
        self.show_frame(self.analysis)
        self.show_status(self.analysis, "PAUSED")

    def skip(self, sec):
        if self.cap and not self.playing and not self.scanning:
            self.seek(self.frame_idx + sec * self.fps)

    def on_slider(self, value):
        if self.slider_guard or not self.cap or self.playing or self.scanning:
            return
        if self.seek_after:
            self.root.after_cancel(self.seek_after)
        self.seek_after = self.root.after(80, lambda: self.seek(float(value)))

    def set_start_here(self):
        self.start_var.set(fmt_hms(self.t_now()))

    def update_time_ui(self):
        self.slider_guard = True
        self.pos_var.set(self.frame_idx)
        self.slider_guard = False
        self.time_label.config(text="%s / %s" % (fmt_hms(self.t_now()), fmt_hms(self.total / self.fps)))

    def show_frame(self, a=None):
        if self.frame is None:
            return
        h, w = self.frame.shape[:2]
        s = min(CANVAS_W / float(w), CANVAS_H / float(h))
        dw, dh = int(w * s), int(h * s)
        ox, oy = (CANVAS_W - dw) // 2, (CANVAS_H - dh) // 2
        rgb = cv2.cvtColor(cv2.resize(self.frame, (dw, dh), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, image=self.photo, anchor="nw")
        hits = (a or {}).get("hits") or {}
        for b in self.boxes:
            tag = b["tag"]
            color = "#00E676" if hits.get(b["roller"]) else "#FF5252"
            self.canvas.create_rectangle(ox + tag["x"] * s, oy + tag["y"] * s,
                                         ox + (tag["x"] + tag["w"]) * s, oy + (tag["y"] + tag["h"]) * s,
                                         outline=color, width=2)
        scene = (a or {}).get("scene", "")
        if a and a.get("close") and scene == "closeup":
            k = s * w / float(ANALYSIS_W)
            lab = a["close"]["label"]
            hx1, hy1, hx2, hy2 = a["close"]["housing"]
            self.canvas.create_rectangle(ox + lab[0] * k, oy + lab[1] * k,
                                         ox + (lab[0] + lab[2]) * k, oy + (lab[1] + lab[3]) * k,
                                         outline="#FFEB3B", width=3)
            self.canvas.create_rectangle(ox + hx1 * k, oy + hy1 * k, ox + hx2 * k, oy + hy2 * k,
                                         outline="#00E5FF", width=3)
        banner = {"machine": "MACHINE — identification only, NOT reading",
                  "multi": "SEVERAL ROLLERS — NOT reading",
                  "closeup": "CLOSE-UP — " + (self.freeze_text or "waiting for digits to stop"),
                  "other": "OTHER — waiting"}.get(scene, "")
        color = {"machine": "#00E676", "multi": "#FFB300", "closeup": "#00E5FF", "other": "#FFAB40"}.get(scene, "#FFFFFF")
        if banner:
            self.canvas.create_rectangle(ox, oy, ox + 760, oy + 32, fill="#000000", outline="")
            self.canvas.create_text(ox + 8, oy + 16, anchor="w", fill=color, font=("Courier", 12, "bold"), text=banner)
        self.update_time_ui()

    def show_status(self, a, mode):
        if not a:
            return
        lines = ["%s  %s" % (mode, fmt_hms(self.t_now())),
                 "Marked tags on yellow: %d / %d" % (a["hit_count"], a["valid"])]
        if a["scene"] == "machine":
            lines.append("Machine identification only. Not reading.")
        elif a["scene"] == "closeup":
            lines.append(self.freeze_text or "Close-up. Waiting for the digits to stop.")
        else:
            lines.append("Not reading.")
        self.status.config(text="\n".join(lines))
        if self.machine_seen:
            self.gate_label.config(text="Machine: seen. Reading later frozen close-ups only.", fg="#2E7D32")
        self.found_label.config(text="Close-ups read: %d / %d" % (len(self.entries), EXPECTED))

    def crops_of(self, a):
        if not a or not a.get("close") or self.frame is None:
            return None, None
        h, w = self.frame.shape[:2]
        sc = w / float(ANALYSIS_W)
        lx, ly, lw, lh = a["close"]["label"]
        tag = self.frame[max(0, int(ly * sc)):min(h, int((ly + lh) * sc)),
                         max(0, int(lx * sc)):min(w, int((lx + lw) * sc))]
        hx1, hy1, hx2, hy2 = a["close"]["housing"]
        pad = 6
        house = refine_housing(self.frame[max(0, int(hy1 * sc) - pad):min(h, int(hy2 * sc) + pad),
                                           max(0, int(hx1 * sc) - pad):min(w, int(hx2 * sc) + pad)])
        return tag, house

    def show_thumb(self, img, label, key, max_w=240, max_h=70):
        if img is None or getattr(img, "size", 0) == 0:
            label.config(image="")
            return
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if img.ndim == 3 else img
        im = Image.fromarray(rgb)
        im.thumbnail((max_w, max_h))
        self.thumbs[key] = ImageTk.PhotoImage(im)
        label.config(image=self.thumbs[key])

    def stop_playback(self):
        self.playing = False
        self.scanning = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.play_btn.config(text="Play", state=NORMAL)
        self.scan_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)

    def toggle_play(self):
        if not self.cap:
            messagebox.showwarning("No video", "Open a video first.")
            return
        if self.scanning:
            return
        if self.playing:
            self.playing = False
            if self.after_id:
                self.root.after_cancel(self.after_id)
                self.after_id = None
            self.play_btn.config(text="Play")
            return
        self.playing = True
        self.play_btn.config(text="Pause")
        self.play_tick()

    def play_tick(self):
        if not self.playing or not self.cap:
            return
        if not self.read_current():
            self.playing = False
            self.play_btn.config(text="Play")
            return
        self.analysis = classify(self.frame, self.boxes)
        self.freeze_text = ""
        self.show_frame(self.analysis)
        self.show_status(self.analysis, "PLAY")
        self.after_id = self.root.after(self.frame_delay_ms(), self.play_tick)

    def test_frame(self):
        if self.frame is None or self.scanning or self.playing:
            return
        a = classify(self.frame, self.boxes)
        self.analysis = a
        self.freeze_text = ""
        self.show_frame(a)
        self.show_status(a, "TEST")
        if a["scene"] != "closeup":
            self.log("Test %s: %s. No number read." % (fmt_hms(self.t_now()), a["scene"]))
            return
        tag, house = self.crops_of(a)
        self.show_thumb(tag, self.tag_thumb, "tag", 80, 80)
        self.show_thumb(house, self.house_thumb, "house", 280, 80)
        self.log("Test close-up %s. Font first, then OCR." % fmt_hms(self.t_now()))
        self.root.update_idletasks()
        number, conf, meta = self.reader.read(house)
        self.log("Test %s  method %s  scores %s. Not saved." % (
            number or "----", meta.get("method", "none"), meta.get("scores", [])))

    def start_scan(self):
        if not self.cap:
            messagebox.showwarning("No video", "Open a video first.")
            return
        if self.playing:
            self.toggle_play()
        if len(self.boxes) < 8:
            messagebox.showwarning("No ROI", "roller_boxes.json needs the 18 yellow tags.")
            return
        keep = False
        if self.entries:
            ans = messagebox.askyesnocancel("Reads", "Keep numbers already read?\n\nYes = continue\nNo = clear\nCancel = stop")
            if ans is None:
                return
            keep = bool(ans)
            if not keep:
                self.entries = []
                self.validation = None
                self.valid_label.config(text="Validation: waits for 19 reads", fg="#6A1B9A")
                self.refresh_list()
        self.fonts.reload()
        self.refresh_font_label()
        if keep:
            start_f = self.frame_idx
            self.machine_seen = True
        else:
            start_f = min(self.total - 1, int(parse_time(self.start_var.get()) * self.fps))
            self.machine_seen = False
            self.gate_label.config(text="Machine: not seen yet", fg="#E65100")
        self.tracker.reset()
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
        self.frame_idx = max(0, start_f - 1)
        self.beat = -1
        self.scanning = True
        self.scan_btn.config(state=DISABLED)
        self.stop_btn.config(state=NORMAL)
        self.play_btn.config(state=DISABLED)
        self.log("SCAN from %s at Play speed. Fonts: %d." % (fmt_hms(start_f / self.fps), self.fonts.count))
        self.scan_tick()

    def stop_scan(self):
        if not self.scanning and self.after_id is None:
            return
        self.scanning = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        pending = self.tracker.visit
        self.tracker.reset()
        if pending and self.machine_seen and len(self.entries) < EXPECTED:
            self.commit(pending)
        self.play_btn.config(state=NORMAL, text="Play")
        self.scan_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)
        self.log("SCAN stopped. %d / %d" % (len(self.entries), EXPECTED))
        if len(self.entries) == EXPECTED:
            self.validate(popup=False)

    def scan_tick(self):
        if not self.scanning or not self.cap:
            return
        t0 = time.time()
        try:
            if not self.read_current():
                self.show_frame(self.analysis)
                self.finish_scan("end of video")
                return
            self.process_sample()
            if not self.scanning:
                return
            self.show_frame(self.analysis)
        except Exception as e:
            self.log("Scan error: %s" % e)
            self.stop_scan()
            return
        delay = max(1, self.frame_delay_ms() - int((time.time() - t0) * 1000))
        if self.scanning:
            self.after_id = self.root.after(delay, self.scan_tick)

    def process_sample(self):
        t = self.t_now()
        a = classify(self.frame, self.boxes)
        self.analysis = a
        scene = a["scene"]
        beat = int(t) // 5
        if beat != self.beat and scene != "closeup":
            self.beat = beat
            self.log("%s  %s  roi %d/%d  read %d/%d" % (
                fmt_hms(t), scene, a["hit_count"], a["valid"], len(self.entries), EXPECTED))
        if scene == "machine":
            self.freeze_text = ""
            if not self.machine_seen:
                self.machine_seen = True
                self.gate_label.config(text="Machine: seen. Reading later frozen close-ups only.", fg="#2E7D32")
                self.log("%s  MACHINE seen. Not reading this board." % fmt_hms(t))
            if self.tracker.visit:
                done = self.tracker.visit
                self.tracker.reset()
                self.commit(done)
            self.show_status(a, "SCAN")
            return
        if not self.machine_seen:
            self.freeze_text = ""
            self.show_status(a, "SCAN")
            return
        if scene == "closeup":
            tag, house = self.crops_of(a)
            self.show_thumb(tag, self.tag_thumb, "tag", 80, 80)
            self.show_thumb(house, self.house_thumb, "house", 280, 80)
            done = self.tracker.update(True, tag, house, self.frame_idx, t)
            if done:
                self.commit(done)
            visit = self.tracker.visit
            if visit is not None:
                frozen = VisitTracker.frozen(visit, t)
                state = "FROZEN" if frozen else "spinning"
                self.freeze_text = "%s  motion %.3f" % (state, visit.get("motion", 1))
                if visit.get("motion_state") != state:
                    visit["motion_state"] = state
                    self.log("%s  close-up %s  motion %.3f" % (fmt_hms(t), state, visit.get("motion", 1)))
                if frozen and not visit.get("final") and visit.get("attempts", 0) < 2:
                    self.read_into(visit, house, t, "frozen")
        else:
            self.freeze_text = ""
            done = self.tracker.update(False, None, None, self.frame_idx, t)
            if done:
                self.commit(done)
        self.show_status(a, "SCAN")

    def read_into(self, visit, house, t, why):
        visit["attempts"] = visit.get("attempts", 0) + 1
        self.status.config(text="Digits stopped. Reading 4 digits...")
        self.root.update_idletasks()
        number, conf, meta = self.reader.read(house)
        if len(number) != 4:
            self.log("  %s frame had no 4-digit read" % why)
            return False
        visit["final"] = number
        visit["final_conf"] = conf
        visit["final_meta"] = meta
        visit["final_why"] = why
        visit["frame"] = self.frame_idx
        visit["time"] = t
        visit["best_house"] = house.copy()
        self.log("  %s %s  %s  %s" % (why, number, meta.get("method", ""), meta.get("scores", [])))
        if meta.get("alts"):
            self.log("    other splits: %s" % ", ".join(meta["alts"][:4]))
        return True

    def commit(self, visit):
        if visit.get("saved") or len(self.entries) >= EXPECTED:
            return
        if visit.get("samples", 0) < 2 and (visit["last"] - visit["start"]) < 0.20:
            return
        why = visit.get("final_why", "")
        number = visit.get("final") or ""
        conf = visit.get("final_conf", 0.0)
        meta = visit.get("final_meta") or {}
        frame = visit.get("frame")
        when = visit.get("time")
        if not number:
            house = visit.get("best_still_house")
            motion = visit.get("best_still_motion", 9)
            if house is not None and motion <= STILL_ACCEPT:
                self.read_into(visit, house, visit.get("best_still_time", when), "stillest")
                number = visit.get("final") or ""
                conf = visit.get("final_conf", 0.0)
                meta = visit.get("final_meta") or {}
                why = visit.get("final_why", "stillest")
                frame = visit.get("frame")
                when = visit.get("time")
            else:
                why = "not-frozen"
                self.log("  close-up never stopped (min motion %.3f). Saved blank." % motion)
        visit["saved"] = True
        roller = len(self.entries) + 1
        entry = {
            "roller": roller, "spin": (roller - 1) // NUM_PER_SPIN + 1,
            "number": number, "confidence": round(float(conf), 3),
            "time": fmt_mmss(when or visit["time"]), "time_hms": fmt_hms(when or visit["time"]),
            "seconds": round(float(when or visit["time"]), 2), "frame": int(frame or visit["frame"]),
            "method": meta.get("method", why or "none"), "why": why or "frozen",
            "scores": meta.get("scores", []), "duplicate": False, "match": "",
            "motion": round(float(visit.get("best_still_motion", visit.get("motion", 1))), 3),
        }
        self.entries.append(entry)
        self.recheck_duplicates()
        self.validation = None
        self.refresh_list()
        self.log("%s  close-up %02d  %s  %s" % (entry["time_hms"], roller, number or "----", entry["method"]))
        if len(self.entries) >= EXPECTED and self.scanning:
            self.finish_scan("19 close-ups read")

    def finish_scan(self, reason):
        self.scanning = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        pending = self.tracker.visit
        self.tracker.reset()
        if pending and self.machine_seen and len(self.entries) < EXPECTED:
            self.commit(pending)
        self.play_btn.config(state=NORMAL, text="Play")
        self.scan_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)
        extra = ""
        if len(self.entries) == EXPECTED:
            extra = "\n\n" + self.validate(popup=False)
        self.log("SCAN done (%s). %d / %d" % (reason, len(self.entries), EXPECTED))
        messagebox.showinfo("Scan", "%s\nClose-ups read: %d / %d%s" % (reason, len(self.entries), EXPECTED, extra))

    def validate(self, popup=False):
        report = compare_both(self.entries)
        self.validation = report
        text = validation_text(report)
        self.refresh_list()
        ok = report["ready"] and not any(report[k] for k in ("missing_from_extraction", "not_in_result", "duplicates", "short"))
        self.valid_label.config(text="Matched %d/%d | missing %d | not in result %d" % (
            report["matched_count"], EXPECTED, len(report["missing_from_extraction"]), len(report["not_in_result"])),
            fg="#2E7D32" if ok else "#B71C1C")
        for line in text.splitlines():
            self.log(line)
        if popup:
            messagebox.showinfo("Validation", text)
        return text

    def validate_clicked(self):
        if len(self.entries) != EXPECTED:
            messagebox.showwarning("Validation", "Need 19 reads first. Have %d." % len(self.entries))
            return
        self.validate(popup=True)

    def recheck_duplicates(self):
        seen = {}
        for e in self.entries:
            n = e["number"]
            e["duplicate"] = bool(n) and len(n) == 4 and n in seen
            if len(n) == 4 and n not in seen:
                seen[n] = e["roller"]

    def refresh_list(self):
        self.listbox.delete(0, END)
        colors = {"ok": "#1B5E20", "wrong": "#B71C1C", "duplicate": "#E65100", "short": "#6A1B9A"}
        for i, e in enumerate(self.entries):
            mark = {"ok": " OK", "wrong": " NOT-IN-RESULT", "duplicate": " DUP", "short": " ??"}.get(e.get("match"), "")
            if not mark and len(e["number"]) != 4:
                mark = " ??"
            self.listbox.insert(END, "%2d  %s  %-6s  %s%s" % (
                e["roller"], (e["number"] or "----").ljust(4), e.get("method", ""), e["time_hms"], mark))
            if e.get("match") in colors:
                self.listbox.itemconfig(i, fg=colors[e["match"]])
        self.found_label.config(text="Close-ups read: %d / %d" % (len(self.entries), EXPECTED))

    def on_select(self, _evt):
        if self.scanning or self.playing:
            return
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self.entries):
            return
        self.selected = sel[0]
        e = self.entries[self.selected]
        self.edit_var.set(e["number"])
        self.seek(e["frame"])

    def save_correction(self):
        if self.selected is None or self.selected >= len(self.entries):
            messagebox.showwarning("Select", "Click a row first.")
            return
        n = four(self.edit_var.get())
        if not n:
            messagebox.showwarning("Number", "Enter exactly 4 digits.")
            return
        self.entries[self.selected]["number"] = n
        self.entries[self.selected]["confidence"] = 1.0
        self.entries[self.selected]["method"] = "manual"
        self.entries[self.selected]["match"] = ""
        self.recheck_duplicates()
        self.refresh_list()
        self.log("Corrected close-up %d -> %s" % (self.entries[self.selected]["roller"], n))
        if len(self.entries) == EXPECTED:
            self.validate(popup=False)

    def delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        gone = self.entries.pop(sel[0])
        for i, e in enumerate(self.entries, start=1):
            e["roller"] = i
            e["spin"] = (i - 1) // NUM_PER_SPIN + 1
            e["match"] = ""
        self.recheck_duplicates()
        self.selected = None
        self.validation = None
        self.valid_label.config(text="Validation: waits for 19 reads", fg="#6A1B9A")
        self.refresh_list()
        self.log("Deleted %s. Rollers renumbered." % (gone["number"] or "blank"))

    def clear_results(self):
        if self.entries and not messagebox.askyesno("Clear", "Delete all reads?"):
            return
        self.entries = []
        self.selected = None
        self.validation = None
        self.valid_label.config(text="Validation: waits for 19 reads", fg="#6A1B9A")
        self.refresh_list()

    def export(self):
        if not self.entries:
            messagebox.showwarning("Empty", "No close-up reads yet.")
            return
        if len(self.entries) == EXPECTED:
            self.validate(popup=False)
        data = {"prize": PRIZE, "expected_numbers": EXPECTED,
                "video": Path(self.video_path).name if self.video_path else "",
                "official_numbers": OFFICIAL_NUMBERS, "validation": self.validation,
                "entries": self.entries}
        OUT_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
        with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["prize", "spin", "roller", "number", "method", "why", "confidence",
                        "time", "time_hms", "seconds", "frame", "duplicate", "match", "motion"])
            for e in self.entries:
                w.writerow([PRIZE, e["spin"], e["roller"], e["number"], e.get("method", ""), e.get("why", ""),
                            e["confidence"], e["time"], e["time_hms"], e["seconds"], e["frame"],
                            "yes" if e["duplicate"] else "no", e.get("match", ""), e.get("motion", "")])
        self.log("Saved %s and %s" % (OUT_JSON.name, OUT_CSV.name))
        messagebox.showinfo("Saved", "Saved:\n%s\n%s" % (OUT_JSON, OUT_CSV))

    def on_close(self):
        self.playing = False
        self.scanning = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
        if self.cap:
            self.cap.release()
        self.root.destroy()


if __name__ == "__main__":
    root = Tk()
    ScanApp(root)
    root.mainloop()
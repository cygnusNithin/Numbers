"""
font_capture.py
Capture the 0-9 digit font from a stopped one-roller close-up.

Mark a digit and the check runs at the same time: saved fonts and OCR.
Your key press is the label that gets saved. The guess is not saved.

The full board is rejected. Digits there are too small.
Saved to digit_fonts/0 .. digit_fonts/9.

No threading. No cv2.imshow. No debug images outside digit_fonts.
Run: python font_capture.py
"""
import csv
from pathlib import Path
from tkinter import (Tk, Frame, Label, Button, Canvas, Text, Entry, StringVar,
                     DoubleVar, messagebox, filedialog, END, DISABLED, NORMAL,
                     )
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

FONT_W, FONT_H = 32, 48
ANALYSIS_W = 640
CANVAS_W, CANVAS_H = 900, 506
HOUSE_W, HOUSE_H = 500, 250

YELLOW_LO = (15, 90, 120)
YELLOW_HI = (40, 255, 255)
CLOSEUP_MIN_FRAC = 0.008
CLOSEUP_DOMINANT = 2.5
MULTI_TAGS = 4
HOUSING_WHITE_MIN = 0.22

HERE = Path(__file__).resolve().parent
FONT_DIR = HERE / "digit_fonts"
INDEX_CSV = FONT_DIR / "index.csv"


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
    f = target_h / max(1, gray.shape[0])
    return cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)


def imread_gray(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)


def imwrite_png(path, img):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(str(path))
    return bool(ok)


def remove_frame_lines(inv):
    """Remove border lines only. A centered 1 is not a frame line."""
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

    def match(self, img):
        norm = img if (img is not None and img.shape[:2] == (FONT_H, FONT_W)) else normalize_font(img)
        best = ("", -1.0)
        second = ("", -1.0)
        if norm is None or sum(len(v) for v in self.samples.values()) == 0:
            return "", -1.0, "", -1.0, norm
        for digit, samples in self.samples.items():
            for sample in samples:
                s = score_pair(norm, sample)
                if s > best[1]:
                    second = best
                    best = (digit, s)
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
            w.writerow([digit, str(norm_path.name), meta.get("time", ""), meta.get("video", "")])
        self.samples[digit].append(cv2.resize(norm, (FONT_W, FONT_H)))
        self.paths[digit].append(norm_path)
        self.last.append((digit, norm_path, raw_path))
        return norm_path

    def rebuild_index(self):
        """Recreate the manifest from the samples that still exist on disk."""
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
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE,
                             cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
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


def fallback_boxes(shape):
    h, w = shape[:2]
    x0, x1 = int(w * 0.05), int(w * 0.95)
    y0, y1 = int(h * 0.20), int(h * 0.82)
    span = max(4, x1 - x0)
    cell_w = span / 4.0
    boxes = []
    for i in range(4):
        xa = int(x0 + i * cell_w + cell_w * 0.16)
        xb = int(x0 + (i + 1) * cell_w - cell_w * 0.16)
        ya = int(y0 + (y1 - y0) * 0.08)
        yb = int(y1 - (y1 - y0) * 0.06)
        if xb - xa >= 4 and yb - ya >= 8:
            boxes.append((xa, ya, xb - xa, yb - ya))
    return boxes


def propose_boxes(housing):
    """Find the four dark digit glyphs; fall back only when the frame is unclear."""
    if housing is None or getattr(housing, "size", 0) == 0:
        return []
    gray = to_gray(housing)
    h, w = gray.shape[:2]
    if h < 20 or w < 40:
        return fallback_boxes(gray.shape)

    # Digits are black and centred in the white enclosure.  This rejects the
    # outer frame, screws and the red background before selecting components.
    min_area = max(18, int(h * w * 0.006))
    candidates = []
    # A lower threshold separates a black digit from its dark cell border on
    # frames where the lighting makes them touch at the normal threshold.
    for threshold in (90, 100, 70):
        dark = (gray < threshold).astype(np.uint8) * 255
        count, _labels, stats, _centres = cv2.connectedComponentsWithStats(dark, connectivity=8)
        found = []
        for i in range(1, count):
            x, y, bw, bh, area = stats[i]
            if not (0.10 * w <= x <= 0.88 * w and 0.22 * h <= y <= 0.70 * h):
                continue
            if bh < 0.18 * h or bh > 0.42 * h or bw < 0.035 * w or bw > 0.14 * w:
                continue
            if area < min_area or not 0.20 <= bw / float(bh) <= 0.90:
                continue
            found.append((int(x), int(y), int(bw), int(bh), int(area)))
        found.sort(key=lambda item: item[0])
        if len(found) == 4:
            candidates = found
            break
    if len(candidates) != 4:
        return fallback_boxes(gray.shape)

    centres = [x + bw / 2.0 for x, _y, bw, _bh, _area in candidates]
    gaps = np.diff(centres)
    if len(gaps) != 3 or min(gaps) < 0.10 * w or max(gaps) > 1.8 * min(gaps):
        return fallback_boxes(gray.shape)

    boxes = []
    for x, y, bw, bh, _area in candidates:
        pad_x = max(4, int(round(bw * 0.30)))
        pad_y = max(5, int(round(bh * 0.15)))
        xa, ya = max(0, x - pad_x), max(0, y - pad_y)
        xb, yb = min(w, x + bw + pad_x), min(h, y + bh + pad_y)
        boxes.append((xa, ya, xb - xa, yb - ya))
    return boxes

class FontApp:
    def __init__(self, root):
        self.root = root
        root.title("Digit font capture — close-ups only")
        root.geometry("1480x960")
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
        self.log("Pause on a CLOSE-UP. Click a cyan box or drag one digit.")
        self.log("The check appears before you save. Press the digit YOU see.")
        root.bind("<Key>", self.on_key)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

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
        Entry(top, textvariable=self.jump_var, width=10, font=("Courier", 10)).pack(side="left")
        Button(top, text="Go", command=self.jump_to, width=4).pack(side="left", padx=2)

        self.video_label = Label(left, text="No video", bg="#f0f0f0", fg="#555", anchor="w")
        self.video_label.pack(fill="x")
        self.canvas = Canvas(left, width=CANVAS_W, height=CANVAS_H, bg="black", highlightthickness=0)
        self.canvas.pack(pady=4)
        self.canvas.bind("<Button-1>", lambda e: self.press(e, "video"))
        self.canvas.bind("<B1-Motion>", lambda e: self.drag_move(e, "video"))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self.release(e, "video"))
        self.pos_var = DoubleVar()
        self.slider = ttk.Scale(left, from_=0, to=1, orient="horizontal", variable=self.pos_var, command=self.on_slider)
        self.slider.pack(fill="x")
        self.time_label = Label(left, text="00:00:00 / 00:00:00", font=("Courier", 12, "bold"), bg="#f0f0f0")
        self.time_label.pack()
        self.hint = Label(left, bg="#f0f0f0", fg="#333", anchor="w", font=("Arial", 9),
                          text="Green banner = one-roller close-up, the only place a font may be saved. "
                               "Board digits are rejected.")
        self.hint.pack(fill="x")

        Label(right, text="Close-up housing — click a digit", font=("Arial", 12, "bold"), bg="#fff").pack(anchor="w", padx=8, pady=(8, 0))
        self.house_canvas = Canvas(right, width=HOUSE_W, height=HOUSE_H, bg="black", highlightthickness=0)
        self.house_canvas.pack(padx=8, pady=4)
        self.house_canvas.bind("<Button-1>", lambda e: self.press(e, "house"))
        self.house_canvas.bind("<B1-Motion>", lambda e: self.drag_move(e, "house"))
        self.house_canvas.bind("<ButtonRelease-1>", lambda e: self.release(e, "house"))

        self.check_label = Label(right, text="Open a video and pause on a close-up.", bg="#fff", fg="#222",
                                 justify="left", anchor="w", font=("Courier", 10), wraplength=490)
        self.check_label.pack(fill="x", padx=8, pady=4)
        prev = Frame(right, bg="#fff")
        prev.pack(fill="x", padx=8)
        self.norm_label = Label(prev, bg="#ddd")
        self.norm_label.pack(side="left")
        self.crop_label = Label(prev, bg="#ddd")
        self.crop_label.pack(side="left", padx=8)

        Label(right, text="Press the digit you see. The guess above is only a check.", bg="#fff",
              fg="#333", font=("Arial", 9)).pack(anchor="w", padx=8, pady=(8, 2))
        keys = Frame(right, bg="#fff")
        keys.pack(fill="x", padx=8)
        self.digit_btns = {}
        for d in "0123456789":
            b = Button(keys, text=d, width=3, font=("Arial", 14, "bold"), command=lambda n=d: self.save_digit(n))
            b.pack(side="left", padx=1)
            self.digit_btns[d] = b
        Button(right, text="Undo last save", command=self.undo, bg="#f44336", fg="white").pack(anchor="w", padx=8, pady=6)
        self.count_label = Label(right, text="", bg="#fff", fg="#1565C0", justify="left", anchor="w",
                                 font=("Courier", 10), wraplength=490)
        self.count_label.pack(fill="x", padx=8)
        self.strip = Frame(right, bg="#fff")
        self.strip.pack(fill="x", padx=8, pady=2)
        self.strip_labels = []
        for d in "0123456789":
            box = Frame(self.strip, bg="#fff")
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
            im = Image.fromarray(imgs[-1]).resize((42, 63))
            ph = ImageTk.PhotoImage(im)
            self.strip_photos.append(ph)
            self.strip_labels[i].config(image=ph)

    def get_reader(self):
        if self.reader is None:
            import easyocr
            self.check_label.config(text="Loading OCR for the live check...")
            self.root.update_idletasks()
            self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return self.reader

    def ocr_one(self, img):
        gray = to_gray(img)
        if gray is None:
            return "", 0.0
        if gray.shape[0] < 24:
            gray = upscale_to_height(gray, 48)
        try:
            reader = self.get_reader()
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
        if not self.playing:
            self.seek(parse_time(self.jump_var.get()) * self.fps)


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
            self.canvas.create_text(ox + 8, oy + 15, anchor="w", fill=color, font=("Courier", 12, "bold"), text=banner)
        self.update_time()

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
        if not self.analysis or self.analysis.get("scene") != "closeup":
            self.housing = None
            self.housing_rect = None
            self.proposals = []
            self.house_canvas.delete("all")
            self.house_canvas.create_text(20, 20, anchor="nw", fill="#FFAB40", font=("Arial", 12, "bold"),
                                          text="Not a close-up. Capture is refused here.")
            return
        housing, rect = self.housing_from_analysis()
        self.housing = housing
        self.housing_rect = rect
        self.proposals = propose_boxes(housing) if housing is not None else []
        self.redraw_housing()

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
        if self.manual:
            x, y, bw, bh = self.manual
            self.house_canvas.create_rectangle(ox + x * s, oy + y * s, ox + (x + bw) * s, oy + (y + bh) * s,
                                              outline="#FF5252", width=2)
        box = self.drag_box("house")
        if box and self.drag_target == "house":
            x1, y1, x2, y2 = box
            self.house_canvas.create_rectangle(x1, y1, x2, y2, outline="#FF5252", dash=(3, 2))

    def press(self, event, target):
        if self.playing:
            return
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
            x1, y1, x2, y2 = self.drag_box("video")
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="#FF5252", width=2)

    def drag_box(self, target):
        if not self.drag:
            return None
        x1, y1, x2, y2 = self.drag
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    def release(self, event, target):
        if not self.drag or self.playing:
            self.drag = None
            return
        x1, y1, x2, y2 = self.drag
        self.drag = None
        moved = abs(event.x - x1) + abs(event.y - y1) > 8
        if self.analysis is None or self.analysis.get("scene") != "closeup":
            self.check_label.config(text="Not a close-up. Font capture is refused.\nGo to a one-roller close-up.")
            return
        if target == "house" and not moved:
            self.select_proposal(event.x, event.y)
            return
        if target == "house":
            box = self.canvas_box_to_housing(x1, y1, event.x, event.y)
            if box is None:
                return
            self.manual = box
            self.selected = ("manual", 0)
            self.redraw_housing()
            self.inspect(self.crop_housing_box(box), ocr=True)
            return
        box = self.canvas_box_to_frame(x1, y1, event.x, event.y)
        if box is None:
            return
        x, y, bw, bh = box
        self.inspect(self.frame[y:y + bh, x:x + bw], ocr=True)

    def select_proposal(self, x, y):
        if self.housing is None:
            return
        ix = int((x - self.h_off[0]) / self.h_scale)
        iy = int((y - self.h_off[1]) / self.h_scale)
        for i, (bx, by, bw, bh) in enumerate(self.proposals):
            if bx <= ix <= bx + bw and by <= iy <= by + bh:
                self.selected = ("prop", i)
                self.manual = None
                self.redraw_housing()
                self.inspect(self.crop_housing_box((bx, by, bw, bh)), ocr=True)
                return
        self.check_label.config(text="Click inside a cyan digit box, or drag a tighter box.")

    def canvas_box_to_housing(self, x1, y1, x2, y2):
        if self.housing is None:
            return None
        xa = int((min(x1, x2) - self.h_off[0]) / self.h_scale)
        ya = int((min(y1, y2) - self.h_off[1]) / self.h_scale)
        xb = int((max(x1, x2) - self.h_off[0]) / self.h_scale)
        yb = int((max(y1, y2) - self.h_off[1]) / self.h_scale)
        h, w = self.housing.shape[:2]
        xa, ya = max(0, xa), max(0, ya)
        xb, yb = min(w, xb), min(h, yb)
        if xb - xa < 6 or yb - ya < 10:
            self.check_label.config(text="Mark is too small. Draw around the whole digit.")
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
        xa, ya = max(0, xa), max(0, ya)
        xb, yb = min(w, xb), min(h, yb)
        if xb - xa < 6 or yb - ya < 10:
            self.check_label.config(text="Mark is too small. Draw around the whole digit.")
            return None
        return xa, ya, xb - xa, yb - ya

    def crop_housing_box(self, box):
        x, y, w, h = box
        return self.housing[y:y + h, x:x + w]

    def show_small(self, img, label, key_name, size):
        gray = to_gray(img) if img is not None and getattr(img, "ndim", 0) == 3 else img
        if gray is None or getattr(gray, "size", 0) == 0:
            label.config(image="")
            return
        im = Image.fromarray(gray if gray.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        im = im.resize(size)
        ph = ImageTk.PhotoImage(im)
        setattr(self, key_name, ph)
        label.config(image=ph)

    def inspect(self, crop, ocr):
        self.current_crop = crop
        digit, score, second, second_s, norm = self.store.match(crop)
        self.current_norm = norm
        self.show_small(crop, self.crop_label, "crop_photo", (90, 120))
        self.show_small(norm, self.norm_label, "norm_photo", (64, 96))
        if norm is None:
            self.check_label.config(text="No digit ink in this mark.\nDraw around the black number, not the screw or the frame.")
            return
        lines = ["CHECK — not saved yet", ""]
        if score < 0:
            lines.append("Saved fonts: none yet")
        else:
            lines.append("Saved fonts: %s  (%.2f)" % (digit or "?", score))
            if second:
                lines.append("Second:     %s  (%.2f)" % (second, second_s))
        if ocr:
            od, oc = self.ocr_one(norm)
            if od:
                lines.append("OCR sees:   %s  (%d%%)" % (od, int(oc * 100)))
                if digit and od != digit and score >= 0.45:
                    lines.append("Font and OCR disagree. Trust your eyes.")
            else:
                lines.append("OCR sees:   nothing")
        else:
            lines.append("OCR: release the mouse to check")
        lines.append("")
        lines.append("Press 0-9 for the digit YOU see.")
        self.check_label.config(text="\n".join(lines))

    def current_box_crop(self):
        if self.selected and self.selected[0] == "prop":
            return self.crop_housing_box(self.proposals[self.selected[1]])
        if self.selected and self.selected[0] == "manual" and self.manual and self.housing is not None:
            return self.crop_housing_box(self.manual)
        return self.current_crop

    def save_digit(self, digit):
        if self.playing:
            self.check_label.config(text="Pause the video before saving.")
            return
        if not self.analysis or self.analysis.get("scene") != "closeup":
            self.check_label.config(text="Refused. This frame is not a one-roller close-up.")
            return
        crop = self.current_box_crop()
        if crop is None or getattr(crop, "size", 0) == 0:
            self.check_label.config(text="Mark a digit first.")
            return
        _d, score, _s, _ss, norm = self.store.match(crop)
        if norm is None:
            self.check_label.config(text="Refused. This mark has no clean digit.")
            return
        path = self.store.save(digit, crop, norm, {"time": fmt_hms(self.t_now()),
                                                   "video": Path(self.video_path).name if self.video_path else ""})
        again_d, again_s, _a, _b, _n = self.store.match(norm)
        self.log("Saved %s as %s. Recheck sees %s (%.2f)." % (path.name, digit, again_d or "?", again_s))
        self.check_label.config(text="SAVED digit %s\nRecheck against saved fonts: %s (%.2f)\nMark the next digit." % (
            digit, again_d or "?", again_s))
        self.refresh_counts()
        if self.selected and self.selected[0] == "prop" and self.selected[1] < 3:
            nxt = self.selected[1] + 1
            self.selected = ("prop", nxt)
            self.redraw_housing()
            self.inspect(self.crop_housing_box(self.proposals[nxt]), ocr=True)

    def undo(self):
        digit = self.store.undo()
        if digit is None:
            self.log("Nothing to undo.")
            return
        self.log("Removed last saved digit %s." % digit)
        self.refresh_counts()

    def on_key(self, event):
        if isinstance(self.root.focus_get(), Entry):
            return
        if event.char in "0123456789":
            self.save_digit(event.char)

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
        if self.t_now() - self.last_live >= 0.10:
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
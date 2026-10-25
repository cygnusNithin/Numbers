"""
lottery_extractor.py
Manual-control video player with on-demand extraction of
prize category + 18 four-digit numbers (one ROI box per number).

Number reading pipeline (per box):
  average frames -> upscale -> find 4 digit windows -> remove window frames
  -> digit memory (template matching, learns from saved entries)
  -> EasyOCR recognize() fallback (no text detection step)

No threading: playback uses root.after().
"""
import csv
import json
import re
from pathlib import Path
from tkinter import (Tk, Toplevel, Frame, Label, Button, Canvas, Text, Entry, StringVar,
                     DoubleVar, messagebox, filedialog, END, DISABLED, NORMAL)
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

# ─────────────────────────── SETTINGS ───────────────────────────
PRIZE_ROI_FILE = Path("prize_location.json")
NUMBERS_ROI_FILE = Path("numbers_roi.json")
RESULTS_FILE = Path("extraction_results.json")
CSV_FILE = Path("extraction_results.csv")
TEMPLATE_FILE = Path("digit_templates.npz")   # learned digit memory (training data)

NUMBER_DIGITS = 4          # 4-digit prizes
NUM_BOXES = 18             # number boxes (roller groups) on the board

# Number reading
AVG_FRAMES = 5             # average N frames from the paused position (1 = off)
UPSCALE_BOX_H = 160        # each number box is upscaled to this height
CELL_EXPAND = 0.10         # grow each found digit window by 10% before cleaning
CELL_W, CELL_H = 24, 32    # normalized digit size
TEMPLATE_MIN_SCORE = 0.75  # digit memory is trusted above this similarity
TEMPLATE_SURE_SCORE = 0.88 # below this, the box is marked "check"
OCR_WEAK_CONF = 0.60       # EasyOCR confidence below this -> "check"
MAX_TEMPLATES_PER_DIGIT = 40

# Used when the digit windows cannot be found in any box
# (relative x1, y1, x2, y2 inside the number box)
DEFAULT_CELLS = [(0.12 + i * 0.19, 0.20, 0.12 + (i + 1) * 0.19, 0.80)
                 for i in range(NUMBER_DIGITS)]

# Optional: fill in once you know the amounts, e.g. "6th Prize": 5000
PRIZE_AMOUNTS = {
}

SPEEDS = [1, 2, 4, 8, 16, 32]
CANVAS_W, CANVAS_H = 960, 540

# Digit-check preview tiles
TILE_W, TILE_H, TILE_STRIP_H, TILE_BAR_H = 160, 64, 30, 18


# ─────────────────────────── HELPERS ────────────────────────────
def fmt_time(sec):
    sec = max(0, sec)
    return f"{int(sec // 3600):02d}:{int(sec % 3600 // 60):02d}:{int(sec % 60):02d}"


def ordinal_prize(n):
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n, "th")
    return f"{n}{suffix} Prize"


def parse_prize(text):
    """'6TH PRIZE', '6 PRIZE', "16' PRIZEL" -> '6th Prize'"""
    t = re.sub(r"[^A-Z0-9 ]", " ", text.upper())
    m = re.search(r"(\d{1,2})\s*(?:ST|ND|RD|TH)?\s*P\s*R\s*[I1L]\s*[Z2]", t)
    if not m:
        m = re.search(r"\b(\d{1,2})\s*(?:ST|ND|RD|TH)\b", t)
    if not m:
        return None
    n = int(m.group(1))
    if n > 10:                 # common artifact: "16" for "6th"
        n = n % 10
    if not 1 <= n <= 10:
        return None
    return ordinal_prize(n)


def parse_amount(text, prize):
    if prize in PRIZE_AMOUNTS:
        return str(PRIZE_AMOUNTS[prize])
    t = text.upper().replace(",", "")
    nums = [int(x) for x in re.findall(r"\d{2,7}", t)]
    cands = [n for n in nums if n >= 50]
    return str(max(cands)) if cands else ""


def make_variants(crop):
    """Preprocessed versions of a crop for prize OCR (kept in memory only)."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    f = min(4.0, max(1.0, 96 / max(1, gray.shape[0])))   # upscale small text
    up = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(up)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return [clahe, otsu, 255 - otsu]


def box_overlap(a, b):
    """Fraction of the smaller box covered by the intersection."""
    x1, y1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x2 = min(a["x"] + a["width"], b["x"] + b["width"])
    y2 = min(a["y"] + a["height"], b["y"] + b["height"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    smaller = min(a["width"] * a["height"], b["width"] * b["height"])
    return inter / smaller if smaller else 0.0


# ─────────────────────── DIGIT PIPELINE ─────────────────────────
def to_gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def upscale_to_height(gray, target_h):
    f = target_h / max(1, gray.shape[0])
    return cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)


def find_digit_cells(gray):
    """
    Find the 4 dark-bordered digit windows inside one number box.
    Returns 4 relative boxes (x1, y1, x2, y2) left to right, or None.
    """
    H, W = gray.shape
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, dark = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, _, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)

    cands = []
    for i in range(1, n):
        x, y, w, h, _a = stats[i]
        if h < 0.25 * H:
            continue
        if not (0.04 * W <= w <= 0.35 * W):
            continue
        if not (0.7 <= h / max(1, w) <= 5.0):
            continue
        cands.append((int(x), int(y), int(x + w), int(y + h)))

    def area(b):
        return (b[2] - b[0]) * (b[3] - b[1])

    # Keep only outermost boxes (the window frame contains the digit)
    outer = []
    for i, a in enumerate(cands):
        inside = any(j != i and b[0] <= a[0] and b[1] <= a[1] and b[2] >= a[2]
                     and b[3] >= a[3] and area(b) > area(a)
                     for j, b in enumerate(cands))
        if not inside:
            outer.append(a)
    if len(outer) < NUMBER_DIGITS:
        return None

    hs = np.array([b[3] - b[1] for b in outer], float)
    ycs = np.array([(b[1] + b[3]) / 2 for b in outer], float)
    mh, myc = np.median(hs), np.median(ycs)
    sel = [b for b, h, yc in zip(outer, hs, ycs)
           if 0.7 * mh <= h <= 1.4 * mh and abs(yc - myc) < 0.2 * H]
    if len(sel) < NUMBER_DIGITS:
        return None
    if len(sel) > NUMBER_DIGITS:
        sel = sorted(sel, key=area, reverse=True)[:NUMBER_DIGITS]
    sel.sort(key=lambda b: b[0])

    # Sanity check: windows are evenly spaced on the roller
    steps = [sel[i + 1][0] - sel[i][0] for i in range(len(sel) - 1)]
    if min(steps) <= 0 or max(steps) > 1.8 * min(steps):
        return None
    return [(b[0] / W, b[1] / H, b[2] / W, b[3] / H) for b in sel]


def normalize_digit(d):
    """Fit a binary digit (white on black) into CELL_H x CELL_W, keeping aspect."""
    h, w = d.shape
    s = (CELL_H - 4) / max(1, h)
    nw = max(1, min(CELL_W - 4, int(round(w * s))))
    r = cv2.resize(d, (nw, CELL_H - 4), interpolation=cv2.INTER_AREA)
    out = np.zeros((CELL_H, CELL_W), np.uint8)
    x0 = (CELL_W - nw) // 2
    out[2:CELL_H - 2, x0:x0 + nw] = r
    return out


def clean_cell(cell):
    """
    Remove the black window frame and return only the digit,
    normalized (white digit on black, CELL_H x CELL_W). None if empty.
    """
    if cell is None or cell.size == 0:
        return None
    h, w = cell.shape[:2]
    if h < 8 or w < 5:
        return None
    blur = cv2.GaussianBlur(cell, (3, 3), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Remove long straight lines (the window frame)
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(w * 0.75)), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(3, int(h * 0.85))))
    lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, hk) | cv2.morphologyEx(bw, cv2.MORPH_OPEN, vk)
    bw = cv2.subtract(bw, cv2.dilate(lines, np.ones((3, 3), np.uint8)))

    n, labels, stats, cents = cv2.connectedComponentsWithStats(bw, connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, cw, ch, a = stats[i]
        if a < 0.004 * h * w or ch < 0.25 * h:
            continue
        if (x == 0 or x + cw >= w) and cw < 0.12 * w:      # frame remnant at the side
            continue
        if not (0.15 * w <= cents[i][0] <= 0.85 * w):       # digit sits in the middle
            continue
        comps.append(i)

    # Drop rings that contain another component (leftover frames)
    def contains(i, j):
        xi, yi, wi, hi, _ = stats[i]
        xj, yj, wj, hj, _ = stats[j]
        return xi <= xj and yi <= yj and xi + wi >= xj + wj and yi + hi >= yj + hj
    comps = [i for i in comps if not any(j != i and contains(i, j) for j in comps)]
    if not comps:
        return None

    largest = max(stats[i][4] for i in comps)
    keep = [i for i in comps if stats[i][4] >= 0.2 * largest]
    mask = np.isin(labels, keep).astype(np.uint8) * 255
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None
    return normalize_digit(mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1])


def ocr_strip_image(norms):
    """Clean black-on-white 4-digit strip for EasyOCR recognize()."""
    parts = []
    for n in norms:
        t = n if n is not None else np.zeros((CELL_H, CELL_W), np.uint8)
        parts.append(cv2.resize(255 - t, (CELL_W * 2, CELL_H * 2), interpolation=cv2.INTER_CUBIC))
        parts.append(np.full((CELL_H * 2, 14), 255, np.uint8))
    strip = np.hstack(parts[:-1])
    return cv2.copyMakeBorder(strip, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)


def ocr_cell_image(n):
    t = cv2.resize(255 - n, (CELL_W * 2, CELL_H * 2), interpolation=cv2.INTER_CUBIC)
    return cv2.copyMakeBorder(t, 16, 16, 24, 24, cv2.BORDER_CONSTANT, value=255)


def make_tile(index, gray_up, rects, norms, text, weak):
    """Preview tile: box with found cells, cleaned digits, and the result."""
    if gray_up is None:
        vis = np.full((TILE_H, TILE_W, 3), 80, np.uint8)
    else:
        vis = cv2.cvtColor(gray_up, cv2.COLOR_GRAY2BGR)
        for (x1, y1, x2, y2) in rects:
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 200, 0), 2)
        vis = cv2.resize(vis, (TILE_W, TILE_H), interpolation=cv2.INTER_AREA)

    strip = np.full((TILE_STRIP_H, TILE_W), 255, np.uint8)
    if norms:
        parts = []
        for n in norms:
            parts.append(255 - n if n is not None else np.full((CELL_H, CELL_W), 200, np.uint8))
            parts.append(np.full((CELL_H, 6), 255, np.uint8))
        s = np.hstack(parts[:-1])
        f = TILE_STRIP_H / s.shape[0]
        s = cv2.resize(s, (max(1, int(s.shape[1] * f)), TILE_STRIP_H), interpolation=cv2.INTER_AREA)
        w = min(TILE_W, s.shape[1])
        x0 = (TILE_W - w) // 2
        strip[:, x0:x0 + w] = s[:, :w]
    strip = cv2.cvtColor(strip, cv2.COLOR_GRAY2BGR)

    bar = np.full((TILE_BAR_H, TILE_W, 3), 255, np.uint8)
    color = (0, 0, 220) if weak else (0, 130, 0)
    cv2.putText(bar, f"{index}: {text}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, color, 1, cv2.LINE_AA)
    tile = np.vstack([vis, strip, bar])
    return cv2.copyMakeBorder(tile, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=(60, 60, 60))


def make_mosaic(tiles, cols=3):
    """Arrange tiles like the board: boxes 1-6 | 7-12 | 13-18."""
    per_col = int(np.ceil(len(tiles) / cols))
    blank = np.full_like(tiles[0], 240)
    columns = []
    for c in range(cols):
        part = list(tiles[c * per_col:(c + 1) * per_col])
        part += [blank] * (per_col - len(part))
        columns.append(np.vstack(part))
    return np.hstack(columns)


class DigitMemory:
    """Template-matching digit classifier that learns from confirmed entries."""

    def __init__(self, path):
        self.path = path
        self.X = np.zeros((0, CELL_H * CELL_W), np.float32)
        self.y = np.zeros(0, np.int64)
        self.load()

    @staticmethod
    def vec(img):
        v = img.astype(np.float32).ravel()
        v -= v.mean()
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def load(self):
        try:
            d = np.load(self.path)
            X, y = d["X"].astype(np.float32), d["y"].astype(np.int64)
            if X.ndim == 2 and X.shape[1] == CELL_H * CELL_W and len(X) == len(y):
                self.X, self.y = X, y
        except Exception:
            pass

    def save(self):
        np.savez_compressed(self.path, X=self.X, y=self.y)

    def clear(self):
        self.X = np.zeros((0, CELL_H * CELL_W), np.float32)
        self.y = np.zeros(0, np.int64)
        if self.path.exists():
            self.path.unlink()

    def counts(self):
        return {int(l): int((self.y == l).sum()) for l in np.unique(self.y)}

    def classify(self, img):
        if img is None or len(self.y) == 0:
            return None, 0.0
        s = self.X @ self.vec(img)
        best = {int(l): float(s[self.y == l].max()) for l in np.unique(self.y)}
        lab = max(best, key=best.get)
        return str(lab), best[lab]

    def add(self, img, label):
        v = self.vec(img)
        same = self.y == label
        if same.any() and float((self.X[same] @ v).max()) > 0.97:
            return False                     # near-duplicate, skip
        self.X = np.vstack([self.X, v[None, :]])
        self.y = np.append(self.y, label)
        idx = np.where(self.y == label)[0]
        if len(idx) > MAX_TEMPLATES_PER_DIGIT:   # drop the oldest sample
            keep = np.ones(len(self.y), bool)
            keep[idx[0]] = False
            self.X, self.y = self.X[keep], self.y[keep]
        return True


# ─────────────────────────── APP ────────────────────────────────
class LotteryExtractor:
    def __init__(self, root):
        self.root = root
        root.title("Lottery Extractor - Manual Control")
        root.geometry("1420x900")
        root.configure(bg="#f0f0f0")

        # Video state
        self.cap = None
        self.video_path = None
        self.total_frames = 0
        self.fps = 25.0
        self.frame = None
        self.frame_idx = 0
        self.playing = False
        self.speed_i = 0
        self.after_id = None
        self.seek_after_id = None
        self.slider_guard = False

        # Display mapping
        self.scale = 1.0
        self.offset = (0, 0)
        self.photo = None

        # ROI drawing
        self.draw_mode = None          # "prize" | "numbers" | None
        self.drag_start = None
        self.temp_rect = None

        self.prize_roi = self.load_roi(PRIZE_ROI_FILE)
        self.number_boxes, self.pending_boxes = self.load_number_boxes(NUMBERS_ROI_FILE)

        # OCR / results
        self.reader = None
        self.memory = DigitMemory(TEMPLATE_FILE)
        self.entries = []
        self.extract_frame = None
        self.last_cells = None
        self.last_mosaic = None
        self.thumb_refs = {}
        self.zoom_photo = None

        self.build_ui()
        self.refresh_roi_labels()
        self.refresh_memory_label()
        root.bind("<Key>", self.on_key)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ───────────── ROI files ─────────────
    @staticmethod
    def load_roi(path):
        try:
            data = json.loads(path.read_text())
            roi = data.get("roi", data)
            return {k: int(roi[k]) for k in ("x", "y", "width", "height")}
        except Exception:
            return None

    @staticmethod
    def load_number_boxes(path):
        """Returns (complete_boxes, pending_boxes). Old single-ROI files are ignored."""
        def clean(lst):
            return [{k: int(b[k]) for k in ("x", "y", "width", "height")} for b in lst]
        try:
            data = json.loads(path.read_text())
            boxes = clean(data.get("boxes", []))
            pending = clean(data.get("pending", []))
            if len(boxes) != NUM_BOXES:
                boxes = []
            return boxes, pending[:NUM_BOXES - 1]
        except Exception:
            return [], []

    def save_prize_roi(self):
        data = {}
        if PRIZE_ROI_FILE.exists():
            try:
                data = json.loads(PRIZE_ROI_FILE.read_text())
            except Exception:
                data = {}
        data["roi"] = self.prize_roi          # keep other metadata intact
        PRIZE_ROI_FILE.write_text(json.dumps(data, indent=2))

    def save_number_boxes(self):
        NUMBERS_ROI_FILE.write_text(json.dumps(
            {"boxes": self.number_boxes, "pending": self.pending_boxes}, indent=2))

    # ───────────── UI ─────────────
    def build_ui(self):
        left = Frame(self.root, bg="#f0f0f0")
        left.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        right = Frame(self.root, bg="#ffffff", width=410, relief="solid", bd=1)
        right.pack(side="right", fill="y", padx=(0, 8), pady=8)
        right.pack_propagate(False)

        # ---- Top bar
        top = Frame(left, bg="#f0f0f0")
        top.pack(fill="x")
        Button(top, text="📁 Open Video", command=self.open_video,
               bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), padx=10).pack(side="left")
        self.video_label = Label(top, text="No video loaded", bg="#f0f0f0",
                                 fg="#555", font=("Arial", 9))
        self.video_label.pack(side="left", padx=10)

        # ---- Video canvas
        self.canvas = Canvas(left, width=CANVAS_W, height=CANVAS_H, bg="black",
                             highlightthickness=0, cursor="crosshair")
        self.canvas.pack(pady=6)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        # ---- Seek slider
        self.pos_var = DoubleVar()
        self.slider = ttk.Scale(left, from_=0, to=1, orient="horizontal",
                                variable=self.pos_var, command=self.on_slider)
        self.slider.pack(fill="x", pady=(4, 0))
        self.time_label = Label(left, text="00:00:00 / 00:00:00   frame 0 / 0",
                                font=("Courier", 11), bg="#f0f0f0")
        self.time_label.pack(pady=2)

        # ---- Transport controls
        c1 = Frame(left, bg="#f0f0f0")
        c1.pack(pady=4)
        for txt, sec in [("⏪ 60s", -60), ("⏪ 10s", -10), ("◀ 5s", -5)]:
            Button(c1, text=txt, width=7,
                   command=lambda s=sec: self.skip_seconds(s)).pack(side="left", padx=2)
        Button(c1, text="◀| frame", width=8,
               command=lambda: self.step_frames(-1)).pack(side="left", padx=2)
        self.play_btn = Button(c1, text="▶ Play", width=10, command=self.toggle_play,
                               bg="#2196F3", fg="white", font=("Arial", 10, "bold"))
        self.play_btn.pack(side="left", padx=6)
        Button(c1, text="frame |▶", width=8,
               command=lambda: self.step_frames(1)).pack(side="left", padx=2)
        for txt, sec in [("5s ▶", 5), ("10s ⏩", 10), ("60s ⏩", 60)]:
            Button(c1, text=txt, width=7,
                   command=lambda s=sec: self.skip_seconds(s)).pack(side="left", padx=2)

        c2 = Frame(left, bg="#f0f0f0")
        c2.pack(pady=4)
        Label(c2, text="Speed:", bg="#f0f0f0", font=("Arial", 10, "bold")).pack(side="left")
        Button(c2, text="− Slower", command=lambda: self.change_speed(-1)).pack(side="left", padx=4)
        self.speed_label = Label(c2, text="1x", width=4, bg="#f0f0f0",
                                 font=("Courier", 12, "bold"))
        self.speed_label.pack(side="left")
        Button(c2, text="+ Faster", command=lambda: self.change_speed(1)).pack(side="left", padx=4)

        Label(left, text="Keys: Space=play/pause  ←/→=5s  ↑/↓=60s  ,/.=frame  +/-=speed  "
                         "E=extract  Backspace=undo last box  Esc=pause marking\n"
                         "(click the video to return keyboard control)",
              bg="#f0f0f0", fg="#666", font=("Courier", 9)).pack(pady=2)

        # ---- Right panel: ROIs
        Label(right, text="Regions (ROI)", font=("Arial", 12, "bold"),
              bg="#fff").pack(anchor="w", padx=10, pady=(8, 2))

        self.prize_roi_label = Label(right, bg="#fff", font=("Courier", 9), fg="#2E7D32")
        self.prize_roi_label.pack(anchor="w", padx=10)
        Button(right, text="🟩 Draw Prize Category ROI", command=lambda: self.start_draw("prize"),
               bg="#43A047", fg="white", font=("Arial", 9, "bold")).pack(fill="x", padx=10, pady=2)

        self.numbers_roi_label = Label(right, bg="#fff", font=("Courier", 9), fg="#1565C0")
        self.numbers_roi_label.pack(anchor="w", padx=10, pady=(4, 0))
        self.mark_btn = Button(right, text="🟦 Mark Number Boxes",
                               command=lambda: self.start_draw("numbers"),
                               bg="#1E88E5", fg="white", font=("Arial", 9, "bold"))
        self.mark_btn.pack(fill="x", padx=10, pady=2)

        box_row = Frame(right, bg="#fff")
        box_row.pack(fill="x", padx=10)
        Button(box_row, text="↶ Undo Last Box", command=self.undo_last_box,
               bg="#90A4AE", fg="white", font=("Arial", 9, "bold")).pack(
            side="left", fill="x", expand=True, padx=(0, 2))
        Button(box_row, text="✕ Restart Boxes", command=self.restart_boxes,
               bg="#B0BEC5", fg="white", font=("Arial", 9, "bold")).pack(
            side="left", fill="x", expand=True, padx=(2, 0))

        self.mode_label = Label(right, text="", bg="#fff", fg="#E65100",
                                font=("Arial", 9, "bold"), wraplength=380, justify="left")
        self.mode_label.pack(anchor="w", padx=10)

        ttk.Separator(right).pack(fill="x", padx=10, pady=4)

        # ---- Extract
        self.extract_btn = Button(right, text="🔍 EXTRACT  (E)", command=self.extract,
                                  bg="#FF5722", fg="white", font=("Arial", 13, "bold"), pady=3)
        self.extract_btn.pack(fill="x", padx=10)

        mem_row = Frame(right, bg="#fff")
        mem_row.pack(fill="x", padx=10, pady=(2, 0))
        self.mem_label = Label(mem_row, text="", bg="#fff", fg="#6A1B9A",
                               font=("Courier", 8), anchor="w")
        self.mem_label.pack(side="left", fill="x", expand=True)
        Button(mem_row, text="Reset memory", command=self.reset_memory,
               font=("Arial", 7)).pack(side="right")

        self.prize_thumb = Label(right, bg="#eeeeee")
        self.prize_thumb.pack(padx=10, pady=(4, 2))
        self.numbers_thumb = Label(right, bg="#eeeeee", cursor="hand2")
        self.numbers_thumb.pack(padx=10, pady=2)
        self.numbers_thumb.bind("<Button-1>", self.open_zoom)

        # ---- Editable results
        row = Frame(right, bg="#fff")
        row.pack(fill="x", padx=10, pady=(2, 0))
        Label(row, text="Prize:", bg="#fff", font=("Arial", 9, "bold"), width=7,
              anchor="w").pack(side="left")
        self.prize_var = StringVar()
        Entry(row, textvariable=self.prize_var, font=("Courier", 11)).pack(side="left", fill="x", expand=True)

        row = Frame(right, bg="#fff")
        row.pack(fill="x", padx=10, pady=2)
        Label(row, text="Amount:", bg="#fff", font=("Arial", 9, "bold"), width=7,
              anchor="w").pack(side="left")
        self.amount_var = StringVar()
        Entry(row, textvariable=self.amount_var, font=("Courier", 11)).pack(side="left", fill="x", expand=True)

        Label(right, text=f"Numbers (line = box 1..{NUM_BOXES}, fix if wrong):", bg="#fff",
              font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(2, 0))
        self.numbers_text = Text(right, height=6, font=("Courier", 11))
        self.numbers_text.pack(fill="x", padx=10)

        self.ocr_info = Label(right, text="", bg="#fff", fg="#666", font=("Courier", 8),
                              wraplength=380, justify="left")
        self.ocr_info.pack(anchor="w", padx=10, pady=2)

        btns = Frame(right, bg="#fff")
        btns.pack(fill="x", padx=10, pady=2)
        Button(btns, text="💾 Save Entry", command=self.save_entry, bg="#2E7D32", fg="white",
               font=("Arial", 9, "bold")).pack(side="left", fill="x", expand=True, padx=(0, 2))
        Button(btns, text="↶ Undo Last", command=self.undo_last, bg="#757575", fg="white",
               font=("Arial", 9, "bold")).pack(side="left", fill="x", expand=True, padx=2)
        Button(btns, text="📤 Export", command=self.export, bg="#FF9800", fg="white",
               font=("Arial", 9, "bold")).pack(side="left", fill="x", expand=True, padx=(2, 0))

        Label(right, text="Saved entries:", bg="#fff",
              font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(2, 0))
        self.log = Text(right, height=4, font=("Courier", 8), bg="#fafafa", state=DISABLED)
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 8))

    def refresh_roi_labels(self):
        r = self.prize_roi
        self.prize_roi_label.config(
            text=f"Prize  : x={r['x']} y={r['y']} {r['width']}x{r['height']}" if r
            else "Prize  : not set")

        if self.number_boxes:
            txt = f"Numbers: {NUM_BOXES} boxes set ✓"
        else:
            txt = "Numbers: not set"
        if self.pending_boxes:
            txt += f"  |  marking {len(self.pending_boxes)}/{NUM_BOXES}"
        self.numbers_roi_label.config(text=txt)

        if self.pending_boxes:
            self.mark_btn.config(
                text=f"🟦 Continue Marking ({len(self.pending_boxes)}/{NUM_BOXES})")
        elif self.number_boxes:
            self.mark_btn.config(text=f"🟦 Re-mark {NUM_BOXES} Number Boxes")
        else:
            self.mark_btn.config(text=f"🟦 Mark {NUM_BOXES} Number Boxes (permanent)")

    def refresh_memory_label(self):
        c = self.memory.counts()
        missing = "".join(str(d) for d in range(10) if not c.get(d, 0))
        self.mem_label.config(
            text=f"🧠 Digit memory: {len(self.memory.y)} samples | missing: {missing or 'none'}")

    def reset_memory(self):
        if messagebox.askyesno("Reset memory", "Delete all learned digit samples?"):
            self.memory.clear()
            self.refresh_memory_label()

    # ───────────── Video loading ─────────────
    def open_video(self):
        path = filedialog.askopenfilename(
            title="Select Lottery Video",
            filetypes=[("Video Files", "*.mp4 *.avi *.mov *.mkv"), ("All Files", "*.*")])
        if not path:
            return
        self.pause()
        if self.cap:
            self.cap.release()
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            messagebox.showerror("Error", "Cannot open this video.")
            return

        self.cap = cap
        self.video_path = path
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.total_frames = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.slider.config(to=max(1, self.total_frames - 1))
        self.video_label.config(text=Path(path).name)

        self.entries = []
        self.maybe_resume()
        self.refresh_log()
        self.seek(0)
        self.canvas.focus_set()

    def maybe_resume(self):
        if not RESULTS_FILE.exists():
            return
        try:
            data = json.loads(RESULTS_FILE.read_text())
        except Exception:
            return
        if data.get("video") == Path(self.video_path).name and data.get("entries"):
            if messagebox.askyesno("Resume?",
                                   f"Found {len(data['entries'])} saved entries for this video.\n"
                                   "Continue from them?"):
                self.entries = data["entries"]

    # ───────────── Playback ─────────────
    def read_frame(self):
        ok, frame = self.cap.read()
        if not ok:
            return False
        self.frame = frame
        self.frame_idx = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        return True

    def seek(self, idx):
        if not self.cap:
            return
        idx = max(0, min(int(idx), self.total_frames - 1))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        if self.read_frame():
            self.show_frame()

    def play_tick(self):
        if not self.playing or not self.cap:
            return
        speed = SPEEDS[self.speed_i]
        for _ in range(speed - 1):          # skip frames (no RGB conversion)
            if not self.cap.grab():
                break
        if not self.read_frame():
            self.pause()
            return
        self.show_frame()
        delay = max(1, int(1000 / self.fps))
        self.after_id = self.root.after(delay, self.play_tick)

    def play(self):
        if not self.cap or self.playing:
            return
        self.cancel_draw()
        self.playing = True
        self.play_btn.config(text="⏸ Pause", bg="#F57C00")
        self.play_tick()

    def pause(self):
        self.playing = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.play_btn.config(text="▶ Play", bg="#2196F3")

    def toggle_play(self):
        self.pause() if self.playing else self.play()

    def skip_seconds(self, sec):
        if self.cap:
            self.seek(self.frame_idx + sec * self.fps)

    def step_frames(self, n):
        if not self.cap:
            return
        self.pause()
        if n == 1:
            if self.read_frame():
                self.show_frame()
        else:
            self.seek(self.frame_idx + n)

    def change_speed(self, d):
        self.speed_i = max(0, min(len(SPEEDS) - 1, self.speed_i + d))
        self.speed_label.config(text=f"{SPEEDS[self.speed_i]}x")

    def on_slider(self, value):
        if self.slider_guard or not self.cap:
            return
        if self.seek_after_id:
            self.root.after_cancel(self.seek_after_id)
        self.seek_after_id = self.root.after(80, lambda: self.seek(float(value)))

    def averaged_frame(self):
        """Average the paused frame with the next few frames to remove noise."""
        if self.frame is None or self.cap is None or AVG_FRAMES <= 1:
            return self.frame
        start = self.frame_idx
        base = self.frame.astype(np.float32)
        acc, count = base.copy(), 1
        try:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, start + 1)
            for _ in range(AVG_FRAMES - 1):
                ok, f = self.cap.read()
                if not ok or f.shape != self.frame.shape:
                    break
                f = f.astype(np.float32)
                if np.mean(np.abs(f - base)) > 12:      # scene changed, stop averaging
                    break
                acc += f
                count += 1
        finally:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, start + 1)   # restore position
        return np.clip(acc / count, 0, 255).astype(np.uint8)

    # ───────────── Display ─────────────
    def show_frame(self):
        if self.frame is None:
            return
        h, w = self.frame.shape[:2]
        scale = min(CANVAS_W / w, CANVAS_H / h)
        dw, dh = int(w * scale), int(h * scale)
        ox, oy = (CANVAS_W - dw) // 2, (CANVAS_H - dh) // 2
        self.scale, self.offset = scale, (ox, oy)

        small = cv2.resize(self.frame, (dw, dh), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))

        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, image=self.photo, anchor="nw")
        self.draw_roi(self.prize_roi, "#00E676", "PRIZE")

        if self.pending_boxes or self.draw_mode == "numbers":
            for i, b in enumerate(self.pending_boxes, 1):      # boxes being marked
                self.draw_roi(b, "#FFAB00", str(i), small_label=True)
        else:
            for i, b in enumerate(self.number_boxes, 1):       # saved boxes
                self.draw_roi(b, "#2979FF", str(i), small_label=True)
        self.update_time_ui()

    def draw_roi(self, roi, color, name, small_label=False):
        if not roi:
            return
        ox, oy = self.offset
        s = self.scale
        x1, y1 = ox + roi["x"] * s, oy + roi["y"] * s
        x2, y2 = x1 + roi["width"] * s, y1 + roi["height"] * s
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2)
        if small_label:
            self.canvas.create_text(x1 + 3, y1 + 2, text=name, fill=color,
                                    anchor="nw", font=("Arial", 8, "bold"))
        else:
            self.canvas.create_text(x1 + 3, y1 - 8, text=name, fill=color,
                                    anchor="w", font=("Arial", 9, "bold"))

    def update_time_ui(self):
        self.slider_guard = True
        self.pos_var.set(self.frame_idx)
        self.slider_guard = False
        cur = self.frame_idx / self.fps
        total = self.total_frames / self.fps
        self.time_label.config(
            text=f"{fmt_time(cur)} / {fmt_time(total)}   frame {self.frame_idx} / {self.total_frames}")

    def show_thumb(self, img, label, key, max_w=390, max_h=90):
        if img is None or img.size == 0:
            label.config(image="", text="(empty)")
            return
        rgb = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        rgb.thumbnail((max_w, max_h))
        self.thumb_refs[key] = ImageTk.PhotoImage(rgb)
        label.config(image=self.thumb_refs[key], text="")

    def open_zoom(self, _event=None):
        """Full-size digit check window (Tkinter, not cv2.imshow)."""
        if self.last_mosaic is None:
            return
        top = Toplevel(self.root)
        top.title("Digit check (green = cells found, red text = please check)")
        img = Image.fromarray(cv2.cvtColor(self.last_mosaic, cv2.COLOR_BGR2RGB))
        self.zoom_photo = ImageTk.PhotoImage(img)
        Label(top, image=self.zoom_photo).pack(padx=4, pady=4)

    # ───────────── ROI drawing ─────────────
    def numbers_prompt(self):
        return (f"✏ Drag box {len(self.pending_boxes) + 1}/{NUM_BOXES} around one "
                f"{NUMBER_DIGITS}-digit number  (Backspace = undo last box, Esc = pause)")

    def start_draw(self, mode):
        if self.frame is None:
            messagebox.showwarning("No video", "Open a video first.")
            return
        self.pause()
        if mode == "numbers" and not self.pending_boxes and self.number_boxes:
            if not messagebox.askyesno(
                    "Re-mark?",
                    f"{NUM_BOXES} number boxes are already set.\nMark a new set?\n\n"
                    f"(The old boxes stay in use until all {NUM_BOXES} new boxes are done.)"):
                return
        self.draw_mode = mode
        if mode == "numbers":
            self.mode_label.config(text=self.numbers_prompt())
        else:
            self.mode_label.config(
                text="✏ Drag a rectangle on the video for the PRIZE ROI  (Esc = cancel)")
        self.show_frame()
        self.canvas.focus_set()

    def cancel_draw(self):
        """Stops drawing mode. Already-marked number boxes are KEPT."""
        was_numbers = self.draw_mode == "numbers"
        self.draw_mode = None
        if self.temp_rect:
            self.canvas.delete(self.temp_rect)
        self.temp_rect = None
        self.drag_start = None
        if was_numbers and self.pending_boxes:
            self.mode_label.config(
                text=f"⏸ Marking paused at {len(self.pending_boxes)}/{NUM_BOXES}. "
                     f"Click 'Continue Marking' to go on.")
        else:
            self.mode_label.config(text="")

    def undo_last_box(self):
        """Remove ONLY the most recent number box."""
        if self.pending_boxes:
            self.pending_boxes.pop()
        elif self.number_boxes:
            if not messagebox.askyesno(
                    "Undo last box",
                    f"All {NUM_BOXES} boxes are complete.\n"
                    f"Remove box {NUM_BOXES} and re-mark it?"):
                return
            self.pending_boxes = self.number_boxes[:-1]
            self.number_boxes = []
        else:
            self.mode_label.config(text="No boxes to undo.")
            return
        self.save_number_boxes()
        self.refresh_roi_labels()
        if self.frame is not None:
            self.draw_mode = "numbers"
            self.mode_label.config(text=self.numbers_prompt())
            self.show_frame()

    def restart_boxes(self):
        if not self.pending_boxes and not self.number_boxes:
            self.start_draw("numbers")
            return
        if not messagebox.askyesno("Restart", "Discard boxes being marked and start again from box 1?\n"
                                              "(Saved complete set stays until the new set is done.)"):
            return
        self.pending_boxes = []
        self.save_number_boxes()
        self.refresh_roi_labels()
        if self.frame is not None:
            self.draw_mode = "numbers"
            self.mode_label.config(text=self.numbers_prompt())
            self.show_frame()

    def check_box(self, roi):
        """Return an error message if the new number box is invalid, else None."""
        if roi["width"] < 8 or roi["height"] < 8:
            return "Box too small"
        for i, b in enumerate(self.pending_boxes, 1):
            if box_overlap(roi, b) > 0.5:
                return f"Box overlaps box {i}"
        return None

    def on_press(self, e):
        self.canvas.focus_set()
        if not self.draw_mode:
            return
        self.drag_start = (e.x, e.y)
        self.temp_rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                      outline="yellow", width=2, dash=(4, 2))

    def on_drag(self, e):
        if self.temp_rect:
            self.canvas.coords(self.temp_rect, *self.drag_start, e.x, e.y)

    def on_release(self, e):
        if not self.temp_rect:
            return
        x0, y0 = self.drag_start
        self.canvas.delete(self.temp_rect)
        self.temp_rect = None
        self.drag_start = None

        roi = self.canvas_to_video(x0, y0, e.x, e.y)

        # ---- Prize ROI (single rectangle)
        if self.draw_mode == "prize":
            if roi["width"] < 8 or roi["height"] < 8:
                self.mode_label.config(text="Rectangle too small, drag again (Esc = cancel)")
                return
            self.prize_roi = roi
            self.save_prize_roi()
            self.draw_mode = None
            self.mode_label.config(text="✓ Prize ROI saved")
            self.refresh_roi_labels()
            self.show_frame()
            return

        # ---- Number boxes (one at a time; a failed box discards only itself)
        err = self.check_box(roi)
        if err:
            self.mode_label.config(
                text=f"✕ {err}. Only this box was discarded, "
                     f"{len(self.pending_boxes)} boxes kept.\n{self.numbers_prompt()}")
            self.show_frame()
            return

        self.pending_boxes.append(roi)
        if len(self.pending_boxes) == NUM_BOXES:
            self.number_boxes = self.pending_boxes
            self.pending_boxes = []
            self.draw_mode = None
            self.mode_label.config(text=f"✓ All {NUM_BOXES} number boxes saved")
        else:
            self.mode_label.config(text=self.numbers_prompt())
        self.save_number_boxes()          # progress saved after every box
        self.refresh_roi_labels()
        self.show_frame()

    def canvas_to_video(self, x0, y0, x1, y1):
        ox, oy = self.offset
        s = self.scale
        fh, fw = self.frame.shape[:2]

        def cx(v):
            return int(max(0, min(fw, (v - ox) / s)))

        def cy(v):
            return int(max(0, min(fh, (v - oy) / s)))

        xa, xb = sorted((cx(x0), cx(x1)))
        ya, yb = sorted((cy(y0), cy(y1)))
        return {"x": xa, "y": ya, "width": xb - xa, "height": yb - ya}

    def crop(self, roi, frame=None):
        frame = self.frame if frame is None else frame
        if frame is None or not roi:
            return None
        fh, fw = frame.shape[:2]
        x1, y1 = max(0, roi["x"]), max(0, roi["y"])
        x2, y2 = min(fw, x1 + roi["width"]), min(fh, y1 + roi["height"])
        c = frame[y1:y2, x1:x2]
        return c if c.size else None

    # ───────────── OCR ─────────────
    def get_reader(self):
        if self.reader is None:
            self.ocr_info.config(text="Loading EasyOCR (first time only)...")
            self.root.update()
            import easyocr
            self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return self.reader

    def read_prize(self, crop):
        reader = self.get_reader()
        best = None
        for v in make_variants(crop):
            res = reader.readtext(v, detail=1, paragraph=False)
            if not res:
                continue
            text = " ".join(r[1] for r in res)
            conf = float(np.mean([r[2] for r in res])) * 100
            prize = parse_prize(text)
            score = conf + (100 if prize else 0)     # prefer variants that parse
            if best is None or score > best["score"]:
                best = {"score": score, "text": text, "conf": conf, "prize": prize}
        return best

    def ocr_digits(self, img):
        """EasyOCR recognition only (no text detection). Returns (digits, conf 0-1)."""
        try:
            res = self.get_reader().recognize(img, allowlist="0123456789", detail=1)
        except Exception:
            return "", 0.0
        if not res:
            return "", 0.0
        best = max(res, key=lambda r: r[2])
        return re.sub(r"\D", "", best[1]), float(best[2])

    def read_box(self, gray_up, rel_cells):
        """Read one 4-digit number from an upscaled grayscale box."""
        H, W = gray_up.shape
        norms, rects = [], []
        for (rx1, ry1, rx2, ry2) in rel_cells:
            cw, ch = (rx2 - rx1) * W, (ry2 - ry1) * H
            x1 = int(max(0, rx1 * W - CELL_EXPAND * cw))
            x2 = int(min(W, rx2 * W + CELL_EXPAND * cw))
            y1 = int(max(0, ry1 * H - CELL_EXPAND * ch))
            y2 = int(min(H, ry2 * H + CELL_EXPAND * ch))
            rects.append((x1, y1, x2, y2))
            norms.append(clean_cell(gray_up[y1:y2, x1:x2]))

        # 1) Digit memory
        tmpl = [self.memory.classify(n) for n in norms]

        # 2) EasyOCR only where memory is not confident
        ocr = [("", 0.0)] * NUMBER_DIGITS
        need_ocr = any(n is not None and s < TEMPLATE_MIN_SCORE for n, (_l, s) in zip(norms, tmpl))
        if need_ocr:
            txt, conf = self.ocr_digits(ocr_strip_image(norms))
            if len(txt) == NUMBER_DIGITS:
                ocr = [(c, conf) for c in txt]
            else:
                ocr = []
                for n in norms:
                    if n is None:
                        ocr.append(("", 0.0))
                    else:
                        t, c = self.ocr_digits(ocr_cell_image(n))
                        ocr.append((t[:1], c))

        # 3) Combine
        digits, weak, n_t, n_o = [], False, 0, 0
        for n, (tl, ts), (ol, oc) in zip(norms, tmpl, ocr):
            if tl is not None and ts >= TEMPLATE_MIN_SCORE:
                digits.append(tl)
                n_t += 1
                weak |= ts < TEMPLATE_SURE_SCORE
            elif ol:
                digits.append(ol)
                n_o += 1
                weak |= oc < OCR_WEAK_CONF
            elif tl is not None and ts > 0.5:
                digits.append(tl)
                n_t += 1
                weak = True
            else:
                digits.append("?")
                weak = True
        return {"digits": "".join(digits), "norms": norms, "rects": rects,
                "weak": weak, "n_t": n_t, "n_o": n_o}

    def extract(self):
        if self.frame is None:
            messagebox.showwarning("No video", "Open a video first.")
            return
        if len(self.number_boxes) != NUM_BOXES:
            done = len(self.pending_boxes)
            messagebox.showwarning(
                "Number boxes",
                f"Mark all {NUM_BOXES} number boxes first (blue button).\n"
                f"Currently marked: {done}/{NUM_BOXES}")
            return
        if not self.prize_roi:
            messagebox.showwarning("Prize ROI", "Draw the Prize Category ROI first (green button).")
            return

        self.pause()
        self.cancel_draw()
        self.extract_btn.config(state=DISABLED, text="⏳ Extracting...")
        self.root.config(cursor="watch")
        self.root.update()

        try:
            src = self.averaged_frame()

            # ---- Prize category
            pcrop = self.crop(self.prize_roi, src)
            self.show_thumb(pcrop, self.prize_thumb, "prize", max_h=50)
            self.root.update()
            p = self.read_prize(pcrop) if pcrop is not None else None
            prize = p["prize"] if p and p["prize"] else ""
            self.prize_var.set(prize)
            self.amount_var.set(parse_amount(p["text"], prize) if p else "")

            # ---- Number boxes: find digit windows
            grays = []
            for box in self.number_boxes:
                c = self.crop(box, src)
                grays.append(upscale_to_height(to_gray(c), UPSCALE_BOX_H) if c is not None else None)
            layouts = [find_digit_cells(g) if g is not None else None for g in grays]
            found = [l for l in layouts if l]
            # All housings are identical: boxes that failed borrow the median layout
            ref = np.median(np.array(found), axis=0).tolist() if found else DEFAULT_CELLS

            # ---- Read each box
            lines, tiles, cells_cache = [], [], []
            weak_boxes, n_t, n_o = [], 0, 0
            for i, g in enumerate(grays, 1):
                self.ocr_info.config(text=f"Reading number box {i}/{NUM_BOXES}...")
                self.root.update()
                if g is None:
                    lines.append("?" * NUMBER_DIGITS)
                    cells_cache.append([None] * NUMBER_DIGITS)
                    tiles.append(make_tile(i, None, [], [], "-", True))
                    weak_boxes.append(f"#{i}")
                    continue
                r = self.read_box(g, layouts[i - 1] or ref)
                lines.append(r["digits"])
                cells_cache.append(r["norms"])
                tiles.append(make_tile(i, g, r["rects"], r["norms"], r["digits"], r["weak"]))
                n_t += r["n_t"]
                n_o += r["n_o"]
                if r["weak"]:
                    weak_boxes.append(f"#{i}")

            self.numbers_text.delete("1.0", END)
            self.numbers_text.insert("1.0", "\n".join(lines))
            self.last_cells = cells_cache
            self.last_mosaic = make_mosaic(tiles)
            self.show_thumb(self.last_mosaic, self.numbers_thumb, "numbers", max_h=210)

            complete = sum(1 for l in lines if re.fullmatch(rf"\d{{{NUMBER_DIGITS}}}", l))
            info = [f"Prize OCR: '{p['text']}' ({p['conf']:.0f}%)" if p else "Prize OCR: nothing read",
                    f"Numbers: {complete}/{NUM_BOXES} complete | digits: memory {n_t}, OCR {n_o}"]
            if len(found) < NUM_BOXES:
                info.append(f"Digit windows auto-found in {len(found)}/{NUM_BOXES} boxes "
                            f"(others used the shared layout)")
            if weak_boxes:
                info.append(f"⚠ Check boxes: {', '.join(weak_boxes)}")
            if not prize:
                info.append("⚠ Prize not recognised, type it manually")
            info.append("Click the board preview to zoom. Fix lines, then Save. "
                        "Saved numbers teach the digit memory.")
            self.ocr_info.config(text="\n".join(info))
            self.extract_frame = self.frame_idx

        except Exception as ex:
            messagebox.showerror("Extraction error", str(ex))
        finally:
            self.extract_btn.config(state=NORMAL, text="🔍 EXTRACT  (E)")
            self.root.config(cursor="")

    # ───────────── Learning ─────────────
    def learn_digits(self):
        """Teach the digit memory from the confirmed numbers (line i = box i)."""
        if not self.last_cells:
            return 0
        lines = [l.strip() for l in self.numbers_text.get("1.0", END).splitlines() if l.strip()]
        if len(lines) != len(self.last_cells):
            return 0
        added = 0
        for line, norms in zip(lines, self.last_cells):
            if not re.fullmatch(rf"\d{{{NUMBER_DIGITS}}}", line):
                continue
            for ch, n in zip(line, norms):
                if n is not None and self.memory.add(n, int(ch)):
                    added += 1
        if added:
            self.memory.save()
        self.last_cells = None
        self.refresh_memory_label()
        return added

    # ───────────── Saving ─────────────
    def save_entry(self):
        prize = self.prize_var.get().strip()
        raw = re.findall(r"[\d?]+", self.numbers_text.get("1.0", END))
        good = [x for x in raw if re.fullmatch(rf"\d{{{NUMBER_DIGITS}}}", x)]
        bad = [x for x in raw if x not in good]

        if not prize:
            messagebox.showwarning("Missing prize", "Enter the prize category first.")
            return
        if not good:
            messagebox.showwarning("No numbers", f"No valid {NUMBER_DIGITS}-digit numbers to save.")
            return
        if bad and not messagebox.askyesno(
                "Check numbers",
                f"These are not complete {NUMBER_DIGITS}-digit numbers and will be skipped:\n"
                f"{', '.join(bad)}\n\nSave the rest?"):
            return
        if len(good) < NUM_BOXES and not bad and not messagebox.askyesno(
                "Check numbers",
                f"Only {len(good)} of {NUM_BOXES} numbers are complete.\nSave anyway?"):
            return

        learned = self.learn_digits()

        frame = self.extract_frame if self.extract_frame is not None else self.frame_idx
        entry = {
            "prize": prize,
            "amount": self.amount_var.get().strip(),
            "frame": frame,
            "time": fmt_time(frame / self.fps),
            "numbers": list(dict.fromkeys(good)),
        }
        self.entries.append(entry)
        self.write_json()
        self.refresh_log()
        msg = f"✓ Saved {len(entry['numbers'])} numbers for {prize}"
        if learned:
            msg += f" | learned {learned} digit samples"
        self.ocr_info.config(text=msg)
        self.canvas.focus_set()

    def undo_last(self):
        if not self.entries:
            return
        last = self.entries[-1]
        if messagebox.askyesno("Undo", f"Remove last entry?\n{last['prize']} @ {last['time']}"):
            self.entries.pop()
            self.write_json()
            self.refresh_log()

    def refresh_log(self):
        self.log.config(state=NORMAL)
        self.log.delete("1.0", END)
        for e in self.entries:
            nums = ", ".join(e["numbers"][:6]) + (" ..." if len(e["numbers"]) > 6 else "")
            amt = f" ₹{e['amount']}" if e["amount"] else ""
            self.log.insert(END, f"{e['time']} {e['prize']}{amt} [{len(e['numbers'])}]: {nums}\n")
        self.log.see(END)
        self.log.config(state=DISABLED)

    def build_results(self):
        by_prize = {}
        for e in self.entries:
            p = by_prize.setdefault(e["prize"], {"amount": e["amount"], "numbers": []})
            if e["amount"] and not p["amount"]:
                p["amount"] = e["amount"]
            for num in e["numbers"]:
                if num not in p["numbers"]:
                    p["numbers"].append(num)
        return {
            "video": Path(self.video_path).name if self.video_path else "",
            "number_boxes": self.number_boxes,
            "entries": self.entries,
            "by_prize": by_prize,
        }

    def write_json(self):
        RESULTS_FILE.write_text(json.dumps(self.build_results(), indent=2, ensure_ascii=False))

    def export(self):
        if not self.entries:
            messagebox.showwarning("Nothing to export", "Save at least one entry first.")
            return
        self.write_json()
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Prize", "Amount", "Number", "Frame", "Time"])
            for e in self.entries:
                for num in e["numbers"]:
                    w.writerow([e["prize"], e["amount"], num, e["frame"], e["time"]])
        messagebox.showinfo("Exported", f"Saved:\n- {RESULTS_FILE}\n- {CSV_FILE}")

    # ───────────── Keyboard ─────────────
    def on_key(self, e):
        try:
            if isinstance(self.root.focus_get(), (Text, Entry)):
                return            # typing in a field, don't control the player
        except Exception:
            pass
        k = e.keysym
        if k == "space":
            self.toggle_play()
        elif k == "Left":
            self.skip_seconds(-5)
        elif k == "Right":
            self.skip_seconds(5)
        elif k == "Down":
            self.skip_seconds(-60)
        elif k == "Up":
            self.skip_seconds(60)
        elif k == "comma":
            self.step_frames(-1)
        elif k == "period":
            self.step_frames(1)
        elif k in ("plus", "equal", "KP_Add"):
            self.change_speed(1)
        elif k in ("minus", "KP_Subtract"):
            self.change_speed(-1)
        elif k in ("e", "E"):
            self.extract()
        elif k == "BackSpace":
            if self.draw_mode == "numbers" or self.pending_boxes:
                self.undo_last_box()
        elif k == "Escape":
            self.cancel_draw()

    def on_close(self):
        self.pause()
        if self.cap:
            self.cap.release()
        self.root.destroy()


if __name__ == "__main__":
    root = Tk()
    LotteryExtractor(root)
    root.mainloop()
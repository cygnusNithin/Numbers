"""
draw_scanner.py
Automatic Kerala Lottery 4-digit draw reader.

1. Detects when the 18-roller machine appears (yellow tags + optional reference image).
2. Reads the prize banner (prize_location.json ROI).
3. Reads each roller close-up: yellow tag -> roller 1-18, white housing -> 4 digits.
4. Votes across frames, exports JSON + CSV.

No threading (root.after), no cv2.imshow, no debug images.
"""
import csv
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from tkinter import (Tk, Frame, Label, Button, Canvas, Text, Entry, StringVar,
                     DoubleVar, messagebox, filedialog, END, DISABLED, NORMAL)
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

# ─────────────────────────── SETTINGS ───────────────────────────
PRIZE_ROI_FILE = Path("prize_location.json")
REFERENCE_FILE = Path("machine_reference.png")     # machine image (input, not debug)
RESULTS_FILE = Path("draw_results.json")
CSV_FILE = Path("draw_results.csv")

NUM_ROLLERS = 18
NUMBER_DIGITS = 4
PRIZE_AMOUNTS = {          # optional, e.g. "4th Prize": 5000
}

# Scanning
ANALYSIS_W = 640           # frames are analysed at this width (fast)
IDLE_STEP_SEC = 1.0        # sampling while searching for the machine
DRAW_STEP_SEC = 0.5        # sampling during a draw (close-ups)
DRAW_TIMEOUT_SEC = 60      # end a draw after this long with no board/close-up
NEW_DRAW_BOARD_SEC = 8     # board shown this long after close-ups = new spin
PRIZE_READ_EVERY_SEC = 2.0
REQUIRE_BOARD_FIRST = True # ignore close-ups until the machine has been seen

# Detection
YELLOW_LO = (15, 90, 120)  # HSV range of the yellow roller tags
YELLOW_HI = (40, 255, 255)
BOARD_MIN_LABELS = 12      # yellow tags needed to call it "full board"
CLOSEUP_MIN_LABEL_FRAC = 0.004   # close-up tag area / frame area
HOUSING_WHITE_MIN = 0.25   # white fraction needed right of the tag
ORB_CONFIRM_INLIERS = 12   # with reference: needed together with yellow tags
ORB_STRONG_INLIERS = 60    # with reference: enough on its own

# Reading
SHARPNESS_MIN = 40         # skip blurry (spinning) close-ups
MIN_VOTES = 2              # agreeing reads to mark a roller confident
UPSCALE_HOUSING_H = 200
CELL_EXPAND = 0.10
CELL_W, CELL_H = 24, 32

CANVAS_W, CANVAS_H = 960, 540


# ─────────────────────────── HELPERS ────────────────────────────
def fmt_time(sec):
    sec = max(0, sec)
    return f"{int(sec // 3600):02d}:{int(sec % 3600 // 60):02d}:{int(sec % 60):02d}"


def parse_time(s):
    """'1:02:30', '17:42', '1062' -> seconds"""
    try:
        sec = 0.0
        for p in s.strip().split(":"):
            sec = sec * 60 + float(p)
        return max(0.0, sec)
    except Exception:
        return 0.0


def imread_safe(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def imwrite_safe(path, img):
    ok, buf = cv2.imencode(Path(path).suffix or ".png", img)
    if ok:
        buf.tofile(str(path))
    return ok


def resize_w(img, w):
    h = max(1, int(img.shape[0] * w / img.shape[1]))
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)


def to_gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def upscale_to_height(gray, target_h):
    f = target_h / max(1, gray.shape[0])
    return cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)


def load_roi(path):
    try:
        data = json.loads(path.read_text())
        roi = data.get("roi", data)
        return {k: int(roi[k]) for k in ("x", "y", "width", "height")}
    except Exception:
        return None


def ordinal_prize(n):
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n, 'th') } Prize"


def parse_prize(text):
    t = re.sub(r"[^A-Z0-9 ]", " ", text.upper())
    m = re.search(r"(\d{1,2})\s*(?:ST|ND|RD|TH)?\s*P\s*R\s*[I1L]\s*[Z2]", t)
    if not m:
        m = re.search(r"\b(\d{1,2})\s*(?:ST|ND|RD|TH)\b", t)
    if not m:
        return None
    n = int(m.group(1))
    if n > 10:
        n = n % 10
    return ordinal_prize(n) if 1 <= n <= 10 else None


def make_variants(crop):
    gray = to_gray(crop)
    f = min(4.0, max(1.0, 96 / max(1, gray.shape[0])))
    up = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(up)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return [clahe, otsu, 255 - otsu]


# ───────────────────── SCENE DETECTION ──────────────────────────
def find_yellow_labels(small):
    """Yellow roller tags as (x, y, w, h) in analysis coordinates."""
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, YELLOW_LO, YELLOW_HI)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    W = mask.shape[1]
    labels = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 30 or w > 0.4 * W:
            continue
        if not 0.6 <= w / max(1, h) <= 1.8:
            continue
        if a / float(w * h) < 0.5:
            continue
        labels.append((int(x), int(y), int(w), int(h)))
    return labels


def board_label_count(labels):
    """Number of tags with similar size (the 18 tags on the board)."""
    if len(labels) < 3:
        return 0
    areas = np.array([w * h for _, _, w, h in labels], float)
    med = np.median(areas)
    return int(np.sum((areas > 0.4 * med) & (areas < 2.5 * med)))


def housing_box(label, W, H):
    """Where the white roller housing should be, right of the tag."""
    x, y, w, h = label
    cy = y + h / 2
    x1, x2 = int(x + w * 1.0), int(min(W, x + w * 7.0))
    y1, y2 = int(max(0, cy - h * 1.6)), int(min(H, cy + h * 1.6))
    if x2 - x1 < w * 2 or y2 - y1 < h:
        return None
    return x1, y1, x2, y2


def white_fraction(img, box):
    x1, y1, x2, y2 = box
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    m = cv2.inRange(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV), (0, 0, 140), (180, 70, 255))
    return float(np.count_nonzero(m)) / m.size


def refine_housing(crop):
    """Tighten a crop to the largest white area (the roller housing)."""
    if crop is None or crop.size == 0:
        return crop
    white = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), (0, 0, 140), (180, 70, 255))
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    if n <= 1:
        return crop
    i = 1 + int(np.argmax(stats[1:, 4]))
    x, y, w, h, a = stats[i]
    if a < 0.1 * crop.shape[0] * crop.shape[1]:
        return crop
    return crop[y:y + h, x:x + w]


def sharpness(gray):
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


class MachineMatcher:
    """Optional: match frames against a reference image of the machine (ORB)."""

    def __init__(self):
        self.orb = cv2.ORB_create(1500)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.kp, self.des = None, None

    @property
    def ready(self):
        return self.des is not None

    def set_reference(self, bgr):
        g = to_gray(resize_w(bgr, ANALYSIS_W))
        kp, des = self.orb.detectAndCompute(g, None)
        if des is None or len(kp) < 20:
            return False
        self.kp, self.des = kp, des
        return True

    def inliers(self, gray_small):
        if self.des is None:
            return -1
        kp, des = self.orb.detectAndCompute(gray_small, None)
        if des is None or len(kp) < 10:
            return 0
        good = [m[0] for m in self.bf.knnMatch(self.des, des, k=2)
                if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
        if len(good) < 10:
            return len(good) // 2
        src = np.float32([self.kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        return int(mask.sum()) if mask is not None else 0


# ───────────────────── DIGIT CLEANING ───────────────────────────
def find_digit_cells(gray):
    """Find the 4 dark-bordered digit windows. Returns relative boxes or None."""
    H, W = gray.shape
    _, dark = cv2.threshold(cv2.GaussianBlur(gray, (3, 3), 0), 0, 255,
                            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, _, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    cands = []
    for i in range(1, n):
        x, y, w, h, _a = stats[i]
        if h < 0.25 * H or not (0.04 * W <= w <= 0.35 * W) or not (0.7 <= h / max(1, w) <= 5.0):
            continue
        cands.append((int(x), int(y), int(x + w), int(y + h)))

    def area(b):
        return (b[2] - b[0]) * (b[3] - b[1])

    outer = [a for i, a in enumerate(cands)
             if not any(j != i and b[0] <= a[0] and b[1] <= a[1] and b[2] >= a[2]
                        and b[3] >= a[3] and area(b) > area(a) for j, b in enumerate(cands))]
    if len(outer) < NUMBER_DIGITS:
        return None
    hs = np.array([b[3] - b[1] for b in outer], float)
    ycs = np.array([(b[1] + b[3]) / 2 for b in outer], float)
    mh, myc = np.median(hs), np.median(ycs)
    sel = [b for b, h, yc in zip(outer, hs, ycs)
           if 0.7 * mh <= h <= 1.4 * mh and abs(yc - myc) < 0.2 * H]
    if len(sel) < NUMBER_DIGITS:
        return None
    sel = sorted(sorted(sel, key=area, reverse=True)[:NUMBER_DIGITS], key=lambda b: b[0])
    steps = [sel[i + 1][0] - sel[i][0] for i in range(len(sel) - 1)]
    if min(steps) <= 0 or max(steps) > 1.8 * min(steps):
        return None
    return [(b[0] / W, b[1] / H, b[2] / W, b[3] / H) for b in sel]


def normalize_digit(d):
    h, w = d.shape
    s = (CELL_H - 4) / max(1, h)
    nw = max(1, min(CELL_W - 4, int(round(w * s))))
    r = cv2.resize(d, (nw, CELL_H - 4), interpolation=cv2.INTER_AREA)
    out = np.zeros((CELL_H, CELL_W), np.uint8)
    x0 = (CELL_W - nw) // 2
    out[2:CELL_H - 2, x0:x0 + nw] = r
    return out


def clean_cell(cell):
    """Remove the window frame, keep the digit (white on black, normalized)."""
    if cell is None or cell.size == 0 or cell.shape[0] < 8 or cell.shape[1] < 5:
        return None
    h, w = cell.shape[:2]
    _, bw = cv2.threshold(cv2.GaussianBlur(cell, (3, 3), 0), 0, 255,
                          cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
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
        if (x == 0 or x + cw >= w) and cw < 0.12 * w:
            continue
        if not (0.15 * w <= cents[i][0] <= 0.85 * w):
            continue
        comps.append(i)

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
    parts = []
    for n in norms:
        parts.append(cv2.resize(255 - n, (CELL_W * 2, CELL_H * 2), interpolation=cv2.INTER_CUBIC))
        parts.append(np.full((CELL_H * 2, 14), 255, np.uint8))
    return cv2.copyMakeBorder(np.hstack(parts[:-1]), 16, 16, 16, 16,
                              cv2.BORDER_CONSTANT, value=255)


def ocr_cell_image(n):
    t = cv2.resize(255 - n, (CELL_W * 2, CELL_H * 2), interpolation=cv2.INTER_CUBIC)
    return cv2.copyMakeBorder(t, 16, 16, 24, 24, cv2.BORDER_CONSTANT, value=255)


# ─────────────────────────── APP ────────────────────────────────
class DrawScanner:
    def __init__(self, root):
        self.root = root
        root.title("Lottery Draw Scanner - Auto Machine Detection")
        root.geometry("1420x900")
        root.configure(bg="#f0f0f0")

        self.cap = None
        self.video_path = None
        self.fps = 25.0
        self.total = 1
        self.frame = None
        self.frame_idx = 0
        self.seek_after_id = None
        self.slider_guard = False
        self.scale, self.offset, self.photo = 1.0, (0, 0), None
        self.thumb_refs = {}

        self.reader = None
        self.matcher = MachineMatcher()
        self.prize_roi = load_roi(PRIZE_ROI_FILE)

        # Scan state
        self.scanning = False
        self.after_id = None
        self.draws = []
        self.cur = None
        self.board_start = None
        self.last_prize_read = -999.0
        self.prev_scene = None
        self.last_analysis = None

        self.build_ui()
        if REFERENCE_FILE.exists():
            img = imread_safe(REFERENCE_FILE)
            if img is not None and self.matcher.set_reference(img):
                self.show_thumb(img, self.ref_thumb, "ref", 380, 120)
        self.refresh_ref_label()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ───────────── UI ─────────────
    def build_ui(self):
        left = Frame(self.root, bg="#f0f0f0")
        left.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        right = Frame(self.root, bg="#ffffff", width=420, relief="solid", bd=1)
        right.pack(side="right", fill="y", padx=(0, 8), pady=8)
        right.pack_propagate(False)

        top = Frame(left, bg="#f0f0f0")
        top.pack(fill="x")
        Button(top, text="📁 Open Video", command=self.open_video, bg="#4CAF50", fg="white",
               font=("Arial", 10, "bold")).pack(side="left", padx=(0, 4))
        Button(top, text="🖼 Load Machine Image", command=self.load_reference,
               font=("Arial", 9)).pack(side="left", padx=2)
        Button(top, text="📌 Use Frame as Reference", command=self.use_frame_reference,
               font=("Arial", 9)).pack(side="left", padx=2)
        Label(top, text="  Start at:", bg="#f0f0f0", font=("Arial", 9, "bold")).pack(side="left")
        self.start_var = StringVar(value="00:00:00")
        Entry(top, textvariable=self.start_var, width=9, font=("Courier", 10)).pack(side="left", padx=2)
        self.scan_btn = Button(top, text="▶ START SCAN", command=self.start_scan, bg="#2196F3",
                               fg="white", font=("Arial", 10, "bold"))
        self.scan_btn.pack(side="left", padx=4)
        self.stop_btn = Button(top, text="⏹ Stop", command=self.stop_scan, bg="#f44336",
                               fg="white", font=("Arial", 10, "bold"), state=DISABLED)
        self.stop_btn.pack(side="left", padx=2)
        Button(top, text="📤 Export", command=self.export, bg="#FF9800", fg="white",
               font=("Arial", 10, "bold")).pack(side="left", padx=2)

        self.video_label = Label(left, text="No video loaded", bg="#f0f0f0", fg="#555",
                                 font=("Arial", 9))
        self.video_label.pack(anchor="w", pady=(4, 0))

        self.canvas = Canvas(left, width=CANVAS_W, height=CANVAS_H, bg="black", highlightthickness=0)
        self.canvas.pack(pady=4)

        self.pos_var = DoubleVar()
        self.slider = ttk.Scale(left, from_=0, to=1, orient="horizontal",
                                variable=self.pos_var, command=self.on_slider)
        self.slider.pack(fill="x")
        self.time_label = Label(left, text="00:00:00 / 00:00:00", font=("Courier", 11), bg="#f0f0f0")
        self.time_label.pack(pady=2)

        self.progress_var = DoubleVar()
        ttk.Progressbar(left, variable=self.progress_var, maximum=100).pack(fill="x", pady=2)

        nav = Frame(left, bg="#f0f0f0")
        nav.pack(pady=4)
        for txt, sec in [("⏪ 60s", -60), ("⏪ 10s", -10), ("◀ 1s", -1),
                         ("1s ▶", 1), ("10s ⏩", 10), ("60s ⏩", 60)]:
            Button(nav, text=txt, width=7, command=lambda s=sec: self.skip(s)).pack(side="left", padx=2)
        Button(nav, text="🔬 Test Frame", command=self.test_frame, bg="#7B1FA2", fg="white",
               font=("Arial", 10, "bold")).pack(side="left", padx=10)
        Button(nav, text="Set Start = here", command=self.set_start_here).pack(side="left", padx=2)

        # ---- Right panel
        Label(right, text="Machine reference", font=("Arial", 11, "bold"), bg="#fff").pack(anchor="w", padx=10, pady=(8, 0))
        self.ref_label = Label(right, bg="#fff", font=("Courier", 8), fg="#555")
        self.ref_label.pack(anchor="w", padx=10)
        self.ref_thumb = Label(right, bg="#eee")
        self.ref_thumb.pack(padx=10, pady=2)

        Label(right, text="Detection", font=("Arial", 11, "bold"), bg="#fff").pack(anchor="w", padx=10, pady=(4, 0))
        self.status = Label(right, text="Open a video, then use 🔬 Test Frame on the board\n"
                                        "and on a close-up to check detection.",
                            bg="#fff", fg="#333", font=("Courier", 8), justify="left", wraplength=400)
        self.status.pack(anchor="w", padx=10)
        crops = Frame(right, bg="#fff")
        crops.pack(fill="x", padx=10, pady=2)
        self.label_thumb = Label(crops, bg="#eee")
        self.label_thumb.pack(side="left", padx=(0, 4))
        self.house_thumb = Label(crops, bg="#eee")
        self.house_thumb.pack(side="left")

        Label(right, text="Log", font=("Arial", 11, "bold"), bg="#fff").pack(anchor="w", padx=10, pady=(4, 0))
        self.log_box = Text(right, height=8, font=("Courier", 8), bg="#fafafa", state=DISABLED)
        self.log_box.pack(fill="x", padx=10)

        Label(right, text="Results (roller: number ✓confident (votes))", font=("Arial", 11, "bold"),
              bg="#fff").pack(anchor="w", padx=10, pady=(4, 0))
        self.results_box = Text(right, font=("Courier", 9), bg="#fafafa", state=DISABLED)
        self.results_box.pack(fill="both", expand=True, padx=10, pady=(0, 8))

    def refresh_ref_label(self):
        self.ref_label.config(
            text=f"✓ Loaded ({len(self.matcher.kp)} features)" if self.matcher.ready
            else "Not set (optional, yellow-tag detection still works)")

    def log(self, msg):
        self.log_box.config(state=NORMAL)
        self.log_box.insert(END, msg + "\n")
        self.log_box.see(END)
        self.log_box.config(state=DISABLED)

    def show_thumb(self, img, label, key, max_w=200, max_h=90):
        if img is None or img.size == 0:
            label.config(image="", text="")
            return
        im = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if img.ndim == 3 else img)
        im.thumbnail((max_w, max_h))
        self.thumb_refs[key] = ImageTk.PhotoImage(im)
        label.config(image=self.thumb_refs[key])

    # ───────────── Video ─────────────
    def open_video(self):
        path = filedialog.askopenfilename(title="Select Lottery Video",
                                          filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv"), ("All", "*.*")])
        if not path:
            return
        self.stop_scan()
        if self.cap:
            self.cap.release()
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            messagebox.showerror("Error", "Cannot open this video.")
            return
        self.cap, self.video_path = cap, path
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.total = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.slider.config(to=self.total - 1)
        self.video_label.config(text=Path(path).name)
        self.seek(0)

    def seek(self, idx):
        if not self.cap:
            return
        idx = max(0, min(int(idx), self.total - 1))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, f = self.cap.read()
        if ok:
            self.frame, self.frame_idx = f, idx
            self.last_analysis = None
            self.show_frame()

    def skip(self, sec):
        if self.cap and not self.scanning:
            self.seek(self.frame_idx + sec * self.fps)

    def on_slider(self, value):
        if self.slider_guard or not self.cap or self.scanning:
            return
        if self.seek_after_id:
            self.root.after_cancel(self.seek_after_id)
        self.seek_after_id = self.root.after(80, lambda: self.seek(float(value)))

    def set_start_here(self):
        self.start_var.set(fmt_time(self.frame_idx / self.fps))

    def update_time_ui(self):
        self.slider_guard = True
        self.pos_var.set(self.frame_idx)
        self.slider_guard = False
        self.time_label.config(text=f"{fmt_time(self.frame_idx / self.fps)} / "
                                    f"{fmt_time(self.total / self.fps)}")
        self.progress_var.set(100.0 * self.frame_idx / self.total)

    def show_frame(self, a=None):
        if self.frame is None:
            return
        h, w = self.frame.shape[:2]
        s = min(CANVAS_W / w, CANVAS_H / h)
        dw, dh = int(w * s), int(h * s)
        ox, oy = (CANVAS_W - dw) // 2, (CANVAS_H - dh) // 2
        self.scale, self.offset = s, (ox, oy)
        rgb = cv2.cvtColor(cv2.resize(self.frame, (dw, dh), interpolation=cv2.INTER_AREA),
                           cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, image=self.photo, anchor="nw")

        if a:
            k = s * w / ANALYSIS_W          # analysis coords -> canvas

            def rect(x1, y1, x2, y2, color, width=2):
                self.canvas.create_rectangle(ox + x1 * k, oy + y1 * k, ox + x2 * k, oy + y2 * k,
                                             outline=color, width=width)
            if a["scene"] == "board":
                for (x, y, lw, lh) in a["labels"]:
                    rect(x, y, x + lw, y + lh, "#00E676")
            elif a["scene"] == "closeup":
                x, y, lw, lh = a["label"]
                rect(x, y, x + lw, y + lh, "#FFEB3B", 3)
                rect(*a["housing"], "#00E5FF", 3)
            color = {"board": "#00E676", "closeup": "#00E5FF"}.get(a["scene"], "#FF5252")
            inl = a["inliers"] if a["inliers"] >= 0 else "-"
            self.canvas.create_text(ox + 8, oy + 8, anchor="nw", fill=color,
                                    font=("Courier", 12, "bold"),
                                    text=f"{a['scene'].upper()}  tags={a['n_board']}  orb={inl}")
        self.update_time_ui()

    # ───────────── Reference ─────────────
    def load_reference(self):
        path = filedialog.askopenfilename(title="Machine image",
                                          filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp"), ("All", "*.*")])
        if not path:
            return
        img = imread_safe(path)
        self.apply_reference(img)

    def use_frame_reference(self):
        if self.frame is None:
            messagebox.showwarning("No frame", "Open a video and go to the full machine first.")
            return
        self.apply_reference(self.frame.copy())

    def apply_reference(self, img):
        if img is None or not self.matcher.set_reference(img):
            messagebox.showerror("Reference", "Could not use this image (too few features).")
            return
        imwrite_safe(REFERENCE_FILE, img)
        self.show_thumb(img, self.ref_thumb, "ref", 380, 120)
        self.refresh_ref_label()
        self.log("✓ Machine reference set")

    # ───────────── Analysis ─────────────
    def analyze(self, frame):
        small = resize_w(frame, ANALYSIS_W)
        H, W = small.shape[:2]
        labels = find_yellow_labels(small)
        nb = board_label_count(labels)
        inl = self.matcher.inliers(to_gray(small)) if self.matcher.ready else -1
        a = {"scene": "other", "labels": labels, "n_board": nb, "inliers": inl,
             "label": None, "housing": None}

        yellow_board = nb >= BOARD_MIN_LABELS
        if self.matcher.ready:
            is_board = (yellow_board and inl >= ORB_CONFIRM_INLIERS) or inl >= ORB_STRONG_INLIERS
        else:
            is_board = yellow_board
        if is_board:
            a["scene"] = "board"
            return a

        big = sorted([l for l in labels if l[2] * l[3] >= CLOSEUP_MIN_LABEL_FRAC * W * H],
                     key=lambda l: l[2] * l[3], reverse=True)
        for l in big[:3]:
            hb = housing_box(l, W, H)
            if hb and white_fraction(small, hb) >= HOUSING_WHITE_MIN:
                a.update(scene="closeup", label=l, housing=hb)
                break
        return a

    # ───────────── OCR ─────────────
    def get_reader(self):
        if self.reader is None:
            self.status.config(text="Loading EasyOCR (first time only)...")
            self.root.update()
            import easyocr
            self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return self.reader

    def read_prize(self, frame):
        if not self.prize_roi:
            return None
        r = self.prize_roi
        crop = frame[r["y"]:r["y"] + r["height"], r["x"]:r["x"] + r["width"]]
        if crop.size == 0:
            return None
        for v in make_variants(crop):
            try:
                res = self.get_reader().readtext(v, detail=1, paragraph=False)
            except Exception:
                continue
            p = parse_prize(" ".join(x[1] for x in res))
            if p:
                return p
        return None

    def ocr_digits(self, img):
        try:
            res = self.get_reader().recognize(img, allowlist="0123456789", detail=1)
        except Exception:
            return "", 0.0
        if not res:
            return "", 0.0
        best = max(res, key=lambda r: r[2])
        return re.sub(r"\D", "", best[1]), float(best[2])

    def read_label(self, crop):
        """Yellow tag -> roller number 1-18."""
        if crop is None or crop.size == 0:
            return None
        g = upscale_to_height(to_gray(crop), 80)
        pad = max(6, g.shape[0] // 6)
        g = cv2.copyMakeBorder(g, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        for img in (bw, g):
            txt = ""
            try:
                res = self.get_reader().readtext(img, allowlist="0123456789", detail=1, paragraph=False)
                res.sort(key=lambda r: min(p[0] for p in r[0]))
                txt = "".join(r[1] for r in res)
            except Exception:
                pass
            if not txt:
                txt, _ = self.ocr_digits(img)
            d = re.sub(r"\D", "", txt)
            if d and 1 <= int(d) <= NUM_ROLLERS:
                return int(d)
        return None

    def read_housing(self, house):
        """White housing -> 4-digit number. Returns (digits, conf 0-1)."""
        if house is None or house.size == 0:
            return "", 0.0
        g = upscale_to_height(to_gray(house), UPSCALE_HOUSING_H)
        H, W = g.shape
        cands = []

        cells = find_digit_cells(g)
        if cells:
            norms = []
            for rx1, ry1, rx2, ry2 in cells:
                cw, ch = (rx2 - rx1) * W, (ry2 - ry1) * H
                x1, x2 = int(max(0, rx1 * W - CELL_EXPAND * cw)), int(min(W, rx2 * W + CELL_EXPAND * cw))
                y1, y2 = int(max(0, ry1 * H - CELL_EXPAND * ch)), int(min(H, ry2 * H + CELL_EXPAND * ch))
                norms.append(clean_cell(g[y1:y2, x1:x2]))
            if all(n is not None for n in norms):
                t, c = self.ocr_digits(ocr_strip_image(norms))
                if len(t) != NUMBER_DIGITS:
                    per = [self.ocr_digits(ocr_cell_image(n)) for n in norms]
                    t = "".join(x[0][:1] for x in per)
                    c = min(x[1] for x in per)
                if len(t) == NUMBER_DIGITS:
                    cands.append((t, c))

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(g)
        try:
            res = self.get_reader().readtext(clahe, allowlist="0123456789", detail=1, paragraph=False)
        except Exception:
            res = []
        if res:
            res.sort(key=lambda r: min(p[0] for p in r[0]))
            t = "".join(re.sub(r"\D", "", r[1]) for r in res)
            if len(t) == NUMBER_DIGITS:
                cands.append((t, float(np.mean([r[2] for r in res]))))

        return max(cands, key=lambda x: x[1]) if cands else ("", 0.0)

    def read_closeup(self, frame, a):
        s = frame.shape[1] / ANALYSIS_W
        lx, ly, lw, lh = a["label"]
        label_crop = frame[int(ly * s):int((ly + lh) * s), int(lx * s):int((lx + lw) * s)]
        hx1, hy1, hx2, hy2 = a["housing"]
        house = refine_housing(frame[int(hy1 * s):int(hy2 * s), int(hx1 * s):int(hx2 * s)])
        out = {"roller": None, "digits": "", "conf": 0.0, "sharp": 0.0,
               "label_crop": label_crop, "house_crop": house}
        if house is None or house.size == 0:
            return out
        out["sharp"] = sharpness(upscale_to_height(to_gray(house), 120))
        if out["sharp"] < SHARPNESS_MIN:
            return out
        out["roller"] = self.read_label(label_crop)
        out["digits"], out["conf"] = self.read_housing(house)
        return out

    # ───────────── Test current frame ─────────────
    def test_frame(self):
        if self.frame is None or self.scanning:
            return
        a = self.analyze(self.frame)
        self.show_frame(a)
        inl = a["inliers"] if a["inliers"] >= 0 else "no reference"
        lines = [f"Scene: {a['scene'].upper()}",
                 f"Board-size yellow tags: {a['n_board']} (board needs {BOARD_MIN_LABELS})",
                 f"ORB inliers vs reference: {inl}"]
        self.show_thumb(None, self.label_thumb, "lab")
        self.show_thumb(None, self.house_thumb, "house")
        if a["scene"] == "board":
            if self.prize_roi:
                lines.append(f"Prize banner: {self.read_prize(self.frame) or 'not read'}")
            else:
                lines.append("Prize ROI missing (prize_location.json)")
        elif a["scene"] == "closeup":
            r = self.read_closeup(self.frame, a)
            self.show_thumb(r["label_crop"], self.label_thumb, "lab", 80, 80)
            self.show_thumb(r["house_crop"], self.house_thumb, "house", 300, 80)
            lines.append(f"Sharpness: {r['sharp']:.0f} (min {SHARPNESS_MIN})")
            if r["sharp"] < SHARPNESS_MIN:
                lines.append("→ too blurry, skipped (rollers moving?)")
            else:
                lines.append(f"Roller tag: {r['roller'] or 'not read'}")
                lines.append(f"Number: {r['digits'] or 'not read'} ({r['conf'] * 100:.0f}%)")
        else:
            big = max((l[2] * l[3] for l in a["labels"]), default=0)
            lines.append(f"Largest yellow tag: {big} px (close-up needs "
                         f"{int(CLOSEUP_MIN_LABEL_FRAC * ANALYSIS_W * ANALYSIS_W * 9 / 16)}+)")
        self.status.config(text="\n".join(lines))

    # ───────────── Scanning ─────────────
    def start_scan(self):
        if not self.cap:
            messagebox.showwarning("No video", "Open a video first.")
            return
        if self.scanning:
            return
        if not self.prize_roi:
            if not messagebox.askyesno("Prize ROI", "prize_location.json not found.\n"
                                                    "Prizes will be named 'Draw 1, 2…'. Continue?"):
                return
        self.get_reader()
        start = parse_time(self.start_var.get())
        sf = min(self.total - 1, int(start * self.fps))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, sf)
        self.frame_idx = sf - 1
        self.draws, self.cur = [], None
        self.board_start, self.prev_scene = None, None
        self.last_prize_read = -999.0
        self.scanning = True
        self.scan_btn.config(state=DISABLED)
        self.stop_btn.config(state=NORMAL)
        self.refresh_results()
        self.log(f"▶ Scan started at {fmt_time(start)}")
        self.scan_tick()

    def stop_scan(self):
        if not self.scanning:
            return
        self.scanning = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.close_draw("scan stopped")
        self.scan_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)
        self.log("⏹ Scan stopped")

    def finish_scan(self):
        self.scanning = False
        self.close_draw("end of video")
        self.scan_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)
        self.log("✅ Scan complete")
        messagebox.showinfo("Done", f"Scan complete.\n{len(self.draws)} draw(s) found.\n"
                                    f"Saved to {RESULTS_FILE}")

    def advance(self, step_sec):
        n = max(1, int(round(step_sec * self.fps)))
        for _ in range(n - 1):
            if not self.cap.grab():
                return False
            self.frame_idx += 1
        ok, f = self.cap.read()
        if not ok:
            return False
        self.frame_idx += 1
        self.frame = f
        return True

    def scan_tick(self):
        if not self.scanning:
            return
        t0 = time.time()
        while self.scanning and time.time() - t0 < 0.08:
            if not self.advance(DRAW_STEP_SEC if self.cur else IDLE_STEP_SEC):
                self.show_frame(self.last_analysis)
                self.finish_scan()
                return
            if self.process_sample():
                break                       # OCR happened: refresh UI now
        self.show_frame(self.last_analysis)
        self.after_id = self.root.after(1, self.scan_tick)

    def process_sample(self):
        t = self.frame_idx / self.fps
        a = self.analyze(self.frame)
        self.last_analysis = a
        if a["scene"] != self.prev_scene and a["scene"] != "other":
            self.log(f"{fmt_time(t)}  scene: {a['scene']}")
        self.prev_scene = a["scene"]

        did_ocr = False
        if a["scene"] == "board":
            did_ocr = self.on_board(t)
        else:
            self.board_start = None
            if a["scene"] == "closeup":
                did_ocr = self.on_closeup(t, a)

        if self.cur and t - self.cur["last_activity"] > DRAW_TIMEOUT_SEC:
            self.close_draw("timeout")
        return did_ocr

    def open_draw(self, t):
        self.cur = {"start": t, "prize_votes": Counter(), "other_prize": Counter(),
                    "votes": defaultdict(Counter), "times": {}, "last_activity": t, "closeups": 0}
        self.log(f"{fmt_time(t)}  🎰 Machine detected → draw {len(self.draws) + 1}")

    def on_board(self, t):
        if self.board_start is None:
            self.board_start = t
        if self.cur is None:
            self.open_draw(t)
        elif self.cur["closeups"] > 0 and t - self.board_start >= NEW_DRAW_BOARD_SEC:
            self.close_draw("machine shown again")
            self.open_draw(t)
        self.cur["last_activity"] = t

        if not self.prize_roi or t - self.last_prize_read < PRIZE_READ_EVERY_SEC:
            return False
        self.last_prize_read = t
        p = self.read_prize(self.frame)
        if p:
            cur_p = self.confirmed_prize(self.cur)
            if cur_p and p != cur_p:
                if self.cur["closeups"] == 0:
                    self.cur["prize_votes"].clear()          # old banner, replace
                else:
                    self.cur["other_prize"][p] += 1
                    if self.cur["other_prize"][p] >= 2:      # changed for real
                        self.close_draw(f"prize changed to {p}")
                        self.open_draw(t)
                        self.cur["prize_votes"][p] += 1
                    return True
            self.cur["prize_votes"][p] += 1
            self.cur["other_prize"].clear()
        return True

    def on_closeup(self, t, a):
        if self.cur is None:
            if REQUIRE_BOARD_FIRST:
                return False
            self.open_draw(t)
        self.cur["last_activity"] = t
        r = self.read_closeup(self.frame, a)
        self.show_thumb(r["label_crop"], self.label_thumb, "lab", 80, 80)
        self.show_thumb(r["house_crop"], self.house_thumb, "house", 300, 80)
        if r["sharp"] < SHARPNESS_MIN:
            return False
        if r["roller"] and len(r["digits"]) == NUMBER_DIGITS:
            votes = self.cur["votes"][r["roller"]]
            votes[r["digits"]] += 1
            self.cur["times"].setdefault(r["roller"], fmt_time(t))
            self.cur["closeups"] += 1
            if votes[r["digits"]] == 1:
                self.log(f"{fmt_time(t)}  roller {r['roller']:>2}: {r['digits']} "
                         f"({r['conf'] * 100:.0f}%)")
            self.refresh_results()
        return True

    @staticmethod
    def confirmed_prize(d):
        return d["prize_votes"].most_common(1)[0][0] if d["prize_votes"] else None

    def finalize_draw(self, d, number):
        prize = self.confirmed_prize(d) or f"Draw {number}"
        rollers = {}
        for r in range(1, NUM_ROLLERS + 1):
            c = d["votes"].get(r)
            if not c:
                continue
            num, v = c.most_common(1)[0]
            total = sum(c.values())
            rollers[str(r)] = {"number": num, "votes": v, "reads": total,
                               "confident": v >= MIN_VOTES and v / total >= 0.6,
                               "time": d["times"].get(r, ""),
                               "alternatives": {k: n for k, n in c.items() if k != num}}
        return {"draw": number, "prize": prize,
                "amount": str(PRIZE_AMOUNTS.get(prize, "")),
                "start": fmt_time(d["start"]), "found": len(rollers), "rollers": rollers}

    def close_draw(self, reason):
        d, self.cur = self.cur, None
        if d is None:
            return
        if not d["votes"]:
            self.log("   (no roller close-ups, ignored)")
            return
        fin = self.finalize_draw(d, len(self.draws) + 1)
        self.draws.append(fin)
        self.write_json()
        self.refresh_results()
        self.log(f"✓ Draw {fin['draw']} closed ({reason}): {fin['prize']}, "
                 f"{fin['found']}/{NUM_ROLLERS} rollers")

    # ───────────── Results ─────────────
    def refresh_results(self):
        items = list(self.draws)
        if self.cur and self.cur["votes"]:
            live = self.finalize_draw(self.cur, len(self.draws) + 1)
            live["prize"] += "  (LIVE)"
            items.append(live)
        lines = []
        for d in items:
            amt = f" ₹{d['amount']}" if d["amount"] else ""
            lines.append(f"Draw {d['draw']}: {d['prize']}{amt}  @ {d['start']}  "
                         f"[{d['found']}/{NUM_ROLLERS}]")
            rows = NUM_ROLLERS // 3
            for i in range(1, rows + 1):
                cells = []
                for r in (i, i + rows, i + 2 * rows):
                    x = d["rollers"].get(str(r))
                    if x:
                        mark = "✓" if x["confident"] else "?"
                        cells.append(f"{r:>2}:{x['number']}{mark}({x['votes']})")
                    else:
                        cells.append(f"{r:>2}:----    ")
                lines.append("  " + "  ".join(c.ljust(13) for c in cells))
            lines.append("")
        self.results_box.config(state=NORMAL)
        self.results_box.delete("1.0", END)
        self.results_box.insert("1.0", "\n".join(lines))
        self.results_box.config(state=DISABLED)

    def write_json(self):
        data = {"video": Path(self.video_path).name if self.video_path else "", "draws": self.draws}
        RESULTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def export(self):
        if not self.draws:
            messagebox.showwarning("Nothing to export", "No completed draws yet.")
            return
        self.write_json()
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Draw", "Prize", "Amount", "Roller", "Number", "Votes", "Reads",
                        "Confident", "Time"])
            for d in self.draws:
                for r in range(1, NUM_ROLLERS + 1):
                    x = d["rollers"].get(str(r))
                    if x:
                        w.writerow([d["draw"], d["prize"], d["amount"], r, x["number"],
                                    x["votes"], x["reads"], "yes" if x["confident"] else "CHECK",
                                    x["time"]])
                    else:
                        w.writerow([d["draw"], d["prize"], d["amount"], r, "", 0, 0, "MISSING", ""])
        messagebox.showinfo("Exported", f"Saved:\n- {RESULTS_FILE}\n- {CSV_FILE}")

    def on_close(self):
        self.scanning = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
        if self.cap:
            self.cap.release()
        self.root.destroy()


if __name__ == "__main__":
    root = Tk()
    DrawScanner(root)
    root.mainloop()
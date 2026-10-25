"""
lottery_extractor.py
Manual-control video player with on-demand extraction of
prize category + 4-digit numbers.
No threading: playback uses root.after().
"""
import csv
import json
import re
from pathlib import Path
from tkinter import (Tk, Frame, Label, Button, Canvas, Text, Entry, StringVar,
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

NUMBER_DIGITS = 4          # 4-digit prizes
MERGE_GAP_FACTOR = 1.0     # merge digit boxes closer than N character widths
                           # (increase if single roller digits are not joined)

# Optional: fill in once you know the amounts, e.g. "6th Prize": 5000
PRIZE_AMOUNTS = {
}

SPEEDS = [1, 2, 4, 8, 16, 32]
CANVAS_W, CANVAS_H = 960, 540


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
    """Preprocessed versions of a crop for OCR (kept in memory only)."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    f = min(4.0, max(1.0, 96 / max(1, gray.shape[0])))   # upscale small text
    up = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(up)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return [clahe, otsu, 255 - otsu]


def group_numbers(results, digits=NUMBER_DIGITS):
    """
    Turn EasyOCR boxes into N-digit numbers.
    Works for: one big number, a board of numbers, or separate roller digits.
    Returns (numbers, unreadable_groups).
    """
    items = []
    for bbox, text, conf in results:
        d = re.sub(r"\D", "", text)
        if not d:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
        items.append({"d": d, "x1": x1, "x2": x2, "yc": (y1 + y2) / 2,
                      "h": y2 - y1, "cw": (x2 - x1) / len(d)})
    if not items:
        return [], []

    avg_h = float(np.mean([i["h"] for i in items]))

    # Group into rows (top to bottom)
    items.sort(key=lambda i: i["yc"])
    rows = []
    for it in items:
        if rows and abs(it["yc"] - np.mean([r["yc"] for r in rows[-1]])) < avg_h * 0.6:
            rows[-1].append(it)
        else:
            rows.append([it])

    numbers, bad = [], []
    for row in rows:
        row.sort(key=lambda i: i["x1"])          # left to right
        groups = []
        for it in row:
            if groups:
                g = groups[-1]
                gap = it["x1"] - g["x2"]
                if (len(g["d"]) + len(it["d"]) <= digits and
                        gap < MERGE_GAP_FACTOR * max(g["cw"], it["cw"])):
                    g["d"] += it["d"]
                    g["x2"] = it["x2"]
                    continue
            groups.append(dict(it))

        for g in groups:
            d = g["d"]
            if len(d) == digits:
                numbers.append(d)
            elif len(d) % digits == 0:
                numbers.extend(d[i:i + digits] for i in range(0, len(d), digits))
            else:
                bad.append(d)
    return numbers, bad


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
        self.numbers_roi = self.load_roi(NUMBERS_ROI_FILE)

        # OCR / results
        self.reader = None
        self.entries = []
        self.extract_frame = None
        self.thumb_refs = {}

        self.build_ui()
        self.refresh_roi_labels()
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

    def save_prize_roi(self):
        data = {}
        if PRIZE_ROI_FILE.exists():
            try:
                data = json.loads(PRIZE_ROI_FILE.read_text())
            except Exception:
                data = {}
        data["roi"] = self.prize_roi          # keep other metadata intact
        PRIZE_ROI_FILE.write_text(json.dumps(data, indent=2))

    def save_numbers_roi(self):
        NUMBERS_ROI_FILE.write_text(json.dumps({"roi": self.numbers_roi}, indent=2))

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
                         "E=extract  Esc=cancel draw   (click the video to return keyboard control)",
              bg="#f0f0f0", fg="#666", font=("Courier", 9)).pack(pady=2)

        # ---- Right panel: ROIs
        Label(right, text="Regions (ROI)", font=("Arial", 12, "bold"),
              bg="#fff").pack(anchor="w", padx=10, pady=(10, 2))

        self.prize_roi_label = Label(right, bg="#fff", font=("Courier", 9), fg="#2E7D32")
        self.prize_roi_label.pack(anchor="w", padx=10)
        Button(right, text="🟩 Draw Prize Category ROI", command=lambda: self.start_draw("prize"),
               bg="#43A047", fg="white", font=("Arial", 9, "bold")).pack(fill="x", padx=10, pady=3)

        self.numbers_roi_label = Label(right, bg="#fff", font=("Courier", 9), fg="#1565C0")
        self.numbers_roi_label.pack(anchor="w", padx=10, pady=(6, 0))
        Button(right, text="🟦 Set Numbers ROI (permanent)", command=lambda: self.start_draw("numbers"),
               bg="#1E88E5", fg="white", font=("Arial", 9, "bold")).pack(fill="x", padx=10, pady=3)

        self.mode_label = Label(right, text="", bg="#fff", fg="#E65100",
                                font=("Arial", 9, "bold"), wraplength=380, justify="left")
        self.mode_label.pack(anchor="w", padx=10)

        ttk.Separator(right).pack(fill="x", padx=10, pady=6)

        # ---- Extract
        self.extract_btn = Button(right, text="🔍 EXTRACT  (E)", command=self.extract,
                                  bg="#FF5722", fg="white", font=("Arial", 13, "bold"), pady=4)
        self.extract_btn.pack(fill="x", padx=10)

        self.prize_thumb = Label(right, bg="#eeeeee")
        self.prize_thumb.pack(padx=10, pady=(6, 2))
        self.numbers_thumb = Label(right, bg="#eeeeee")
        self.numbers_thumb.pack(padx=10, pady=2)

        # ---- Editable results
        row = Frame(right, bg="#fff")
        row.pack(fill="x", padx=10, pady=(4, 0))
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

        Label(right, text="Numbers (one per line, fix if wrong):", bg="#fff",
              font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(4, 0))
        self.numbers_text = Text(right, height=6, font=("Courier", 11))
        self.numbers_text.pack(fill="x", padx=10)

        self.ocr_info = Label(right, text="", bg="#fff", fg="#666", font=("Courier", 8),
                              wraplength=380, justify="left")
        self.ocr_info.pack(anchor="w", padx=10, pady=2)

        btns = Frame(right, bg="#fff")
        btns.pack(fill="x", padx=10, pady=3)
        Button(btns, text="💾 Save Entry", command=self.save_entry, bg="#2E7D32", fg="white",
               font=("Arial", 9, "bold")).pack(side="left", fill="x", expand=True, padx=(0, 2))
        Button(btns, text="↶ Undo Last", command=self.undo_last, bg="#757575", fg="white",
               font=("Arial", 9, "bold")).pack(side="left", fill="x", expand=True, padx=2)
        Button(btns, text="📤 Export", command=self.export, bg="#FF9800", fg="white",
               font=("Arial", 9, "bold")).pack(side="left", fill="x", expand=True, padx=(2, 0))

        Label(right, text="Saved entries:", bg="#fff",
              font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(4, 0))
        self.log = Text(right, height=6, font=("Courier", 8), bg="#fafafa", state=DISABLED)
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def refresh_roi_labels(self):
        def txt(name, r):
            if not r:
                return f"{name}: not set"
            return f"{name}: x={r['x']} y={r['y']} {r['width']}x{r['height']}"
        self.prize_roi_label.config(text=txt("Prize  ", self.prize_roi))
        self.numbers_roi_label.config(text=txt("Numbers", self.numbers_roi))

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
        self.draw_roi(self.numbers_roi, "#2979FF", "NUMBERS")
        self.update_time_ui()

    def draw_roi(self, roi, color, name):
        if not roi:
            return
        ox, oy = self.offset
        s = self.scale
        x1, y1 = ox + roi["x"] * s, oy + roi["y"] * s
        x2, y2 = x1 + roi["width"] * s, y1 + roi["height"] * s
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2)
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

    def show_thumb(self, img, label, key, max_w=380, max_h=90):
        if img is None or img.size == 0:
            label.config(image="", text="(empty)")
            return
        rgb = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        rgb.thumbnail((max_w, max_h))
        self.thumb_refs[key] = ImageTk.PhotoImage(rgb)
        label.config(image=self.thumb_refs[key], text="")

    # ───────────── ROI drawing ─────────────
    def start_draw(self, mode):
        if self.frame is None:
            messagebox.showwarning("No video", "Open a video first.")
            return
        self.pause()
        if mode == "numbers" and self.numbers_roi:
            if not messagebox.askyesno("Replace?", "Numbers ROI is already set.\nReplace it?"):
                return
        self.draw_mode = mode
        self.mode_label.config(
            text=f"✏ Drag a rectangle on the video for the {mode.upper()} ROI  (Esc = cancel)")

    def cancel_draw(self):
        self.draw_mode = None
        if self.temp_rect:
            self.canvas.delete(self.temp_rect)
        self.temp_rect = None
        self.drag_start = None
        self.mode_label.config(text="")

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
        if roi["width"] < 8 or roi["height"] < 8:
            self.mode_label.config(text="Rectangle too small, drag again (Esc = cancel)")
            return

        if self.draw_mode == "prize":
            self.prize_roi = roi
            self.save_prize_roi()
        else:
            self.numbers_roi = roi
            self.save_numbers_roi()

        self.draw_mode = None
        self.mode_label.config(text="✓ ROI saved")
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

    def crop(self, roi):
        if self.frame is None or not roi:
            return None
        fh, fw = self.frame.shape[:2]
        x1, y1 = max(0, roi["x"]), max(0, roi["y"])
        x2, y2 = min(fw, x1 + roi["width"]), min(fh, y1 + roi["height"])
        c = self.frame[y1:y2, x1:x2]
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

    def read_numbers(self, crop):
        reader = self.get_reader()
        best = None
        for v in make_variants(crop):
            res = reader.readtext(v, detail=1, paragraph=False, allowlist="0123456789")
            nums, bad = group_numbers(res)
            conf = float(np.mean([r[2] for r in res])) * 100 if res else 0
            score = (len(nums), -len(bad), conf)
            if best is None or score > best["score"]:
                best = {"score": score, "numbers": list(dict.fromkeys(nums)),
                        "bad": bad, "conf": conf}
        return best

    def extract(self):
        if self.frame is None:
            messagebox.showwarning("No video", "Open a video first.")
            return
        if not self.numbers_roi:
            messagebox.showwarning("Numbers ROI", "Set the Numbers ROI first (blue button).")
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
            pcrop = self.crop(self.prize_roi)
            ncrop = self.crop(self.numbers_roi)
            self.show_thumb(pcrop, self.prize_thumb, "prize")
            self.show_thumb(ncrop, self.numbers_thumb, "numbers", max_h=140)
            self.root.update()

            p = self.read_prize(pcrop) if pcrop is not None else None
            n = self.read_numbers(ncrop) if ncrop is not None else None

            prize = p["prize"] if p and p["prize"] else ""
            self.prize_var.set(prize)
            self.amount_var.set(parse_amount(p["text"], prize) if p else "")

            self.numbers_text.delete("1.0", END)
            if n and n["numbers"]:
                self.numbers_text.insert("1.0", "\n".join(n["numbers"]))

            info = []
            if p:
                info.append(f"Prize OCR: '{p['text']}' ({p['conf']:.0f}%)")
            else:
                info.append("Prize OCR: nothing read")
            if n:
                info.append(f"Numbers: {len(n['numbers'])} found ({n['conf']:.0f}%)")
                if n["bad"]:
                    info.append(f"Unclear groups: {', '.join(n['bad'])}")
            else:
                info.append("Numbers: nothing read")
            if not prize:
                info.append("⚠ Prize not recognised, type it manually")
            self.ocr_info.config(text="\n".join(info))
            self.extract_frame = self.frame_idx

        except Exception as ex:
            messagebox.showerror("Extraction error", str(ex))
        finally:
            self.extract_btn.config(state=NORMAL, text="🔍 EXTRACT  (E)")
            self.root.config(cursor="")

    # ───────────── Saving ─────────────
    def save_entry(self):
        prize = self.prize_var.get().strip()
        raw = re.findall(r"\d+", self.numbers_text.get("1.0", END))
        good = [x for x in raw if len(x) == NUMBER_DIGITS]
        bad = [x for x in raw if len(x) != NUMBER_DIGITS]

        if not prize:
            messagebox.showwarning("Missing prize", "Enter the prize category first.")
            return
        if not good:
            messagebox.showwarning("No numbers", f"No valid {NUMBER_DIGITS}-digit numbers to save.")
            return
        if bad and not messagebox.askyesno(
                "Check numbers",
                f"These are not {NUMBER_DIGITS} digits and will be skipped:\n"
                f"{', '.join(bad)}\n\nSave the rest?"):
            return

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
        self.ocr_info.config(text=f"✓ Saved {len(entry['numbers'])} numbers for {prize}")
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
            "numbers_roi": self.numbers_roi,
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
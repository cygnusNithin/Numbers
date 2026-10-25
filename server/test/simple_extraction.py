"""
sixth_prize_extraction.py - trainable digit reader (NO DATABASE)

Run:  python sixth_prize_extraction.py
      python sixth_prize_extraction.py --video "x.mp4" --t 1062
      python sixth_prize_extraction.py --review-all   # verify every box
      python sixth_prize_extraction.py --no-review    # never prompt
First run: type the 4 digits for each box -> builds digit_library.npz.
"""
import argparse
import csv
import glob
import json
import os
from pathlib import Path

import cv2
import numpy as np

# ============================================================
# CONFIG
# ============================================================
ROLLER_FILE = "roller_groups.json"
LIB_FILE = "digit_library.npz"
OUTPUT_CSV = "sixth_prize_extracted.csv"
OUTPUT_JSON = "sixth_prize_extracted.json"
OUTPUT_IMAGE = "sixth_prize_annotated.png"
DEBUG_DIR = "debug_6th"

TIMESTAMP_SEC = 17 * 60 + 42            # 17:42
SAMPLE_OFFSETS_SEC = [-0.4, -0.2, 0.0, 0.2, 0.4]   # drums are stopped, so keep close

DIGITS = 4
GW, GH = 32, 48                         # normalized glyph size
MIN_SCORE = 0.80                        # best similarity below this -> review
MIN_MARGIN = 0.08                       # best minus second best below this -> review
DUP_SIM = 0.995                         # skip near-identical library samples

SHOW_UI = True
UI_WIN = "6th Prize - Extraction"
ROWS_PER_COLUMN = 6
PANEL_H = 260

COLORS = {
    "verified": (0, 220, 0),     # human confirmed
    "auto":     (0, 200, 120),   # confident, auto accepted
    "unsure":   (0, 165, 255),   # flagged, not reviewed
    "unknown":  (0, 0, 220),     # contains ?
}


# ============================================================
# HELPERS
# ============================================================
def put(img, text, org, scale=0.5, color=(230, 230, 230), thick=1):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


# ============================================================
# VIDEO
# ============================================================
def find_video():
    for pattern in ["Kerala Lottery*SAMRUDHI*.mp4", "*.mp4"]:
        files = glob.glob(pattern)
        if files:
            return files[0]
    raise FileNotFoundError("No video file found")


def load_rollers(json_path):
    if not os.path.exists(json_path):
        print(f"Roller config not found: {json_path} - generating defaults")
        rollers = []
        for row in range(2):
            for col in range(9):
                rollers.append({"x": 50 + col * 100, "y": 50 + row * 160,
                                "width": 80, "height": 120})
        with open(json_path, "w") as f:
            json.dump({"roller_groups": rollers}, f, indent=2)
        print("IMPORTANT: adjust coordinates for your video!\n")
        return rollers
    with open(json_path) as f:
        data = json.load(f)
    rollers = data.get("roller_groups") or data.get("rollers", [])
    if not rollers:
        raise ValueError("No rollers defined in config")
    return rollers


def load_frames(video_path, t0):
    cap = cv2.VideoCapture(video_path)
    frames = []
    for off in SAMPLE_OFFSETS_SEC:
        if t0 + off < 0:
            continue
        cap.set(cv2.CAP_PROP_POS_MSEC, (t0 + off) * 1000)
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    if not frames:
        raise SystemExit("Could not read any video frames")
    H, W = frames[0].shape[:2]
    print(f"Frames loaded: {len(frames)} | size {W}x{H}\n")
    return frames


def crop_roi(frame, roi):
    H, W = frame.shape[:2]
    x, y = int(roi["x"]), int(roi["y"])
    w, h = int(roi["width"]), int(roi["height"])
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return frame[y0:y1, x0:x1]


# ============================================================
# GLYPH EXTRACTION
# ============================================================
def get_slots(box):
    """Trim bezel, split into 4 equal digit slots."""
    H, W = box.shape[:2]
    inner = box[int(H * .15):int(H * .85), int(W * .08):int(W * .92)]
    sw = inner.shape[1] / DIGITS
    return [inner[:, int(i * sw):int((i + 1) * sw)] for i in range(DIGITS)]


def _normalize(patch):
    patch = cv2.resize(patch, (GW, GH), interpolation=cv2.INTER_AREA).astype(np.float32)
    patch -= patch.mean()
    n = np.linalg.norm(patch)
    return (patch / n).ravel() if n > 1e-6 else None


def glyph_vector(slot):
    """Tight-crop the dark digit, resize, zero-mean unit-norm vector."""
    if slot is None or slot.size == 0:
        return None
    g = cv2.cvtColor(slot, cv2.COLOR_BGR2GRAY)
    g = cv2.createCLAHE(2.0, (4, 4)).apply(g)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    _, ink = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = ink.shape
    n, _, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = []
    for i in range(1, n):
        x, y, bw, bh, a = st[i]
        if a < 12 or bw > 0.85 * w:               # specks / horizontal bezel bars
            continue
        if x <= 0 or x + bw >= w:                 # touches side = cell border
            continue
        if not (0.2 * w <= x + bw / 2 <= 0.8 * w):  # must be near slot centre
            continue
        keep.append((x, y, x + bw, y + bh))
    if keep:
        x0 = min(k[0] for k in keep); y0 = min(k[1] for k in keep)
        x1 = max(k[2] for k in keep); y1 = max(k[3] for k in keep)
        if (y1 - y0) >= 0.35 * h:
            m = 2
            return _normalize(g[max(0, y0 - m):min(h, y1 + m),
                                max(0, x0 - m):min(w, x1 + m)])
    # fallback: centre of slot (still usable for matching)
    return _normalize(g[int(h * .1):int(h * .9), int(w * .15):int(w * .85)])


# ============================================================
# LIBRARY (learns from human-confirmed digits)
# ============================================================
class Library:
    def __init__(self, path=LIB_FILE):
        self.path = path
        self.X = np.zeros((0, GW * GH), np.float32)
        self.y = np.zeros((0,), np.int8)
        if os.path.exists(path):
            z = np.load(path)
            self.X, self.y = z["X"].astype(np.float32), z["y"].astype(np.int8)

    def __len__(self):
        return len(self.y)

    def scores(self, v):
        """Best similarity per digit class 0-9."""
        out = np.full(10, -1.0)
        if len(self.y) == 0:
            return out
        sims = self.X @ v
        for d in range(10):
            m = self.y == d
            if m.any():
                out[d] = sims[m].max()
        return out

    def add(self, v, d):
        if len(self.y):
            m = self.y == d
            if m.any() and (self.X[m] @ v).max() > DUP_SIM:
                return False
        self.X = np.vstack([self.X, v[None]])
        self.y = np.append(self.y, np.int8(d))
        return True

    def save(self):
        np.savez(self.path, X=self.X, y=self.y)


# ============================================================
# READING
# ============================================================
def read_box(frames, roi, lib):
    per_slot = [{"vecs": [], "scores": []} for _ in range(DIGITS)]
    crop0 = None
    for f in frames:
        b = crop_roi(f, roi)
        if b is None or b.size == 0:
            continue
        if crop0 is None:
            crop0 = b.copy()
        for i, s in enumerate(get_slots(b)):
            v = glyph_vector(s)
            if v is not None:
                per_slot[i]["vecs"].append(v)
                per_slot[i]["scores"].append(lib.scores(v))

    digits, best_l, margin_l, flags = "", [], [], []
    for s in per_slot:
        if not s["scores"] or len(lib) == 0:
            digits += "?"; best_l.append(0.0); margin_l.append(0.0); flags.append(True)
            continue
        avg = np.mean(s["scores"], axis=0)
        order = np.argsort(avg)[::-1]
        best, second = avg[order[0]], avg[order[1]]
        agree = len({int(np.argmax(sc)) for sc in s["scores"]}) == 1
        digits += str(order[0])
        best_l.append(float(best)); margin_l.append(float(best - second))
        flags.append(best < MIN_SCORE or (best - second) < MIN_MARGIN or not agree)
    return {"number": digits, "best": best_l, "margin": margin_l,
            "flags": flags, "slots": per_slot, "crop": crop0}


def review_box(i, res):
    """Show box, let human confirm or type the 4 digits. Returns (number|None, human_confirmed)."""
    guess = res["number"]
    big = cv2.resize(res["crop"], None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
    typed = ""
    while True:
        h, w = big.shape[:2]
        canvas = np.full((h + 90, max(w, 620), 3), 30, np.uint8)
        canvas[90:, :w] = big
        flagged = "".join("!" if f else "." for f in res["flags"])
        put(canvas, f"R{i+1}   guess: {guess}   flags: {flagged}", (8, 24), 0.6, (255, 255, 255))
        put(canvas, f"typed: {typed:<4}", (8, 52), 0.6, (0, 255, 255))
        put(canvas, "type 4 digits + Enter to set | Enter alone = accept guess | Backspace | Esc = skip rest",
            (8, 78), 0.42, (0, 200, 255))
        cv2.imshow("review", canvas)
        k = cv2.waitKey(0) & 0xFF
        if 48 <= k <= 57 and len(typed) < DIGITS:
            typed += chr(k)
        elif k in (8, 127):
            typed = typed[:-1]
        elif k == 13:
            if len(typed) == DIGITS:
                return typed, True
            if not typed and "?" not in guess:
                return guess, True
        elif k == 27:
            return None, False


def learn(lib, res, number):
    added = 0
    for pos, ch in enumerate(number):
        for v in res["slots"][pos]["vecs"]:
            added += lib.add(v, int(ch))
    return added


# ============================================================
# DRAWING
# ============================================================
def draw_canvas(frame, rollers, results, cur, header):
    H, W = frame.shape[:2]
    canvas = np.full((H + PANEL_H, W, 3), 28, np.uint8)
    img = frame.copy()
    for i, roi in enumerate(rollers):
        if i >= len(results):
            continue
        r = results[i]
        color = COLORS[r["status"]]
        x, y, w, h = (int(roi[k]) for k in ("x", "y", "width", "height"))
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 3 if i == cur else 1)
        put(img, f"R{i+1} {r['number']}", (x, max(14, y - 6)), 0.5, color)
    canvas[:H, :W] = img
    put(canvas, header, (10, H + 24), 0.6, (255, 255, 255))
    col_w = W // 3
    for i, r in enumerate(results[:18]):
        x = 10 + (i // ROWS_PER_COLUMN) * col_w
        y = H + 60 + (i % ROWS_PER_COLUMN) * 32
        put(canvas, f"R{i+1:<2} {r['number']}  {r['status'].upper():<8} min={r['min_score']:.2f}",
            (x, y), 0.45, COLORS[r["status"]])
    return canvas


# ============================================================
# MAIN
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video")
    ap.add_argument("--t", type=float, default=TIMESTAMP_SEC)
    ap.add_argument("--review-all", action="store_true")
    ap.add_argument("--no-review", action="store_true")
    a = ap.parse_args()

    os.makedirs(DEBUG_DIR, exist_ok=True)
    video_path = a.video or find_video()
    print(f"Video: {Path(video_path).name} @ {a.t:.1f}s")
    rollers = load_rollers(ROLLER_FILE)
    frames = load_frames(video_path, a.t)
    lib = Library()
    print(f"Library: {len(lib)} glyphs"
          f"{'  (empty - you will type every number this run)' if len(lib) == 0 else ''}\n")

    base = frames[len(frames) // 2].copy()
    results, learned, stop = [], 0, a.no_review

    if SHOW_UI:
        cv2.namedWindow(UI_WIN, cv2.WINDOW_AUTOSIZE)

    for i, roi in enumerate(rollers):
        res = read_box(frames, roi, lib)
        needs = any(res["flags"]) or a.review_all
        number, status = res["number"], "auto"

        if needs and not stop and res["crop"] is not None:
            new, human = review_box(i, res)
            if new is None:
                stop = True
            elif human:
                number, status = new, "verified"
                learned += learn(lib, res, number)
        if status != "verified":
            if "?" in number:
                status = "unknown"
            elif any(res["flags"]):
                status = "unsure"

        min_score = min(res["best"]) if res["best"] else 0.0
        results.append({"number": number, "status": status, "min_score": min_score})
        print(f"R{i+1:<2} {number}  {status:<9} min_score={min_score:.2f}")

        if res["crop"] is not None:
            cv2.imwrite(f"{DEBUG_DIR}/roller_{i+1:02d}_box.png", res["crop"])
        if SHOW_UI:
            cv2.imshow(UI_WIN, draw_canvas(base, rollers, results, i, f"R{i+1}/{len(rollers)}"))
            cv2.waitKey(1)

    cv2.destroyWindow("review") if cv2.getWindowProperty("review", 0) >= 0 else None

    if learned:
        lib.save()
        print(f"\nLibrary updated: +{learned} glyphs (total {len(lib)})")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["box", "number", "status", "min_score"])
        w.writeheader()
        for i, r in enumerate(results, 1):
            w.writerow({"box": i, "number": r["number"], "status": r["status"],
                        "min_score": f"{r['min_score']:.2f}"})
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"video": Path(video_path).name, "timestamp_sec": a.t,
                   "boxes": [{"box": i + 1, **r} for i, r in enumerate(results)]}, f, indent=2)
    final = draw_canvas(base, rollers, results, -1, "6th Prize - Extraction Complete")
    cv2.imwrite(OUTPUT_IMAGE, final)

    counts = {s: sum(r["status"] == s for r in results) for s in COLORS}
    print(f"\nSaved {OUTPUT_CSV}, {OUTPUT_JSON}, {OUTPUT_IMAGE}")
    print("Summary:", counts)

    if SHOW_UI:
        cv2.imshow(UI_WIN, final)
        print("Press any key to exit...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
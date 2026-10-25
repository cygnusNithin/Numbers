import csv
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

from extract_numbers_from_rollers import (
    NumberExtractor, TESSERACT_CMD, TIMESTAMP_SEC, ROWS_PER_COLUMN, OUTPUT_CSV,
)

WIN = "Roller OCR - Live"
CANVAS_W, CANVAS_H = 1600, 900
FRAME_W, FRAME_H = 960, 540
HOLD_SEC = 1.5          # pause on each finished roller before moving on
FONT = cv2.FONT_HERSHEY_SIMPLEX

STATUS_COLORS = {       # BGR
    "pending":   (110, 110, 110),
    "reading":   (255, 200, 0),
    "match":     (0, 220, 0),
    "mismatch":  (0, 140, 255),
    "not_in_db": (255, 0, 255),
    "no_read":   (0, 0, 220),
}


# ---------------- helpers ----------------

def put(img, text, org, scale=0.5, color=(230, 230, 230), thick=1):
    cv2.putText(img, text, org, FONT, scale, color, thick, cv2.LINE_AA)


def fit(img, max_w, max_h):
    h, w = img.shape[:2]
    if w == 0 or h == 0:
        return img
    s = min(max_w / w, max_h / h)
    return cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))),
                      interpolation=cv2.INTER_CUBIC)


def fmt(t):
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


def build_variants(crop):
    """Much better preprocessing for mechanical roller digits."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Strong upscaling
    big = cv2.resize(gray, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)

    # Contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(big)

    variants = []

    # 1. Otsu
    _, otsu = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("otsu", otsu))

    # 2. Adaptive
    adap = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 41, 11)
    variants.append(("adap", adap))

    # 3. Simple high threshold
    _, simple = cv2.threshold(enhanced, 140, 255, cv2.THRESH_BINARY)
    variants.append(("simple", simple))

    # 4. Slightly lower threshold
    _, simple2 = cv2.threshold(enhanced, 120, 255, cv2.THRESH_BINARY)
    variants.append(("simple2", simple2))

    # Clean each variant with morphology
    cleaned_variants = []
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    for name, img in variants:
        # Remove small noise
        clean = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel)
        clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, kernel2)

        # Add good padding
        pad = cv2.copyMakeBorder(clean, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)

        cleaned_variants.append((name, pad))
        cleaned_variants.append((name + "_inv", cv2.bitwise_not(pad)))

    return cleaned_variants


def tesseract(img, psm):
    """Improved Tesseract call focused on digits."""
    tmp = tempfile.mkdtemp()
    try:
        in_path = os.path.join(tmp, "roi.png")
        out_base = os.path.join(tmp, "out")
        cv2.imwrite(in_path, img)

        cmd = [
            TESSERACT_CMD, in_path, out_base,
            "--psm", str(psm),
            "-c", "tessedit_char_whitelist=0123456789",
            "-c", "classify_bln_numeric_mode=1"
        ]

        t0 = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        ms = int((time.time() - t0) * 1000)

        text = ""
        if os.path.exists(out_base + ".txt"):
            with open(out_base + ".txt", "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()

        # Keep only digits
        text = re.sub(r"[^0-9]", "", text)

        return {
            "text": text,
            "rc": proc.returncode,
            "err": proc.stderr.strip()[:50],
            "ms": ms
        }
    except Exception as e:
        return {"text": "", "rc": -1, "err": str(e)[:50], "ms": 0}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- viewer ----------------

class LiveViewer:
    def __init__(self, video_path):
        self.video_path = video_path
        self.ex = NumberExtractor(video_path)
        if not self.ex.prize_numbers:
            raise SystemExit("No prize numbers loaded from DB, stopping")

        self.rollers = self.ex.roller_groups
        self.n = len(self.rollers)
        self.t = TIMESTAMP_SEC
        self.frame = self.load_frame(self.t)
        if self.frame is None:
            raise SystemExit("Could not load video frame")

        self.cur = 0
        self.auto = True
        self.delay = 300
        self.gen = None
        self.done = [False] * self.n
        self.done_time = 0.0
        self.views = [self.blank_view(i) for i in range(self.n)]
        self.canvas = None

    def blank_view(self, i):
        return {
            "status": "pending",
            "expected": self.ex.expected_tier_for_roller(i + 1),
            "crop": None, "img": None, "label": "", "text": "",
            "number": None, "detected": None, "log": [],
        }

    def load_frame(self, t):
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ret, frame = cap.read()
        cap.release()
        return frame if ret else None

    def reset(self, idx=None):
        if self.gen is not None:
            self.gen.close()
            self.gen = None
        targets = range(self.n) if idx is None else [idx]
        for i in targets:
            self.done[i] = False
            self.views[i] = self.blank_view(i)

    def goto(self, idx):
        if self.gen is not None:
            self.gen.close()
            self.gen = None
        self.cur = max(0, min(idx, self.n - 1))

    def scrub(self, seconds):
        t = max(0, self.t + seconds)
        f = self.load_frame(t)
        if f is None:
            print(f"✗ Could not load frame at {fmt(t)}")
            return
        self.t, self.frame = t, f
        self.reset()
        print(f"\n→ Frame moved to {fmt(t)}")

    def run_roller(self, idx):
        v = self.views[idx]
        roi = self.rollers[idx]
        x, y, w, h = roi["x"], roi["y"], roi["width"], roi["height"]
        crop = self.frame[y:y + h, x:x + w]

        v.update(status="reading", crop=crop, img=None, label="",
                 text="", number=None, detected=None, log=[])
        if crop.size == 0:
            v["status"] = "no_read"
            return

        best_num = None
        best_text = ""
        best_label = ""

        for vname, img in build_variants(crop):
            for psm in (7, 6, 8, 13):
                res = tesseract(img, psm)
                label = f"{vname} psm{psm}"
                v["img"], v["label"], v["text"] = img, label, res["text"]

                line = f"{label:<22} rc={res['rc']} {res['ms']:>4}ms '{res['text'][:12]}'"
                if res["rc"] != 0:
                    line += f" ERR:{res['err'][:20]}"
                v["log"] = (v["log"] + [line])[-18:]

                # Look for 4-digit numbers
                nums = re.findall(r"\d{4}", res["text"])
                for num in nums:
                    tiers = self.ex.find_tiers(num)
                    if tiers:
                        tier = tiers[0]
                        v.update(number=num, detected=tier,
                                 status="match" if tier == v["expected"] else "mismatch")
                        v["log"] = (v["log"] + [f"  → {num} = {tier}th Prize"])[-18:]
                        self.log_result(idx)
                        return

                    if best_num is None:
                        best_num = num
                        best_text = res["text"]
                        best_label = label

                yield

        if best_num:
            v["number"] = best_num
            v["text"] = best_text
            v["label"] = best_label
            v["status"] = "not_in_db"
        else:
            v["status"] = "no_read"

        self.log_result(idx)

    def log_result(self, idx):
        v = self.views[idx]
        num = v["number"] or "-"
        det = f"{v['detected']}th" if v["detected"] else "-"
        print(f"Roller #{idx + 1:2d}: read {num:<5} detected {det:<5} "
              f"expected {v['expected']}th  -> {v['status'].upper()}")

    def tick(self):
        if not self.done[self.cur]:
            if self.gen is None:
                self.gen = self.run_roller(self.cur)
            try:
                next(self.gen)
            except StopIteration:
                self.gen = None
                self.done[self.cur] = True
                self.done_time = time.time()
        elif self.auto and time.time() - self.done_time > HOLD_SEC:
            if self.cur < self.n - 1:
                self.goto(self.cur + 1)
            else:
                self.auto = False
                self.print_summary()

    def draw(self):
        c = np.full((CANVAS_H, CANVAS_W, 3), 28, np.uint8)
        v = self.views[self.cur]

        # Left: frame with all boxes
        s = FRAME_W / self.frame.shape[1]
        disp = cv2.resize(self.frame, (FRAME_W, FRAME_H))
        for i, roi in enumerate(self.rollers):
            x0 = int(roi["x"] * s)
            y0 = int(roi["y"] * s)
            x1 = int((roi["x"] + roi["width"]) * s)
            y1 = int((roi["y"] + roi["height"]) * s)
            color = STATUS_COLORS[self.views[i]["status"]]
            cv2.rectangle(disp, (x0, y0), (x1, y1), color, 3 if i == self.cur else 1)
            if i == self.cur:
                cv2.rectangle(disp, (x0 - 3, y0 - 3), (x1 + 3, y1 + 3), (0, 255, 255), 1)
            put(disp, f"R{i + 1}", (x0 + 2, max(12, y0 - 4)), 0.4, color, 1)
        c[0:FRAME_H, 0:FRAME_W] = disp

        # Status bar under frame
        put(c, f"Video {fmt(self.t)}   Roller {self.cur + 1}/{self.n}   "
               f"expected {v['expected']}th Prize   auto:{'ON' if self.auto else 'OFF'}   "
               f"step:{self.delay}ms", (10, 556), 0.5, (255, 255, 255), 1)
        det = f"{v['detected']}th" if v["detected"] else "-"
        put(c, f"Status: {v['status'].upper()}   OCR text: '{v['text']}'   "
               f"Number read: {v['number'] or '-'}   Detected: {det}",
            (10, 582), 0.5, STATUS_COLORS[v["status"]], 1)
        put(c, f"Attempt: {v['label'] or '-'}", (10, 606), 0.5, (200, 200, 200), 1)

        # Bottom-left: results grid
        for i in range(self.n):
            col = i // ROWS_PER_COLUMN
            row = i % ROWS_PER_COLUMN
            vv = self.views[i]
            x = 10 + col * 315
            y = 650 + row * 38
            color = STATUS_COLORS[vv["status"]]
            if i == self.cur:
                cv2.rectangle(c, (x - 4, y - 16), (x + 305, y + 10), (0, 255, 255), 1)
            text = (f"R{i + 1:<2} exp {vv['expected']}th  "
                    f"read {vv['number'] or '----'}  {vv['status']}")
            put(c, text, (x, y), 0.42, color, 1)

        # Right: source crop
        put(c, "Source crop (what is being read)", (980, 22), 0.5, (255, 255, 255), 1)
        if v["crop"] is not None and v["crop"].size:
            big = fit(v["crop"], 600, 200)
            c[30:30 + big.shape[0], 980:980 + big.shape[1]] = big

        # Right: preprocessed image
        put(c, "Preprocessed image (sent to Tesseract)", (980, 250), 0.5, (255, 255, 255), 1)
        if v["img"] is not None:
            pre = fit(v["img"], 600, 150)
            if pre.ndim == 2:
                pre = cv2.cvtColor(pre, cv2.COLOR_GRAY2BGR)
            c[266:266 + pre.shape[0], 980:980 + pre.shape[1]] = pre

        # Right: attempt log
        put(c, "Attempts (live)", (980, 440), 0.5, (255, 255, 255), 1)
        for k, line in enumerate(v["log"]):
            put(c, line[:95], (980, 462 + k * 19), 0.4, (200, 200, 200), 1)

        # Right: summary + keys
        counts = {k: sum(1 for x in self.views if x["status"] == k) for k in STATUS_COLORS}
        put(c, f"Matched {counts['match']}/{self.n}   mismatch {counts['mismatch']}   "
               f"not in DB {counts['not_in_db']}",
            (980, 834), 0.42, (255, 255, 255), 1)
        put(c, f"no read {counts['no_read']}   pending {counts['pending']}",
            (980, 852), 0.42, (255, 255, 255), 1)
        put(c, "SPACE auto  n/p next/prev  r retry  a run all  +/- speed",
            (980, 872), 0.38, (180, 180, 180), 1)
        put(c, ".  ,  = +1s / -1s frame   s snapshot   q quit",
            (980, 890), 0.38, (180, 180, 180), 1)

        self.canvas = c
        return c

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
            self.delay = min(2000, self.delay + 100)
        elif key == ord("-"):
            self.delay = max(50, self.delay - 100)
        elif key == ord("."):
            self.scrub(+1)
        elif key == ord(","):
            self.scrub(-1)
        elif key == ord("s"):
            os.makedirs("debug", exist_ok=True)
            path = f"debug/ui_roller_{self.cur + 1:02d}.png"
            cv2.imwrite(path, self.canvas)
            print(f"✓ Snapshot saved: {path}")
        return True

    def run(self):
        cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)
        print("Live viewer running. Keys: SPACE auto | n/p | r retry | a run all | "
              "+/- speed | ./, frame | s snapshot | q quit")
        while True:
            self.tick()
            cv2.imshow(WIN, self.draw())
            key = cv2.waitKey(self.delay) & 0xFF
            if not self.handle_key(key):
                break
        cv2.destroyAllWindows()

    def print_summary(self):
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)
        matched = sum(1 for v in self.views if v["status"] == "match")
        print(f"Matched: {matched}/{self.n}\n")
        print(f"{'R#':<4}{'Read':<7}{'Detected':<10}{'Expected':<10}{'Status'}")
        print("-" * 50)
        for i, v in enumerate(self.views, 1):
            det = f"{v['detected']}th" if v["detected"] else "-"
            print(f"{i:<4}{v['number'] or '-':<7}{det:<10}{v['expected']}th{'':<6}"
                  f"{v['status'].upper()}")

    def save_csv(self):
        fields = ["roller_id", "extracted_number", "detected_prize", "expected_prize",
                  "matched", "status", "raw_ocr"]
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for i, v in enumerate(self.views, 1):
                writer.writerow({
                    "roller_id": i,
                    "extracted_number": v["number"] or "",
                    "detected_prize": f"{v['detected']}th" if v["detected"] else "",
                    "expected_prize": f"{v['expected']}th",
                    "matched": v["status"] == "match",
                    "status": v["status"],
                    "raw_ocr": v["text"],
                })
        print(f"\n✓ Saved {OUTPUT_CSV}")

    def finish(self):
        self.save_csv()
        self.ex.close()


if __name__ == "__main__":
    videos = list(Path(".").glob("*.mp4"))
    if not videos:
        raise SystemExit("✗ No video files found")

    try:
        ver = subprocess.run([TESSERACT_CMD, "--version"], capture_output=True, text=True)
        print(f"Tesseract: {ver.stdout.splitlines()[0] if ver.stdout else ver.stderr.strip()}")
    except Exception as e:
        raise SystemExit(f"✗ Tesseract not runnable: {e}")

    viewer = LiveViewer(str(videos[0]))
    try:
        viewer.run()
    finally:
        viewer.finish()
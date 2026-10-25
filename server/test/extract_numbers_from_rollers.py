import cv2
import json
import os
import re
import csv
import shutil
import subprocess
import tempfile
from pathlib import Path

from pymongo import MongoClient

# ---------------- CONFIG ----------------
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
ROLLER_FILE = "roller_groups.json"
OUTPUT_CSV = "roller_analysis.csv"

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "absolute_data"

# Leave None to auto-read the serial from the video filename ("... SM-70 - ...").
# Set it manually if needed, e.g. "SM-70".
TARGET_SERIAL = None

TIMESTAMP_SEC = 17 * 60 + 42     # 17:42 where the rollers are marked
ROWS_PER_COLUMN = 6              # 6 prize rows per column (4th..9th)
PRIZE_TIERS = [4, 5, 6, 7, 8, 9]  # 4-digit prize tiers, largest amount = 4th
PRIZE_MAX_AMOUNT = 5000          # 4th prize amount; 1st-3rd are above this
# ----------------------------------------


def serial_from_filename(filename):
    """'Kerala Lottery ... - SM-70 - 30.08.2026.mp4' -> 'SM-70'"""
    m = re.search(r"\b([A-Za-z]{2,})[-\s]?(\d{1,4})\b", filename)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def date_from_filename(filename):
    """'... 30.08.2026.mp4' -> '30/08/2026'"""
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", filename)
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else None


class NumberExtractor:
    def __init__(self, video_path):
        self.video_path = video_path
        self.roller_groups = []
        self.prize_numbers = {}      # {4: {"1234", ...}, 5: {...}, ...}
        self.draw_info = {}
        self.results = []
        self.client = None
        self.db = None

        self.load_roller_groups()
        self.connect_mongodb()
        self.load_prizes_from_db()

    # ---------- Setup ----------

    def load_roller_groups(self):
        if not os.path.exists(ROLLER_FILE):
            print(f"✗ {ROLLER_FILE} not found")
            return False
        with open(ROLLER_FILE, "r") as f:
            self.roller_groups = json.load(f).get("roller_groups", [])
        print(f"✓ Loaded {len(self.roller_groups)} roller groups")
        return True

    def connect_mongodb(self):
        try:
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            self.db = self.client[DB_NAME]
            self.db.command("ping")
            print(f"✓ Connected to MongoDB: {MONGO_URI} / {DB_NAME}")
            return True
        except Exception as e:
            print(f"✗ MongoDB connection failed: {e}")
            self.db = None
            return False

    # ---------- Draw lookup ----------

    def find_draw(self, coll):
        """Find the draw by serialNumber (primary), then by date (secondary).
        Never falls back to an unrelated draw."""
        filename = Path(self.video_path).name
        serial = TARGET_SERIAL or serial_from_filename(filename)
        draw_date = date_from_filename(filename)

        print(f"  Video serial: {serial}")
        print(f"  Video date:   {draw_date}")

        if serial:
            m = re.match(r"([A-Za-z]+)[-\s]?(\d+)$", serial.strip())
            if m:
                # Tolerates "SM-70", "SM 70", "SM70", any case
                pattern = rf"^{m.group(1)}[-\s]?{m.group(2)}$"
                draw = coll.find_one(
                    {"serialNumber": {"$regex": pattern, "$options": "i"}}
                )
                if draw:
                    print("  Matched by serialNumber")
                    return draw

        if draw_date:
            draw = coll.find_one({"date": draw_date})
            if draw:
                print("  Matched by date")
                return draw

        return None

    # ---------- Prizes from DB ----------

    def load_prizes_from_db(self):
        if self.db is None:
            print("✗ Not connected to database")
            return False

        coll = self.db[COLLECTION]
        print(f"  Documents in {DB_NAME}.{COLLECTION}: {coll.count_documents({})}")

        draw = self.find_draw(coll)

        if draw is None:
            print("\n✗ No draw matched this video.")
            print("  Last 10 serialNumbers in the database:")
            for d in coll.find({}, {"serialNumber": 1, "date": 1, "fileName": 1}) \
                         .sort("recordNumber", -1).limit(10):
                print(f"    {d.get('serialNumber')!r:12}  {d.get('date')}  {d.get('fileName')}")
            return False

        self.draw_info = {
            "serialNumber": draw.get("serialNumber"),
            "date": draw.get("date"),
            "fileName": draw.get("fileName"),
        }

        print("\n" + "=" * 70)
        print("DRAW FROM DATABASE")
        print("=" * 70)
        print(f"  Serial:   {self.draw_info['serialNumber']}")
        print(f"  Date:     {self.draw_info['date']}")
        print(f"  FileName: {self.draw_info['fileName']}")

        series = draw.get("series", [])
        print("\n  All series entries:")
        for s in sorted(series, key=lambda s: -s.get("prize", 0)):
            nums = [n["number"] for n in s.get("numbers", [])]
            print(f"    amount={s.get('prize')}  count={len(nums)}  sample={nums[:5]}")

        small = sorted(
            [s for s in series if 0 < s.get("prize", 0) <= PRIZE_MAX_AMOUNT],
            key=lambda s: -s["prize"],
        )

        if len(small) != len(PRIZE_TIERS):
            print(f"\n⚠️  Found {len(small)} small-amount tiers, expected {len(PRIZE_TIERS)}."
                  " Check the list above.")

        for tier, s in zip(PRIZE_TIERS, small):
            self.prize_numbers[tier] = {n["number"] for n in s.get("numbers", [])}

        print("\n  Mapped prize tiers:")
        for tier in PRIZE_TIERS:
            nums = sorted(self.prize_numbers.get(tier, []))
            more = " ..." if len(nums) > 8 else ""
            print(f"    {tier}th Prize: {len(nums)} numbers  {nums[:8]}{more}")
        print()
        return True

    # ---------- Video / OCR ----------

    def load_frame(self):
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(TIMESTAMP_SEC * fps))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            print("✗ Could not load frame")
            return None
        print(f"✓ Frame loaded at {TIMESTAMP_SEC}s: {frame.shape[1]}x{frame.shape[0]}")
        return frame

    def preprocess_variants(self, crop_bgr):
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        scaled = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        _, otsu = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        padded = cv2.copyMakeBorder(otsu, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        return {"normal": padded, "inverted": cv2.bitwise_not(padded)}

    def run_tesseract(self, img, psm):
        if not os.path.exists(TESSERACT_CMD):
            print(f"✗ Tesseract not found at {TESSERACT_CMD}")
            return ""

        tmp_dir = tempfile.mkdtemp()
        try:
            img_path = os.path.join(tmp_dir, "roi.png")
            out_base = os.path.join(tmp_dir, "out")
            cv2.imwrite(img_path, img)

            cmd = [
                TESSERACT_CMD, img_path, out_base,
                "--psm", str(psm),
                "-c", "tessedit_char_whitelist=0123456789",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if res.returncode != 0:
                print(f"  ⚠️  tesseract error: {res.stderr.strip()[:200]}")

            txt_path = out_base + ".txt"
            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            return ""
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def ocr_roller(self, crop_bgr):
        """Try several preprocessing/PSM combos; return first text containing a 4-digit number."""
        best_text = ""
        for variant_name, img in self.preprocess_variants(crop_bgr).items():
            for psm in (7, 6):
                text = self.run_tesseract(img, psm)
                if re.search(r"\d{4}", text):
                    return text, variant_name, psm
                if text and not best_text:
                    best_text = text
        return best_text, None, None

    # ---------- Matching ----------

    def find_tiers(self, number):
        return [tier for tier, nums in self.prize_numbers.items() if number in nums]

    @staticmethod
    def expected_tier_for_roller(roller_index):
        """Roller 1..6 = column 1 top->bottom (4th..9th), 7..12 = column 2, etc."""
        return PRIZE_TIERS[(roller_index - 1) % ROWS_PER_COLUMN]

    # ---------- Main ----------

    def extract_all(self):
        frame = self.load_frame()
        if frame is None:
            return False

        print("\n" + "=" * 70)
        print("EXTRACTING NUMBERS FROM ROLLERS")
        print("=" * 70 + "\n")

        Path("debug").mkdir(exist_ok=True)

        for i, roi in enumerate(self.roller_groups, 1):
            x, y, w, h = roi["x"], roi["y"], roi["width"], roi["height"]
            expected = self.expected_tier_for_roller(i)
            print(f"🎲 Roller #{i:2d}  (expected {expected}th Prize)")

            crop = frame[y:y + h, x:x + w]
            if crop.size == 0:
                print("  ✗ ROI out of bounds\n")
                self._record(i, None, "", [], None, expected, error="out of bounds")
                continue

            cv2.imwrite(f"debug/roller_{i:02d}.png", crop)
            text, variant, psm = self.ocr_roller(crop)
            numbers = sorted(set(re.findall(r"\d{4}", text)))

            print(f"  OCR text: '{text}'  (variant={variant}, psm={psm})")
            if not numbers:
                print("  ✗ No 4-digit number read\n")
                self._record(i, None, text, [], None, expected)
                continue

            # Prefer a number that exists in the DB prizes
            matched_tier = None
            primary = numbers[0]
            for num in numbers:
                tiers = self.find_tiers(num)
                if tiers:
                    primary, matched_tier = num, tiers[0]
                    break

            ok = matched_tier == expected
            if matched_tier is None:
                print(f"  ✗ {primary} not in DB prizes")
            elif ok:
                print(f"  ✓ {primary} = {matched_tier}th Prize (expected)")
            else:
                print(f"  ✗ {primary} = {matched_tier}th Prize, expected {expected}th")
            print()

            self._record(i, primary, text, numbers, matched_tier, expected)

        return True

    def _record(self, roller_id, number, raw, all_numbers, detected, expected, error=""):
        self.results.append({
            "roller_id": roller_id,
            "extracted_number": number or "",
            "all_numbers_read": " ".join(all_numbers),
            "detected_prize": f"{detected}th" if detected else "",
            "expected_prize": f"{expected}th",
            "matched": bool(detected is not None and detected == expected),
            "raw_ocr": raw,
            "error": error,
        })

    def print_results(self):
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)
        matched = sum(1 for r in self.results if r["matched"])
        total = len(self.results)
        print(f"Matched: {matched}/{total}\n")
        print(f"{'R#':<4}{'Number':<8}{'Detected':<11}{'Expected':<11}{'Status'}")
        print("-" * 50)
        for r in self.results:
            status = "✓ MATCH" if r["matched"] else "✗ FAIL"
            print(f"{r['roller_id']:<4}{r['extracted_number'] or 'FAIL':<8}"
                  f"{r['detected_prize'] or '-':<11}{r['expected_prize']:<11}{status}")

    def save_csv(self):
        fields = ["roller_id", "extracted_number", "all_numbers_read", "detected_prize",
                  "expected_prize", "matched", "raw_ocr", "error"]
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.results)
        print(f"\n✓ Saved {OUTPUT_CSV}")

    def close(self):
        if self.client:
            self.client.close()


if __name__ == "__main__":
    videos = list(Path(".").glob("*.mp4"))
    if not videos:
        print("✗ No video files found")
        raise SystemExit(1)

    extractor = NumberExtractor(str(videos[0]))

    if not extractor.prize_numbers:
        print("✗ No prize numbers loaded from DB, stopping")
        extractor.close()
        raise SystemExit(1)

    if extractor.extract_all():
        extractor.print_results()
        extractor.save_csv()

    extractor.close()
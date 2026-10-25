import cv2
import json
from pathlib import Path
import numpy as np
import os
import sys
import subprocess
import tempfile
import re
from difflib import SequenceMatcher

try:
    import pytesseract
    PYTESSERACT_IMPORTED = True
except ImportError:
    PYTESSERACT_IMPORTED = False


class ROIFixerWithRectangle:
    """Fix ROI with smooth rectangle selection + robust OCR for prize labels"""

    def __init__(self, video_path: str = None, image_path: str = None,
                 roi_file: str = "prize_location.json"):
        self.video_path = video_path
        self.image_path = image_path
        self.roi_file = roi_file
        self.frame = None
        self.frame_original = None
        self.drawing = False
        self.start_point = None
        self.roi_fixed = None
        self.tesseract_cmd = None
        self.setup_tesseract()

    def setup_tesseract(self):
        """Setup Tesseract from Program Files (Windows)"""
        possible_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        found_path = None
        for path in possible_paths:
            if os.path.exists(path):
                found_path = path
                break

        if found_path:
            try:
                result = subprocess.run([found_path, '--version'],
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.tesseract_cmd = found_path
                    print(f"✓ Tesseract found and working: {found_path}")
                    print(f"  {result.stdout.split(chr(10))[0]}")
                    return
            except Exception as e:
                print(f"⚠️  Tesseract test error: {e}")
        else:
            print("⚠️  Tesseract not found in default locations")
            for p in possible_paths:
                print(f"    Checked: {p}")
            print("\n   Install from: https://github.com/UB-Mannheim/tesseract/wiki")
            print("   Use the Full installer and keep the default path\n")

    def ocr_via_subprocess(self, image, psm=7):
        """Run Tesseract via subprocess"""
        if not self.tesseract_cmd:
            return None, 0.0

        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_image = tmp.name
            with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
                tmp_output = tmp.name

            cv2.imwrite(tmp_image, image)

            cmd = [
                self.tesseract_cmd,
                tmp_image,
                tmp_output.replace('.txt', ''),
                '--psm', str(psm),
                '-c', 'tessedit_char_whitelist=0123456789thPRIZE ',
                '-c', 'tessedit_do_invert=0'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            output_file = tmp_output.replace('.txt', '') + '.txt'
            if os.path.exists(output_file):
                with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read().strip()
                for f in (tmp_image, output_file, tmp_output):
                    if os.path.exists(f):
                        try:
                            os.unlink(f)
                        except:
                            pass
                confidence = 90.0 if text else 0.0
                return text, confidence
            else:
                if os.path.exists(tmp_image):
                    os.unlink(tmp_image)
                return None, 0.0
        except Exception as e:
            print(f"⚠️  Subprocess OCR error: {e}")
            return None, 0.0

    def load_frame(self):
        """Load either a video frame (at 17:42) or a static image"""
        if self.image_path and os.path.exists(self.image_path):
            frame = cv2.imread(self.image_path)
            if frame is None:
                print("✗ Could not load image")
                return False
            self.frame_original = frame.copy()
            self.frame = cv2.resize(frame, (1280, 720))
            print(f"✓ Image loaded: {self.image_path}")
            print(f"  Original size: {frame.shape[1]}x{frame.shape[0]}")
            return True

        if not self.video_path:
            print("✗ No video or image provided")
            return False

        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        timestamp_sec = 17 * 60 + 42          # 17:42
        frame_num = int(timestamp_sec * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        cap.release()

        if ret:
            self.frame_original = frame.copy()
            self.frame = cv2.resize(frame, (1280, 720))
            print(f"✓ Frame loaded at 17:42")
            print(f"  Original size: {frame.shape[1]}x{frame.shape[0]}")
            return True
        else:
            print("✗ Could not load frame")
            return False

    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.start_point = (x, y)
            print(f"\n  ▼ Started selection at: ({x}, {y})")
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            frame_copy = self.frame.copy()
            cv2.rectangle(frame_copy, self.start_point, (x, y), (0, 255, 0), 2)
            cv2.line(frame_copy, (x, 0), (x, frame_copy.shape[0]), (0, 255, 0), 1)
            cv2.line(frame_copy, (0, y), (frame_copy.shape[1], y), (0, 255, 0), 1)
            w = abs(x - self.start_point[0])
            h = abs(y - self.start_point[1])
            cv2.putText(frame_copy, f"W: {w} H: {h}",
                        (self.start_point[0] + 10, self.start_point[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imshow('Mark Prize Area', frame_copy)
        elif event == cv2.EVENT_LBUTTONUP and self.drawing:
            self.drawing = False
            end_point = (x, y)
            roi_x = min(self.start_point[0], end_point[0])
            roi_y = min(self.start_point[1], end_point[1])
            roi_w = abs(end_point[0] - self.start_point[0])
            roi_h = abs(end_point[1] - self.start_point[1])
            print(f"  ▲ Ended selection at: ({x}, {y})")
            print(f"\n  ✓ Rectangle (Display 1280x720): X={roi_x} Y={roi_y} W={roi_w} H={roi_h}")

            oh, ow = self.frame_original.shape[:2]
            dh, dw = self.frame.shape[:2]
            scale_x = ow / dw
            scale_y = oh / dh
            self.roi_fixed = (
                int(roi_x * scale_x),
                int(roi_y * scale_y),
                int(roi_w * scale_x),
                int(roi_h * scale_y)
            )
            print(f"  ✓ Rectangle (Original {ow}x{oh}): "
                  f"X={self.roi_fixed[0]} Y={self.roi_fixed[1]} "
                  f"W={self.roi_fixed[2]} H={self.roi_fixed[3]}")

            frame_copy = self.frame.copy()
            cv2.rectangle(frame_copy, self.start_point, end_point, (0, 255, 0), 3)
            cv2.putText(frame_copy, "Press 'q' to finish / 'c' to clear",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow('Mark Prize Area', frame_copy)

    def mark_roi(self):
        if not self.load_frame():
            return None
        print("\n" + "=" * 70)
        print("MARK PRIZE AREA – RECTANGLE SELECTION")
        print("=" * 70)
        print("1. Click-drag a tight rectangle around the prize text")
        print("2. Release mouse → press 'q' to accept, 'c' to clear\n")
        cv2.imshow('Mark Prize Area', self.frame)
        cv2.setMouseCallback('Mark Prize Area', self.mouse_callback)
        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('c'):
                self.drawing = False
                self.start_point = None
                self.roi_fixed = None
                cv2.imshow('Mark Prize Area', self.frame)
        cv2.destroyAllWindows()
        return self.roi_fixed

    def recognize_text_in_roi(self, roi: tuple):
        """Robust OCR for 'Nth PRIZE' labels – tries multiple pipelines"""
        if roi is None:
            return None

        if not self.tesseract_cmd or not os.path.exists(self.tesseract_cmd):
            return {
                'raw_text': '[Tesseract Not Available]',
                'cleaned_text': None,
                'confidence': 0,
                'detected_prize': None,
                'match_confidence': 0,
                'is_valid': False,
                'expected_prizes': ["4th Prize", "5th Prize", "6th Prize",
                                    "7th Prize", "8th Prize", "9th Prize"]
            }

        x, y, w, h = roi
        # Small padding helps capture full text
        pad = 8
        y1 = max(0, y - pad)
        x1 = max(0, x - pad)
        y2 = min(self.frame_original.shape[0], y + h + pad)
        x2 = min(self.frame_original.shape[1], x + w + pad)
        cropped = self.frame_original[y1:y2, x1:x2]

        if cropped.size == 0:
            print("✗ Cropped area is empty")
            return None

        recognition_result = {
            'raw_text': None,
            'cleaned_text': None,
            'confidence': 0.0,
            'detected_prize': None,
            'match_confidence': 0.0,
            'is_valid': False,
            'expected_prizes': ["4th Prize", "5th Prize", "6th Prize",
                                "7th Prize", "8th Prize", "9th Prize"]
        }

        def preprocess_variants(img):
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Upscale – Tesseract prefers larger text
            gray = cv2.resize(gray, None, fx=3.5, fy=3.5, interpolation=cv2.INTER_CUBIC)

            variants = []

            # 1. CLAHE + adaptive
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            th1 = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 31, 7)
            variants.append(("clahe_adapt", th1))

            # 2. Otsu
            _, th2 = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(("otsu", th2))

            # 3. Simple high threshold (good for bright text)
            _, th3 = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            variants.append(("simple150", th3))

            # 4. Slightly lower threshold
            _, th4 = cv2.threshold(gray, 130, 255, cv2.THRESH_BINARY)
            variants.append(("simple130", th4))

            # 5. Inverted versions
            variants.append(("clahe_adapt_inv", 255 - th1))
            variants.append(("otsu_inv", 255 - th2))
            variants.append(("simple150_inv", 255 - th3))

            return variants

        best_text = ""
        best_conf = 0.0
        best_name = ""

        variants = preprocess_variants(cropped)
        psms = [7, 6, 8, 13]   # single line, block, word, raw line

        print("  Trying multiple preprocessing + PSM combinations...")

        for name, img in variants:
            # Save debug images (optional – comment out if not needed)
            cv2.imwrite(f"debug_{name}.png", img)

            for psm in psms:
                text, conf = self.ocr_via_subprocess(img, psm=psm)
                if text:
                    # Prefer longer / more complete results
                    score = len(text) + (10 if any(c.isdigit() for c in text) else 0)
                    current_score = len(best_text) + (10 if any(c.isdigit() for c in best_text) else 0)
                    if score > current_score:
                        best_text = text
                        best_conf = conf
                        best_name = f"{name}_psm{psm}"
                        print(f"    → {name} PSM {psm}: '{text}'")

        if not best_text:
            print("  ✗ OCR returned no usable text")
            return recognition_result

        print(f"  Best result ({best_name}): '{best_text}'  conf≈{best_conf:.1f}%")

        recognition_result['raw_text'] = best_text.strip()
        recognition_result['confidence'] = float(best_conf)

        # Clean text
        cleaned = best_text.upper().strip()
        cleaned = ''.join(c for c in cleaned if c.isalnum() or c.isspace())
        cleaned = ' '.join(cleaned.split())
        recognition_result['cleaned_text'] = cleaned
        print(f"  Cleaned: '{cleaned}'")

        # ---------- Smart matching (handles common OCR mistakes) ----------
        cleaned_upper = cleaned.upper().replace(" ", "")

        # 1. Look for clear ordinal: 4TH, 5TH, 6TH ...
        match = re.search(r'([4-9])TH', cleaned_upper)
        if match:
            num = match.group(1)
            prize = f"{num}th Prize"
            recognition_result['detected_prize'] = prize
            recognition_result['match_confidence'] = float(best_conf)
            recognition_result['is_valid'] = best_conf > 40
            print(f"  ✓ Matched via ordinal: {prize}")

        # 2. Handle common misreads: "16 PRIZE", "6 PRIZE", "61 PRIZE", etc.
        elif re.search(r'1?6', cleaned_upper) and "PRIZE" in cleaned_upper:
            recognition_result['detected_prize'] = "6th Prize"
            recognition_result['match_confidence'] = float(best_conf)
            recognition_result['is_valid'] = best_conf > 40
            print(f"  ✓ Matched via '6' + PRIZE pattern: 6th Prize")

        # 3. Generic fallback
        else:
            for prize in recognition_result['expected_prizes']:
                prize_u = prize.upper().replace(" ", "")
                if (prize_u in cleaned_upper or
                        SequenceMatcher(None, cleaned_upper, prize_u).ratio() > 0.65):
                    recognition_result['detected_prize'] = prize
                    recognition_result['match_confidence'] = float(best_conf)
                    recognition_result['is_valid'] = best_conf > 40
                    print(f"  ✓ Matched: {prize}")
                    break

        if not recognition_result['detected_prize']:
            print("  ✗ No prize match found")

        return recognition_result

    def analyze_roi(self, roi: tuple):
        if roi is None:
            return None
        x, y, w, h = roi
        cropped = self.frame_original[y:y+h, x:x+w]
        if cropped.size == 0:
            return None
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        edge_density = (edges > 0).sum() / edges.size * 100
        contrast = gray.std()
        hsv = cv2.cvtColor(cropped, cv2.COLOR_BGR2HSV)
        brightness = int(hsv.mean(axis=0).mean(axis=0)[2])
        analysis = {
            'location': f"({x}, {y})",
            'size': f"{w}x{h}",
            'area_pixels': w * h,
            'position_h': self._get_h_pos(x),
            'position_v': self._get_v_pos(y),
            'brightness': brightness,
            'contrast': int(contrast),
            'edge_density': round(edge_density, 1),
            'has_detail': bool(contrast > 30),
            'suitable_for_text': bool(contrast > 30 and brightness > 50)
        }
        return analysis, cropped

    def _get_h_pos(self, x):
        w = self.frame_original.shape[1]
        r = x / w
        return "Left" if r < 0.33 else "Center" if r < 0.66 else "Right"

    def _get_v_pos(self, y):
        h = self.frame_original.shape[0]
        r = y / h
        return "Top" if r < 0.33 else "Middle" if r < 0.66 else "Bottom"

    def print_analysis(self, analysis):
        print("\n" + "=" * 70)
        print("ROI ANALYSIS RESULTS")
        print("=" * 70)
        print(f"\n📍 Location & Size:")
        print(f"   Position: {analysis['position_h']} - {analysis['position_v']}")
        print(f"   Coordinates: {analysis['location']}")
        print(f"   Dimensions: {analysis['size']} pixels")
        print(f"   Total Area: {analysis['area_pixels']:,} pixels")
        print(f"\n🎨 Visual Properties:")
        print(f"   Brightness: {analysis['brightness']}/255")
        print(f"   Contrast: {analysis['contrast']}")
        print(f"   Edge Density: {analysis['edge_density']}%")
        print(f"   Contains Detail: {'✓ YES' if analysis['has_detail'] else '✗ NO'}")
        print(f"\n✅ Suitability for Prize Detection:")
        if analysis['suitable_for_text']:
            print("   ✓ GOOD – Area is suitable for text/prize detection")
        else:
            print("   ⚠ FAIR – Area may not be ideal")
        print("=" * 70)

    def print_recognition(self, recognition):
        if not recognition:
            print("\n⚠️  No recognition data")
            return
        print("\n" + "=" * 70)
        print("TEXT RECOGNITION RESULTS")
        print("=" * 70)
        print(f"\n📖 Raw OCR Output: '{recognition['raw_text']}'")
        print(f"   Confidence: {recognition['confidence']:.1f}%")
        print(f"\n🔍 Cleaned Text: '{recognition['cleaned_text']}'")
        print(f"\n🎯 Prize Detection:")
        if recognition['detected_prize']:
            print(f"   ✓ Detected: {recognition['detected_prize']}")
            print(f"   Confidence: {recognition['match_confidence']:.1f}%")
            print(f"   Valid: {'✓ YES' if recognition['is_valid'] else '✗ NO'}")
        else:
            print("   ✗ No prize category detected")
            print(f"   Expected: {', '.join(recognition['expected_prizes'])}")
        print("=" * 70)

    def preview_roi(self, roi: tuple):
        if roi is None:
            return
        x, y, w, h = roi
        cropped = self.frame_original[y:y+h, x:x+w]
        if cropped.size == 0:
            return
        frame_with_rect = self.frame_original.copy()
        cv2.rectangle(frame_with_rect, (x, y), (x+w, y+h), (0, 255, 0), 3)
        display_frame = cv2.resize(frame_with_rect, (1280, 720))
        cv2.imshow('Full Frame with Selection', display_frame)
        cv2.waitKey(0)
        display_cropped = cv2.resize(cropped, (800, 300))
        cv2.imshow('Selected Area Close-up', display_cropped)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def save_roi(self, roi: tuple, analysis: dict = None, recognition: dict = None):
        """Save ROI to JSON – fully JSON-safe"""
        if roi is None:
            print("✗ No ROI to save")
            return False

        def make_json_safe(obj):
            if isinstance(obj, (np.integer, np.int_, np.intc, np.intp,
                                np.int8, np.int16, np.int32, np.int64)):
                return int(obj)
            if isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
                return float(obj)
            if isinstance(obj, (np.bool_, bool)):
                return bool(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, dict):
                return {k: make_json_safe(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [make_json_safe(v) for v in obj]
            return obj

        try:
            data = {
                'roi': {
                    'x': int(roi[0]),
                    'y': int(roi[1]),
                    'width': int(roi[2]),
                    'height': int(roi[3])
                },
                'timestamp': '00:17:42',
                'description': 'Prize category display area',
                'video': str(self.video_path) if self.video_path else None,
                'image': str(self.image_path) if self.image_path else None
            }

            if analysis:
                data['analysis'] = make_json_safe(analysis)

            if recognition:
                data['recognition'] = make_json_safe({
                    'raw_text': recognition.get('raw_text'),
                    'cleaned_text': recognition.get('cleaned_text'),
                    'confidence': recognition.get('confidence', 0),
                    'detected_prize': recognition.get('detected_prize'),
                    'match_confidence': recognition.get('match_confidence', 0),
                    'is_valid': recognition.get('is_valid', False),
                    'expected_prizes': recognition.get('expected_prizes', [])
                })

            with open(self.roi_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"\n✓ ROI saved successfully: {self.roi_file}")
            print(f"  X: {roi[0]}, Y: {roi[1]}, W: {roi[2]}, H: {roi[3]}")
            if recognition and recognition.get('detected_prize'):
                print(f"  Detected Prize: {recognition['detected_prize']}")
            return True

        except Exception as e:
            print(f"✗ Save failed: {e}")
            import traceback
            traceback.print_exc()
            return False


# -------------------- main --------------------
if __name__ == "__main__":
    # Prefer image if present, otherwise video
    image_path = "image.png"          # change if needed
    video_files = list(Path('.').glob('*.mp4'))
    video_path = str(video_files[0]) if video_files else None

    print("\n" + "=" * 70)
    print("PRIZE AREA MARKER – WITH IMPROVED OCR")
    print("=" * 70)

    if Path(image_path).exists():
        marker = ROIFixerWithRectangle(image_path=image_path)
        print(f"Using static image: {image_path}")
    elif video_path:
        marker = ROIFixerWithRectangle(video_path=video_path)
        print(f"Using video: {Path(video_path).name}")
    else:
        print("✗ No image or video found")
        sys.exit(1)

    print("\n[1/5] Marking prize area...")
    roi = marker.mark_roi()
    if not roi:
        print("✗ No area marked")
        sys.exit(1)

    print("\n[2/5] Preview...")
    marker.preview_roi(roi)

    print("\n[3/5] Analyzing...")
    result = marker.analyze_roi(roi)
    analysis = result[0] if result else None
    if analysis:
        marker.print_analysis(analysis)

    print("\n[4/5] Recognizing text...")
    recognition = marker.recognize_text_in_roi(roi)
    if recognition:
        marker.print_recognition(recognition)

    print("\n[5/5] Saving...")
    marker.save_roi(roi, analysis, recognition)

    print("\n" + "=" * 70)
    print("✓ COMPLETE")
    print("=" * 70)
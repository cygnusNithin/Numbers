import json
from pathlib import Path
import numpy as np
import os
import sys
import re
from difflib import SequenceMatcher
import cv2
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

try:
    import easyocr
    EASYOCR_IMPORTED = True
except ImportError:
    EASYOCR_IMPORTED = False
    print("⚠️  EasyOCR not installed. Install with: pip install easyocr")


class ROIExtractorGUI:
    """Extract ROI with improved GUI + EasyOCR"""

    def __init__(self, video_path: str = None, image_path: str = None,
                 roi_file: str = "prize_location.json"):
        self.video_path = video_path
        self.image_path = image_path
        self.roi_file = roi_file
        self.frame = None
        self.frame_original = None
        self.frame_rgb = None
        self.photo = None
        self.drawing = False
        self.start_point = None
        self.current_point = None
        self.roi_fixed = None
        self.reader = None
        
        self.root = None
        self.canvas = None
        self.rect_id = None
        
        self.setup_easyocr()

    def setup_easyocr(self):
        """Setup EasyOCR reader"""
        if not EASYOCR_IMPORTED:
            print("✗ EasyOCR not available")
            return False
        
        try:
            print("⏳ Loading EasyOCR (this may take a moment on first run)...")
            self.reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            print("✓ EasyOCR loaded successfully\n")
            return True
        except Exception as e:
            print(f"✗ EasyOCR setup error: {e}")
            return False

    def ocr_via_easyocr(self, image):
        """Run EasyOCR on image"""
        if self.reader is None:
            return "", 0.0

        try:
            results = self.reader.readtext(image, detail=1)
            
            if not results:
                return "", 0.0
            
            all_text = ""
            confidences = []
            
            for (bbox, text, confidence) in results:
                all_text += text + " "
                confidences.append(confidence)
            
            avg_confidence = (sum(confidences) / len(confidences) * 100) if confidences else 0.0
            
            return all_text.strip(), avg_confidence
        
        except Exception as e:
            print(f"⚠️  EasyOCR error: {e}")
            return "", 0.0

    def load_frame(self):
        """Load video frame or image"""
        if self.image_path and os.path.exists(self.image_path):
            frame = cv2.imread(self.image_path)
            if frame is None:
                print("✗ Could not load image")
                return False
            self.frame_original = frame.copy()
            print(f"✓ Image loaded: {self.image_path}")
            print(f"  Original size: {frame.shape[1]}x{frame.shape[0]}\n")
            return True

        if not self.video_path:
            print("✗ No video or image provided")
            return False

        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        timestamp_sec = 17 * 60 + 42  # 17:42
        frame_num = int(timestamp_sec * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        cap.release()

        if ret:
            self.frame_original = frame.copy()
            print(f"✓ Frame loaded at 17:42")
            print(f"  Original size: {frame.shape[1]}x{frame.shape[0]}\n")
            return True
        else:
            print("✗ Could not load frame")
            return False

    def setup_gui(self):
        """Setup Tkinter GUI with better layout"""
        if not self.load_frame():
            return False
        
        self.root = tk.Tk()
        self.root.title("Prize Area Marker - Draw Rectangle")
        self.root.geometry("1600x900")
        self.root.resizable(True, True)
        
        # Resize frame for display (keep aspect ratio)
        h, w = self.frame_original.shape[:2]
        max_w, max_h = 1000, 800
        scale = min(max_w / w, max_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        self.frame = cv2.resize(self.frame_original, (new_w, new_h))
        
        # Convert BGR to RGB for Tkinter
        self.frame_rgb = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(self.frame_rgb)
        self.photo = ImageTk.PhotoImage(img)
        
        # Main container
        main_frame = tk.Frame(self.root, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left side: Canvas
        left_frame = tk.Frame(main_frame, bg="lightgray")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        title_label = tk.Label(
            left_frame,
            text="MARK PRIZE AREA",
            font=("Arial", 14, "bold"),
            bg="lightgray"
        )
        title_label.pack(anchor=tk.NW, padx=5, pady=5)
        
        # Canvas for drawing
        self.canvas = tk.Canvas(left_frame, width=new_w, height=new_h, bg="gray", cursor="crosshair")
        self.canvas.pack(side=tk.TOP, padx=5, pady=5)
        self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
        
        # Mouse events
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        
        # Right side: Control panel
        right_frame = tk.Frame(main_frame, bg="white", width=350)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=15, pady=15)
        right_frame.pack_propagate(False)
        
        # Title
        title_right = tk.Label(
            right_frame,
            text="PRIZE MARKER",
            font=("Arial", 13, "bold"),
            bg="white",
            fg="darkblue"
        )
        title_right.pack(anchor=tk.NW, pady=(10, 15))
        
        # Instructions
        instructions_label = tk.Label(
            right_frame,
            text="HOW TO USE:",
            font=("Arial", 11, "bold"),
            bg="white",
            fg="darkblue"
        )
        instructions_label.pack(anchor=tk.NW, pady=(0, 5))
        
        instructions = tk.Label(
            right_frame,
            text=(
                "1. Click and drag to draw\n"
                "   rectangle around text\n\n"
                "2. Release mouse\n\n"
                "3. Click 'CONFIRM' button\n\n"
                "TIPS:\n"
                "• Tight rectangle works best\n"
                "• Avoid red/dark lines\n"
                "• Include all text clearly\n"
                "• Min size: 20x20 pixels"
            ),
            font=("Arial", 9),
            bg="lightyellow",
            fg="black",
            justify=tk.LEFT,
            wraplength=300,
            padx=10,
            pady=10,
            relief=tk.GROOVE,
            bd=2
        )
        instructions.pack(anchor=tk.NW, fill=tk.BOTH, expand=False, pady=(0, 10))
        
        # Status display
        status_frame = tk.LabelFrame(
            right_frame,
            text="STATUS",
            font=("Arial", 10, "bold"),
            bg="white",
            fg="darkblue",
            padx=10,
            pady=10
        )
        status_frame.pack(anchor=tk.NW, fill=tk.X, pady=(0, 10))
        
        self.status_label = tk.Label(
            status_frame,
            text="Ready: Draw rectangle",
            font=("Arial", 10, "bold"),
            bg="lightyellow",
            fg="darkgreen",
            wraplength=300,
            justify=tk.LEFT,
            padx=10,
            pady=10,
            relief=tk.SUNKEN,
            bd=2
        )
        self.status_label.pack(fill=tk.BOTH, expand=True)
        
        # ROI info display
        info_frame = tk.LabelFrame(
            right_frame,
            text="ROI COORDINATES",
            font=("Arial", 10, "bold"),
            bg="white",
            fg="darkblue",
            padx=10,
            pady=10
        )
        info_frame.pack(anchor=tk.NW, fill=tk.X, pady=(0, 10))
        
        # Use Courier instead of monospace
        self.info_label = tk.Label(
            info_frame,
            text="No selection yet",
            font=("Courier", 9),
            bg="lightcyan",
            fg="darkblue",
            wraplength=300,
            justify=tk.LEFT,
            padx=10,
            pady=10,
            relief=tk.SUNKEN,
            bd=2
        )
        self.info_label.pack(fill=tk.BOTH, expand=True)
        
        # Buttons frame
        button_frame = tk.Frame(right_frame, bg="white")
        button_frame.pack(anchor=tk.NW, fill=tk.X, pady=(0, 10))
        
        confirm_btn = tk.Button(
            button_frame,
            text="✓ CONFIRM",
            command=self.on_confirm,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 11, "bold"),
            padx=20,
            pady=12,
            relief=tk.RAISED,
            bd=2,
            activebackground="#45a049",
            cursor="hand2"
        )
        confirm_btn.pack(fill=tk.X, pady=5)
        
        clear_btn = tk.Button(
            button_frame,
            text="⟳ CLEAR",
            command=self.on_clear,
            bg="#FF9800",
            fg="white",
            font=("Arial", 11, "bold"),
            padx=20,
            pady=12,
            relief=tk.RAISED,
            bd=2,
            activebackground="#e68900",
            cursor="hand2"
        )
        clear_btn.pack(fill=tk.X, pady=5)
        
        cancel_btn = tk.Button(
            button_frame,
            text="✕ CANCEL",
            command=self.on_cancel,
            bg="#f44336",
            fg="white",
            font=("Arial", 11, "bold"),
            padx=20,
            pady=12,
            relief=tk.RAISED,
            bd=2,
            activebackground="#da190b",
            cursor="hand2"
        )
        cancel_btn.pack(fill=tk.X, pady=5)
        
        return True

    def on_mouse_down(self, event):
        """Mouse button pressed"""
        self.drawing = True
        self.start_point = (event.x, event.y)
        self.current_point = (event.x, event.y)
        print(f"  ▼ Started selection at: ({event.x}, {event.y})")
        self.status_label.config(text="Drawing...", bg="lightblue", fg="darkblue")

    def on_mouse_move(self, event):
        """Mouse move while button held"""
        if not self.drawing or self.start_point is None:
            return
        
        self.current_point = (event.x, event.y)
        self.redraw_canvas()
        
        x1, y1 = self.start_point
        x2, y2 = event.x, event.y
        
        # Draw rectangle
        self.rect_id = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="lime",
            width=3
        )
        
        # Draw dimensions text with background
        w = abs(x2 - x1)
        h = abs(y2 - y1)
        text = f"W: {w}px  H: {h}px"
        
        # Background for text
        self.canvas.create_rectangle(
            x1 + 5, y1 - 25, x1 + 150, y1 - 5,
            fill="black",
            outline="lime",
            width=2
        )
        
        self.canvas.create_text(
            x1 + 10, y1 - 15,
            text=text,
            fill="lime",
            font=("Arial", 10, "bold"),
            anchor=tk.W
        )

    def on_mouse_up(self, event):
        """Mouse button released"""
        if not self.drawing:
            return
        
        self.drawing = False
        end_point = (event.x, event.y)
        print(f"  ▲ Ended selection at: ({event.x}, {event.y})")
        
        # Calculate ROI in display coordinates
        roi_x = min(self.start_point[0], end_point[0])
        roi_y = min(self.start_point[1], end_point[1])
        roi_w = abs(end_point[0] - self.start_point[0])
        roi_h = abs(end_point[1] - self.start_point[1])
        
        if roi_w < 20 or roi_h < 20:
            messagebox.showwarning("Too Small", "Rectangle too small (min 20x20). Try again.")
            self.status_label.config(text="Rectangle too small!", bg="lightcoral", fg="darkred")
            return
        
        print(f"  ✓ Rectangle (Display): X={roi_x} Y={roi_y} W={roi_w} H={roi_h}")
        
        # Convert to original coordinates
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
              f"W={self.roi_fixed[2]} H={self.roi_fixed[3]}\n")
        
        # Update info display
        info_text = (
            f"DISPLAY:\n"
            f"X={roi_x}  Y={roi_y}\n"
            f"W={roi_w}  H={roi_h}\n\n"
            f"ORIGINAL:\n"
            f"X={self.roi_fixed[0]}\n"
            f"Y={self.roi_fixed[1]}\n"
            f"W={self.roi_fixed[2]}\n"
            f"H={self.roi_fixed[3]}"
        )
        self.info_label.config(text=info_text)
        
        self.status_label.config(
            text="✓ ROI Selected\nClick 'CONFIRM'",
            bg="lightgreen",
            fg="darkgreen"
        )

    def redraw_canvas(self):
        """Redraw canvas with current image"""
        img = Image.fromarray(self.frame_rgb)
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)

    def on_clear(self):
        """Clear the selection"""
        self.drawing = False
        self.start_point = None
        self.current_point = None
        self.roi_fixed = None
        self.rect_id = None
        self.redraw_canvas()
        self.status_label.config(text="Cleared - Draw again", bg="lightyellow", fg="darkblue")
        self.info_label.config(text="No selection yet")
        print("  ✕ Selection cleared\n")

    def on_confirm(self):
        """Confirm and proceed"""
        if self.roi_fixed is None:
            messagebox.showwarning("No Selection", "Please draw a rectangle first")
            return
        
        print("  ✓ Selection confirmed")
        self.root.quit()

    def on_cancel(self):
        """Cancel and exit"""
        print("  ✗ Cancelled by user")
        self.roi_fixed = None
        self.root.quit()

    def run_gui(self):
        """Run the GUI"""
        if not self.setup_gui():
            return None
        
        print("=" * 70)
        print("MARK PRIZE AREA – DRAW RECTANGLE")
        print("=" * 70)
        print("Click-drag to draw rectangle around prize text\n")
        
        self.root.mainloop()
        
        if self.roi_fixed:
            return self.roi_fixed
        return None

    def recognize_text_in_roi(self, roi: tuple):
        """Robust OCR with improved cleaning"""
        if roi is None:
            return None

        if self.reader is None:
            return {
                'raw_text': '[EasyOCR Not Available]',
                'cleaned_text': None,
                'confidence': 0,
                'detected_prize': None,
                'match_confidence': 0,
                'is_valid': False,
                'expected_prizes': ["4th Prize", "5th Prize", "6th Prize",
                                    "7th Prize", "8th Prize", "9th Prize"]
            }

        x, y, w, h = roi
        pad = 4  # Minimal padding to avoid red lines
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
            """Optimized preprocessing for prize labels"""
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)

            variants = []

            # 1. CLAHE for contrast
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            
            # 2. Threshold variants
            _, th_binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(("otsu_binary", th_binary))
            
            _, th_binary_inv = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            variants.append(("otsu_inv", 255 - th_binary_inv))
            
            # 3. Adaptive threshold
            th_adaptive = cv2.adaptiveThreshold(
                enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 21, 5
            )
            variants.append(("adaptive", th_adaptive))
            
            # 4. Morphological cleanup
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            th_morph = cv2.morphologyEx(th_binary, cv2.MORPH_CLOSE, kernel)
            variants.append(("morph_close", th_morph))

            return variants

        best_text = ""
        best_conf = 0.0
        best_name = ""

        variants = preprocess_variants(cropped)

        print("=" * 70)
        print("OCR PROCESSING - PRIZE LABEL")
        print("=" * 70)
        print("Testing preprocessing variants...\n")

        for name, img in variants:
            text, conf = self.ocr_via_easyocr(img)
            
            if text:
                # Score: prefer text with "PRIZE" and digits
                has_prize = "PRIZE" in text.upper()
                has_digit = any(c.isdigit() for c in text)
                score = len(text) + (30 if has_prize else 0) + (20 if has_digit else 0)
                
                current_score = len(best_text) + (30 if "PRIZE" in best_text.upper() else 0) + (20 if any(c.isdigit() for c in best_text) else 0)
                
                if score > current_score:
                    best_text = text
                    best_conf = conf
                    best_name = name
                    print(f"  ✓ {name:<20} '{text}' (conf: {conf:.1f}%) [BEST]")
                else:
                    print(f"  - {name:<20} '{text}' (conf: {conf:.1f}%)")

        if not best_text:
            print("\n✗ EasyOCR returned no usable text")
            return recognition_result

        print(f"\n  Winner: {best_name}")
        print(f"  Raw: '{best_text}'")
        print(f"  Confidence: {best_conf:.1f}%\n")

        recognition_result['raw_text'] = best_text.strip()
        recognition_result['confidence'] = float(best_conf)

        # Aggressive cleaning - remove artifacts
        cleaned = best_text.upper().strip()
        # Remove special characters, keep only alphanumeric and spaces
        cleaned = re.sub(r"[^0-9A-Z\s]", "", cleaned)
        cleaned = ' '.join(cleaned.split())
        recognition_result['cleaned_text'] = cleaned

        cleaned_upper = cleaned.replace(" ", "")

        # Match logic
        match = re.search(r'([4-9])TH', cleaned_upper)
        if match:
            num = match.group(1)
            prize = f"{num}th Prize"
            recognition_result['detected_prize'] = prize
            recognition_result['match_confidence'] = float(best_conf)
            recognition_result['is_valid'] = best_conf > 50
            print(f"✓ Matched via ordinal: {prize}")

        elif re.search(r'[4-9]', cleaned_upper) and "PRIZE" in cleaned_upper:
            # Extract the first digit
            digit_match = re.search(r'([4-9])', cleaned_upper)
            if digit_match:
                num = digit_match.group(1)
                prize = f"{num}th Prize"
                recognition_result['detected_prize'] = prize
                recognition_result['match_confidence'] = float(best_conf)
                recognition_result['is_valid'] = best_conf > 50
                print(f"✓ Matched via digit + PRIZE: {prize}")

        if not recognition_result['detected_prize']:
            print("✗ No clear prize match - trying fallback")
            for prize in recognition_result['expected_prizes']:
                prize_u = prize.upper().replace(" ", "")
                if prize_u in cleaned_upper:
                    recognition_result['detected_prize'] = prize
                    recognition_result['match_confidence'] = float(best_conf)
                    recognition_result['is_valid'] = best_conf > 50
                    print(f"✓ Matched (fallback): {prize}")
                    break

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
        
        return analysis

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
        print("=" * 70 + "\n")

    def print_recognition(self, recognition):
        if not recognition:
            print("\n⚠️  No recognition data")
            return
        
        print("=" * 70)
        print("TEXT RECOGNITION RESULTS (EasyOCR)")
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
        
        print("=" * 70 + "\n")

    def save_roi(self, roi: tuple, analysis: dict = None, recognition: dict = None):
        """Save ROI to JSON"""
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
                'image': str(self.image_path) if self.image_path else None,
                'ocr_engine': 'easyocr'
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

            print(f"✓ ROI saved successfully: {self.roi_file}")
            print(f"  X: {roi[0]}, Y: {roi[1]}, W: {roi[2]}, H: {roi[3]}")
            if recognition and recognition.get('detected_prize'):
                print(f"  Detected Prize: {recognition['detected_prize']}")
            print()
            return True

        except Exception as e:
            print(f"✗ Save failed: {e}")
            import traceback
            traceback.print_exc()
            return False


# -------------------- main --------------------
if __name__ == "__main__":
    image_path = "image.png"
    video_files = list(Path('.').glob('*.mp4'))
    video_path = str(video_files[0]) if video_files else None

    print("\n" + "=" * 70)
    print("PRIZE AREA EXTRACTOR – IMPROVED GUI + EASYOCR")
    print("=" * 70 + "\n")

    if Path(image_path).exists():
        extractor = ROIExtractorGUI(image_path=image_path)
        print(f"Using static image: {image_path}\n")
    elif video_path:
        extractor = ROIExtractorGUI(video_path=video_path)
        print(f"Using video: {Path(video_path).name}\n")
    else:
        print("✗ No image or video found")
        sys.exit(1)

    print("[1/4] GUI: Mark prize area...")
    roi = extractor.run_gui()
    
    if not roi:
        print("✗ No ROI selected")
        sys.exit(1)

    print("[2/4] Analyzing...")
    analysis = extractor.analyze_roi(roi)
    if analysis:
        extractor.print_analysis(analysis)

    print("[3/4] Recognizing text...")
    recognition = extractor.recognize_text_in_roi(roi)
    if recognition:
        extractor.print_recognition(recognition)

    print("[4/4] Saving...")
    extractor.save_roi(roi, analysis, recognition)

    print("=" * 70)
    print("✓ COMPLETE")
    print("=" * 70) 
    #working
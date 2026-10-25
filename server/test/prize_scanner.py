import json
from pathlib import Path
import numpy as np
import os
import sys
import re
from difflib import SequenceMatcher
import cv2
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk
import threading
from collections import defaultdict

try:
    import easyocr
    EASYOCR_IMPORTED = True
except ImportError:
    EASYOCR_IMPORTED = False
    print("⚠️  EasyOCR not installed. Install with: pip install easyocr")


class PrizeCategoryDetector:
    """Detect all prize categories from video"""

    def __init__(self, video_path: str = None, roi_file: str = "prize_location.json"):
        self.video_path = video_path
        self.roi_file = roi_file
        self.frame = None
        self.frame_original = None
        self.frame_rgb = None
        self.photo = None
        self.reader = None
        self.roi = None
        self.root = None
        self.canvas = None
        self.progress_var = None
        self.result_text = None
        
        self.detected_prizes = defaultdict(list)  # {prize_name: [frame_numbers]}
        
        self.setup_easyocr()

    def setup_easyocr(self):
        """Setup EasyOCR reader"""
        if not EASYOCR_IMPORTED:
            print("✗ EasyOCR not available")
            return False
        
        try:
            print("⏳ Loading EasyOCR...")
            self.reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            print("✓ EasyOCR loaded successfully\n")
            return True
        except Exception as e:
            print(f"✗ EasyOCR setup error: {e}")
            return False

    def load_roi_from_file(self):
        """Load ROI from saved JSON file"""
        if not os.path.exists(self.roi_file):
            print(f"✗ ROI file not found: {self.roi_file}")
            return False
        
        try:
            with open(self.roi_file, 'r') as f:
                data = json.load(f)
            
            roi_data = data.get('roi', {})
            self.roi = (
                roi_data.get('x'),
                roi_data.get('y'),
                roi_data.get('width'),
                roi_data.get('height')
            )
            
            print(f"✓ ROI loaded from {self.roi_file}")
            print(f"  X={self.roi[0]}, Y={self.roi[1]}, W={self.roi[2]}, H={self.roi[3]}\n")
            return True
        
        except Exception as e:
            print(f"✗ Error loading ROI: {e}")
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
            return "", 0.0

    def preprocess_image(self, img):
        """Preprocess image for OCR"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)
        
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        _, th_binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return th_binary

    def recognize_prize_category(self, image):
        """Recognize prize category from image"""
        if image.size == 0:
            return None, 0.0
        
        preprocessed = self.preprocess_image(image)
        text, conf = self.ocr_via_easyocr(preprocessed)
        
        if not text:
            return None, 0.0
        
        # Clean text
        cleaned = text.upper().strip()
        cleaned = re.sub(r"[^0-9A-Z\s]", "", cleaned)
        cleaned = ' '.join(cleaned.split())
        
        # Extract prize number
        prize_match = re.search(r'([1-9]|10)(?:ST|ND|RD|TH)?', cleaned)
        if not prize_match:
            return None, conf
        
        num = prize_match.group(1)
        
        # Map to ordinal
        ordinals = {
            '1': '1st', '2': '2nd', '3': '3rd', '4': '4th', '5': '5th',
            '6': '6th', '7': '7th', '8': '8th', '9': '9th', '10': '10th'
        }
        
        if num in ordinals:
            prize = f"{ordinals[num]} Prize"
            return prize, conf
        
        return None, conf

    def scan_video_for_prizes(self, progress_callback=None):
        """Scan entire video for prize categories"""
        if not self.video_path or not os.path.exists(self.video_path):
            print(f"✗ Video not found: {self.video_path}")
            return
        
        if self.roi is None:
            print("✗ ROI not loaded")
            return
        
        cap = cv2.VideoCapture(self.video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        x, y, w, h = self.roi
        
        print("=" * 70)
        print(f"SCANNING VIDEO FOR PRIZE CATEGORIES")
        print("=" * 70)
        print(f"Total frames: {total_frames}")
        print(f"FPS: {fps:.1f}")
        print(f"Duration: {total_frames / fps:.1f}s")
        print(f"ROI: X={x} Y={y} W={w} H={h}\n")
        
        frame_count = 0
        prize_frames = defaultdict(list)
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Crop ROI
            if y + h <= frame.shape[0] and x + w <= frame.shape[1]:
                cropped = frame[y:y+h, x:x+w]
            else:
                frame_count += 1
                continue
            
            # Recognize prize
            prize, conf = self.recognize_prize_category(cropped)
            
            if prize and conf > 50:
                timestamp = frame_count / fps
                prize_frames[prize].append({
                    'frame': frame_count,
                    'timestamp': timestamp,
                    'confidence': conf
                })
            
            frame_count += 1
            
            # Progress update
            if progress_callback and frame_count % int(fps) == 0:
                progress = (frame_count / total_frames) * 100
                progress_callback(progress, frame_count, total_frames)
            
            if frame_count % 300 == 0:
                print(f"  Processed {frame_count}/{total_frames} frames ({frame_count/total_frames*100:.1f}%)")
        
        cap.release()
        
        self.detected_prizes = prize_frames
        return prize_frames

    def print_results(self, prize_frames):
        """Print detected prizes"""
        if not prize_frames:
            print("✗ No prizes detected")
            return
        
        print("\n" + "=" * 70)
        print("DETECTED PRIZE CATEGORIES")
        print("=" * 70 + "\n")
        
        # Sort by prize order
        prize_order = ['1st Prize', '2nd Prize', '3rd Prize', '4th Prize', '5th Prize',
                       '6th Prize', '7th Prize', '8th Prize', '9th Prize', '10th Prize']
        
        for prize in prize_order:
            if prize in prize_frames:
                frames = prize_frames[prize]
                print(f"✓ {prize:<12} ({len(frames)} occurrences)")
                
                # Show first and last occurrence
                first = frames[0]
                last = frames[-1]
                
                print(f"  First seen: Frame {first['frame']} at {first['timestamp']:.2f}s (conf: {first['confidence']:.1f}%)")
                print(f"  Last seen:  Frame {last['frame']} at {last['timestamp']:.2f}s (conf: {last['confidence']:.1f}%)")
                
                if len(frames) > 2:
                    print(f"  All frames: {', '.join([str(f['frame']) for f in frames[:10]])}" + 
                          (f", ..." if len(frames) > 10 else ""))
                print()
        
        print("=" * 70 + "\n")

    def save_results_json(self, output_file="prize_detection_results.json"):
        """Save results to JSON"""
        if not self.detected_prizes:
            print("✗ No results to save")
            return False
        
        def make_json_safe(obj):
            if isinstance(obj, (np.integer, np.int_, np.intc, np.intp,
                                np.int8, np.int16, np.int32, np.int64)):
                return int(obj)
            if isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, dict):
                return {k: make_json_safe(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [make_json_safe(v) for v in obj]
            return obj
        
        try:
            data = {
                'video': str(self.video_path),
                'roi': {
                    'x': self.roi[0],
                    'y': self.roi[1],
                    'width': self.roi[2],
                    'height': self.roi[3]
                },
                'results': {}
            }
            
            for prize, frames in self.detected_prizes.items():
                data['results'][prize] = make_json_safe(frames)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"✓ Results saved to {output_file}\n")
            return True
        
        except Exception as e:
            print(f"✗ Save failed: {e}")
            return False

    def save_results_csv(self, output_file="prize_detection_results.csv"):
        """Save results to CSV"""
        if not self.detected_prizes:
            print("✗ No results to save")
            return False
        
        try:
            import csv
            
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Prize', 'Frame', 'Timestamp (seconds)', 'Confidence (%)'])
                
                prize_order = ['1st Prize', '2nd Prize', '3rd Prize', '4th Prize', '5th Prize',
                               '6th Prize', '7th Prize', '8th Prize', '9th Prize', '10th Prize']
                
                for prize in prize_order:
                    if prize in self.detected_prizes:
                        for frame_info in self.detected_prizes[prize]:
                            writer.writerow([
                                prize,
                                frame_info['frame'],
                                f"{frame_info['timestamp']:.2f}",
                                f"{frame_info['confidence']:.1f}"
                            ])
            
            print(f"✓ Results saved to {output_file}\n")
            return True
        
        except Exception as e:
            print(f"✗ Save failed: {e}")
            return False

    def setup_gui(self):
        """Setup GUI for progress display"""
        self.root = tk.Tk()
        self.root.title("Prize Category Scanner")
        self.root.geometry("700x500")
        
        # Title
        title = tk.Label(
            self.root,
            text="PRIZE CATEGORY SCANNER",
            font=("Arial", 14, "bold"),
            bg="darkblue",
            fg="white",
            pady=15
        )
        title.pack(fill=tk.X)
        
        # Info frame
        info_frame = tk.LabelFrame(
            self.root,
            text="VIDEO INFO",
            font=("Arial", 10, "bold"),
            padx=15,
            pady=15
        )
        info_frame.pack(fill=tk.X, padx=15, pady=10)
        
        self.info_label = tk.Label(
            info_frame,
            text="Preparing to scan...",
            font=("Arial", 9),
            justify=tk.LEFT,
            wraplength=600
        )
        self.info_label.pack(anchor=tk.NW)
        
        # Progress frame
        progress_frame = tk.LabelFrame(
            self.root,
            text="SCANNING PROGRESS",
            font=("Arial", 10, "bold"),
            padx=15,
            pady=15
        )
        progress_frame.pack(fill=tk.X, padx=15, pady=10)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            length=600,
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_label = tk.Label(
            progress_frame,
            text="0% - 0 / 0 frames",
            font=("Arial", 9)
        )
        self.progress_label.pack(anchor=tk.W)
        
        # Results frame
        results_frame = tk.LabelFrame(
            self.root,
            text="DETECTED PRIZES",
            font=("Arial", 10, "bold"),
            padx=15,
            pady=15
        )
        results_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        # Scrollable text area
        scrollbar = tk.Scrollbar(results_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.result_text = tk.Text(
            results_frame,
            font=("Courier", 9),
            yscrollcommand=scrollbar.set,
            height=10,
            width=80
        )
        self.result_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.result_text.yview)
        
        self.result_text.insert(tk.END, "Scanning in progress...\n")
        
        return True

    def update_progress(self, progress, current, total):
        """Update progress bar (thread-safe)"""
        if self.progress_var:
            self.progress_var.set(progress)
            self.progress_label.config(text=f"{progress:.1f}% - {current} / {total} frames")
            self.root.update()

    def add_result_text(self, text):
        """Add text to result box (thread-safe)"""
        if self.result_text:
            self.result_text.insert(tk.END, text + "\n")
            self.result_text.see(tk.END)
            self.root.update()

    def run_scan_threaded(self):
        """Run scan in separate thread"""
        def scan_thread():
            # Update info
            cap = cv2.VideoCapture(self.video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            
            info_text = (
                f"Video: {Path(self.video_path).name}\n"
                f"Total Frames: {total_frames}\n"
                f"FPS: {fps:.1f}\n"
                f"Duration: {total_frames/fps:.1f}s\n"
                f"ROI: X={self.roi[0]}, Y={self.roi[1]}, W={self.roi[2]}, H={self.roi[3]}"
            )
            self.info_label.config(text=info_text)
            
            self.result_text.delete(1.0, tk.END)
            self.add_result_text("🔍 Scanning video...\n")
            
            # Scan video
            prize_frames = self.scan_video_for_prizes(self.update_progress)
            
            # Display results
            self.result_text.delete(1.0, tk.END)
            
            if prize_frames:
                prize_order = ['1st Prize', '2nd Prize', '3rd Prize', '4th Prize', '5th Prize',
                               '6th Prize', '7th Prize', '8th Prize', '9th Prize', '10th Prize']
                
                self.add_result_text("=" * 70 + "\nDETECTED PRIZES:\n" + "=" * 70 + "\n\n")
                
                for prize in prize_order:
                    if prize in prize_frames:
                        frames = prize_frames[prize]
                        self.add_result_text(f"✓ {prize:<12} ({len(frames)} occurrences)")
                        
                        first = frames[0]
                        last = frames[-1]
                        
                        self.add_result_text(f"  First: Frame {first['frame']} at {first['timestamp']:.2f}s")
                        self.add_result_text(f"  Last:  Frame {last['frame']} at {last['timestamp']:.2f}s\n")
            else:
                self.add_result_text("✗ No prizes detected in video")
            
            self.progress_label.config(text="100% - Scan Complete!")
        
        thread = threading.Thread(target=scan_thread, daemon=True)
        thread.start()

    def run_gui(self):
        """Run GUI"""
        if not self.setup_gui():
            return
        
        print("Starting GUI...\n")
        
        # Start scan in background
        self.run_scan_threaded()
        
        self.root.mainloop()


# -------------------- main --------------------
if __name__ == "__main__":
    video_files = list(Path('.').glob('*.mp4'))
    video_path = str(video_files[0]) if video_files else None

    print("\n" + "=" * 70)
    print("PRIZE CATEGORY DETECTOR – FULL VIDEO SCAN")
    print("=" * 70 + "\n")

    if not video_path:
        print("✗ No video file found")
        sys.exit(1)

    detector = PrizeCategoryDetector(video_path=video_path)
    print(f"Video: {Path(video_path).name}\n")

    # Load ROI from saved file
    if not detector.load_roi_from_file():
        print("✗ Cannot proceed without ROI")
        print("   Run the marker script first to save ROI")
        sys.exit(1)

    # Run GUI scan
    print("[SCANNING] Starting full video scan with GUI...\n")
    detector.run_gui()

    # After GUI closes, save results
    print("\n[SAVING] Writing results...")
    detector.save_results_json("prize_detection_results.json")
    detector.save_results_csv("prize_detection_results.csv")

    print("=" * 70)
    print("✓ COMPLETE")
    print("=" * 70)
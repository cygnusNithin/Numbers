#!/usr/bin/env python3
"""
extract_meter.py

Read 4-digit meter numbers from close-up video using trained font set.
Detects close-ups, extracts 4 digits, matches against digit_fonts/.
Improved preprocessing for aged/yellowed meters.
"""

import os
import sys
import csv
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

# Constants (must match font_capture.py)
FONT_W, FONT_H = 32, 48
MATCH_MIN = 0.50
NUM_DIGITS = 4

# ============================================================================
# PREPROCESSING & NORMALIZATION
# ============================================================================

def preprocess_digit(img):
    """
    Preprocess aged/yellowed digit image for better thresholding.
    - White balance (LAB color normalization)
    - CLAHE (Contrast Limited Adaptive Histogram Equalization)
    - Adaptive thresholding
    - Shadow removal via morphological closing
    """
    if len(img.shape) == 3:
        # Convert to LAB color space (better for white balance)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        
        # Normalize L channel (luminance) to full range
        l, a, b = cv2.split(lab)
        l = cv2.equalizeHist(l)
        lab = cv2.merge([l, a, b])
        
        # Convert back to BGR
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    
    # CLAHE: Boost contrast locally
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # Adaptive threshold: handles uneven lighting better than Otsu
    # Gaussian: window 11x11, constant subtracted = 2
    thresh_adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    
    # Also try Otsu as fallback
    _, thresh_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU)
    
    # Morphological closing: fill small holes (shadows) in digits
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    thresh_adaptive = cv2.morphologyEx(thresh_adaptive, cv2.MORPH_CLOSE, kernel)
    thresh_otsu = cv2.morphologyEx(thresh_otsu, cv2.MORPH_CLOSE, kernel)
    
    return thresh_adaptive, thresh_otsu


def pick_glyph(ink):
    """
    Extract central digit from ink mask.
    More robust: handles weak strokes and edge noise.
    Returns (mask, clean_img).
    """
    if not np.any(ink):
        return ink, np.zeros_like(ink, dtype=np.uint8)
    
    # Find bounding box of ink
    ys, xs = np.where(ink)
    y1, y2 = ys.min(), ys.max()
    x1, x2 = xs.min(), xs.max()
    
    h, w = y2 - y1 + 1, x2 - x1 + 1
    
    # Reject thin bars (cell borders are < 13% of height)
    if w < 0.13 * h:
        return np.zeros_like(ink, dtype=np.uint8), np.zeros_like(ink, dtype=np.uint8)
    
    # Reject too-wide blurs (likely borders or merged digits)
    if w > 0.95 * ink.shape[1]:
        return np.zeros_like(ink, dtype=np.uint8), np.zeros_like(ink, dtype=np.uint8)
    
    # Remove edge pixels (margin) to exclude cell borders and shadows
    margin = max(2, min(h, w) // 10)
    center_ink = ink.copy()
    center_ink[:, :margin] = 0
    center_ink[:, -margin:] = 0
    center_ink[:margin, :] = 0
    center_ink[-margin:, :] = 0
    
    # If center is empty, try smaller margin
    if not np.any(center_ink):
        margin = max(1, min(h, w) // 15)
        center_ink = ink.copy()
        center_ink[:, :margin] = 0
        center_ink[:, -margin:] = 0
        center_ink[:margin, :] = 0
        center_ink[-margin:, :] = 0
    
    if not np.any(center_ink):
        # Fall back to original if no center survives
        center_ink = ink
    
    return center_ink, center_ink.astype(np.uint8) * 255


def normalize_font(img, verbose=False):
    """Normalize digit crop to 32x48 with improved preprocessing."""
    if img.shape[0] == 0 or img.shape[1] == 0:
        return np.zeros((FONT_H, FONT_W), dtype=np.uint8)
    
    # Preprocess with white balance + CLAHE + adaptive threshold
    thresh_adaptive, thresh_otsu = preprocess_digit(img)
    
    # Try adaptive threshold first (better for aged/uneven lighting)
    for thresh in [thresh_adaptive, thresh_otsu]:
        ink, clean = pick_glyph(thresh)
        
        if np.any(clean):
            resized = cv2.resize(clean, (FONT_W, FONT_H))
            return resized
    
    # Fallback: just resize
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    return cv2.resize(gray, (FONT_W, FONT_H))


# ============================================================================
# DIGIT DETECTION
# ============================================================================

def digit_candidates(gray):
    """
    Find dark blobs likely to be digits.
    More robust version for aged/yellowed meters.
    """
    h, w = gray.shape
    
    # Preprocess: white balance + CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # Try multiple thresholds
    _, thresh_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU)
    thresh_adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    
    # Combine: use adaptive as primary
    thresh = thresh_adaptive
    
    # Morphological opening: remove thin borders
    k = max(3, int(round(h * 0.012)))
    morph = cv2.morphologyEx(
        thresh, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    )
    
    # Find contours
    contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    cands = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = cv2.contourArea(cnt)
        aspect = h / max(w, 1)
        
        # Digit-like: tall (0.5–3.0 aspect), reasonable area (>30% of bbox)
        if 0.5 < aspect < 3.0 and area > (h * w * 0.3):
            cands.append((x, y, w, h, area))
    
    return cands


def select_four(cands, h):
    """Pick best 4-digit combination from candidates."""
    if len(cands) < 4:
        return None
    
    # Sort by x (left to right)
    cands = sorted(cands, key=lambda c: c[0])
    
    best = None
    best_score = -1
    
    for i in range(len(cands) - 3):
        quad = cands[i:i+4]
        
        # Check: same height, same baseline, no overlap, even spacing
        heights = [c[3] for c in quad]
        med_h = np.median(heights)
        
        # Height ratio check
        if max(heights) / min(heights) > 1.30:
            continue
        
        # Baseline check
        baselines = [c[1] + c[3] for c in quad]  # y + h
        v_spread = max(baselines) - min(baselines)
        if v_spread > 0.22 * med_h:
            continue
        
        # Overlap check
        for j in range(len(quad) - 1):
            if quad[j][0] + quad[j][2] > quad[j+1][0]:
                break
        else:
            # No overlap
            score = np.mean([c[4] for c in quad])  # avg area
            if score > best_score:
                best = quad
                best_score = score
    
    return best


def propose_boxes(img):
    """
    Detect 4-digit boxes.
    Returns (boxes, detected) tuple.
    detected=True: connected-components found 4 digits.
    detected=False: grid fallback used.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    cands = digit_candidates(gray)
    quad = select_four(cands, gray.shape[0])
    
    if quad:
        boxes = [(x, y, w, h) for x, y, w, h, _ in quad]
        return boxes, True
    
    # Fallback: grid
    h, w = gray.shape
    box_w = w // (NUM_DIGITS + 1)
    box_h = h // 2
    boxes = [(box_w * (i + 1), h // 4, box_w, box_h) for i in range(NUM_DIGITS)]
    return boxes, False


# ============================================================================
# FONT LOADING & MATCHING
# ============================================================================

class FontSet:
    """Load and match against trained digit fonts."""
    
    def __init__(self, font_dir="digit_fonts"):
        self.font_dir = Path(font_dir)
        self.fonts = {}  # {digit: [img_array, ...]}
        self.load_all()
    
    def load_all(self):
        """Load all normalized fonts from disk."""
        for digit in range(10):
            digit_dir = self.font_dir / str(digit)
            if not digit_dir.exists():
                self.fonts[digit] = []
                continue
            
            imgs = []
            for png in sorted(digit_dir.glob("*.png")):
                # Skip raw files, load only normalized
                if "_raw" not in png.name:
                    img = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        imgs.append(img)
            self.fonts[digit] = imgs
        
        total = sum(len(imgs) for imgs in self.fonts.values())
        print(f"FontSet loaded: {total} samples")
        for d in range(10):
            print(f"  {d}: {len(self.fonts[d])} samples")
    
    def match(self, img):
        """
        Match normalized digit image against all 10 fonts.
        Returns (best_digit, best_score, all_scores).
        """
        if img.shape != (FONT_H, FONT_W):
            img = cv2.resize(img, (FONT_W, FONT_H))
        
        scores = {}
        for digit in range(10):
            if not self.fonts[digit]:
                scores[digit] = 0.0
                continue
            
            # Average MSE against all samples of this digit
            mses = []
            for template in self.fonts[digit]:
                mse = np.mean((img.astype(float) - template.astype(float)) ** 2)
                mses.append(mse)
            
            # Convert MSE to similarity (0..1)
            # Normalize by max possible MSE (255^2)
            avg_mse = np.mean(mses)
            score = max(0, 1.0 - avg_mse / (255 ** 2))
            scores[digit] = score
        
        best_digit = max(scores, key=scores.get)
        best_score = scores[best_digit]
        
        return best_digit, best_score, scores


# ============================================================================
# EXTRACTION GUI
# ============================================================================

class MeterExtractorGUI:
    def __init__(self, root, font_set, video_path):
        self.root = root
        self.root.title("Meter Extractor")
        self.root.geometry("1200x750")
        
        self.font_set = font_set
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)
        
        self.results = []  # List of (timestamp, reading, scores)
        
        # UI
        self.canvas = tk.Canvas(root, width=960, height=540, bg="black")
        self.canvas.pack(pady=10)
        self.photo = None
        
        # Info label
        self.info_label = tk.Label(
            root, text="", font=("Arial", 11), fg="white", bg="gray20", height=2
        )
        self.info_label.pack(pady=5, fill=tk.X, padx=10)
        
        # Reading display
        self.reading_label = tk.Label(
            root, text="Reading: ---", font=("Arial", 28, "bold"), fg="lime", bg="gray20", height=2
        )
        self.reading_label.pack(pady=5, fill=tk.X, padx=10)
        
        # Controls
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Play/Pause", command=self.toggle_play, width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Save Results", command=self.save_results, width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Quit", command=self.quit_app, width=12).pack(side=tk.LEFT, padx=5)
        
        self.playing = False
        self.frame_count = 0
        
        self.update_loop()
    
    def toggle_play(self):
        self.playing = not self.playing
    
    def extract_one_frame(self, frame):
        """Extract 4-digit reading from one frame."""
        boxes, detected = propose_boxes(frame)
        
        if not boxes or len(boxes) < 4:
            return None, None, {}
        
        reading = ""
        scores_all = {}
        
        for i, (x, y, w, h) in enumerate(boxes[:4]):
            crop = frame[y:y+h, x:x+w]
            if crop.size == 0:
                continue
            
            norm = normalize_font(crop)
            digit, score, digit_scores = self.font_set.match(norm)
            
            reading += str(digit)
            scores_all[i] = (digit, score, digit_scores)
        
        if len(reading) == 4:
            return reading, boxes, scores_all
        
        return None, None, {}
    
    def update_loop(self):
        """Main loop: read frames, extract, display."""
        if self.playing:
            ret, frame = self.cap.read()
            if ret:
                self.frame_count += 1
                
                # Scale frame for display
                display = cv2.resize(frame, (960, 540))
                
                # Try extraction
                reading, boxes, scores = self.extract_one_frame(frame)
                
                # Draw boxes on display
                if boxes:
                    scale_x = display.shape[1] / frame.shape[1]
                    scale_y = display.shape[0] / frame.shape[0]
                    
                    for i, (x, y, w, h) in enumerate(boxes[:4]):
                        x1 = int(x * scale_x)
                        y1 = int(y * scale_y)
                        x2 = int((x + w) * scale_x)
                        y2 = int((y + h) * scale_y)
                        
                        color = (0, 255, 0) if reading else (0, 0, 255)
                        cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
                        
                        if i in scores:
                            digit, conf, _ = scores[i]
                            cv2.putText(display, f"{digit} {conf:.2f}", (x1, y1 - 5),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                
                # Update display
                rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)
                self.photo = ImageTk.PhotoImage(pil_img)
                self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
                
                # Update info
                fps = self.cap.get(cv2.CAP_PROP_FPS)
                sec = self.frame_count / max(fps, 1)
                
                status = "✓ CLOSE-UP DETECTED" if reading else "✗ Not a valid close-up"
                self.info_label.config(text=f"Frame {self.frame_count} ({sec:.1f}s) | {status}")
                
                if reading:
                    self.reading_label.config(text=f"Reading: {reading}")
                    self.results.append((datetime.now().isoformat(), reading, scores))
                else:
                    self.reading_label.config(text="Reading: ---")
            else:
                self.playing = False
                self.info_label.config(text="End of video")
        
        self.root.after(30, self.update_loop)
    
    def save_results(self):
        """Save extracted readings to CSV."""
        out_file = f"meter_readings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with open(out_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'reading', 'digit0', 'score0', 'digit1', 'score1', 'digit2', 'score2', 'digit3', 'score3'])
            
            for ts, reading, scores in self.results:
                row = [ts, reading]
                for i in range(4):
                    if i in scores:
                        digit, conf, _ = scores[i]
                        row.extend([digit, f"{conf:.3f}"])
                    else:
                        row.extend(['', ''])
                writer.writerow(row)
        
        print(f"Saved {len(self.results)} readings to {out_file}")
        self.info_label.config(text=f"Saved to {out_file}")
        messagebox.showinfo("Saved", f"{len(self.results)} readings saved to {out_file}")
    
    def quit_app(self):
        self.cap.release()
        self.root.destroy()


# ============================================================================
# MAIN
# ============================================================================

def main():
    # Load font set
    fonts = FontSet("digit_fonts")
    
    if sum(len(f) for f in fonts.fonts.values()) == 0:
        print("ERROR: No fonts found. Run font_capture.py first.")
        sys.exit(1)
    
    # Pick video
    root = tk.Tk()
    root.withdraw()
    
    video_path = filedialog.askopenfilename(
        title="Select meter video",
        filetypes=[("Video", "*.mp4 *.avi *.mov"), ("All", "*.*")]
    )
    
    if not video_path:
        print("No video selected.")
        sys.exit(0)
    
    root.destroy()
    
    # Launch extractor
    root = tk.Tk()
    app = MeterExtractorGUI(root, fonts, video_path)
    root.mainloop()


if __name__ == "__main__":
    main()
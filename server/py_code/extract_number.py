import cv2
import json
import numpy as np
import pytesseract
import pandas as pd
from collections import Counter
from tqdm import tqdm  # For progress bar

# ================= CONFIG =================
VIDEO = "draw.mp4"
START_SEC = 8
END_SEC = 15
ROIS_JSON = "roller_rois.json"
OUT_FILE = "roller_digits.csv"

# ======== TESSERACT PATH (Windows) ========
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ======== Load ROIs ========
with open(ROIS_JSON, "r") as f:
    rois = json.load(f)

# ======== Open Video ========
cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
start_frame = int(START_SEC * fps)
end_frame = int(END_SEC * fps)
cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

# ======== OCR Helpers ========
def preprocess(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Upscale for better OCR accuracy
    gray = cv2.resize(gray, (gray.shape[1]*3, gray.shape[0]*3))
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    return thresh

def ocr_digit(crop):
    proc = preprocess(crop)
    text = pytesseract.image_to_string(
        proc,
        config="--psm 10 -c tessedit_char_whitelist=0123456789"
    ).strip()
    return text if text.isdigit() else "?"

# ======== Collect OCR Results ========
digits_per_roi = [[] for _ in range(len(rois))]

print(f"🔄 Extracting frames {start_frame} → {end_frame} ({END_SEC-START_SEC}s)...")

for frame_idx in tqdm(range(start_frame, end_frame + 1)):
    ret, frame = cap.read()
    if not ret:
        break
    for i, r in enumerate(rois):
        x, y, w, h = r
        crop = frame[y:y+h, x:x+w]
        digit = ocr_digit(crop)
        digits_per_roi[i].append(digit)

cap.release()

# ======== Determine Most Frequent Digit per ROI ========
final_digits = [
    Counter(d).most_common(1)[0][0] if d else "?"
    for d in digits_per_roi
]

# ======== Group into 18 Numbers (4 digits each) ========
results = []
for slot in range(18):
    d4 = final_digits[slot*4 : (slot+1)*4]
    number = "".join(d4)
    results.append({"slot": slot+1, "digits": d4, "number": number})

# ======== Save Results ========
df = pd.DataFrame(results)
df.to_csv(OUT_FILE, index=False)
print(f"✅ Saved 18 extracted numbers to {OUT_FILE}")
print(df)

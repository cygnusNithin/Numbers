import cv2
import json
import pytesseract
import pandas as pd
from collections import defaultdict

# ================= CONFIG =================
VIDEO = "full.mp4"
START_SEC = 2
END_SEC = 4
ROIS_JSON = "roller_rois1.json"
OUT_FILE = "roller_sequences_live.csv"

# Tesseract (Windows path)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Load ROIs
with open(ROIS_JSON, "r") as f:
    rois = json.load(f)

# Open video
cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
start_frame = int(START_SEC * fps)
end_frame = int(END_SEC * fps)
cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

# OCR preprocess
def preprocess(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (gray.shape[1]*3, gray.shape[0]*3))
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

def ocr_digit(crop):
    proc = preprocess(crop)
    text = pytesseract.image_to_string(
        proc,
        config="--psm 10 -c tessedit_char_whitelist=0123456789"
    ).strip()
    return text if text.isdigit() else "?"

# Store sequences
sequences = defaultdict(list)

print(f"🔄 Processing video {VIDEO} from {START_SEC}s to {END_SEC}s...")
frame_idx = start_frame

while frame_idx <= end_frame:
    ret, frame = cap.read()
    if not ret:
        break

    display_frame = frame.copy()

    for i, r in enumerate(rois):
        x, y, w, h = r
        crop = frame[y:y+h, x:x+w]
        digit = ocr_digit(crop)

        # Append only if different from last digit
        if not sequences[i] or sequences[i][-1] != digit:
            sequences[i].append(digit)

        # Draw rectangle + last digit
        cv2.rectangle(display_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.putText(display_frame, digit, (x, y-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    # Show live OCR
    cv2.imshow("Live OCR", display_frame)

    key = cv2.waitKey(int(1000/fps))
    if key == 27:  # ESC to quit
        break

    frame_idx += 1

cap.release()
cv2.destroyAllWindows()

# Save results into CSV
rows = []
for slot in range(len(rois)//4):
    for pos in range(4):
        idx = slot*4 + pos
        seq = [d for d in sequences[idx] if d.isdigit()]
        seq_str = "|".join(seq)
        rows.append({
            "number_id": slot+1,
            "roll_position": pos+1,
            "sequence": seq_str
        })

df = pd.DataFrame(rows)
df.to_csv(OUT_FILE, index=False, encoding="utf-8")

print(f"✅ Saved roller sequences to {OUT_FILE}")
print(df.head(20))

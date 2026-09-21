import cv2
import json
import numpy as np
from tqdm import tqdm

# =====================
# CONFIG
# =====================
VIDEO = "roll.mp4"
ROIS_JSON = "roller_rois1.json"
START_SEC = 1
END_SEC = 4

# =====================
# Load ROIs
# =====================
with open(ROIS_JSON, "r") as f:
    rois = json.load(f)

# Normalize: convert [x,y,w,h] lists → dicts
rois = [
    {"x": r[0], "y": r[1], "w": r[2], "h": r[3]} if isinstance(r, list) else r
    for r in rois
]

print(f"✅ Loaded {len(rois)} ROIs")

# =====================
# Open Video
# =====================
cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
start_frame = int(START_SEC * fps)
end_frame = int(END_SEC * fps)

cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

# =====================
# Process Frames
# =====================
frame_idx = start_frame
roi_speeds = {i: [] for i in range(len(rois))}

print("🔄 Estimating roller speeds...")

pbar = tqdm(total=end_frame - start_frame, desc="Processing frames")

prev_vals = [None] * len(rois)

while frame_idx < end_frame:
    ret, frame = cap.read()
    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    for i, roi in enumerate(rois):
        x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]
        crop = gray[y:y+h, x:x+w]

        # Calculate mean pixel intensity
        mean_val = np.mean(crop)

        if prev_vals[i] is not None:
            speed = abs(mean_val - prev_vals[i])
            roi_speeds[i].append(speed)

        prev_vals[i] = mean_val

        # Draw rectangle + index on video
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 1)
        cv2.putText(frame, str(i), (x, y-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    # Show live
    cv2.imshow("Roller Speed Estimation", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

    frame_idx += 1
    pbar.update(1)

pbar.close()
cap.release()
cv2.destroyAllWindows()

# =====================
# Results
# =====================
print("\n📊 Average Roller Speeds:")
for i, speeds in roi_speeds.items():
    if speeds:
        avg_speed = np.mean(speeds)
        print(f"Roller {i}: {avg_speed:.2f}")
    else:
        print(f"Roller {i}: No data")

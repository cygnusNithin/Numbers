import cv2
import json
import numpy as np
import time
import os
import csv

# ==========================
# CONFIG
# ==========================
VIDEO = r"draw.mp4"
ROIS_JSON = r"roller_rois.json"
OUTPUT_CSV = "roller_rotations.csv"

START_TIME_SEC = 0.5
MATCH_THRESHOLD = 0.9
MIN_FRAME_GAP = 30
SHOW_SCALE = 1.0

# ==========================
# SAFETY CHECKS
# ==========================
if not os.path.exists(VIDEO):
    raise FileNotFoundError(f"❌ Video not found: {VIDEO}")
if not os.path.exists(ROIS_JSON):
    raise FileNotFoundError(f"❌ ROI file not found: {ROIS_JSON}")

# ==========================
# LOAD VIDEO + ROIs
# ==========================
rois = json.load(open(ROIS_JSON))
if not isinstance(rois, list) or len(rois) < 1:
    raise ValueError("❌ ROI JSON must be a list of roller rectangles.")

cap = cv2.VideoCapture(VIDEO)
if not cap.isOpened():
    raise Exception("❌ Cannot open video file")

fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"✅ Video Loaded — FPS: {fps:.2f}, Frames: {total_frames}")

# ==========================
# START POSITION
# ==========================
start_frame = int(fps * START_TIME_SEC)
if start_frame >= total_frames:
    raise ValueError("❌ START_TIME_SEC is beyond video length")
cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

# ==========================
# SELECT TEMPLATE FOR EACH ROLLER
# ==========================
templates = []
coords = []

ret, frame = cap.read()
if not ret:
    raise Exception("❌ Could not read frame for selection")

print("👉 Select tracking mark for each roller (6 total)")

for i, r in enumerate(rois):
    x1, y1, x2, y2 = map(int, [r["x1"], r["y1"], r["x2"], r["y2"]])
    roi = frame[y1:y2, x1:x2]
    roi_disp = cv2.resize(roi, None, fx=SHOW_SCALE, fy=SHOW_SCALE)

    cv2.imshow(f"Roller {i+1} ROI", roi_disp)
    sel = cv2.selectROI(f"Select mark Roller {i+1}", roi_disp, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow(f"Select mark Roller {i+1}")

    if sel == (0, 0, 0, 0):
        print(f"⚠️ Skipping roller {i+1}")
        templates.append(None)
        coords.append((x1, y1, x2, y2))
        continue

    sx, sy, sw, sh = [int(v / SHOW_SCALE) for v in sel]
    template = roi[sy:sy+sh, sx:sx+sw]
    templates.append(template)
    coords.append((x1, y1, x2, y2))
    print(f"✅ Template selected for roller {i+1}")

cv2.destroyAllWindows()

# ==========================
# TRACKING INITIALIZATION
# ==========================
tracking_data = [{
    "id": i + 1,
    "template": templates[i],
    "coords": coords[i],
    "initial_pos": None,
    "rotation_frame": None,
    "frame_idx": 0,
    "last_detect_frame": 0
} for i in range(len(rois)) if templates[i] is not None]

# ==========================
# TRACK ALL ROLLERS
# ==========================
print("\n▶ Tracking started... Press 'q' to stop\n")

while True:
    ret, frame = cap.read()
    if not ret:
        print("⏹️ Video ended.")
        break

    for roller in tracking_data:
        roller["frame_idx"] += 1
        if roller["frame_idx"] - roller["last_detect_frame"] < MIN_FRAME_GAP:
            continue

        x1, y1, x2, y2 = roller["coords"]
        roller_frame = frame[y1:y2, x1:x2]
        template = roller["template"]

        res = cv2.matchTemplate(roller_frame, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val >= MATCH_THRESHOLD:
            roller["last_detect_frame"] = roller["frame_idx"]

            cv2.rectangle(roller_frame, max_loc,
                          (max_loc[0] + template.shape[1], max_loc[1] + template.shape[0]),
                          (0, 255, 0), 2)
            cv2.putText(roller_frame, f"{max_val:.2f}", (5, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            if roller["initial_pos"] is None:
                roller["initial_pos"] = max_loc
                print(f"🎯 Roller {roller['id']} started tracking at frame {roller['frame_idx']}")
            else:
                dx = abs(max_loc[0] - roller["initial_pos"][0])
                dy = abs(max_loc[1] - roller["initial_pos"][1])

                if dx < 5 and dy < 5 and roller["frame_idx"] > 20:
                    roller["rotation_frame"] = roller["frame_idx"]
                    print(f"✅ Roller {roller['id']} completed rotation at frame {roller['frame_idx']}")

    # Combine views for visualization
    combined = np.zeros_like(frame)
    for roller in tracking_data:
        x1, y1, x2, y2 = roller["coords"]
        combined[y1:y2, x1:x2] = frame[y1:y2, x1:x2]
    cv2.imshow("All Rollers Tracking", combined)

    if cv2.waitKey(10) & 0xFF == ord('q'):
        print("⏹️ Manually stopped.")
        break

cap.release()
cv2.destroyAllWindows()

# ==========================
# SAVE RESULTS
# ==========================
print("\n💾 Saving rotation data...")

results = []
for roller in tracking_data:
    if roller["rotation_frame"]:
        time_per_rotation = (roller["rotation_frame"] - start_frame) / fps
        rpm = 60 / time_per_rotation
        results.append({
            "roller_id": roller["id"],
            "rotation_time_sec": round(time_per_rotation, 2),
            "rpm": round(rpm, 2)
        })
        print(f"🌀 Roller {roller['id']} → {rpm:.2f} RPM ({time_per_rotation:.2f}s per rotation)")
    else:
        results.append({
            "roller_id": roller["id"],
            "rotation_time_sec": None,
            "rpm": None
        })
        print(f"⚠️ Roller {roller['id']} did not complete a rotation.")

# Save to CSV
with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["roller_id", "rotation_time_sec", "rpm"])
    writer.writeheader()
    writer.writerows(results)

print(f"\n✅ Results saved to {OUTPUT_CSV}")

import cv2
import json
import numpy as np
import csv
import os

# ==========================
# CONFIG
# ==========================
VIDEO = "draw.mp4"
ROIS_JSON = "roller_rois.json"
START_TIME_SEC = 0.5
FPS = 30
MATCH_THRESHOLD = 0.8
SHOW_SCALE = 1.0
RESULT_CSV = "roller_speed_results.csv"

# Roller number sequences
ROLLER_SEQUENCES = {
    1: "7|1|4|9|5|2|8|6|3".split("|"),
    2: "7|6|8|5|9|0|3|1|2|4".split("|"),
    3: "7|8|9|0|1|2|3|4|5|6".split("|"),
    4: "7|5|9|1|3|6|8|4|0|2".split("|"),
    5: "7|5|1|9|6|4|2|8|3|0".split("|"),
    6: "7|9|2|5|1|6|3|8|0|4".split("|")
}

# ==========================
# LOAD VIDEO + ROIS
# ==========================
if not os.path.exists(VIDEO):
    raise FileNotFoundError("Video not found")

if not os.path.exists(ROIS_JSON):
    raise FileNotFoundError("ROI file not found")

rois = json.load(open(ROIS_JSON))
if len(rois) != 6:
    raise ValueError("Expected 6 roller ROIs")

cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
if not fps or fps == 0:
    fps = FPS  # fallback

total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
start_frame = int(fps * START_TIME_SEC)
cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

print(f"🎞 Loaded video: {VIDEO}")
print(f"FPS: {fps:.2f}, Frames: {total_frames}, Start: {START_TIME_SEC}s\n")

# ==========================
# TRACKING ALL ROLLERS
# ==========================
results = []

for i, r in enumerate(rois, start=1):
    x1, y1, x2, y2 = map(int, [r["x1"], r["y1"], r["x2"], r["y2"]])
    print(f"\n🎯 Roller {i}: region=({x1},{y1})-({x2},{y2})")

    # Reset video for each roller
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    ret, frame = cap.read()
    if not ret:
        print("⚠️ Cannot read starting frame.")
        continue

    roi = frame[y1:y2, x1:x2]
    roi_disp = cv2.resize(roi, None, fx=SHOW_SCALE, fy=SHOW_SCALE)
    cv2.imshow(f"Roller {i} ROI", roi_disp)
    cv2.waitKey(300)

    print("👉 Select the first visible number on this roller")
    sel = cv2.selectROI(f"Select Number Roller {i}", roi_disp, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow(f"Select Number Roller {i}")

    sx, sy, sw, sh = [int(v / SHOW_SCALE) for v in sel]
    template = roi[sy:sy+sh, sx:sx+sw]
    th, tw = template.shape[:2]

    initial_pos = None
    rotation_frame = None
    frame_idx = 0
    detected_positions = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        roller_frame = frame[y1:y2, x1:x2]
        res = cv2.matchTemplate(roller_frame, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val >= MATCH_THRESHOLD:
            if initial_pos is None:
                initial_pos = max_loc
                first_frame = frame_idx
                print(f"Tracking started (frame {frame_idx})")
            else:
                dx = abs(max_loc[0] - initial_pos[0])
                dy = abs(max_loc[1] - initial_pos[1])
                if dx < 5 and dy < 5 and frame_idx - first_frame > 10:
                    rotation_frame = frame_idx
                    print(f"✅ Full rotation at frame {frame_idx}")
                    break

        cv2.rectangle(roller_frame, max_loc, (max_loc[0]+tw, max_loc[1]+th), (0,255,0), 2)
        cv2.imshow(f"Roller {i} Tracking", roller_frame)
        if cv2.waitKey(5) & 0xFF == ord('q'):
            break

    if rotation_frame:
        time_per_rotation = (rotation_frame - first_frame) / fps
        rpm = 60 / time_per_rotation
        circumference_px = np.sqrt((dx**2 + dy**2)) * len(ROLLER_SEQUENCES[i])
        diameter_px = circumference_px / np.pi

        results.append({
            "roller_id": i,
            "frames_per_rotation": rotation_frame - first_frame,
            "time_per_rotation": time_per_rotation,
            "rpm": rpm,
            "circumference_px": circumference_px,
            "diameter_px": diameter_px
        })

        print(f"🌀 Roller {i}: {rpm:.2f} RPM, Circumference≈{circumference_px:.1f}px, Diameter≈{diameter_px:.1f}px")
    else:
        print(f"⚠️ No full rotation detected for Roller {i}")

cap.release()
cv2.destroyAllWindows()

# ==========================
# SAVE RESULTS
# ==========================
with open(RESULT_CSV, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=results[0].keys())
    writer.writeheader()
    writer.writerows(results)

print(f"\n✅ Results saved to: {RESULT_CSV}")

import cv2
import json
import numpy as np
import time
import os

# ==========================
# CONFIG
# ==========================
VIDEO = r"draw1.mp4"             # path to video
ROIS_JSON = r"roller_rois.json" # file with roller regions
SELECTED_ROLLER = 2             # which roller (1-indexed)
START_TIME_SEC = 0              # start after some seconds
MATCH_THRESHOLD = 0.9           # how strong match must be
MIN_FRAME_GAP = 10              # skip frames between checks for speed
SHOW_SCALE = 1.0                # 1.0 = normal size

# ==========================
# SAFETY CHECKS
# ==========================
if not os.path.exists(VIDEO):
    raise FileNotFoundError(f"❌ Video not found: {VIDEO}")

if not os.path.exists(ROIS_JSON):
    raise FileNotFoundError(f"❌ ROI file not found: {ROIS_JSON}")

# ==========================
# LOAD VIDEO AND ROI
# ==========================
rois = json.load(open(ROIS_JSON))
if not isinstance(rois, list) or SELECTED_ROLLER > len(rois):
    raise ValueError("Invalid roller index or ROI format.")

r = rois[SELECTED_ROLLER - 1]
cap = cv2.VideoCapture(VIDEO)

if not cap.isOpened():
    raise Exception("❌ Cannot open video file")

fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"✅ Loaded video — FPS: {fps:.2f}, Frames: {total_frames}")

# Seek to start position
start_frame = int(fps * START_TIME_SEC)
if start_frame >= total_frames:
    raise ValueError("❌ START_TIME_SEC is beyond video length")

cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
time.sleep(0.3)

# ==========================
# FIRST FRAME + ROI
# ==========================
ret, frame = cap.read()
if not ret:
    raise Exception("❌ Can't read first frame. Check codec or start time.")

x1, y1, x2, y2 = map(int, [r["x1"], r["y1"], r["x2"], r["y2"]])
roi = frame[y1:y2, x1:x2]
roi_disp = cv2.resize(roi, None, fx=SHOW_SCALE, fy=SHOW_SCALE)

cv2.imshow("ROI", roi_disp)
cv2.waitKey(500)

# ==========================
# SELECT MARK TEMPLATE
# ==========================
print("👉 Select a small mark or number on the roller to track")
sel = cv2.selectROI("Select mark", roi_disp, fromCenter=False, showCrosshair=True)
cv2.destroyWindow("Select mark")

if sel == (0, 0, 0, 0):
    raise Exception("❌ No region selected")

# Scale selection back to original if resized
sx, sy, sw, sh = [int(v / SHOW_SCALE) for v in sel]
template = roi[sy:sy+sh, sx:sx+sw]
th, tw = template.shape[:2]

cv2.imshow("Selected Template", template)
cv2.waitKey(500)

# ==========================
# TRACKING LOOP
# ==========================
print("▶ Tracking started... Press 'q' to stop")
initial_pos = None
rotation_frame = None
frame_idx = 0
last_detect_frame = 0
matches = []

while True:
    ret, frame = cap.read()
    if not ret:
        print("⏹️ Video ended.")
        break

    frame_idx += 1
    if frame_idx - last_detect_frame < MIN_FRAME_GAP:
        continue  # skip frames to reduce processing load

    roller_frame = frame[y1:y2, x1:x2]
    res = cv2.matchTemplate(roller_frame, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val >= MATCH_THRESHOLD:
        last_detect_frame = frame_idx
        matches.append(max_loc)

        # Draw detection
        cv2.rectangle(roller_frame, max_loc,
                      (max_loc[0] + tw, max_loc[1] + th),
                      (0, 255, 0), 2)
        cv2.putText(roller_frame, f"{max_val:.2f}", (5, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        if initial_pos is None:
            initial_pos = max_loc
            print(f"🎯 Started tracking at frame {frame_idx}")
        else:
            dx = abs(max_loc[0] - initial_pos[0])
            dy = abs(max_loc[1] - initial_pos[1])

            # rotation detected (mark returns near start)
            if dx < 5 and dy < 5 and frame_idx > 20:
                rotation_frame = frame_idx
                print(f"✅ Rotation completed at frame {frame_idx}")
                break

    cv2.imshow("Tracking Roller", roller_frame)
    if cv2.waitKey(10) & 0xFF == ord('q'):
        print("⏹️ Manually stopped.")
        break

cap.release()
cv2.destroyAllWindows()

# ==========================
# RESULTS
# ==========================
if rotation_frame:
    time_per_rotation = (rotation_frame - start_frame) / fps
    rpm = 60 / time_per_rotation
    print(f"\n🌀 Rotation time: {time_per_rotation:.2f}s → {rpm:.2f} RPM")
else:
    print("\n⚠️ No full rotation detected.")

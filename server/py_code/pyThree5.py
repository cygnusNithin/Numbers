import cv2
import json
import numpy as np
import time

VIDEO = "draw.mp4"
START_TIME_SEC = 0.5
FPS = 30  # given

# 6 roller ROIs
ROIS = [
    {"x1": 826, "y1": 452, "x2": 893, "y2": 551},
    {"x1": 996, "y1": 458, "x2": 1061, "y2": 550},
    {"x1": 1160, "y1": 457, "x2": 1230, "y2": 550},
    {"x1": 1328, "y1": 456, "x2": 1403, "y2": 550},
    {"x1": 1500, "y1": 451, "x2": 1565, "y2": 547},
    {"x1": 1668, "y1": 454, "x2": 1731, "y2": 548}
]

# number sequences for reference
ROLLER_NUMBERS = {
    1: "7|1|4|9|5|2|8|6|3",
    2: "7|6|8|5|9|0|3|1|2|4",
    3: "7|8|9|0|1|2|3|4|5|6",
    4: "7|5|9|1|3|6|8|4|0|2",
    5: "7|5|1|9|6|4|2|8|3|0",
    6: "7|9|2|5|1|6|3|8|0|4"
}

MATCH_THRESHOLD = 0.85
SHOW_SCALE = 1.0

cap = cv2.VideoCapture(VIDEO)
if not cap.isOpened():
    raise Exception("Cannot open video")

cap.set(cv2.CAP_PROP_POS_FRAMES, int(START_TIME_SEC * FPS))

# choose one roller to manually mark once (same ROI template used for all)
ret, frame = cap.read()
if not ret:
    raise Exception("Can't read frame")

# Display all rollers
for i, r in enumerate(ROIS):
    cv2.rectangle(frame, (r["x1"], r["y1"]), (r["x2"], r["y2"]), (0, 255, 0), 2)
    cv2.putText(frame, f"R{i+1}", (r["x1"], r["y1"] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

cv2.imshow("Rollers", frame)
cv2.waitKey(1500)

# manually mark a unique number/symbol on roller 1
roller1 = frame[ROIS[0]["y1"]:ROIS[0]["y2"], ROIS[0]["x1"]:ROIS[0]["x2"]]
r = cv2.selectROI("Select a mark to track (Roller 1)", roller1,
                  fromCenter=False, showCrosshair=True)
template = roller1[int(r[1]):int(r[1]+r[3]), int(r[0]):int(r[0]+r[2])]
cv2.destroyAllWindows()

# reset video pointer
cap.set(cv2.CAP_PROP_POS_FRAMES, int(START_TIME_SEC * FPS))

# Tracking data
trackers = [{"init": None, "rot_frame": None} for _ in range(6)]
frame_idx = 0
start_time = time.time()

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_idx += 1
    for i, r in enumerate(ROIS):
        roi = frame[r["y1"]:r["y2"], r["x1"]:r["x2"]]
        res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val >= MATCH_THRESHOLD:
            cv2.rectangle(roi, max_loc,
                          (max_loc[0] + template.shape[1], max_loc[1] + template.shape[0]),
                          (0, 255, 0), 1)
            if trackers[i]["init"] is None:
                trackers[i]["init"] = max_loc
            else:
                dx = abs(max_loc[0] - trackers[i]["init"][0])
                dy = abs(max_loc[1] - trackers[i]["init"][1])
                if dx < 5 and dy < 5 and trackers[i]["rot_frame"] is None:
                    trackers[i]["rot_frame"] = frame_idx
                    print(f"Roller {i+1} completed one rotation at frame {frame_idx}")

        frame[r["y1"]:r["y2"], r["x1"]:r["x2"]] = roi

    disp = cv2.resize(frame, (0, 0), fx=SHOW_SCALE, fy=SHOW_SCALE)
    cv2.imshow("Tracking Rollers", disp)

    if cv2.waitKey(10) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

print("\n=== RESULTS ===")
for i, tr in enumerate(trackers):
    if tr["rot_frame"]:
        time_per_rotation = tr["rot_frame"] / FPS
        rpm = 60 / time_per_rotation
        # pixel-based diameter estimate: horizontal motion path
        r = ROIS[i]
        pixel_height = r["y2"] - r["y1"]
        pixel_width = r["x2"] - r["x1"]
        circumference_px = pixel_width
        diameter_px = circumference_px / np.pi
        print(f"Roller {i+1}: {rpm:.2f} RPM | Time per rotation: {time_per_rotation:.2f}s | "
              f"Diameter ≈ {diameter_px:.1f}px | Circumference ≈ {circumference_px:.1f}px")
    else:
        print(f"Roller {i+1}: No full rotation detected.")

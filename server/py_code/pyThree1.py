import cv2
import json
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks

VIDEO = "draw1.mp4"
ROIS_JSON = "roller_rois.json"
THRESH_MOTION = 15
HALT_THRESHOLD = 3
DIGITS_PER_REV = 10  # number of digits on the roller

# --- Load ROIs ---
with open(ROIS_JSON, "r") as f:
    rois = json.load(f)

cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
ret, prev_frame = cap.read()
if not ret:
    raise RuntimeError("Could not read first frame")

prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

motion_history = [[] for _ in rois]

while True:
    ret, frame = cap.read()
    if not ret:
        break
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    for i, r in enumerate(rois):
        roi_prev = prev_gray[r["y1"]:r["y2"], r["x1"]:r["x2"]]
        roi_now  = gray[r["y1"]:r["y2"], r["x1"]:r["x2"]]
        diff = cv2.absdiff(roi_prev, roi_now)
        motion_value = np.mean(diff)
        motion_history[i].append(motion_value)

        color = (0,255,0) if motion_value < HALT_THRESHOLD else (0,0,255)
        cv2.rectangle(frame, (r["x1"],r["y1"]), (r["x2"],r["y2"]), color, 2)
        cv2.putText(frame, f"{motion_value:.1f}", (r["x1"],r["y1"]-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    cv2.imshow("Roller Speed Monitor", frame)
    if cv2.waitKey(10) & 0xFF == 27:
        break

    prev_gray = gray.copy()

cap.release()
cv2.destroyAllWindows()

# --- Analyze motion history ---
for i, history in enumerate(motion_history):
    arr = np.array(history)
    if len(arr) < 2: 
        continue

    # Normalize and find peaks
    arr_smooth = cv2.GaussianBlur(arr.reshape(-1,1), (5,1), 0).flatten()
    peaks, _ = find_peaks(arr_smooth, height=np.mean(arr_smooth) + np.std(arr_smooth))
    
    if len(peaks) > 1:
        avg_frames_per_digit = np.mean(np.diff(peaks))
        frames_per_rotation = avg_frames_per_digit * DIGITS_PER_REV
        rpm = (fps / frames_per_rotation) * 60
    else:
        rpm = 0

    max_speed = np.max(arr)
    stop_idx = np.argmax(arr[::-1] < HALT_THRESHOLD)
    time_to_stop = stop_idx / fps if stop_idx > 0 else 0

    print(f"Roller {i+1}:")
    print(f"  Max visual speed: {max_speed:.1f}")
    print(f"  Estimated RPM: {rpm:.1f}")
    print(f"  Time to stop: {time_to_stop:.2f}s\n")

    # Plot speed curve
    plt.figure(figsize=(8,4))
    plt.title(f"Roller {i+1} Speed Curve (Est. {rpm:.1f} RPM)")
    plt.plot(arr_smooth, label="Motion Intensity", color='blue')
    plt.scatter(peaks, arr_smooth[peaks], color='red', s=30, label="Digit Passes")
    plt.xlabel("Frame")
    plt.ylabel("Motion Level")
    plt.legend()
    plt.show()

import cv2
import json

VIDEO = "full.mp4"
OUTPUT_JSON = "roller_rois1.json"
FRAME_TIME = 4  # seconds (pause on this frame to select)

# Load video
cap = cv2.VideoCapture(VIDEO)
fps = cap.get(cv2.CAP_PROP_FPS)
cap.set(cv2.CAP_PROP_POS_FRAMES, int(FRAME_TIME * fps))

ret, frame = cap.read()
if not ret:
    print("❌ Could not grab frame.")
    exit()

# Global storage for ROIs
rois = []

def select_roi(event, x, y, flags, param):
    global x1, y1, drawing, frame_copy, rois
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        x1, y1 = x, y
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        x2, y2 = x, y
        w, h = abs(x2 - x1), abs(y2 - y1)
        x_min, y_min = min(x1, x2), min(y1, y2)
        rois.append((x_min, y_min, w, h))
        print(f"✅ ROI saved: {(x_min, y_min, w, h)}")
        cv2.rectangle(frame_copy, (x_min, y_min), (x_min + w, y_min + h), (0, 255, 0), 2)
        cv2.imshow("Frame", frame_copy)

# Show frame
frame_copy = frame.copy()
cv2.namedWindow("Frame")
cv2.setMouseCallback("Frame", select_roi)

print("👉 Draw ROIs with mouse (click+drag). Press [s] to save, [q] to quit.")
while True:
    cv2.imshow("Frame", frame_copy)
    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        break
    elif key == ord("s"):
        with open(OUTPUT_JSON, "w") as f:
            json.dump(rois, f, indent=2)
        print(f"💾 Saved {len(rois)} ROIs → {OUTPUT_JSON}")
        break

cap.release()
cv2.destroyAllWindows()

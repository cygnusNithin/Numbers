import cv2
import json

VIDEO = "draw.mp4"   # or 0 for webcam
OUT_JSON = "roller_rois.json"

cap = cv2.VideoCapture(VIDEO)
if not cap.isOpened():
    raise RuntimeError("Cannot open video or camera")

rois = []
drawing = False
x1, y1 = -1, -1

def draw_roi(event, x, y, flags, param):
    global x1, y1, drawing, rois, frame
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        x1, y1 = x, y
    elif event == cv2.EVENT_MOUSEMOVE and drawing:
        img_copy = frame.copy()
        cv2.rectangle(img_copy, (x1, y1), (x, y), (0,255,0), 2)
        cv2.imshow("Select", img_copy)
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        x2, y2 = x, y
        rois.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0,255,0), 2)
        cv2.imshow("Select", frame)
        print(f"ROI saved: {(x1, y1, x2, y2)}")

# Read first frame
ret, frame = cap.read()
if not ret:
    raise RuntimeError("No frame found")

cv2.imshow("Select", frame)
cv2.setMouseCallback("Select", draw_roi)

print("👉 Draw boxes around each roller. Press 's' to save, 'q' to quit.")
while True:
    key = cv2.waitKey(1) & 0xFF
    if key == ord('s'):
        with open(OUT_JSON, "w") as f:
            json.dump(rois, f, indent=2)
        print(f"✅ Saved {len(rois)} ROIs to {OUT_JSON}")
        break
    elif key == ord('q'):
        break

cv2.destroyAllWindows()
cap.release()

# SAVE DIGIT CROPS FOR TRAINING (first dataset builder)
import cv2, json, os

VIDEO = "sample_video.mp4"
ROIS = "rois.json"
OUT = "digits/"

os.makedirs(OUT, exist_ok=True)

# Load video & ROIs
cap=cv2.VideoCapture(VIDEO)
rois=json.load(open(ROIS))["rois"]

def save_digits(frame, idx):
    for r_i,(x,y,w,h) in enumerate(rois[:18]):
        crop=frame[y:y+h, x:x+w]
        # split horizontally into 4 equal digits
        dw = w//4
        for d in range(4):
            d_crop = crop[:, d*dw:(d+1)*dw]
            cv2.imwrite(f"{OUT}/{idx}_{r_i}_{d}.png", d_crop)

i=0
while True:
    ret,frame=cap.read()
    if not ret: break
    save_digits(frame, i)
    i+=1

cap.release()
print("DONE. Crops saved in /digits/")

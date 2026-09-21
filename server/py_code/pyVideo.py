# roller_speed_from_video.py
import cv2
import numpy as np
from tqdm import tqdm

# ---------- USER CONFIG ----------
VIDEO_PATH = "roller_video.mp4"   # your video file
FPS = None                        # set to None to read from video, or specify exact fps (float)
# ROI: if you know the center and radius of the roller in pixels, set these.
# If None, script will try to detect circle via Hough.
ROI_CENTER = None   # (x,y) e.g. (640,360) or None
ROI_RADIUS = None   # integer pixels or None
# Real-world measurement: length of one face in meters (or mm). If None, result will be in pixels.
L_FACE_REAL = 0.012   # meters (example). If you have mm, convert to meters: 12 mm = 0.012 m
N_FACES = 10
UNWRAP_HEIGHT = 100   # number of radial pixels in the unwrapped image
SKIP_INITIAL = 5      # skip first few frames to let video start
MAX_FRAMES = None     # limit frames to process (None = whole video)

# ---------- END CONFIG ----------

def detect_circle(frame_gray):
    # Try HoughCircles for approximate circle detection
    # Pre-blur and edge enhance
    img = cv2.medianBlur(frame_gray, 5)
    circles = cv2.HoughCircles(img, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100,
                               param1=100, param2=30, minRadius=20, maxRadius=1000)
    if circles is not None:
        c = circles[0][0]
        return int(c[0]), int(c[1]), int(c[2])
    return None

def unwrap_frame(frame, center, radius, width_out):
    # WarpPolar parameters: size = (width_out, UNWRAP_HEIGHT)
    # Use cv2.WARP_POLAR_LINEAR + cv2.WARP_FILL_OUTLIERS
    flags = cv2.WARP_POLAR_LINEAR + cv2.WARP_FILL_OUTLIERS
    # OpenCV expects (w,h)
    unp = cv2.warpPolar(frame, (width_out, UNWRAP_HEIGHT), center, radius, flags)
    # warpPolar maps angle to x axis (0...width_out), radius to y.
    # optionally rotate so angle=0 at left: transpose or roll
    return unp

def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        raise SystemExit("Cannot open video: " + VIDEO_PATH)

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    if FPS is None or FPS <= 0:
        fps = video_fps if video_fps>0 else 30.0
    else:
        fps = FPS

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if MAX_FRAMES:
        total_frames = min(total_frames, MAX_FRAMES)

    # read first frame to detect circle if needed
    ret, frame = cap.read()
    if not ret:
        raise SystemExit("Empty video or cannot read frames.")

    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if ROI_CENTER is None or ROI_RADIUS is None:
        det = detect_circle(frame_gray)
        if det is None:
            raise SystemExit("Could not auto-detect roller circle. Provide ROI_CENTER and ROI_RADIUS in config.")
        cx, cy, r = det
    else:
        cx, cy = ROI_CENTER
        r = ROI_RADIUS

    print(f"Using center=({cx},{cy}), radius={r}, fps={fps}")

    # choose unwrap width — we want one pixel per angular sample; pick width roughly equal to circumference in px
    # estimate width_out = int(2*pi*r) or use N_FACES * pixels_per_face if known
    width_out = int(2 * np.pi * r)
    if width_out < 200:
        width_out = max(width_out, N_FACES * 20, 400)  # ensure decent resolution

    # reset video to start
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    prev_unwrap = None
    shifts = []      # horizontal shifts in pixels between consecutive frames
    times = []       # timestamps (seconds) of frames used

    frame_idx = 0
    # iterate frames
    pbar = tqdm(total=total_frames, desc="Processing frames")
    while True:
        ret, f = cap.read()
        if not ret:
            break
        frame_idx += 1
        if MAX_FRAMES and frame_idx > MAX_FRAMES:
            break

        if frame_idx <= SKIP_INITIAL:
            pbar.update(1)
            continue

        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        # crop ROI to small box around circle to speed unwrap (optional)
        x0 = max(int(cx - r - 5), 0)
        y0 = max(int(cy - r - 5), 0)
        x1 = min(int(cx + r + 5), f.shape[1])
        y1 = min(int(cy + r + 5), f.shape[0])
        crop = gray[y0:y1, x0:x1]
        center_local = (cx - x0, cy - y0)
        radius_local = r

        # unwrap
        unwrap = unwrap_frame(crop, center_local, radius_local, width_out)
        # convert to float32 for phaseCorrelate
        unwrap_f = np.float32(unwrap)

        if prev_unwrap is not None:
            # Use phase correlation to find shift; this returns (shift_y, shift_x) (we expect horizontal shift)
            shift, _ = cv2.phaseCorrelate(prev_unwrap, unwrap_f)
            # shift is (dx,dy)? phaseCorrelate returns (dx,dy) as floats
            dx = shift[0]
            # store horizontal shift
            shifts.append(dx)
            times.append(frame_idx / fps)
        prev_unwrap = unwrap_f
        pbar.update(1)

    pbar.close()
    cap.release()

    if len(shifts) == 0:
        raise SystemExit("No shifts computed — check video and ROI settings.")

    # Convert shifts to rotation fractions:
    # shift (pixels) horizontally corresponds to angular shift = shift_pixels / width_out * 360deg
    shifts = np.array(shifts)
    mean_dx = np.mean(shifts)
    std_dx = np.std(shifts)
    fps_effective = fps

    # rotation per frame (fraction of full rotation)
    rot_frac_per_frame = mean_dx / width_out
    # rotations per second = rot_frac_per_frame * fps
    rotations_per_second = rot_frac_per_frame * fps_effective
    rotations_per_min = rotations_per_second * 60.0
    omega = 2 * np.pi * rotations_per_second  # rad/s

    # If you have real L_face (m):
    if L_FACE_REAL is not None:
        v_tangential = rotations_per_second * (N_FACES * L_FACE_REAL)  # m/s
    else:
        v_tangential = None

    print("Results (video-based):")
    print(f" mean horizontal shift per frame (px): {mean_dx:.3f} ± {std_dx:.3f}")
    print(f" width_out (px): {width_out}")
    print(f" rotations/frame (fraction): {rot_frac_per_frame:.6f}")
    print(f" rotations/sec (RPS): {rotations_per_second:.6f}")
    print(f" rotations/min (RPM): {rotations_per_min:.3f}")
    print(f" angular speed ω (rad/s): {omega:.3f}")
    if v_tangential is not None:
        print(f" tangential speed at rim v: {v_tangential:.4f} (meters/sec)")

    # Optionally: print distribution info
    print("\nShift distribution summary (px): min,25%,median,75%,max")
    print(np.percentile(shifts, [0,25,50,75,100]))

if __name__ == "__main__":
    main()

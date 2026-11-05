
import cv2
import json
import re
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog
from datetime import datetime

try:
    import easyocr
    OCR = easyocr.Reader(["en"], gpu=False)
except Exception:
    OCR = None


CONFIG_DIR = Path(__file__).resolve().parent / "video_configs"
OUTPUT_DIR = Path(__file__).resolve().parent / "inspection_results"

ROLLER_COUNT = 18
LABEL_COUNT = 18


class LotteryVideoWorkflow:

    def __init__(self, root):
        self.root = root
        root.title("Lottery Machine Video Workflow")
        root.geometry("1500x900")

        self.cap = None
        self.video_path = None
        self.frame = None
        self.fps = 30
        self.frame_index = 0
        self.playing = False

        self.machine_config = {
            "machine_body": None,
            "rollers": {},
            "yellow_labels": {},
            "category": None,
            "serial": None,
            "red_light": None
        }

        self.roi_target = None
        self.drag_start = None
        self.drag_end = None
        self.roi_drawing = False

        self.expected_count = 0
        self.results = []
        self.roll_active = False
        self.roll_start_frame = None
        self.previous_roller_frames = {}
        self.roll_events = []
        self.red_light_events = []

        self.build_ui()

    # ---------------------------------------------------------
    # UI
    # ---------------------------------------------------------

    def build_ui(self):
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=8)

        ttk.Button(top, text="Select Video",
                   command=self.select_video).pack(side="left")

        ttk.Button(top, text="Play / Pause",
                   command=self.toggle_play).pack(side="left")

        ttk.Button(top, text="−10 sec",
                   command=lambda: self.seek(-10)).pack(side="left")

        ttk.Button(top, text="+10 sec",
                   command=lambda: self.seek(10)).pack(side="left")

        ttk.Button(top, text="Previous Frame",
                   command=lambda: self.seek_frames(-1)).pack(side="left")

        ttk.Button(top, text="Next Frame",
                   command=lambda: self.seek_frames(1)).pack(side="left")

        self.video_label = ttk.Label(top, text="No video")
        self.video_label.pack(side="left", padx=10)

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(body, bg="#151515")
        self.canvas.pack(side="left", fill="both", expand=True)

        side = ttk.Frame(body, width=350)
        side.pack(side="right", fill="y", padx=10)
        side.pack_propagate(False)

        # PASS 1
        ttk.Label(side, text="PASS 1 — MACHINE CONFIGURATION",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")

        self.region_type = ttk.Combobox(
            side, state="readonly",
            values=[
                "Machine body",
                "Roller",
                "Yellow label",
                "Category",
                "Serial",
                "Red light"
            ])
        self.region_type.current(0)
        self.region_type.pack(fill="x", pady=3)

        self.region_index = ttk.Combobox(
            side, state="readonly",
            values=[str(i) for i in range(1, 19)])
        self.region_index.current(0)
        self.region_index.pack(fill="x", pady=3)

        ttk.Button(side, text="Draw Selected ROI",
                   command=self.begin_roi).pack(fill="x", pady=3)

        ttk.Button(side, text="Save Machine Configuration",
                   command=self.save_config).pack(fill="x", pady=3)

        ttk.Button(side, text="Load Machine Configuration",
                   command=self.load_config).pack(fill="x", pady=3)

        ttk.Separator(side).pack(fill="x", pady=10)

        # PASS 2
        ttk.Label(side, text="PASS 2 — INSPECTION",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")

        ttk.Button(side, text="Start Inspection",
                   command=self.start_inspection).pack(fill="x", pady=3)

        ttk.Label(side, text="Expected number count").pack(anchor="w")

        self.expected_var = tk.StringVar(value="18")
        ttk.Entry(side, textvariable=self.expected_var).pack(fill="x")

        ttk.Button(side, text="Inspect Current Frame",
                   command=self.inspect_frame).pack(fill="x", pady=3)

        ttk.Button(side, text="Extract Number From Close-up",
                   command=self.extract_number).pack(fill="x", pady=3)

        ttk.Button(side, text="Export Inspection Results",
                   command=self.export_results).pack(fill="x", pady=3)

        self.status = ttk.Label(side, text="Ready", wraplength=330)
        self.status.pack(anchor="w", pady=10)

        self.results_text = tk.Text(side, height=15)
        self.results_text.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.mouse_down)
        self.canvas.bind("<B1-Motion>", self.mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)

    # ---------------------------------------------------------
    # VIDEO
    # ---------------------------------------------------------

    def select_video(self):
        path = filedialog.askopenfilename(
            filetypes=[("Videos", "*.mp4 *.avi *.mov *.mkv")])

        if not path:
            return

        self.stop_video()

        if self.cap:
            self.cap.release()

        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            messagebox.showerror("Video", "Cannot open video.")
            return

        self.video_path = Path(path)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.frame_index = 0

        self.video_label.config(text=self.video_path.name)

        # Do not clear machine_config here.
        self.read_frame(0)

    def read_frame(self, index):
        if not self.cap:
            return

        count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        index = max(0, min(index, count - 1))

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self.cap.read()

        if ok:
            self.frame = frame
            self.frame_index = index
            self.render()

    def seek(self, seconds):
        self.read_frame(
            self.frame_index + int(seconds * self.fps))

    def seek_frames(self, count):
        self.read_frame(self.frame_index + count)

    def toggle_play(self):
        self.playing = not self.playing
        if self.playing:
            self.play_loop()

    def play_loop(self):
        if not self.playing:
            return

        self.read_frame(self.frame_index + 1)
        self.root.after(
            max(1, int(1000 / self.fps)),
            self.play_loop
        )

    def stop_video(self):
        self.playing = False

    # ---------------------------------------------------------
    # ROI CONFIGURATION
    # ---------------------------------------------------------

    def begin_roi(self):
        if self.frame is None:
            messagebox.showwarning("Video", "Select a video first.")
            return

        kind = self.region_type.get()

        if kind == "Roller":
            self.roi_target = f"roller_{self.region_index.get()}"
        elif kind == "Yellow label":
            self.roi_target = f"label_{self.region_index.get()}"
        else:
            self.roi_target = {
                "Machine body": "machine_body",
                "Category": "category",
                "Serial": "serial",
                "Red light": "red_light"
            }[kind]

        self.roi_drawing = True
        self.status.config(text=f"Draw {self.roi_target} ROI")

    def mouse_down(self, event):
        if not self.roi_drawing:
            return

        self.drag_start = (event.x, event.y)
        self.drag_end = self.drag_start

    def mouse_move(self, event):
        if not self.roi_drawing or not self.drag_start:
            return

        self.drag_end = (event.x, event.y)
        self.render()

        self.canvas.create_rectangle(
            *self.drag_start,
            *self.drag_end,
            outline="red",
            width=2
        )

    def mouse_up(self, event):
        if not self.roi_drawing or not self.drag_start:
            return

        self.drag_end = (event.x, event.y)

        x1, y1 = self.drag_start
        x2, y2 = self.drag_end

        # Convert displayed canvas coordinates to frame coordinates.
        sx = self.display_scale
        ox = self.display_offset[0]
        oy = self.display_offset[1]

        x = int((min(x1, x2) - ox) / sx)
        y = int((min(y1, y2) - oy) / sx)
        w = int(abs(x2 - x1) / sx)
        h = int(abs(y2 - y1) / sx)

        fh, fw = self.frame.shape[:2]

        x = max(0, min(x, fw - 1))
        y = max(0, min(y, fh - 1))
        w = max(1, min(w, fw - x))
        h = max(1, min(h, fh - y))

        if self.roi_target.startswith("roller_"):
            self.machine_config["rollers"][
                self.roi_target.split("_")[1]
            ] = [x, y, w, h]

        elif self.roi_target.startswith("label_"):
            self.machine_config["yellow_labels"][
                self.roi_target.split("_")[1]
            ] = [x, y, w, h]

        else:
            self.machine_config[self.roi_target] = [x, y, w, h]

        self.roi_drawing = False
        self.drag_start = None
        self.drag_end = None

        self.status.config(text=f"Saved ROI: {self.roi_target}")
        self.render()

    def save_config(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        path = filedialog.asksaveasfilename(
            initialdir=str(CONFIG_DIR),
            defaultextension=".json",
            filetypes=[("JSON", "*.json")])

        if not path:
            return

        data = {
            "version": 1,
            "machine_config": self.machine_config,
            "reference_video": {
                "filename": self.video_path.name if self.video_path else None,
                "width": self.frame.shape[1],
                "height": self.frame.shape[0]
            },
            "saved_at": datetime.now().isoformat()
        }

        Path(path).write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )

        messagebox.showinfo("Saved", "Machine configuration saved.")

    def load_config(self):
        path = filedialog.askopenfilename(
            initialdir=str(CONFIG_DIR),
            filetypes=[("JSON", "*.json")])

        if not path:
            return

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.machine_config = data["machine_config"]

        messagebox.showinfo(
            "Loaded",
            "Machine configuration loaded.\nSelect inspection video next."
        )

    # ---------------------------------------------------------
    # PASS 2
    # ---------------------------------------------------------

    def start_inspection(self):
        if not self.machine_config.get("machine_body"):
            messagebox.showwarning("Configuration", "Load machine configuration.")
            return

        if not self.cap:
            messagebox.showwarning("Video", "Select inspection video.")
            return

        self.expected_count = int(self.expected_var.get())
        self.results = []
        self.roll_events = []
        self.red_light_events = []
        self.previous_roller_frames = {}

        self.status.config(
            text=f"Inspection started: 0/{self.expected_count}")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def inspect_frame(self):
        if self.frame is None:
            return

        frame = self.frame

        # Monitor red light ROI.
        red_roi = self.machine_config.get("red_light")
        if red_roi:
            red_on = self.detect_red_light(frame, red_roi)
            self.red_light_events.append({
                "frame": self.frame_index,
                "red_on": red_on
            })

        # Monitor roller activity.
        movement = self.detect_roller_movement(frame)

        self.roll_events.append({
            "frame": self.frame_index,
            "movement": movement
        })

        # Detect likely close-up frame.
        closeup = self.detect_closeup(frame)

        if closeup:
            self.save_closeup(frame)

        self.status.config(
            text=f"Frame {self.frame_index}: "
                 f"movement={movement}, close-up={closeup}")

    @staticmethod
    def detect_red_light(frame, roi):
        x, y, w, h = roi
        crop = frame[y:y+h, x:x+w]

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

        mask1 = cv2.inRange(
            hsv, (0, 100, 100), (10, 255, 255))
        mask2 = cv2.inRange(
            hsv, (160, 100, 100), (180, 255, 255))

        red_pixels = cv2.countNonZero(mask1 + mask2)
        total = max(1, w * h)

        return red_pixels / total > 0.05

    def detect_roller_movement(self, frame):
        moved = False

        for index, roi in self.machine_config["rollers"].items():
            x, y, w, h = roi
            crop = cv2.cvtColor(
                frame[y:y+h, x:x+w],
                cv2.COLOR_BGR2GRAY
            )

            previous = self.previous_roller_frames.get(index)

            if previous is not None:
                diff = cv2.absdiff(crop, previous)
                motion = cv2.countNonZero(
                    cv2.threshold(diff, 25, 255,
                                  cv2.THRESH_BINARY)[1]
                )

                if motion / max(1, w * h) > 0.08:
                    moved = True

            self.previous_roller_frames[index] = crop

        if moved:
            self.roll_active = True

        elif self.roll_active:
            self.roll_active = False

        return moved

    @staticmethod
    def detect_closeup(frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Focus metric (Laplacian variance).
        focus = cv2.Laplacian(gray, cv2.CV_64F).var()

        return focus > 100

    def save_closeup(self, frame):
        path = OUTPUT_DIR / f"closeup_{self.frame_index}.jpg"
        cv2.imwrite(str(path), frame)

    # ---------------------------------------------------------
    # OCR + CONFIDENCE
    # ---------------------------------------------------------

    def extract_number(self):
        if self.frame is None:
            return

        if OCR is None:
            messagebox.showerror(
                "OCR unavailable",
                "Install EasyOCR: pip install easyocr"
            )
            return

        crop = self.frame

        category_roi = self.machine_config.get("category")
        if category_roi:
            x, y, w, h = category_roi
            crop = self.frame[y:y+h, x:x+w]

        results = OCR.readtext(crop)

        candidates = []

        for box, text, confidence in results:
            text = re.sub(r"\D", "", text)

            if len(text) == 4:
                candidates.append({
                    "number": text,
                    "confidence": float(confidence)
                })

        if not candidates:
            messagebox.showwarning("OCR", "No four-digit number detected.")
            return

        best = max(candidates, key=lambda item: item["confidence"])

        record = {
            "sequence": len(self.results) + 1,
            "number": best["number"],
            "confidence": best["confidence"],
            "frame": self.frame_index,
            "time_seconds": self.frame_index / self.fps
        }

        self.results.append(record)

        self.results_text.insert(
            "end",
            f"{record['sequence']}. {record['number']} "
            f"confidence={record['confidence']:.3f}\n"
        )

        self.status.config(
            text=f"Captured {len(self.results)}/{self.expected_count}"
        )

        if len(self.results) >= self.expected_count:
            self.status.config(text="Expected number count reached.")

    # ---------------------------------------------------------
    # EXPORT
    # ---------------------------------------------------------

    def export_results(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        path = OUTPUT_DIR / "inspection.json"

        data = {
            "video": str(self.video_path),
            "expected_count": self.expected_count,
            "actual_count": len(self.results),
            "results": self.results,
            "roller_events": self.roll_events,
            "red_light_events": self.red_light_events
        }

        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        messagebox.showinfo("Export", f"Saved:\n{path}")

    # ---------------------------------------------------------
    # RENDER
    # ---------------------------------------------------------

    def render(self):
        if self.frame is None:
            return

        self.canvas.delete("all")

        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        h, w = self.frame.shape[:2]

        scale = min(cw / w, ch / h)

        dw = int(w * scale)
        dh = int(h * scale)

        ox = (cw - dw) // 2
        oy = (ch - dh) // 2

        self.display_scale = scale
        self.display_offset = (ox, oy)

        resized = cv2.resize(self.frame, (dw, dh))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        self.image = tk.PhotoImage(
            width=dw,
            height=dh
        )

        # PIL handles image display efficiently.
        from PIL import Image, ImageTk
        self.image = ImageTk.PhotoImage(Image.fromarray(rgb))

        self.canvas.create_image(
            ox, oy, anchor="nw", image=self.image
        )

        self.draw_rois()

    def draw_rois(self):
        layout = self.machine_config

        for key, roi in layout.items():
            if key in ("rollers", "yellow_labels"):
                for idx, box in roi.items():
                    self.draw_roi(f"{key}:{idx}", box)
            elif roi:
                self.draw_roi(key, roi)

    def draw_roi(self, label, roi):
        x, y, w, h = roi

        scale = self.display_scale
        ox, oy = self.display_offset

        self.canvas.create_rectangle(
            ox + x * scale,
            oy + y * scale,
            ox + (x+w) * scale,
            oy + (y+h) * scale,
            outline="yellow",
            width=2
        )

        self.canvas.create_text(
            ox + x * scale,
            oy + y * scale,
            text=label,
            anchor="nw",
            fill="yellow"
        )


def main():
    root = tk.Tk()
    LotteryVideoWorkflow(root)
    root.mainloop()


if __name__ == "__main__":
    main()

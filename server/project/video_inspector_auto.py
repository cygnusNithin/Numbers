
import cv2
import json
import re
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime

from digit_capture_v2 import DigitStore, classify_frame, propose_boxes, ANALYSIS_W

try:
    import easyocr
    OCR = easyocr.Reader(["en"], gpu=False, verbose=False)
except Exception:
    OCR = None

HERE = Path(__file__).resolve().parent
CONFIG_DIR = HERE / "video_configs"
OUTPUT_DIR = HERE / "inspection_results"

# Detection tuning
MOTION_SCALE = 0.5
MOTION_THRESHOLD = 18
MOTION_RATIO = 0.025
MIN_MOVING_ROLLERS = 2
ROLL_CONFIRM = 3
STOP_CONFIRM = 10
CLOSE_CONFIRM = 4
CLOSE_READ_INTERVAL = 0.5
FONT_MIN_SCORE = 0.50
FONT_MIN_MARGIN = 0.035
OCR_MIN_SCORE = 0.45


class LotteryVideoWorkflow:
    REGIONS = [
        "Machine body", "Roller", "Yellow label",
        "Category", "Serial", "Red light"
    ]

    def __init__(self, root):
        self.root = root
        root.title("Lottery Machine Automatic Inspection")
        root.geometry("1550x920")

        self.cap = None
        self.video_path = None
        self.frame = None
        self.fps = 30.0
        self.frame_index = 0
        self.total_frames = 1
        self.playing = False
        self.play_job = None

        self.config_path = None
        self.machine_config = {
            "positions": {"A": self.empty_layout(), "B": self.empty_layout()}
        }
        self.active_position = tk.StringVar(value="A")

        self.roi_history = []
        self.roi_target = None
        self.roi_drawing = False
        self.drag_start = self.drag_end = None
        self.scale = 1.0
        self.offset = (0, 0)
        self.image = None

        self.inspection_active = False
        self.expected_count = 18
        self.results = []
        self.roller_events = []
        self.machine_events = []
        self.red_events = []

        self.font_store = DigitStore(HERE / "digit_fonts")

        self.reset_detection()
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    @staticmethod
    def empty_layout():
        return {
            "machine_body": None,
            "rollers": {},
            "yellow_labels": {},
            "category": None,
            "serial": None,
            "red_light": None
        }

    @staticmethod
    def next_number(mapping):
        for n in range(1, 19):
            if str(n) not in mapping:
                return n
        return None

    # ------------------------------------------------ UI

    def build_ui(self):
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=6)

        for label, fn in [
            ("Select Video", self.select_video),
            ("Play / Pause", self.toggle_play),
            ("-10 sec", lambda: self.seek_seconds(-10)),
            ("+10 sec", lambda: self.seek_seconds(10)),
            ("Previous Frame", lambda: self.seek_frames(-1)),
            ("Next Frame", lambda: self.seek_frames(1))
        ]:
            ttk.Button(top, text=label, command=fn).pack(side="left", padx=2)

        self.video_label = ttk.Label(top, text="No video")
        self.video_label.pack(side="left", padx=8)

        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(main, bg="#151515", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        side = ttk.Frame(main, width=380)
        side.pack(side="right", fill="y", padx=8, pady=4)
        side.pack_propagate(False)

        ttk.Label(
            side, text="PASS 1 — MACHINE CONFIGURATION",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w")

        ttk.Label(side, text="ROI Position").pack(anchor="w")
        self.position_box = ttk.Combobox(
            side, textvariable=self.active_position,
            values=["A", "B"], state="readonly"
        )
        self.position_box.pack(fill="x", pady=2)
        self.position_box.bind(
            "<<ComboboxSelected>>", lambda e: self.status_refresh()
        )

        ttk.Label(side, text="ROI Region").pack(anchor="w")
        self.region_box = ttk.Combobox(
            side, values=self.REGIONS, state="readonly"
        )
        self.region_box.current(0)
        self.region_box.pack(fill="x", pady=2)

        ttk.Button(side, text="Draw Selected ROI", command=self.begin_roi).pack(fill="x", pady=2)
        ttk.Button(side, text="Remove Last Mark", command=self.undo_roi).pack(fill="x", pady=2)
        ttk.Button(side, text="Save Machine Configuration", command=self.save_config).pack(fill="x", pady=2)
        ttk.Button(side, text="Load Machine Configuration", command=self.load_config).pack(fill="x", pady=2)

        self.config_status = ttk.Label(side, text="A: 0/40 | B: 0/40")
        self.config_status.pack(anchor="w", pady=5)

        ttk.Separator(side).pack(fill="x", pady=7)

        ttk.Label(
            side, text="PASS 2 — AUTOMATIC INSPECTION",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w")

        ttk.Button(side, text="Start / Reset Inspection", command=self.start_inspection).pack(fill="x", pady=2)

        ttk.Label(side, text="Expected number count").pack(anchor="w")
        self.expected_var = tk.StringVar(value="18")
        ttk.Entry(side, textvariable=self.expected_var).pack(fill="x", pady=2)

        ttk.Button(
            side, text="Inspect Current Frame",
            command=self.inspect_current_frame
        ).pack(fill="x", pady=2)

        ttk.Button(side, text="Export Inspection Results", command=self.export_results).pack(fill="x", pady=2)

        self.phase_status = ttk.Label(side, text="PHASE: IDLE", font=("Segoe UI", 10, "bold"))
        self.phase_status.pack(anchor="w", pady=4)

        self.inspect_status = ttk.Label(
            side, text="Load configuration, select video, start inspection.",
            wraplength=360
        )
        self.inspect_status.pack(anchor="w", pady=4)

        self.result_box = tk.Text(side, height=17, wrap="word")
        self.result_box.pack(fill="both", expand=True)

        self.canvas.bind("<Configure>", lambda e: self.render())
        self.canvas.bind("<ButtonPress-1>", self.mouse_down)
        self.canvas.bind("<B1-Motion>", self.mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)

    def log(self, text):
        self.result_box.insert("end", str(text) + "\n")
        self.result_box.see("end")

    # ------------------------------------------------ VIDEO

    def select_video(self):
        p = filedialog.askopenfilename(
            filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv"), ("All", "*.*")]
        )
        if not p:
            return

        self.stop_play()
        if self.cap:
            self.cap.release()

        self.cap = cv2.VideoCapture(p)
        if not self.cap.isOpened():
            messagebox.showerror("Video", "Cannot open video.")
            return

        self.video_path = Path(p)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.total_frames = max(1, int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1))
        self.video_label.config(text=self.video_path.name)
        self.read_frame(0)

    def read_frame(self, index):
        if not self.cap:
            return

        index = max(0, min(int(index), self.total_frames - 1))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self.cap.read()

        if ok:
            self.frame = frame
            self.frame_index = index
            self.render()

    def seek_seconds(self, seconds):
        self.read_frame(self.frame_index + int(seconds * self.fps))

    def seek_frames(self, count):
        self.read_frame(self.frame_index + count)

    def toggle_play(self):
        if not self.cap:
            messagebox.showwarning("Video", "Select a video first.")
            return

        if self.playing:
            self.stop_play()
        else:
            self.playing = True
            self.play_loop()

    def stop_play(self):
        self.playing = False
        if self.play_job:
            try:
                self.root.after_cancel(self.play_job)
            except tk.TclError:
                pass
            self.play_job = None

    def play_loop(self):
        if not self.playing or not self.cap:
            return

        if self.frame_index + 1 >= self.total_frames:
            self.stop_play()
            return

        self.read_frame(self.frame_index + 1)

        # Critical: automatic inspection happens during playback.
        if self.inspection_active:
            self.auto_inspect(self.frame)

        self.play_job = self.root.after(
            max(1, int(1000 / self.fps)), self.play_loop
        )

    # ------------------------------------------------ ROI

    def begin_roi(self):
        if self.frame is None:
            messagebox.showwarning("Video", "Select reference video first.")
            return

        pos = self.active_position.get()
        kind = self.region_box.get()
        layout = self.machine_config["positions"][pos]

        if kind == "Roller":
            n = self.next_number(layout["rollers"])
            if n is None:
                messagebox.showinfo("Complete", "18 rollers already marked.")
                return
            self.roi_target = ("rollers", str(n))

        elif kind == "Yellow label":
            n = self.next_number(layout["yellow_labels"])
            if n is None:
                messagebox.showinfo("Complete", "18 labels already marked.")
                return
            self.roi_target = ("yellow_labels", str(n))

        else:
            key = {
                "Machine body": "machine_body",
                "Category": "category",
                "Serial": "serial",
                "Red light": "red_light"
            }[kind]
            self.roi_target = (key, None)

        self.roi_drawing = True
        self.drag_start = self.drag_end = None

    def mouse_down(self, e):
        if self.roi_drawing:
            self.drag_start = self.drag_end = (e.x, e.y)

    def mouse_move(self, e):
        if self.roi_drawing and self.drag_start:
            self.drag_end = (e.x, e.y)
            self.render()

    def mouse_up(self, e):
        if not self.roi_drawing or not self.drag_start or self.frame is None:
            return

        self.drag_end = (e.x, e.y)
        x1, y1 = self.drag_start
        x2, y2 = self.drag_end
        ox, oy = self.offset

        x = int((min(x1, x2) - ox) / self.scale)
        y = int((min(y1, y2) - oy) / self.scale)
        w = int(abs(x2 - x1) / self.scale)
        h = int(abs(y2 - y1) / self.scale)

        fh, fw = self.frame.shape[:2]
        x, y = max(0, min(x, fw - 1)), max(0, min(y, fh - 1))
        w, h = max(1, min(w, fw - x)), max(1, min(h, fh - y))

        if w < 3 or h < 3:
            self.roi_drawing = False
            self.drag_start = self.drag_end = None
            self.render()
            return

        pos = self.active_position.get()
        key, idx = self.roi_target
        layout = self.machine_config["positions"][pos]

        old = layout[key].get(idx) if idx is not None else layout[key]

        if idx is not None:
            layout[key][idx] = [x, y, w, h]
        else:
            layout[key] = [x, y, w, h]

        self.roi_history.append({
            "position": pos, "key": key, "index": idx, "old": old
        })

        self.roi_drawing = False
        self.drag_start = self.drag_end = None
        self.status_refresh()
        self.render()

    def undo_roi(self):
        if not self.roi_history:
            return

        item = self.roi_history.pop()
        layout = self.machine_config["positions"][item["position"]]
        key, idx, old = item["key"], item["index"], item["old"]

        if idx is not None:
            if old is None:
                layout[key].pop(idx, None)
            else:
                layout[key][idx] = old
        else:
            layout[key] = old

        self.status_refresh()
        self.render()

    def status_refresh(self):
        def count(layout):
            return (
                sum(layout[k] is not None for k in
                    ("machine_body", "category", "serial", "red_light"))
                + len(layout["rollers"]) + len(layout["yellow_labels"])
            )

        a = count(self.machine_config["positions"]["A"])
        b = count(self.machine_config["positions"]["B"])
        self.config_status.config(text=f"A: {a}/40 | B: {b}/40")

    # ------------------------------------------------ CONFIG SAVE/LOAD

    def save_config(self):
        if self.frame is None or not self.video_path:
            messagebox.showwarning("Reference", "Select reference video.")
            return

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        p = filedialog.asksaveasfilename(
            initialdir=str(CONFIG_DIR),
            initialfile=f"{self.video_path.stem}_machine.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")]
        )
        if not p:
            return

        data = {
            "configuration_version": 3,
            "machine_config": self.machine_config,
            "reference_video": {
                "filename": self.video_path.name,
                "width": self.frame.shape[1],
                "height": self.frame.shape[0]
            },
            "updated_at": datetime.now().isoformat()
        }

        Path(p).write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.config_path = str(Path(p).resolve())
        messagebox.showinfo("Saved", "Configuration saved.")

    def load_config(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        p = filedialog.askopenfilename(
            initialdir=str(CONFIG_DIR), filetypes=[("JSON", "*.json")]
        )
        if not p:
            return

        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            cfg = data.get("machine_config", {})

            if "positions" not in cfg:
                old = cfg
                cfg = {"positions": {"A": self.empty_layout(), "B": self.empty_layout()}}
                for key in self.empty_layout():
                    cfg["positions"]["A"][key] = old.get(
                        key, {} if key in ("rollers", "yellow_labels") else None
                    )

            for pos in ("A", "B"):
                cfg["positions"].setdefault(pos, self.empty_layout())
                for key, value in self.empty_layout().items():
                    cfg["positions"][pos].setdefault(
                        key, {} if key in ("rollers", "yellow_labels") else None
                    )

            self.machine_config = cfg
            self.config_path = str(Path(p).resolve())
            self.roi_history.clear()
            self.status_refresh()
            self.render()
            messagebox.showinfo("Loaded", "Position A and B loaded.")

        except Exception as exc:
            messagebox.showerror("Config", str(exc))

    # ------------------------------------------------ AUTO INSPECTION

    def reset_detection(self):
        self.previous_rollers = {"A": {}, "B": {}}
        self.rolling_streak = 0
        self.still_streak = 0
        self.machine_streak = 0
        self.rolling_detected = False
        self.closeup_streak = 0
        self.last_capture_time = 0
        self.last_capture_frame = -1
        self.last_scene = "other"
        self.active_position = None

    def start_inspection(self):
        if not self.config_path:
            messagebox.showwarning("Config", "Load saved configuration first.")
            return
        if not self.cap or self.frame is None:
            messagebox.showwarning("Video", "Select inspection video.")
            return

        try:
            count = int(self.expected_var.get())
            if count <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Count", "Expected count must be positive.")
            return

        self.expected_count = count
        self.results = []
        self.roller_events = []
        self.machine_events = []
        self.red_events = []
        self.reset_detection()
        self.inspection_active = True

        self.result_box.delete("1.0", "end")
        self.phase_status.config(text="PHASE: WAIT MACHINE")
        self.inspect_status.config(text=f"Inspection active: 0/{count}. Press Play.")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        self.log(f"Digit font templates: {self.font_store.counts()}")
        self.log("Automatic inspection started.")

    @staticmethod
    def crop_roi(frame, roi):
        if not roi:
            return None

        x, y, w, h = map(int, roi)
        H, W = frame.shape[:2]
        x, y = max(0, x), max(0, y)
        x2, y2 = min(W, x + w), min(H, y + h)

        if x2 <= x or y2 <= y:
            return None

        crop = frame[y:y2, x:x2]
        return crop if crop.size else None

    def machine_present(self, frame, roi):
        crop = self.crop_roi(frame, roi)
        if crop is None:
            return False

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        return gray.std() > 7 and cv2.Canny(gray, 50, 120).mean() > 3

    def choose_position(self, frame):
        scores = {}

        for pos, layout in self.machine_config["positions"].items():
            crop = self.crop_roi(frame, layout.get("machine_body"))
            if crop is None:
                scores[pos] = 0
                continue

            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            scores[pos] = float(gray.std() + cv2.Canny(gray, 50, 120).mean())

        return max(scores, key=scores.get)

    def roller_motion(self, frame, pos):
        moving = []
        previous = self.previous_rollers[pos]
        rollers = self.machine_config["positions"][pos]["rollers"]

        for idx, roi in rollers.items():
            crop = self.crop_roi(frame, roi)
            if crop is None:
                continue

            small = cv2.resize(
                crop, None, fx=MOTION_SCALE, fy=MOTION_SCALE,
                interpolation=cv2.INTER_AREA
            )
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            old = previous.get(idx)

            if old is not None and old.shape == gray.shape:
                diff = cv2.absdiff(gray, old)
                mask = cv2.threshold(
                    diff, MOTION_THRESHOLD, 255, cv2.THRESH_BINARY
                )[1]
                ratio = cv2.countNonZero(mask) / float(mask.size)

                if ratio >= MOTION_RATIO:
                    moving.append(idx)

            previous[idx] = gray

        return moving

    def red_detect(self, frame, roi):
        crop = self.crop_roi(frame, roi)
        if crop is None:
            return False

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        a = cv2.inRange(hsv, (0, 90, 90), (12, 255, 255))
        b = cv2.inRange(hsv, (165, 90, 90), (180, 255, 255))
        ratio = cv2.countNonZero(cv2.bitwise_or(a, b)) / float(crop.shape[0] * crop.shape[1])
        return ratio >= 0.05

    def auto_inspect(self, frame):
        pos = self.choose_position(frame)
        layout = self.machine_config["positions"][pos]

        present = self.machine_present(frame, layout.get("machine_body"))
        moving = self.roller_motion(frame, pos)
        red = self.red_detect(frame, layout.get("red_light"))

        scene_info = classify_frame(frame)
        scene = scene_info.get("scene", "other")

        self.machine_streak = self.machine_streak + 1 if present else 0
        self.rolling_streak = (
            self.rolling_streak + 1
            if len(moving) >= MIN_MOVING_ROLLERS else 0
        )
        self.still_streak = self.still_streak + 1 if not moving else 0

        self.roller_events.append({
            "frame": self.frame_index,
            "position": pos,
            "moving_rollers": moving,
            "red_on": red,
            "scene": scene
        })

        if present and self.machine_streak == 1:
            self.log(f"{self.time_text()} Machine detected at position {pos}")

        # Stage 1: machine + sustained roller movement.
        if not self.rolling_detected:
            if self.machine_streak >= 2 and self.rolling_streak >= ROLL_CONFIRM:
                self.rolling_detected = True
                self.active_position = pos
                self.closeup_streak = 0
                self.phase_status.config(text=f"PHASE: ROLLING ({pos})")
                self.log(f"{self.time_text()} Rolling confirmed: {len(moving)} rollers")
            else:
                self.phase_status.config(text=f"PHASE: WAIT ROLL ({len(moving)} moving)")
                self.inspect_status.config(
                    text=f"Machine={present} Position={pos} Moving={len(moving)} Results={len(self.results)}"
                )
                return

        # Stage 2: rolling is confirmed; wait for stable digit close-up.
        if self.rolling_detected:
            self.closeup_streak = self.closeup_streak + 1 if scene == "closeup" else 0

            self.phase_status.config(
                text=f"PHASE: WAIT CLOSE-UP ({self.closeup_streak}/{CLOSE_CONFIRM})"
            )

            self.inspect_status.config(
                text=f"Position={pos} Moving={len(moving)} Scene={scene} "
                     f"Close={self.closeup_streak} Results={len(self.results)}"
            )

            if scene == "closeup" and self.closeup_streak >= CLOSE_CONFIRM:
                now = time.monotonic()
                if now - self.last_capture_time >= CLOSE_READ_INTERVAL:
                    self.last_capture_time = now
                    self.capture_number(frame, scene_info, pos)

            # Reset cycle only after close-up ends and rollers become still.
            if scene != "closeup" and self.still_streak >= STOP_CONFIRM:
                self.rolling_detected = False
                self.active_position = None
                self.closeup_streak = 0
                self.phase_status.config(text="PHASE: WAIT NEXT ROLL")

    # ------------------------------------------------ DIGIT CAPTURE

    def capture_number(self, frame, scene_info, pos):
        close = scene_info.get("close")
        if not close:
            return

        h, w = frame.shape[:2]
        factor = w / float(ANALYSIS_W)

        hx1, hy1, hx2, hy2 = close["housing"]
        pad = 8

        x1 = max(0, int(hx1 * factor) - pad)
        y1 = max(0, int(hy1 * factor) - pad)
        x2 = min(w, int(hx2 * factor) + pad)
        y2 = min(h, int(hy2 * factor) + pad)

        housing = frame[y1:y2, x1:x2]
        if housing.size == 0:
            return

        boxes, detected = propose_boxes(housing)
        if len(boxes) != 4:
            return

        digits, scores = [], []

        for box in boxes:
            x, y, bw, bh = box
            crop = housing[y:y + bh, x:x + bw]

            digit, score, second_digit, second_score, normalized = self.font_store.match(crop)

            chosen = ""
            source = "font"

            if (
                digit and score >= FONT_MIN_SCORE
                and score - second_score >= FONT_MIN_MARGIN
            ):
                chosen = digit

            # OCR fallback only when font match is uncertain.
            if not chosen and OCR is not None and normalized is not None:
                try:
                    ocr_results = OCR.recognize(
                        normalized, allowlist="0123456789", detail=1
                    )

                    candidates = [
                        (re.sub(r"\D", "", str(item[1])), float(item[2]))
                        for item in ocr_results if len(item) >= 3
                    ]
                    candidates = [
                        (d, c) for d, c in candidates
                        if len(d) == 1 and c >= OCR_MIN_SCORE
                    ]

                    if candidates:
                        chosen, score = max(candidates, key=lambda z: z[1])
                        source = "ocr"
                except Exception:
                    pass

            digits.append(chosen if chosen else "?")
            scores.append(round(float(score), 4))

        number = "".join(digits)

        # Don't record an uncertain number as a valid result.
        if "?" in number:
            self.last_capture_frame = self.frame_index
            self.save_closeup(frame, pos, number)
            self.inspect_status.config(text=f"UNCERTAIN {number}; close-up saved")
            self.log(f"{self.time_text()} Uncertain {number}; scores={scores}")
            return

        if self.frame_index == self.last_capture_frame:
            return

        item = {
            "sequence": len(self.results) + 1,
            "number": number,
            "digit_scores": scores,
            "minimum_score": min(scores),
            "position": pos,
            "frame": self.frame_index,
            "time_seconds": round(self.frame_index / self.fps, 3),
            "method": "digit_fonts",
            "boxes_detected": bool(detected),
            "housing_roi": [x1, y1, x2 - x1, y2 - y1]
        }

        self.results.append(item)
        self.last_capture_frame = self.frame_index
        self.save_closeup(frame, pos, number)

        self.log(
            f"{self.time_text()} RESULT {item['sequence']:02d}: "
            f"{number} scores={scores}"
        )

        self.inspect_status.config(
            text=f"Captured {number} | {len(self.results)}/{self.expected_count}"
        )

        if len(self.results) >= self.expected_count:
            self.inspection_active = False
            self.stop_play()
            self.phase_status.config(text="PHASE: COMPLETE")
            messagebox.showinfo("Complete", f"Captured {len(self.results)} numbers.")

    def save_closeup(self, frame, pos, number):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"closeup_{pos}_{self.frame_index:08d}_{number}.jpg"
        cv2.imwrite(str(path), frame)

    def inspect_current_frame(self):
        if not self.inspection_active or self.frame is None:
            return
        pos = self.choose_position(self.frame)
        self.capture_number(self.frame, classify_frame(self.frame), pos)

    def time_text(self):
        sec = int(self.frame_index / self.fps)
        return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"

    # ------------------------------------------------ EXPORT

    def export_results(self):
        if not self.video_path:
            messagebox.showwarning("Video", "Select video first.")
            return

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        p = filedialog.asksaveasfilename(
            initialdir=str(OUTPUT_DIR),
            defaultextension=".json",
            initialfile="inspection_results.json",
            filetypes=[("JSON", "*.json")]
        )
        if not p:
            return

        data = {
            "video": str(self.video_path),
            "configuration": self.config_path,
            "expected_count": self.expected_count,
            "result_count": len(self.results),
            "results": self.results,
            "roller_events": self.roller_events,
            "machine_events": self.machine_events,
            "red_light_events": self.red_events,
            "digit_font_counts": self.font_store.counts(),
            "exported_at": datetime.now().isoformat()
        }

        Path(p).write_text(json.dumps(data, indent=2), encoding="utf-8")
        messagebox.showinfo("Export", f"Saved {p}")

    # ------------------------------------------------ RENDER

    def render(self):
        if not hasattr(self, "canvas") or self.frame is None:
            return

        self.canvas.delete("all")
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        fh, fw = self.frame.shape[:2]

        self.scale = min(cw / fw, ch / fh)
        dw, dh = int(fw * self.scale), int(fh * self.scale)
        ox, oy = (cw - dw) // 2, (ch - dh) // 2
        self.offset = (ox, oy)

        rgb = cv2.cvtColor(cv2.resize(self.frame, (dw, dh)), cv2.COLOR_BGR2RGB)
        from PIL import Image, ImageTk
        self.image = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.canvas.create_image(ox, oy, anchor="nw", image=self.image)

        for pos, layout in self.machine_config["positions"].items():
            color = "#ffe600" if pos == "A" else "#00e5ff"

            for key, value in layout.items():
                if key in ("rollers", "yellow_labels"):
                    for idx, roi in value.items():
                        self.draw_roi(f"{pos}:{key}:{idx}", roi, color)
                elif value:
                    self.draw_roi(f"{pos}:{key}", value, color)

        if self.roi_drawing and self.drag_start and self.drag_end:
            self.canvas.create_rectangle(
                *self.drag_start, *self.drag_end, outline="red", width=2
            )

    def draw_roi(self, label, roi, color):
        x, y, w, h = roi
        ox, oy = self.offset
        s = self.scale

        self.canvas.create_rectangle(
            ox + x * s, oy + y * s,
            ox + (x + w) * s, oy + (y + h) * s,
            outline=color, width=2
        )

        self.canvas.create_text(
            ox + x * s + 2, oy + y * s + 2,
            text=label, anchor="nw", fill=color,
            font=("Segoe UI", 8, "bold")
        )

    def close(self):
        self.stop_play()
        if self.cap:
            self.cap.release()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    LotteryVideoWorkflow(root)
    root.mainloop()

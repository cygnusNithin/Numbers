
"""
Integrated Kerala Lottery Video Inspector.

Features:
- Select and play lottery videos.
- Extract draw serial from the video filename.
- Look up draw metadata and prize-category counts in MongoDB.
- Select a prize category and load its expected number count.
- Mark multiple machine-roll intervals.
- Select and redraw the machine ROI.
- Detect candidate yellow labels inside the machine ROI.
- Save a video configuration JSON for the next processing stage.

Important:
- MongoDB is used only for draw metadata and expected counts.
- Winning number values are never retrieved or used.
- Yellow-label detection identifies candidate regions only. It does not
  recognize the printed group number or associate it with a housing.
"""

import cv2
import json
import re
import logging
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk


# ============================================================
# CONFIGURATION
# ============================================================

MONGODB_URI = "mongodb://localhost:27017"
DB_NAME = "numbergrid"
COLLECTION_NAME = "absolute_data_v2"

CONFIG_DIR = Path(__file__).resolve().parent / "video_configs"

DEFAULT_FPS = 30.0

# Yellow label HSV range.
# These values are initial detection settings and may need adjustment
# against actual video frames.
YELLOW_LOWER = (15, 70, 90)
YELLOW_UPPER = (40, 255, 255)

MIN_YELLOW_LABEL_AREA = 80
MAX_YELLOW_LABEL_AREA = 50000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("VideoInspector")


# ============================================================
# VIDEO INSPECTOR
# ============================================================

class VideoInspector:

    def __init__(self, root):

        self.root = root

        self.root.title("Kerala Lottery Video Inspector")
        self.root.geometry("1450x900")
        self.root.minsize(1100, 700)

        # ----------------------------------------------------
        # Video
        # ----------------------------------------------------

        self.video_path = None
        self.cap = None

        self.frame_index = 0
        self.frame_count = 0

        self.fps = DEFAULT_FPS

        self.width = 0
        self.height = 0

        self.duration = 0.0

        self.current_frame = None

        # ----------------------------------------------------
        # Playback
        # ----------------------------------------------------

        self.playing = False
        self.after_id = None

        # ----------------------------------------------------
        # Canvas rendering
        # ----------------------------------------------------

        self.tk_image = None

        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0

        # ----------------------------------------------------
        # Machine-roll intervals
        # ----------------------------------------------------

        self.roll_intervals = []

        self.pending_roll_start = None

        # ----------------------------------------------------
        # Machine ROI
        # ----------------------------------------------------

        self.machine_roi = None

        self.roi_mode = False
        self.roi_drag_start = None
        self.roi_drag_current = None

        # ----------------------------------------------------
        # Yellow-label detection
        # ----------------------------------------------------

        self.yellow_candidates = []

        # ----------------------------------------------------
        # MongoDB draw metadata
        # ----------------------------------------------------

        self.draw_serial = None
        self.draw_data = None

        self.prize_categories = []

        self.selected_prize = None
        self.expected_number_count = 0

        # ----------------------------------------------------
        # Build interface
        # ----------------------------------------------------

        self.build_ui()

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close
        )

    # ========================================================
    # UI
    # ========================================================

    def build_ui(self):

        # ----------------------------------------------------
        # Top toolbar
        # ----------------------------------------------------

        top = ttk.Frame(
            self.root,
            padding=8
        )

        top.pack(
            fill="x"
        )

        ttk.Button(
            top,
            text="Select Video",
            command=self.select_video
        ).pack(
            side="left",
            padx=3
        )

        self.file_label = ttk.Label(
            top,
            text="No video selected",
            width=45
        )

        self.file_label.pack(
            side="left",
            padx=8
        )

        ttk.Button(
            top,
            text="Play / Pause",
            command=self.toggle_play
        ).pack(
            side="left",
            padx=3
        )

        ttk.Button(
            top,
            text="◀ Frame",
            command=lambda: self.step_frame(-1)
        ).pack(
            side="left",
            padx=3
        )

        ttk.Button(
            top,
            text="Frame ▶",
            command=lambda: self.step_frame(1)
        ).pack(
            side="left",
            padx=3
        )

        ttk.Button(
            top,
            text="−5s",
            command=lambda: self.seek_seconds(-5)
        ).pack(
            side="left",
            padx=3
        )

        ttk.Button(
            top,
            text="+5s",
            command=lambda: self.seek_seconds(5)
        ).pack(
            side="left",
            padx=3
        )

        # ----------------------------------------------------
        # Main content
        # ----------------------------------------------------

        body = ttk.Frame(
            self.root,
            padding=(8, 0)
        )

        body.pack(
            fill="both",
            expand=True
        )

        # ----------------------------------------------------
        # Video canvas
        # ----------------------------------------------------

        self.canvas = tk.Canvas(
            body,
            bg="#171717",
            highlightthickness=1,
            highlightbackground="#555"
        )

        self.canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        self.canvas.bind(
            "<Configure>",
            lambda event: self.render_frame()
        )

        self.canvas.bind(
            "<ButtonPress-1>",
            self.roi_mouse_down
        )

        self.canvas.bind(
            "<B1-Motion>",
            self.roi_mouse_move
        )

        self.canvas.bind(
            "<ButtonRelease-1>",
            self.roi_mouse_up
        )

        # ----------------------------------------------------
        # Right panel
        # ----------------------------------------------------

        side = ttk.Frame(
            body,
            width=360,
            padding=10
        )

        side.pack(
            side="right",
            fill="y"
        )

        side.pack_propagate(False)

        # ----------------------------------------------------
        # Draw information
        # ----------------------------------------------------

        ttk.Label(
            side,
            text="DRAW DETAILS",
            font=("Segoe UI", 11, "bold")
        ).pack(
            anchor="w"
        )

        self.draw_info = tk.Text(
            side,
            height=10,
            wrap="word",
            font=("Consolas", 9),
            state="disabled"
        )

        self.draw_info.pack(
            fill="x",
            pady=(5, 10)
        )

        # ----------------------------------------------------
        # Prize category
        # ----------------------------------------------------

        ttk.Label(
            side,
            text="PRIZE CATEGORY",
            font=("Segoe UI", 10, "bold")
        ).pack(
            anchor="w"
        )

        self.prize_combo = ttk.Combobox(
            side,
            state="readonly"
        )

        self.prize_combo.pack(
            fill="x",
            pady=4
        )

        self.prize_combo.bind(
            "<<ComboboxSelected>>",
            self.on_prize_selected
        )

        ttk.Label(
            side,
            text="Expected number count"
        ).pack(
            anchor="w",
            pady=(5, 0)
        )

        self.expected_count_var = tk.StringVar(
            value="0"
        )

        self.expected_count_entry = ttk.Entry(
            side,
            textvariable=self.expected_count_var
        )

        self.expected_count_entry.pack(
            fill="x",
            pady=3
        )

        ttk.Label(
            side,
            text="This is the expected number of result entries, "
                 "not the number of physical rollers.",
            wraplength=330,
            foreground="#666"
        ).pack(
            anchor="w",
            pady=(0, 10)
        )

        # ----------------------------------------------------
        # Machine roll
        # ----------------------------------------------------

        ttk.Label(
            side,
            text="MACHINE ROLL",
            font=("Segoe UI", 11, "bold")
        ).pack(
            anchor="w"
        )

        self.frame_label = ttk.Label(
            side,
            text="Frame: — | Time: —"
        )

        self.frame_label.pack(
            anchor="w",
            pady=4
        )

        ttk.Button(
            side,
            text="Mark Roll Start",
            command=self.mark_start
        ).pack(
            fill="x",
            pady=3
        )

        ttk.Button(
            side,
            text="Mark Roll End / Add Interval",
            command=self.mark_end
        ).pack(
            fill="x",
            pady=3
        )

        ttk.Button(
            side,
            text="Undo Last Roll Interval",
            command=self.undo_last_interval
        ).pack(
            fill="x",
            pady=3
        )

        ttk.Button(
            side,
            text="Reset All Roll Marks",
            command=self.reset_marks
        ).pack(
            fill="x",
            pady=3
        )

        # ----------------------------------------------------
        # ROI
        # ----------------------------------------------------

        ttk.Separator(
            side
        ).pack(
            fill="x",
            pady=10
        )

        ttk.Label(
            side,
            text="MACHINE ROI",
            font=("Segoe UI", 11, "bold")
        ).pack(
            anchor="w"
        )

        ttk.Button(
            side,
            text="Select / Redraw Machine ROI",
            command=self.begin_roi
        ).pack(
            fill="x",
            pady=3
        )

        ttk.Button(
            side,
            text="Clear ROI",
            command=self.clear_roi
        ).pack(
            fill="x",
            pady=3
        )

        ttk.Button(
            side,
            text="Detect Yellow Labels in ROI",
            command=self.detect_yellow_labels
        ).pack(
            fill="x",
            pady=3
        )

        # ----------------------------------------------------
        # Save
        # ----------------------------------------------------

        ttk.Separator(
            side
        ).pack(
            fill="x",
            pady=10
        )

        ttk.Button(
            side,
            text="Save Configuration",
            command=self.save_config
        ).pack(
            fill="x",
            pady=3
        )

        # ----------------------------------------------------
        # Mark information
        # ----------------------------------------------------

        self.marks_label = ttk.Label(
            side,
            text="Roll intervals: 0\nStart: —\nROI: —",
            justify="left",
            wraplength=330
        )

        self.marks_label.pack(
            anchor="w",
            pady=8
        )

        # ----------------------------------------------------
        # Yellow detection information
        # ----------------------------------------------------

        ttk.Label(
            side,
            text="YELLOW LABEL DETECTION",
            font=("Segoe UI", 10, "bold")
        ).pack(
            anchor="w",
            pady=(8, 3)
        )

        self.yellow_info = ttk.Label(
            side,
            text="No detection performed",
            justify="left",
            wraplength=330
        )

        self.yellow_info.pack(
            anchor="w"
        )

        # ----------------------------------------------------
        # Bottom status
        # ----------------------------------------------------

        self.status = ttk.Label(
            self.root,
            text="Choose a video to begin",
            relief="sunken",
            anchor="w",
            padding=5
        )

        self.status.pack(
            fill="x",
            side="bottom"
        )

    # ========================================================
    # VIDEO SELECTION
    # ========================================================

    def select_video(self):

        path = filedialog.askopenfilename(
            title="Select lottery video",
            filetypes=[
                (
                    "Video files",
                    "*.mp4 *.avi *.mov *.mkv"
                ),
                (
                    "All files",
                    "*.*"
                )
            ]
        )

        if not path:
            return

        self.stop_playback()

        if self.cap:
            self.cap.release()
            self.cap = None

        cap = cv2.VideoCapture(path)

        if not cap.isOpened():

            cap.release()

            messagebox.showerror(
                "Video error",
                "Could not open selected video."
            )

            return

        self.cap = cap
        self.video_path = Path(path)

        self.width = int(
            cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        )

        self.height = int(
            cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        )

        self.fps = cap.get(
            cv2.CAP_PROP_FPS
        ) or DEFAULT_FPS

        if self.fps <= 0:
            self.fps = DEFAULT_FPS

        self.frame_count = int(
            cap.get(cv2.CAP_PROP_FRAME_COUNT)
        )

        self.duration = (
            self.frame_count / self.fps
            if self.fps
            else 0
        )

        self.frame_index = 0

        self.current_frame = None

        self.roll_intervals = []
        self.pending_roll_start = None

        self.machine_roi = None

        self.yellow_candidates = []

        self.file_label.config(
            text=self.video_path.name
        )

        self.lookup_draw(
            self.video_path.name
        )

        self.read_frame(0)

        self.update_marks()

        self.status.config(
            text=(
                f"Loaded {self.width}×{self.height} | "
                f"{self.fps:.2f} FPS | "
                f"{self.frame_count:,} frames | "
                f"{self.duration / 60:.2f} min"
            )
        )

    # ========================================================
    # SERIAL PARSING
    # ========================================================

    @staticmethod
    def parse_serial(filename):

        # Examples:
        # SM-70
        # KN-543
        # KL-123
        # SM_70
        # SM 70

        match = re.search(
            r"\b([A-Z]{1,4})[-_ ](\d{1,5})\b",
            filename.upper()
        )

        if not match:
            return None

        return (
            f"{match.group(1)}-"
            f"{match.group(2)}"
        )

    # ========================================================
    # MONGODB LOOKUP
    # ========================================================

    def lookup_draw(self, filename):

        self.draw_serial = self.parse_serial(
            filename
        )

        self.draw_data = None
        self.prize_categories = []

        self.selected_prize = None
        self.expected_number_count = 0

        self.prize_combo.set("")
        self.prize_combo["values"] = []

        self.expected_count_var.set("0")

        if not self.draw_serial:

            self.show_draw_info(
                "Could not identify draw serial from filename."
            )

            return

        try:

            from pymongo import MongoClient

            with MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=3000
            ) as client:

                doc = client[DB_NAME][COLLECTION_NAME].find_one(
                    {
                        "serialNumber": self.draw_serial
                    },
                    {
                        "_id": 0,
                        "serialNumber": 1,
                        "date": 1,
                        "drawDate": 1,
                        "drawCategory": 1,
                        "fileName": 1,
                        "series.prizeCategory": 1,
                        "series.prize": 1,
                        "series.numbers.count": 1
                    }
                )

            if not doc:

                self.show_draw_info(
                    f"Serial: {self.draw_serial}\n"
                    "No matching draw in MongoDB."
                )

                return

            series = []

            for item in doc.get("series", []):

                numbers = item.get("numbers", [])

                number_count = len(numbers)

                total_count = sum(
                    int(number.get("count", 0))
                    for number in numbers
                )

                category = item.get(
                    "prizeCategory"
                )

                prize = item.get(
                    "prize"
                )

                series_item = {
                    "prizeCategory": category,
                    "prize": prize,
                    "numberCount": number_count,
                    "totalCount": total_count
                }

                series.append(series_item)

            self.draw_data = {
                "serialNumber": doc.get("serialNumber"),
                "date": doc.get(
                    "date",
                    doc.get("drawDate")
                ),
                "drawCategory": doc.get("drawCategory"),
                "fileName": doc.get("fileName"),
                "series": series
            }

            self.prize_categories = series

            lines = [
                f"Serial: {self.draw_data['serialNumber']}",
                f"Date: {self.draw_data['date']}",
                f"Category: {self.draw_data['drawCategory']}",
                "",
                "Prize categories:"
            ]

            for item in series:

                lines.append(
                    f"{item['prizeCategory']} | "
                    f"Prize {item['prize']} | "
                    f"Numbers {item['numberCount']}"
                )

            self.show_draw_info(
                "\n".join(lines)
            )

            self.populate_prize_categories()

            self.status.config(
                text=(
                    f"MongoDB lookup successful: "
                    f"{self.draw_serial}"
                )
            )

        except Exception as error:

            logger.exception(
                "MongoDB lookup failed"
            )

            self.show_draw_info(
                f"Serial: {self.draw_serial}\n"
                f"MongoDB lookup failed:\n{error}"
            )

            self.status.config(
                text="MongoDB lookup failed; video is still available"
            )

    # ========================================================
    # PRIZE CATEGORY
    # ========================================================

    def populate_prize_categories(self):

        values = []

        for item in self.prize_categories:

            category = item.get(
                "prizeCategory"
            )

            if category is None:
                continue

            values.append(
                str(category)
            )

        self.prize_combo["values"] = values

        if values:

            self.prize_combo.current(0)

            self.on_prize_selected()

    def on_prize_selected(self, event=None):

        selected = self.prize_combo.get()

        if not selected:
            return

        item = next(
            (
                entry
                for entry in self.prize_categories
                if str(entry.get("prizeCategory")) == selected
            ),
            None
        )

        if not item:
            return

        self.selected_prize = item

        self.expected_number_count = int(
            item.get("numberCount", 0)
        )

        self.expected_count_var.set(
            str(self.expected_number_count)
        )

        self.status.config(
            text=(
                f"Selected {selected}: "
                f"{self.expected_number_count} expected entries"
            )
        )

    def get_expected_count(self):

        value = self.expected_count_var.get().strip()

        try:
            count = int(value)
        except (TypeError, ValueError):
            raise ValueError(
                "Expected number count must be a whole number."
            )

        if count <= 0:
            raise ValueError(
                "Expected number count must be greater than zero."
            )

        return count

    # ========================================================
    # DRAW INFO
    # ========================================================

    def show_draw_info(self, text):

        self.draw_info.config(
            state="normal"
        )

        self.draw_info.delete(
            "1.0",
            "end"
        )

        self.draw_info.insert(
            "end",
            text
        )

        self.draw_info.config(
            state="disabled"
        )

    # ========================================================
    # FRAME READING
    # ========================================================

    def read_frame(self, index):

        if not self.cap:
            return

        if self.frame_count <= 0:
            return

        index = max(
            0,
            min(
                int(index),
                self.frame_count - 1
            )
        )

        self.cap.set(
            cv2.CAP_PROP_POS_FRAMES,
            index
        )

        ok, frame = self.cap.read()

        if not ok:
            return

        self.frame_index = index

        self.current_frame = frame

        self.render_frame()

        self.update_marks()

    # ========================================================
    # FRAME RENDERING
    # ========================================================

    def render_frame(self):

        if self.current_frame is None:
            return

        h, w = self.current_frame.shape[:2]

        canvas_width = max(
            1,
            self.canvas.winfo_width()
        )

        canvas_height = max(
            1,
            self.canvas.winfo_height()
        )

        self.scale = min(
            canvas_width / w,
            canvas_height / h
        )

        display_width = int(
            w * self.scale
        )

        display_height = int(
            h * self.scale
        )

        self.offset_x = (
            canvas_width - display_width
        ) // 2

        self.offset_y = (
            canvas_height - display_height
        ) // 2

        resized = cv2.resize(
            self.current_frame,
            (
                display_width,
                display_height
            )
        )

        rgb = cv2.cvtColor(
            resized,
            cv2.COLOR_BGR2RGB
        )

        self.tk_image = ImageTk.PhotoImage(
            Image.fromarray(rgb)
        )

        self.canvas.delete("all")

        self.canvas.create_image(
            self.offset_x,
            self.offset_y,
            anchor="nw",
            image=self.tk_image
        )

        # ----------------------------------------------------
        # Draw machine ROI
        # ----------------------------------------------------

        if self.machine_roi:

            x, y, rw, rh = self.machine_roi

            self.canvas.create_rectangle(
                self.offset_x + x * self.scale,
                self.offset_y + y * self.scale,
                self.offset_x + (x + rw) * self.scale,
                self.offset_y + (y + rh) * self.scale,
                outline="#00ff66",
                width=2
            )

        # ----------------------------------------------------
        # Draw detected yellow candidates
        # ----------------------------------------------------

        for candidate in self.yellow_candidates:

            x, y, rw, rh = candidate["box"]

            self.canvas.create_rectangle(
                self.offset_x + x * self.scale,
                self.offset_y + y * self.scale,
                self.offset_x + (x + rw) * self.scale,
                self.offset_y + (y + rh) * self.scale,
                outline="#ffcc00",
                width=2
            )

        # ----------------------------------------------------
        # Draw ROI drag preview
        # ----------------------------------------------------

        if (
            self.roi_drag_start is not None
            and self.roi_drag_current is not None
        ):

            x1, y1 = self.roi_drag_start
            x2, y2 = self.roi_drag_current

            self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                outline="#ffcc00",
                width=2,
                dash=(5, 3)
            )

    # ========================================================
    # PLAYBACK
    # ========================================================

    def toggle_play(self):

        if not self.cap:
            return

        if self.playing:
            self.stop_playback()
        else:
            self.playing = True
            self.play_tick()

    def play_tick(self):

        if not self.playing:
            return

        if self.frame_index >= self.frame_count - 1:

            self.stop_playback()

            return

        self.read_frame(
            self.frame_index + 1
        )

        delay = max(
            1,
            int(1000 / self.fps)
        )

        self.after_id = self.root.after(
            delay,
            self.play_tick
        )

    def stop_playback(self):

        self.playing = False

        if self.after_id is not None:

            try:
                self.root.after_cancel(
                    self.after_id
                )

            except tk.TclError:
                pass

            self.after_id = None

    def step_frame(self, amount):

        self.stop_playback()

        self.read_frame(
            self.frame_index + amount
        )

    def seek_seconds(self, seconds):

        self.stop_playback()

        self.read_frame(
            self.frame_index + int(seconds * self.fps)
        )

    # ========================================================
    # ROLL INTERVAL MARKING
    # ========================================================

    def mark_start(self):

        if not self.cap:
            return

        if self.pending_roll_start is not None:

            messagebox.showwarning(
                "Roll already started",
                "Finish or reset the current roll interval first."
            )

            return

        self.pending_roll_start = self.frame_index

        self.update_marks()

        self.status.config(
            text=(
                f"Roll start marked at frame "
                f"{self.pending_roll_start}"
            )
        )

    def mark_end(self):

        if not self.cap:
            return

        if self.pending_roll_start is None:

            messagebox.showwarning(
                "Mark start first",
                "Set the roll start before its end."
            )

            return

        if self.frame_index < self.pending_roll_start:

            messagebox.showwarning(
                "Invalid end",
                "End frame must be after start."
            )

            return

        interval = {
            "roll_index": len(self.roll_intervals) + 1,
            "start_frame": self.pending_roll_start,
            "end_frame": self.frame_index,
            "start_seconds": self.pending_roll_start / self.fps,
            "end_seconds": self.frame_index / self.fps,
            "start_time": self.format_time(
                self.pending_roll_start / self.fps
            ),
            "end_time": self.format_time(
                self.frame_index / self.fps
            )
        }

        self.roll_intervals.append(
            interval
        )

        logger.info(
            "Added roll interval %s",
            interval
        )

        self.pending_roll_start = None

        self.update_marks()

        self.status.config(
            text=(
                f"Added machine roll interval "
                f"{len(self.roll_intervals)}"
            )
        )

    def undo_last_interval(self):

        if not self.roll_intervals:

            messagebox.showinfo(
                "Nothing to undo",
                "There are no saved roll intervals."
            )

            return

        removed = self.roll_intervals.pop()

        self.update_marks()

        self.status.config(
            text=(
                f"Removed roll interval "
                f"{removed['roll_index']}"
            )
        )

    def reset_marks(self):

        self.roll_intervals = []

        self.pending_roll_start = None

        self.update_marks()

        self.status.config(
            text="All roll marks reset"
        )

    # ========================================================
    # MACHINE ROI
    # ========================================================

    def begin_roi(self):

        if self.current_frame is None:
            return

        self.stop_playback()

        self.roi_drag_start = None
        self.roi_drag_current = None

        self.roi_mode = True

        self.status.config(
            text=(
                "Drag on the video to draw machine ROI. "
                "Release mouse to finish."
            )
        )

    def roi_mouse_down(self, event):

        if self.current_frame is None:
            return

        if not self.roi_mode:
            return

        # Ignore clicks outside the displayed video.
        if not self.canvas_point_inside_video(
            event.x,
            event.y
        ):
            return

        self.roi_drag_start = (
            event.x,
            event.y
        )

        self.roi_drag_current = (
            event.x,
            event.y
        )

        self.render_frame()

    def roi_mouse_move(self, event):

        if self.roi_drag_start is None:
            return

        self.roi_drag_current = (
            event.x,
            event.y
        )

        self.render_frame()

    def roi_mouse_up(self, event):

        if self.roi_drag_start is None:
            return

        if self.current_frame is None:
            return

        self.roi_mode = False

        x1, y1 = self.roi_drag_start

        x2, y2 = (
            event.x,
            event.y
        )

        canvas_left = min(x1, x2)
        canvas_top = min(y1, y2)

        canvas_right = max(x1, x2)
        canvas_bottom = max(y1, y2)

        video_left = self.offset_x
        video_top = self.offset_y

        video_right = (
            self.offset_x + self.width * self.scale
        )

        video_bottom = (
            self.offset_y + self.height * self.scale
        )

        # Clamp selection to the displayed video.
        canvas_left = max(
            canvas_left,
            video_left
        )

        canvas_top = max(
            canvas_top,
            video_top
        )

        canvas_right = min(
            canvas_right,
            video_right
        )

        canvas_bottom = min(
            canvas_bottom,
            video_bottom
        )

        if (
            canvas_right <= canvas_left
            or canvas_bottom <= canvas_top
        ):

            self.roi_drag_start = None
            self.roi_drag_current = None

            self.render_frame()

            return

        left = int(
            (canvas_left - self.offset_x) / self.scale
        )

        top = int(
            (canvas_top - self.offset_y) / self.scale
        )

        right = int(
            (canvas_right - self.offset_x) / self.scale
        )

        bottom = int(
            (canvas_bottom - self.offset_y) / self.scale
        )

        left = max(
            0,
            min(left, self.width - 1)
        )

        top = max(
            0,
            min(top, self.height - 1)
        )

        right = max(
            0,
            min(right, self.width)
        )

        bottom = max(
            0,
            min(bottom, self.height)
        )

        roi_width = right - left
        roi_height = bottom - top

        if roi_width > 2 and roi_height > 2:

            self.machine_roi = [
                left,
                top,
                roi_width,
                roi_height
            ]

            self.yellow_candidates = []

            self.yellow_info.config(
                text="ROI changed. Run detection again."
            )

            self.status.config(
                text=f"Machine ROI selected: {self.machine_roi}"
            )

        self.roi_drag_start = None
        self.roi_drag_current = None

        self.render_frame()

        self.update_marks()

    def canvas_point_inside_video(self, x, y):

        video_left = self.offset_x
        video_top = self.offset_y

        video_right = (
            self.offset_x + self.width * self.scale
        )

        video_bottom = (
            self.offset_y + self.height * self.scale
        )

        return (
            video_left <= x <= video_right
            and video_top <= y <= video_bottom
        )

    def clear_roi(self):

        self.machine_roi = None

        self.roi_mode = False

        self.roi_drag_start = None
        self.roi_drag_current = None

        self.yellow_candidates = []

        self.yellow_info.config(
            text="No ROI selected"
        )

        self.render_frame()

        self.update_marks()

        self.status.config(
            text="Machine ROI cleared"
        )

    # ========================================================
    # YELLOW LABEL DETECTION
    # ========================================================

    def detect_yellow_labels(self):

        if self.current_frame is None:

            messagebox.showwarning(
                "No video frame",
                "Load a video first."
            )

            return

        if self.machine_roi is None:

            messagebox.showwarning(
                "ROI missing",
                "Select the machine ROI first."
            )

            return

        x, y, w, h = self.machine_roi

        frame_height, frame_width = (
            self.current_frame.shape[:2]
        )

        x1 = max(0, x)
        y1 = max(0, y)

        x2 = min(
            frame_width,
            x + w
        )

        y2 = min(
            frame_height,
            y + h
        )

        roi = self.current_frame[
            y1:y2,
            x1:x2
        ]

        if roi.size == 0:

            messagebox.showerror(
                "Invalid ROI",
                "The selected machine ROI is empty."
            )

            return

        hsv = cv2.cvtColor(
            roi,
            cv2.COLOR_BGR2HSV
        )

        lower = cv2.inRange(
            hsv,
            YELLOW_LOWER,
            YELLOW_UPPER
        )

        # Reduce small noise.
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (3, 3)
        )

        mask = cv2.morphologyEx(
            lower,
            cv2.MORPH_OPEN,
            kernel
        )

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            kernel
        )

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        candidates = []

        for contour in contours:

            area = cv2.contourArea(
                contour
            )

            if not (
                MIN_YELLOW_LABEL_AREA
                <= area
                <= MAX_YELLOW_LABEL_AREA
            ):
                continue

            rx, ry, rw, rh = cv2.boundingRect(
                contour
            )

            # Convert ROI coordinates back to original
            # video-frame coordinates.
            absolute_box = [
                x1 + rx,
                y1 + ry,
                rw,
                rh
            ]

            aspect_ratio = (
                rw / rh
                if rh > 0
                else 0
            )

            candidates.append({
                "box": absolute_box,
                "area": float(area),
                "aspect_ratio": float(aspect_ratio)
            })

        candidates.sort(
            key=lambda item: item["area"],
            reverse=True
        )

        self.yellow_candidates = candidates

        self.render_frame()

        if candidates:

            self.yellow_info.config(
                text=(
                    f"Candidate yellow regions: {len(candidates)}\n"
                    "Yellow boxes are highlighted on the video.\n"
                    "Printed label numbers have not been recognized."
                )
            )

            self.status.config(
                text=(
                    f"Detected {len(candidates)} candidate "
                    "yellow regions in the current frame"
                )
            )

        else:

            self.yellow_info.config(
                text=(
                    "No yellow candidates found in this frame.\n"
                    "Try another frame or review the ROI."
                )
            )

            self.status.config(
                text="No yellow candidates detected"
            )

        logger.info(
            "Yellow candidates at frame %s: %s",
            self.frame_index,
            len(candidates)
        )

    # ========================================================
    # MARK DISPLAY
    # ========================================================

    def update_marks(self):

        current_time = (
            self.frame_index / self.fps
            if self.fps
            else 0
        )

        self.frame_label.config(
            text=(
                f"Frame: {self.frame_index:,}/"
                f"{self.frame_count:,} | "
                f"Time: {self.format_time(current_time)}"
            )
        )

        if self.pending_roll_start is not None:

            start_text = (
                f"{self.pending_roll_start} "
                f"({self.format_time(self.pending_roll_start / self.fps)})"
            )

        else:

            start_text = "—"

        roi_text = (
            str(self.machine_roi)
            if self.machine_roi
            else "—"
        )

        interval_lines = []

        for interval in self.roll_intervals:

            interval_lines.append(
                f"Roll {interval['roll_index']}: "
                f"{interval['start_time']} - "
                f"{interval['end_time']}"
            )

        if not interval_lines:
            interval_lines.append("No completed intervals")

        text = (
            f"Completed intervals: {len(self.roll_intervals)}\n"
            f"Pending start: {start_text}\n"
            f"ROI x,y,w,h: {roi_text}\n\n"
            + "\n".join(interval_lines)
        )

        self.marks_label.config(
            text=text
        )

    # ========================================================
    # TIME
    # ========================================================

    @staticmethod
    def format_time(seconds):

        seconds = max(
            0,
            int(seconds)
        )

        hours = seconds // 3600

        minutes = (
            seconds % 3600
        ) // 60

        remaining_seconds = (
            seconds % 60
        )

        return (
            f"{hours:02}:"
            f"{minutes:02}:"
            f"{remaining_seconds:02}"
        )

    # ========================================================
    # CONFIGURATION SAVING
    # ========================================================

    def save_config(self):

        if not self.video_path:

            messagebox.showwarning(
                "No video",
                "Select a video first."
            )

            return

        if not self.roll_intervals:

            messagebox.showwarning(
                "Roll intervals missing",
                "Mark at least one complete machine-roll interval."
            )

            return

        if self.pending_roll_start is not None:

            messagebox.showwarning(
                "Incomplete interval",
                "You marked a roll start but have not marked its end."
            )

            return

        if self.machine_roi is None:

            messagebox.showwarning(
                "ROI missing",
                "Select the machine ROI before saving."
            )

            return

        try:

            expected_count = self.get_expected_count()

        except ValueError as error:

            messagebox.showwarning(
                "Invalid expected count",
                str(error)
            )

            return

        CONFIG_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        x, y, w, h = self.machine_roi

        # Keep the original machine_roll structure for
        # compatibility with older configuration readers.
        first_interval = self.roll_intervals[0]
        last_interval = self.roll_intervals[-1]

        data = {

            "video": {
                "path": str(
                    self.video_path.resolve()
                ),
                "filename": self.video_path.name,
                "width": self.width,
                "height": self.height,
                "fps": self.fps,
                "frame_count": self.frame_count,
                "duration_seconds": self.duration
            },

            "draw": {
                "serialNumber": self.draw_serial,
                "metadata": self.draw_data
            },

            "prize_selection": {
                "prizeCategory": (
                    self.selected_prize.get("prizeCategory")
                    if self.selected_prize
                    else None
                ),
                "prize": (
                    self.selected_prize.get("prize")
                    if self.selected_prize
                    else None
                ),
                "expected_number_count": expected_count,
                "physical_rollers_per_spin": 18
            },

            "machine_roll": {
                "start_frame": first_interval["start_frame"],
                "end_frame": last_interval["end_frame"],
                "start_seconds": first_interval["start_seconds"],
                "end_seconds": last_interval["end_seconds"],
                "start_time": first_interval["start_time"],
                "end_time": last_interval["end_time"]
            },

            "roll_intervals": self.roll_intervals,

            "machine_roi": {
                "x": x,
                "y": y,
                "width": w,
                "height": h
            },

            "yellow_label_detection": {
                "performed": bool(self.yellow_candidates),
                "frame_index": (
                    self.frame_index
                    if self.yellow_candidates
                    else None
                ),
                "candidate_count": len(
                    self.yellow_candidates
                ),
                "candidates": [
                    {
                        "x": item["box"][0],
                        "y": item["box"][1],
                        "width": item["box"][2],
                        "height": item["box"][3],
                        "area": item["area"],
                        "aspect_ratio": item["aspect_ratio"]
                    }
                    for item in self.yellow_candidates
                ]
            },

            "created_at": datetime.now().isoformat(
                timespec="seconds"
            )
        }

        output_path = (
            CONFIG_DIR /
            f"{self.video_path.stem}.json"
        )

        try:

            output_path.write_text(
                json.dumps(
                    data,
                    indent=2,
                    ensure_ascii=False
                ),
                encoding="utf-8"
            )

        except Exception as error:

            logger.exception(
                "Configuration save failed"
            )

            messagebox.showerror(
                "Save failed",
                str(error)
            )

            return

        self.status.config(
            text=f"Configuration saved: {output_path}"
        )

        messagebox.showinfo(
            "Saved",
            f"Configuration saved successfully:\n\n{output_path}"
        )

    # ========================================================
    # CLEANUP
    # ========================================================

    def close(self):

        self.stop_playback()

        if self.cap:

            self.cap.release()

            self.cap = None

        self.root.destroy()


# ============================================================
# APPLICATION ENTRY POINT
# ============================================================

def main():

    root = tk.Tk()

    app = VideoInspector(root)

    root.mainloop()


if __name__ == "__main__":

    main()

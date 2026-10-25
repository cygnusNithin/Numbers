# marking_gui.py
import tkinter as tk
from tkinter import filedialog, messagebox, Label, Button, Canvas, Frame, Entry
from tkinter import ttk
import cv2
from PIL import Image, ImageTk
import json
import logging
import time

logger = logging.getLogger(__name__)

def fmt_time(sec):
    """Format seconds to HH:MM:SS"""
    sec = max(0, sec)
    return f"{int(sec // 3600):02d}:{int(sec % 3600 // 60):02d}:{int(sec % 60):02d}"

def parse_time(s):
    """Parse 'HH:MM:SS' or 'MM:SS' to seconds"""
    try:
        sec = 0.0
        for p in s.strip().split(":"):
            sec = sec * 60 + float(p)
        return max(0.0, sec)
    except Exception:
        return 0.0

class MarkingGUI:
    """Tkinter GUI for marking roller positions on board frame."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Roller Marking Tool - with Video Controls")
        self.root.geometry("1600x950")
        
        self.cap = None
        self.video_path = None
        self.fps = 30.0
        self.total_frames = 1
        self.frame_idx = 0
        self.frame = None
        self.photo_image = None
        self.playing = False
        self.after_id = None
        self.seek_after_id = None
        self.slider_guard = False
        
        self.image = None  # Full resolution frame
        self.boxes = []  # List of (type, x, y, w, h) in full resolution
        self.current_type = "tag"  # "tag" or "housing"
        self.drawing = False
        self.start_x, self.start_y = 0, 0
        
        self.roller_count = 0
        self.expected_rollers = 18
        
        self.canvas_scale = 1.0  # Scale factor from full to canvas display
        self.canvas_offset = (0, 0)  # Canvas offset (x, y)
        
        self.build_ui()
    
    def build_ui(self):
        """Build UI elements."""
        # Top control panel
        control_frame = tk.Frame(self.root, bg="lightgray", height=100)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # Row 1: File and marking controls
        row1 = tk.Frame(control_frame, bg="lightgray")
        row1.pack(fill=tk.X, padx=5, pady=5)
        
        Button(row1, text="📁 Load Video", command=self.load_video, 
               bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        Button(row1, text="Mark Tag (Yellow)", command=lambda: self.set_type("tag"),
               bg="#FFC107", fg="black", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5)
        Button(row1, text="Mark Housing (White)", command=lambda: self.set_type("housing"),
               bg="#00BCD4", fg="white", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5)
        Button(row1, text="Undo Last", command=self.undo, bg="#FF5722", fg="white", 
               font=("Arial", 9)).pack(side=tk.LEFT, padx=5)
        Button(row1, text="Clear All", command=self.clear_all, bg="#9C27B0", fg="white",
               font=("Arial", 9)).pack(side=tk.LEFT, padx=5)
        Button(row1, text="💾 Save Boxes", command=self.save_boxes, bg="#2196F3", fg="white",
               font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        self.status_label = Label(row1, text="Status: Ready", fg="blue", 
                                  font=("Arial", 9, "bold"))
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        # Row 2: Video controls
        row2 = tk.Frame(control_frame, bg="lightgray")
        row2.pack(fill=tk.X, padx=5, pady=5)
        
        Button(row2, text="⏮ -60s", command=lambda: self.skip(-60), width=6).pack(side=tk.LEFT, padx=2)
        Button(row2, text="⏪ -10s", command=lambda: self.skip(-10), width=6).pack(side=tk.LEFT, padx=2)
        Button(row2, text="◀ -1s", command=lambda: self.skip(-1), width=6).pack(side=tk.LEFT, padx=2)
        
        self.play_btn = Button(row2, text="▶ Play", command=self.toggle_play, 
                               bg="#4CAF50", fg="white", width=8, font=("Arial", 9, "bold"))
        self.play_btn.pack(side=tk.LEFT, padx=5)
        
        self.pause_btn = Button(row2, text="⏸ Pause", command=self.pause, 
                                bg="#FF9800", fg="white", width=8, font=("Arial", 9, "bold"), state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=2)
        
        Button(row2, text="1s ▶", command=lambda: self.skip(1), width=6).pack(side=tk.LEFT, padx=2)
        Button(row2, text="10s ⏩", command=lambda: self.skip(10), width=6).pack(side=tk.LEFT, padx=2)
        Button(row2, text="60s ⏩", command=lambda: self.skip(60), width=6).pack(side=tk.LEFT, padx=2)
        
        Label(row2, text="Jump to:", bg="lightgray", font=("Arial", 9)).pack(side=tk.LEFT, padx=5)
        self.jump_var = tk.StringVar(value="00:00:00")
        Entry(row2, textvariable=self.jump_var, width=10, font=("Courier", 9)).pack(side=tk.LEFT, padx=2)
        Button(row2, text="Go", command=self.jump_to, width=4).pack(side=tk.LEFT, padx=2)
        
        # Row 3: Slider and time display
        row3 = tk.Frame(control_frame, bg="lightgray")
        row3.pack(fill=tk.X, padx=5, pady=5)
        
        self.slider_var = tk.DoubleVar()
        self.slider = ttk.Scale(row3, from_=0, to=1, orient=tk.HORIZONTAL,
                                variable=self.slider_var, command=self.on_slider)
        self.slider.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 10))
        
        self.time_label = Label(row3, text="00:00:00 / 00:00:00", font=("Courier", 10, "bold"),
                                bg="lightgray", fg="#333", width=20)
        self.time_label.pack(side=tk.LEFT)
        
        # Main content area
        content_frame = tk.Frame(self.root)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left: Canvas
        left_frame = tk.Frame(content_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        Label(left_frame, text="Board Frame - Click & Drag to Mark", 
              font=("Arial", 12, "bold")).pack()
        
        self.canvas = Canvas(left_frame, bg="black", cursor="crosshair", highlightthickness=1)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        
        # Right: Info panel
        right_frame = tk.Frame(content_frame, bg="lightgray", width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))
        right_frame.pack_propagate(False)
        
        Label(right_frame, text="Marking Info", font=("Arial", 11, "bold"), bg="lightgray").pack(pady=10)
        
        self.info_label = Label(right_frame, text="", justify=tk.LEFT, bg="lightgray", 
                                font=("Arial", 9))
        self.info_label.pack(fill=tk.X, padx=10)
        
        Label(right_frame, text="Current Type:", font=("Arial", 9, "bold"), bg="lightgray").pack(pady=(20, 5))
        self.type_label = Label(right_frame, text="TAG (Yellow)", font=("Arial", 10, "bold"), 
                                bg="lightgray", fg="#FFC107")
        self.type_label.pack()
        
        Label(right_frame, text="Boxes Marked:", font=("Arial", 9, "bold"), bg="lightgray").pack(pady=(20, 5))
        self.count_label = Label(right_frame, text="Tags: 0/18\nHousings: 0/18", 
                                 font=("Arial", 10), bg="lightgray")
        self.count_label.pack()
        
        Label(right_frame, text="Instructions:", font=("Arial", 9, "bold"), bg="lightgray").pack(pady=(20, 5))
        instructions = """1. Load a video
2. Use Play/Pause/Skip
3. Find the FULL BOARD
4. Mark all 18 YELLOW tags
5. Mark all 18 WHITE housings
6. Save to roller_boxes.json

Yellow tags: left side
White housings: right of tags
Mark in order: roller 1→18"""
        Label(right_frame, text=instructions, justify=tk.LEFT, bg="lightgray", 
              font=("Arial", 8), fg="#333").pack(padx=10, pady=10)
    
    def load_video(self):
        """Load video file."""
        filepath = filedialog.askopenfilename(filetypes=[("MP4 files", "*.mp4"), 
                                                         ("Video files", "*.avi *.mov *.mkv"),
                                                         ("All files", "*.*")])
        if not filepath:
            return
        
        if self.cap:
            self.pause()
            self.cap.release()
        
        self.cap = cv2.VideoCapture(filepath)
        if not self.cap.isOpened():
            messagebox.showerror("Error", "Cannot open this video")
            return
        
        self.video_path = filepath
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.slider.config(to=self.total_frames - 1)
        
        self.status_label.config(text=f"Status: Loaded {filepath.split('/')[-1]}")
        logger.info(f"Loaded video: {filepath}")
        
        self.seek(0)
    
    def seek(self, frame_idx):
        """Go to specific frame."""
        if not self.cap:
            return
        
        frame_idx = max(0, min(int(frame_idx), self.total_frames - 1))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self.cap.read()
        
        if ret:
            self.frame = frame
            self.image = frame.copy()
            self.frame_idx = frame_idx
            self.display_frame()
    
    def skip(self, seconds):
        """Skip forward/backward by N seconds."""
        if not self.cap or self.playing:
            return
        new_idx = self.frame_idx + int(seconds * self.fps)
        self.seek(new_idx)
    
    def jump_to(self):
        """Jump to time entered in jump_var."""
        time_str = self.jump_var.get()
        seconds = parse_time(time_str)
        frame_idx = int(seconds * self.fps)
        self.seek(frame_idx)
    
    def on_slider(self, value):
        """Handle slider movement."""
        if self.slider_guard or not self.cap or self.playing:
            return
        
        if self.seek_after_id:
            self.root.after_cancel(self.seek_after_id)
        
        self.seek_after_id = self.root.after(80, lambda: self.seek(float(value)))
    
    def toggle_play(self):
        """Play/Pause toggle."""
        if self.playing:
            self.pause()
        else:
            self.play()
    
    def play(self):
        """Start playback."""
        if not self.cap:
            return
        
        self.playing = True
        self.play_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.slider.config(state=tk.DISABLED)
        self.play_tick()
    
    def pause(self):
        """Stop playback."""
        self.playing = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.play_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        self.slider.config(state=tk.NORMAL)
    
    def play_tick(self):
        """Playback tick."""
        if not self.playing or not self.cap:
            self.pause()
            return
        
        ret, frame = self.cap.read()
        if ret:
            self.frame = frame
            self.image = frame.copy()
            self.frame_idx += 1
            self.display_frame()
            
            # Schedule next frame
            delay = int(1000 / self.fps)  # milliseconds
            self.after_id = self.root.after(delay, self.play_tick)
        else:
            # End of video
            self.pause()
            messagebox.showinfo("Info", "End of video reached")
    
    def display_frame(self):
        """Display frame on canvas with marked boxes."""
        if self.frame is None:
            return
        
        # Resize to fit canvas
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        
        if canvas_w <= 1 or canvas_h <= 1:
            canvas_w, canvas_h = 800, 600
        
        h, w = self.frame.shape[:2]
        scale = min(canvas_w / w, canvas_h / h)
        display_w = int(w * scale)
        display_h = int(h * scale)
        
        self.canvas_scale = scale
        self.canvas_offset = ((canvas_w - display_w) // 2, (canvas_h - display_h) // 2)
        
        # Resize frame
        display_frame = cv2.resize(self.frame, (display_w, display_h))
        rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        self.photo_image = ImageTk.PhotoImage(pil_image)
        
        # Display on canvas
        self.canvas.create_image(*self.canvas_offset, image=self.photo_image, anchor=tk.NW)
        
        # Draw existing boxes
        self.redraw_boxes()
        
        # Update time label
        self.update_time_label()
    
    def redraw_boxes(self):
        """Redraw all marked boxes on canvas."""
        self.canvas.delete("rect")
        
        for box_type, x, y, w, h in self.boxes:
            # Convert from full resolution to canvas coordinates
            x1 = self.canvas_offset[0] + x * self.canvas_scale
            y1 = self.canvas_offset[1] + y * self.canvas_scale
            x2 = x1 + w * self.canvas_scale
            y2 = y1 + h * self.canvas_scale
            
            color = "yellow" if box_type == "tag" else "cyan"
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, tags="rect")
            
            # Label
            label_text = "T" if box_type == "tag" else "H"
            self.canvas.create_text(x1 + 3, y1 + 3, anchor=tk.NW, text=label_text,
                                    fill=color, font=("Arial", 10, "bold"), tags="rect")
    
    def update_time_label(self):
        """Update time display."""
        self.slider_guard = True
        self.slider_var.set(self.frame_idx)
        self.slider_guard = False
        
        current_time = fmt_time(self.frame_idx / self.fps)
        total_time = fmt_time(self.total_frames / self.fps)
        self.time_label.config(text=f"{current_time} / {total_time}")
    
    def set_type(self, box_type: str):
        """Set current marking type."""
        self.current_type = box_type
        type_name = "TAG (Yellow)" if box_type == "tag" else "HOUSING (White)"
        type_color = "#FFC107" if box_type == "tag" else "#00BCD4"
        self.type_label.config(text=type_name, fg=type_color)
        self.status_label.config(text=f"Status: Marking {box_type.upper()}")
    
    def on_canvas_press(self, event):
        """Handle mouse press on canvas."""
        self.drawing = True
        self.start_x, self.start_y = event.x, event.y
    
    def on_canvas_drag(self, event):
        """Handle mouse drag on canvas."""
        if not self.drawing:
            return
        
        self.redraw_boxes()
        
        # Draw preview rectangle
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        
        color = "yellow" if self.current_type == "tag" else "cyan"
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, dash=(4, 4), tags="rect")
    
    def on_canvas_release(self, event):
        """Handle mouse release on canvas."""
        if not self.drawing:
            return
        
        self.drawing = False
        
        # Convert canvas coords to full resolution
        x1_canvas = min(self.start_x, event.x)
        y1_canvas = min(self.start_y, event.y)
        x2_canvas = max(self.start_x, event.x)
        y2_canvas = max(self.start_y, event.y)
        
        # Convert to full resolution coordinates
        ox, oy = self.canvas_offset
        x1_full = (x1_canvas - ox) / self.canvas_scale
        y1_full = (y1_canvas - oy) / self.canvas_scale
        x2_full = (x2_canvas - ox) / self.canvas_scale
        y2_full = (y2_canvas - oy) / self.canvas_scale
        
        w = x2_full - x1_full
        h = y2_full - y1_full
        
        # Minimum box size
        if w > 10 and h > 10:
            self.boxes.append((self.current_type, int(x1_full), int(y1_full), int(w), int(h)))
            self.update_count_label()
            self.redraw_boxes()
    
    def update_count_label(self):
        """Update box count display."""
        tags = sum(1 for b in self.boxes if b[0] == "tag")
        housings = sum(1 for b in self.boxes if b[0] == "housing")
        self.count_label.config(text=f"Tags: {tags}/18\nHousings: {housings}/18")
        
        info_lines = [
            f"Total boxes: {len(self.boxes)}/36",
            f"Tags: {tags}/18",
            f"Housings: {housings}/18"
        ]
        
        if tags == 18 and housings == 18:
            info_lines.append("\n✓ Ready to save!")
        
        self.info_label.config(text="\n".join(info_lines))
    
    def undo(self):
        """Remove last box."""
        if self.boxes:
            self.boxes.pop()
            self.update_count_label()
            self.redraw_boxes()
            self.status_label.config(text="Status: Undone last box")
    
    def clear_all(self):
        """Clear all boxes."""
        if messagebox.askyesno("Confirm", "Clear all marked boxes?"):
            self.boxes = []
            self.update_count_label()
            self.redraw_boxes()
            self.status_label.config(text="Status: Cleared all boxes")
    
    def save_boxes(self):
        """Save marked boxes to JSON."""
        if len(self.boxes) != 36:  # 18 tags + 18 housings
            messagebox.showwarning("Warning", f"Expected 36 boxes (18 tags + 18 housings), got {len(self.boxes)}")
            return
        
        # Separate tags and housings
        tags = [b for b in self.boxes if b[0] == "tag"]
        housings = [b for b in self.boxes if b[0] == "housing"]
        
        # Sort by position (roughly by roller order)
        # Tags should be from left to right, top to bottom
        tags = sorted(tags, key=lambda t: (t[2], t[1]))  # Sort by y, then x
        housings = sorted(housings, key=lambda h: (h[2], h[1]))  # Same
        
        output = {
            "boxes": [
                {
                    "roller": i + 1,
                    "tag": {"x": tags[i][1], "y": tags[i][2], "w": tags[i][3], "h": tags[i][4]},
                    "housing": {"x": housings[i][1], "y": housings[i][2], "w": housings[i][3], "h": housings[i][4]}
                }
                for i in range(18)
            ]
        }
        
        with open("roller_boxes.json", 'w') as f:
            json.dump(output, f, indent=2)
        
        messagebox.showinfo("Success", f"Saved {len(self.boxes)} boxes to roller_boxes.json")
        logger.info("Saved roller boxes to roller_boxes.json")
        self.status_label.config(text="Status: ✓ Saved to roller_boxes.json")

def main():
    root = tk.Tk()
    gui = MarkingGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
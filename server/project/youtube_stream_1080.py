
# youtube_stream_1080.py
# YouTube Live / Replay Viewer - 1080p
# Install: python -m pip install -U yt-dlp opencv-python pillow
# Run: python project/youtube_stream_1080.py

import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import cv2
import yt_dlp


class YouTubeStream1080:

    def __init__(self, root):
        self.root = root
        root.title("YouTube Streaming Viewer - 1080p")
        root.geometry("1400x850")

        self.url_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Enter YouTube URL")

        self.frames = queue.Queue(maxsize=2)
        self.stop_event = threading.Event()
        self.worker = None
        self.photo = None
        self.cap = None

        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="YouTube URL").pack(side="left")

        ttk.Entry(
            top,
            textvariable=self.url_var
        ).pack(side="left", fill="x", expand=True, padx=5)

        ttk.Button(
            top,
            text="Start Stream",
            command=self.start
        ).pack(side="left", padx=3)

        ttk.Button(
            top,
            text="Stop",
            command=self.stop
        ).pack(side="left", padx=3)

        self.video_label = tk.Label(root, bg="black")
        self.video_label.pack(fill="both", expand=True, padx=8, pady=5)

        ttk.Label(
            root,
            textvariable=self.status_var,
            padding=5
        ).pack(fill="x")

        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(30, self.update_frame)

    # --------------------------------------------------
    # START STREAM
    # --------------------------------------------------

    def start(self):
        url = self.url_var.get().strip()

        if not url:
            messagebox.showwarning("URL", "Enter YouTube URL.")
            return

        self.stop()

        # Clear stale frames
        while not self.frames.empty():
            try:
                self.frames.get_nowait()
            except queue.Empty:
                break

        self.stop_event = threading.Event()

        self.status_var.set("Resolving YouTube stream...")

        self.worker = threading.Thread(
            target=self.stream_worker,
            args=(url, self.stop_event),
            daemon=True
        )

        self.worker.start()

        # --------------------------------------------------
    # STREAM WORKER (UPDATED)
    # --------------------------------------------------

    def stream_worker(self, url, stop_event):
        cap = None

        try:
            options = {
                # OpenCV only reads video (no audio). 
                # 1. Try 1080p video-only (for standard YouTube videos) or combined (for Live streams)
                # 2. Fall back to <=1080p
                # 3. Fall back to any available video stream
                "format": (
                    "bestvideo[height=1080][ext=mp4]/"
                    "best[height=1080]/"
                    "bestvideo[height=1080]/"
                    "bestvideo[height<=1080][ext=mp4]/"
                    "best[height<=1080]/"
                    "bestvideo[height<=1080]/"
                    "bestvideo/best"
                ),
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "live_from_start": False,
            }

            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(
                    url,
                    download=False
                )

            if stop_event.is_set():
                return

            # If a playlist or channel URL slipped through, grab the first video
            if "entries" in info:
                info = info["entries"][0]

            stream_url = info.get("url")

            if not stream_url:
                raise RuntimeError(
                    "yt-dlp did not return a direct stream URL."
                )

            # Open stream with OpenCV FFmpeg
            cap = cv2.VideoCapture(
                stream_url,
                cv2.CAP_FFMPEG
            )

            if not cap.isOpened():
                raise RuntimeError(
                    "OpenCV could not open YouTube stream. "
                    "Try updating yt-dlp and OpenCV."
                )

            width = int(
                cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            )

            height = int(
                cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            )

            self.set_status(
                f"Connected: {width}x{height}"
            )

            if height < 1080:
                self.set_status(
                    f"Warning: Source is {width}x{height}; "
                    "1080p was unavailable."
                )

            # Read frames
            while not stop_event.is_set():

                success, frame = cap.read()

                if not success:
                    self.set_status(
                        "Stream ended or stalled."
                    )
                    break

                try:
                    self.frames.put(
                        frame,
                        timeout=0.1
                    )

                except queue.Full:

                    # Drop older frames to reduce latency
                    try:
                        self.frames.get_nowait()
                    except queue.Empty:
                        pass

                    try:
                        self.frames.put_nowait(frame)
                    except queue.Full:
                        pass

        except Exception as error:

            error_message = str(error)

            self.set_status(
                f"Error: {error_message}"
            )

        finally:

            if cap is not None:
                cap.release()
    # --------------------------------------------------
    # THREAD-SAFE STATUS
    # --------------------------------------------------

    def set_status(self, text):
        try:
            self.root.after(
                0,
                lambda msg=text: self.status_var.set(msg)
            )
        except tk.TclError:
            pass

    # --------------------------------------------------
    # DISPLAY
    # --------------------------------------------------

    def update_frame(self):

        try:
            frame = self.frames.get_nowait()

            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            image = Image.fromarray(rgb)

            # Display scaling only.
            # Processing frame remains native resolution.
            image.thumbnail(
                (1350, 720),
                Image.Resampling.LANCZOS
            )

            self.photo = ImageTk.PhotoImage(image)

            self.video_label.configure(
                image=self.photo
            )

        except queue.Empty:
            pass

        except tk.TclError:
            return

        self.root.after(
            30,
            self.update_frame
        )

    # --------------------------------------------------
    # STOP
    # --------------------------------------------------

    def stop(self):

        self.stop_event.set()

        self.status_var.set(
            "Stream stopped."
        )

    # --------------------------------------------------
    # CLOSE
    # --------------------------------------------------

    def close(self):

        self.stop()

        self.root.destroy()


# ------------------------------------------------------
# MAIN
# ------------------------------------------------------

if __name__ == "__main__":

    root = tk.Tk()

    app = YouTubeStream1080(root)

    root.mainloop()

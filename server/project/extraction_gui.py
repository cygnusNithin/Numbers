# extraction_gui.py
import tkinter as tk
from tkinter import messagebox, filedialog, Label, Button, Frame, Entry, Canvas, Text
from PIL import Image, ImageTk
import cv2
import json
import logging
from datetime import datetime
from typing import Dict, List
import csv

from video_parser import VideoParser
from digit_reader import DigitReader
from db_manager import DBManager
from utils import FileManager, seconds_to_mmss
from config import *

logger = logging.getLogger(__name__)

class ExtractionGUI:
    """Tkinter GUI for extracting and confirming lottery numbers."""
    
    def __init__(self, root):
        self.root = root
        self.root.title(f"4th Prize Lottery Extraction - {PRIZE} Numbers")
        self.root.geometry("1800x1000")
        
        self.video_path = None
        self.roller_boxes = None
        self.video_parser = None
        self.digit_reader = None
        self.db_manager = None
        
        self.closeup_frames = []
        self.current_idx = 0
        self.extracted_entries = []
        
        self.photo_image = None  # Keep reference
        self.housing_photo = None  # Keep reference
        
        self.build_ui()
        self.init_components()
    
    def build_ui(self):
        """Build GUI layout."""
        # Top control panel
        top_frame = Frame(self.root, bg="lightgray", height=80)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        row1 = Frame(top_frame, bg="lightgray")
        row1.pack(fill=tk.X, padx=5, pady=5)
        
        Button(row1, text="📁 Load Video", command=self.load_video, 
               bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        Button(row1, text="🔍 Detect Close-ups", command=self.detect_closeups,
               bg="#2196F3", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        Button(row1, text="▶ Start Extraction", command=self.start_extraction,
               bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        Button(row1, text="💾 Save & Export", command=self.save_results,
               bg="#FF9800", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        
        self.status_label = Label(row1, text="Status: Ready", fg="blue", font=("Arial", 10, "bold"))
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        row2 = Frame(top_frame, bg="lightgray")
        row2.pack(fill=tk.X, padx=5, pady=5)
        
        Button(row2, text="⟨ Previous", command=self.prev_entry, 
               bg="#2196F3", fg="white", width=10).pack(side=tk.LEFT, padx=5)
        Button(row2, text="Next ⟩", command=self.next_entry,
               bg="#2196F3", fg="white", width=10).pack(side=tk.LEFT, padx=5)
        Button(row2, text="✓ Confirm", command=self.confirm_entry,
               bg="#4CAF50", fg="white", width=10).pack(side=tk.LEFT, padx=5)
        Button(row2, text="✎ Edit", command=self.edit_entry,
               bg="#FF9800", fg="white", width=10).pack(side=tk.LEFT, padx=5)
        
        self.progress_label = Label(row2, text="Progress: 0/0", fg="blue", font=("Arial", 9, "bold"))
        self.progress_label.pack(side=tk.LEFT, padx=20)
        
        # Main content area
        content_frame = Frame(self.root)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left: Frame display + housing + digit display
        left_frame = Frame(content_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Close-up frame
        Label(left_frame, text="Close-up Frame", font=("Arial", 11, "bold")).pack()
        self.frame_canvas = Canvas(left_frame, bg="black", width=700, height=400)
        self.frame_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Housing zoom
        Label(left_frame, text="Housing Detail (4-Digit Display)", font=("Arial", 11, "bold")).pack()
        self.housing_canvas = Canvas(left_frame, bg="black", width=700, height=150)
        self.housing_canvas.pack(fill=tk.X, padx=5, pady=5)
        
        # Right: Info and controls
        right_frame = Frame(content_frame, bg="lightgray", width=350)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=5)
        right_frame.pack_propagate(False)
        
        # Info display
        Label(right_frame, text="Entry Info", font=("Arial", 12, "bold"), bg="lightgray").pack(pady=10)
        
        self.info_label = Label(right_frame, text="", justify=tk.LEFT, bg="lightgray", 
                               font=("Arial", 9), wraplength=330)
        self.info_label.pack(fill=tk.X, padx=10)
        
        # Number input
        Label(right_frame, text="Extracted Number:", bg="lightgray", 
              font=("Arial", 10, "bold")).pack(pady=(20, 5))
        
        self.number_entry = Entry(right_frame, font=("Arial", 18, "bold"), 
                                 justify=tk.CENTER, width=6)
        self.number_entry.pack(pady=5)
        self.number_entry.bind("<Return>", lambda e: self.confirm_entry())
        
        # Confidence display
        self.confidence_label = Label(right_frame, text="Confidence: N/A", bg="lightgray", 
                                     font=("Arial", 9), wraplength=330, justify=tk.LEFT)
        self.confidence_label.pack(fill=tk.X, padx=10, pady=5)
        
        # Status display
        self.entry_status_label = Label(right_frame, text="Status: Pending", bg="lightgray",
                                       font=("Arial", 9, "bold"), fg="orange")
        self.entry_status_label.pack(fill=tk.X, padx=10, pady=5)
        
        # Log
        Label(right_frame, text="Log", font=("Arial", 11, "bold"), bg="lightgray").pack(pady=(20, 5))
        self.log_box = Text(right_frame, height=15, font=("Courier", 8), 
                           bg="white", state=tk.DISABLED)
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    
    def init_components(self):
        """Initialize components."""
        try:
            self.digit_reader = DigitReader(DIGIT_TEMPLATES_FILE, DIGIT_CONFIDENCE_THRESHOLD)
            self.db_manager = DBManager(MONGODB_URI, DB_NAME, COLLECTION_NAME)
            logger.info("Components initialized")
            self.log("✓ Components initialized")
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            messagebox.showerror("Error", f"Initialization failed: {e}")
    
    def log(self, msg):
        """Add message to log."""
        self.log_box.config(state=tk.NORMAL)
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)
        self.log_box.config(state=tk.DISABLED)
        self.root.update()
    
    def load_video(self):
        """Load video file."""
        filepath = filedialog.askopenfilename(filetypes=[("MP4 files", "*.mp4"),
                                                         ("Video files", "*.avi *.mov *.mkv"),
                                                         ("All files", "*.*")])
        if not filepath:
            return
        
        # Load roller boxes
        try:
            self.roller_boxes = FileManager.load_json(ROLLER_BOXES_FILE)
            if not self.roller_boxes.get("boxes"):
                raise ValueError("No boxes found in roller_boxes.json")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load roller boxes: {e}")
            self.log(f"✗ Failed to load roller boxes: {e}")
            return
        
        # Initialize video parser
        try:
            self.video_parser = VideoParser(filepath, self.roller_boxes)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load video: {e}")
            self.log(f"✗ Failed to load video: {e}")
            return
        
        self.video_path = filepath
        self.status_label.config(text=f"Status: Loaded {filepath.split('/')[-1]}")
        logger.info(f"Loaded video: {filepath}")
        self.log(f"✓ Loaded video: {filepath.split('/')[-1]}")
        
        # Display first frame
        self.root.after(100, self.display_first_frame)
    
    def display_first_frame(self):
        """Display the first frame on canvas."""
        if not self.video_parser:
            return
        
        try:
            self.video_parser.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.video_parser.cap.read()
            
            if ret:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Resize to fit canvas
                h, w = frame_rgb.shape[:2]
                display_h = 400
                display_w = int(display_h * w / h)
                frame_resized = cv2.resize(frame_rgb, (display_w, display_h))
                
                pil_image = Image.fromarray(frame_resized)
                self.photo_image = ImageTk.PhotoImage(pil_image)
                
                self.frame_canvas.create_image(0, 0, anchor=tk.NW, image=self.photo_image)
                self.log("✓ First frame displayed. Click 'Detect Close-ups'")
        except Exception as e:
            logger.error(f"Error displaying first frame: {e}")
            self.log(f"✗ Error: {e}")
    
    def detect_closeups(self):
        """Detect close-up frames in video."""
        if not self.video_path or not self.roller_boxes:
            messagebox.showwarning("Warning", "Please load video and roller boxes first")
            return
        
        if not self.video_parser:
            messagebox.showwarning("Warning", "Video parser not initialized")
            return
        
        try:
            self.log("🔍 Detecting close-ups... (this may take a minute)")
            self.root.update()
            
            self.closeup_frames = self.video_parser.detect_closeups(max_closeups=EXPECTED_NUMBERS)
            
            if not self.closeup_frames:
                messagebox.showwarning("Warning", "No close-up frames detected")
                self.log("✗ No close-ups detected")
                return
            
            self.status_label.config(text=f"Status: Detected {len(self.closeup_frames)} close-ups")
            logger.info(f"Detected {len(self.closeup_frames)} close-ups")
            self.log(f"✓ Detected {len(self.closeup_frames)} close-up frames")
            
            messagebox.showinfo("Success", f"Detected {len(self.closeup_frames)} close-ups")
            
        except Exception as e:
            logger.error(f"Error detecting close-ups: {e}")
            messagebox.showerror("Error", f"Detection failed: {e}")
            self.log(f"✗ Error: {e}")
    
    def start_extraction(self):
        """Start extracting numbers from detected close-ups."""
        if not self.closeup_frames:
            messagebox.showwarning("Warning", "Please detect close-ups first")
            return
        
        try:
            self.extracted_entries = []
            
            # Initialize entries from detected close-ups
            for i, closeup in enumerate(self.closeup_frames[:EXPECTED_NUMBERS]):
                self.extracted_entries.append({
                    'entry_id': i + 1,
                    'spin': closeup['spin_num'],
                    'roller': closeup['marked_roller'],
                    'number': '?',
                    'confidence': 0.0,
                    'digit_confidences': [],
                    'timestamp': closeup['timestamp'],
                    'frame_idx': closeup['frame_idx'],
                    'status': 'pending',
                    'notes': ''
                })
            
            self.current_idx = 0
            self.display_entry(0)
            
            self.status_label.config(text=f"Status: Extraction started. Ready for {len(self.extracted_entries)} entries")
            logger.info(f"Extraction started with {len(self.extracted_entries)} entries")
            self.log(f"✓ Extraction started with {len(self.extracted_entries)} entries")
            
        except Exception as e:
            logger.error(f"Error starting extraction: {e}")
            messagebox.showerror("Error", f"Extraction failed: {e}")
            self.log(f"✗ Error: {e}")
    
    def display_entry(self, idx: int):
        """Display frame and extracted number for entry."""
        if idx < 0 or idx >= len(self.extracted_entries):
            return
        
        if idx >= len(self.closeup_frames):
            return
        
        self.current_idx = idx
        closeup = self.closeup_frames[idx]
        entry = self.extracted_entries[idx]
        
        # Display frame
        frame = closeup['frame']
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Resize to fit canvas
        h, w = frame_rgb.shape[:2]
        display_h = 400
        display_w = int(display_h * w / h)
        frame_resized = cv2.resize(frame_rgb, (display_w, display_h))
        
        pil_image = Image.fromarray(frame_resized)
        self.photo_image = ImageTk.PhotoImage(pil_image)
        
        self.frame_canvas.create_image(0, 0, anchor=tk.NW, image=self.photo_image)
        
        # Display info
        info_text = f"""Entry: {entry['entry_id']}/{len(self.extracted_entries)}
Spin: {entry['spin']}
Roller: {entry['roller']}
Timestamp: {entry['timestamp']}
Frame Index: {entry['frame_idx']}
Status: {entry['status']}"""
        
        self.info_label.config(text=info_text)
        
        # Extract number if not done yet
        if entry['status'] == 'pending':
            self.read_number_from_closeup(closeup, entry)
        
        # Display number
        self.number_entry.delete(0, tk.END)
        self.number_entry.insert(0, entry['number'])
        
        # Display confidence
        confidence_text = f"Confidence: {entry['confidence']:.2%}"
        if entry['digit_confidences']:
            digit_conf = " | ".join([f"{c:.0%}" for c in entry['digit_confidences']])
            confidence_text += f"\nDigits: {digit_conf}"
        
        self.confidence_label.config(text=confidence_text)
        
        # Display status with color
        status_text = entry['status'].upper()
        status_color = "green" if entry['status'] == 'confirmed' else "orange" if entry['status'] == 'pending' else "red"
        self.entry_status_label.config(text=f"Status: {status_text}", fg=status_color)
        
        # Display housing detail
        self.display_housing_detail(closeup, entry)
        
        # Update progress
        confirmed_count = sum(1 for e in self.extracted_entries if e['status'] == 'confirmed')
        self.progress_label.config(text=f"Progress: {confirmed_count}/{len(self.extracted_entries)}")
    
    def display_housing_detail(self, closeup: Dict, entry: Dict):
        """Display zoomed housing detail on separate canvas."""
        try:
            housing_roi = closeup['housing_roi']
            frame = closeup['frame']
            
            x, y, w, h = housing_roi
            if w > 0 and h > 0:
                housing_crop = frame[y:y+h, x:x+w]
                
                if housing_crop.size > 0:
                    # Resize to fit canvas
                    display_h = 150
                    display_w = int(display_h * housing_crop.shape[1] / housing_crop.shape[0])
                    housing_resized = cv2.resize(housing_crop, (display_w, display_h))
                    
                    housing_rgb = cv2.cvtColor(housing_resized, cv2.COLOR_BGR2RGB)
                    pil_housing = Image.fromarray(housing_rgb)
                    self.housing_photo = ImageTk.PhotoImage(pil_housing)
                    
                    self.housing_canvas.create_image(0, 0, anchor=tk.NW, image=self.housing_photo)
        except Exception as e:
            logger.warning(f"Could not display housing detail: {e}")
    
    def read_number_from_closeup(self, closeup: Dict, entry: Dict):
        """Read number from close-up frame."""
        try:
            housing_roi = closeup['housing_roi']
            frame = closeup['frame']
            
            x, y, w, h = housing_roi
            if w > 0 and h > 0:
                housing_image = frame[y:y+h, x:x+w]
                
                if housing_image.size > 0:
                    number, confidence, digit_confidences = self.digit_reader.read_number(housing_image)
                    
                    entry['number'] = number
                    entry['confidence'] = confidence
                    entry['digit_confidences'] = digit_confidences
                    
                    logger.info(f"Entry {entry['entry_id']}: {number} (confidence: {confidence:.2%})")
                    self.log(f"Read entry {entry['entry_id']}: {number} ({confidence:.2%})")
        
        except Exception as e:
            logger.error(f"Error reading number: {e}")
            entry['number'] = '?'
            entry['confidence'] = 0.0
            self.log(f"✗ Error reading: {e}")
    
    def confirm_entry(self):
        """Confirm current entry."""
        if self.current_idx >= len(self.extracted_entries):
            return
        
        entry = self.extracted_entries[self.current_idx]
        number = self.number_entry.get()
        
        if not number or not number.isdigit() or len(number) != 4:
            messagebox.showwarning("Warning", "Please enter a valid 4-digit number")
            return
        
        entry['number'] = number
        entry['status'] = 'confirmed'
        logger.info(f"Confirmed entry {entry['entry_id']}: {number}")
        self.log(f"✓ Confirmed entry {entry['entry_id']}: {number}")
        
        self.display_entry(self.current_idx)  # Refresh display
        self.next_entry()
    
    def edit_entry(self):
        """Edit current entry manually."""
        self.number_entry.focus()
        self.number_entry.select_range(0, tk.END)
    
    def next_entry(self):
        """Move to next entry."""
        if self.current_idx < len(self.extracted_entries) - 1:
            self.display_entry(self.current_idx + 1)
        else:
            messagebox.showinfo("Info", "Reached last entry")
    
    def prev_entry(self):
        """Move to previous entry."""
        if self.current_idx > 0:
            self.display_entry(self.current_idx - 1)
    
    def save_results(self):
        """Save extracted numbers to JSON, CSV, and MongoDB."""
        if not self.extracted_entries:
            messagebox.showwarning("Warning", "No entries to save")
            return
        
        confirmed_count = sum(1 for e in self.extracted_entries if e['status'] == 'confirmed')
        if confirmed_count < len(self.extracted_entries):
            response = messagebox.askyesno(
                "Warning",
                f"Only {confirmed_count}/{len(self.extracted_entries)} entries confirmed. Continue anyway?"
            )
            if not response:
                return
        
        try:
            # Prepare data
            extraction_date = datetime.now().strftime("%Y-%m-%d")
            
            # Save to MongoDB
            record = self.db_manager.create_extraction_record(PRIZE, extraction_date, self.extracted_entries)
            
            # Save to JSON
            json_data = {
                "extraction_id": record['extraction_id'],
                "prize": PRIZE,
                "extraction_date": extraction_date,
                "total_numbers": len(self.extracted_entries),
                "expected_numbers": EXPECTED_NUMBERS,
                "entries": self.extracted_entries
            }
            FileManager.save_json(json_data, EXTRACTED_JSON)
            
            # Save to CSV
            csv_entries = [
                {
                    "entry_id": e['entry_id'],
                    "spin": e['spin'],
                    "roller": e['roller'],
                    "number": e['number'],
                    "confidence": f"{e['confidence']:.2%}",
                    "timestamp": e['timestamp'],
                    "status": e['status']
                }
                for e in self.extracted_entries
            ]
            FileManager.save_csv(csv_entries, EXTRACTED_CSV)
            
            logger.info(f"Saved results to {EXTRACTED_JSON}, {EXTRACTED_CSV}, and MongoDB")
            self.log(f"✓ Saved {len(self.extracted_entries)} entries to JSON, CSV, and MongoDB")
            messagebox.showinfo("Success", f"Saved {len(self.extracted_entries)} entries")
            
        except Exception as e:
            logger.error(f"Error saving results: {e}")
            messagebox.showerror("Error", f"Failed to save results: {e}")
            self.log(f"✗ Error saving: {e}")

def main():
    root = tk.Tk()
    gui = ExtractionGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
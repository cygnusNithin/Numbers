import cv2
from pathlib import Path
import json

class PrizeLocationMarker:
    """Mark prize category location on screen"""
    
    def __init__(self, video_path: str):
        self.video_path = video_path
        self.roi = None  # Region of Interest
        self.drawing = False
        self.start_point = None
        self.frame = None
        self.display_frame = None
    
    def mouse_callback(self, event, x, y, flags, param):
        """Handle mouse events for marking area"""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.start_point = (x, y)
            print(f"  Started marking at: ({x}, {y})")
        
        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing:
                # Draw rectangle while dragging
                frame_copy = self.display_frame.copy()
                cv2.rectangle(frame_copy, self.start_point, (x, y), (0, 255, 0), 2)
                cv2.imshow('Mark Prize Area', frame_copy)
        
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            end_point = (x, y)
            
            # Calculate ROI
            roi_x = min(self.start_point[0], end_point[0])
            roi_y = min(self.start_point[1], end_point[1])
            roi_w = abs(end_point[0] - self.start_point[0])
            roi_h = abs(end_point[1] - self.start_point[1])
            
            self.roi = (roi_x, roi_y, roi_w, roi_h)
            
            print(f"\n✓ Prize area marked!")
            print(f"  X: {roi_x}, Y: {roi_y}")
            print(f"  Width: {roi_w}, Height: {roi_h}")
            print(f"  Area: {roi_w * roi_h} pixels")
    
    def time_to_seconds(self, time_str: str) -> float:
        """Convert HH:MM:SS to seconds"""
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    
    def mark_prize_area(self, timestamp_str: str = "00:17:42"):
        """
        Show video frame and let user mark prize area
        timestamp_str: time in HH:MM:SS format (default 17:42)
        """
        # Convert timestamp to seconds
        timestamp_sec = self.time_to_seconds(timestamp_str)
        
        print(f"\nLoading video frame at {timestamp_str}...")
        
        cap = cv2.VideoCapture(self.video_path)
        
        if not cap.isOpened():
            print(f"✗ Could not open video: {self.video_path}")
            return None
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        total_duration = total_frames / fps
        
        print(f"  Video Duration: {int(total_duration//3600):02d}:{int((total_duration%3600)//60):02d}:{int(total_duration%60):02d}")
        print(f"  FPS: {fps}")
        
        # Go to timestamp
        frame_num = int(timestamp_sec * fps)
        
        if frame_num >= total_frames:
            print(f"✗ Timestamp {timestamp_str} is beyond video duration")
            cap.release()
            return None
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, self.frame = cap.read()
        cap.release()
        
        if not ret:
            print(f"✗ Could not read frame at {timestamp_str}")
            return None
        
        print(f"✓ Frame loaded at {timestamp_str}")
        
        # Resize for display (keep aspect ratio)
        height, width = self.frame.shape[:2]
        scale = 1280 / width
        new_width = 1280
        new_height = int(height * scale)
        self.display_frame = cv2.resize(self.frame, (new_width, new_height))
        
        print(f"  Original size: {width}x{height}")
        print(f"  Display size: {new_width}x{new_height}")
        
        # Show instructions
        print("\n" + "="*70)
        print("MARK PRIZE CATEGORY AREA")
        print("="*70)
        print("\nInstructions:")
        print("  1. Look for where the prize category is displayed")
        print("  2. Click and drag to mark the area containing prize text")
        print("  3. The area should include text like '4th Prize', '5th Prize', etc.")
        print("  4. Release the mouse to complete the marking")
        print("  5. Press 'q' to finish\n")
        
        # Display frame
        cv2.imshow('Mark Prize Area at 17:42', self.display_frame)
        cv2.setMouseCallback('Mark Prize Area at 17:42', self.mouse_callback)
        
        print("Waiting for you to mark the area...")
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):  # Reset
                print("\n  Resetting... Mark again\n")
                self.roi = None
                cv2.imshow('Mark Prize Area at 17:42', self.display_frame)
        
        cv2.destroyAllWindows()
        
        if self.roi:
            # Scale back to original frame size
            original_h, original_w = self.frame.shape[:2]
            display_h, display_w = self.display_frame.shape[:2]
            
            scale_x = original_w / display_w
            scale_y = original_h / display_h
            
            scaled_roi = (
                int(self.roi[0] * scale_x),
                int(self.roi[1] * scale_y),
                int(self.roi[2] * scale_x),
                int(self.roi[3] * scale_y)
            )
            
            print(f"\n✓ ROI scaled to original video size:")
            print(f"  X: {scaled_roi[0]}, Y: {scaled_roi[1]}")
            print(f"  Width: {scaled_roi[2]}, Height: {scaled_roi[3]}")
            
            return scaled_roi
        
        return None
    
    def save_marked_location(self, roi: tuple, output_file: str = "prize_location.json"):
        """Save marked location to JSON"""
        data = {
            'roi': {
                'x': roi[0],
                'y': roi[1],
                'width': roi[2],
                'height': roi[3]
            },
            'timestamp': '00:17:42',
            'description': 'Prize category display area - marked at 17:42',
            'video': self.video_path
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\n✓ Prize location saved to: {output_file}")
        print("\nContent of prize_location.json:")
        print(json.dumps(data, indent=2))
        return output_file
    
    def preview_roi(self, roi: tuple):
        """Show preview of marked area"""
        x, y, w, h = roi
        
        if y + h > self.frame.shape[0] or x + w > self.frame.shape[1]:
            print("✗ ROI is outside frame bounds")
            return
        
        cropped = self.frame[y:y+h, x:x+w]
        
        if cropped.size == 0:
            print("✗ ROI is empty")
            return
        
        # Resize for display
        display = cv2.resize(cropped, (600, 400))
        
        print("\n" + "="*70)
        print("PREVIEW OF MARKED AREA")
        print("="*70)
        print(f"\nShowing zoomed preview of marked area")
        print(f"Area: {w}x{h} pixels")
        print(f"Position: ({x}, {y})")
        print("\nPress any key to close preview...")
        
        cv2.imshow('Marked Prize Area Preview (17:42)', display)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # Find video
    video_files = list(Path('.').glob('*.mp4'))
    
    if not video_files:
        print("✗ No video files found in current directory")
        print("\nPlease add your video file (.mp4) to the current folder")
        exit()
    
    video_path = str(video_files[0])
    print("\n" + "="*70)
    print("PRIZE LOCATION MARKER")
    print("="*70)
    print(f"\nVideo found: {video_path}")
    
    marker = PrizeLocationMarker(video_path)
    
    # Mark the prize area at 17:42
    print("\n[1/3] Loading video frame at 17:42...")
    roi = marker.mark_prize_area(timestamp_str="00:17:42")
    
    if roi:
        print("\n[2/3] Showing preview of marked area...")
        marker.preview_roi(roi)
        
        print("\n[3/3] Saving location data...")
        marker.save_marked_location(roi, "prize_location.json")
        
        print("\n" + "="*70)
        print("✓ SETUP COMPLETE!")
        print("="*70)
        print("\nNext steps:")
        print("  1. Run: python detect_prize_timestamps.py")
        print("  2. Then: python agent.py")
        print("\n" + "="*70 + "\n")
    else:
        print("\n✗ No area marked - Exiting")
        print("Please try again and mark the prize category area\n")
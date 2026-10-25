import cv2
import json
from pathlib import Path
import pytesseract

pytesseract.pytesseract.pytesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class MarkedAreaVerifier:
    """Verify and visualize the marked area"""
    
    def __init__(self, video_path: str, roi_file: str = "prize_location.json"):
        self.video_path = video_path
        self.roi_file = roi_file
        self.roi = self._load_roi()
    
    def _load_roi(self) -> dict:
        """Load ROI from JSON"""
        try:
            with open(self.roi_file, 'r') as f:
                data = json.load(f)
            return data['roi']
        except FileNotFoundError:
            print(f"✗ File not found: {self.roi_file}")
            return None
    
    def extract_marked_area(self) -> tuple:
        """Extract the marked area from video"""
        if not self.roi:
            print("✗ No ROI loaded")
            return None, None
        
        cap = cv2.VideoCapture(self.video_path)
        
        # Go to 17:42
        fps = cap.get(cv2.CAP_PROP_FPS)
        timestamp_sec = 17 * 60 + 42  # 17:42 = 1062 seconds
        frame_num = int(timestamp_sec * fps)
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            print("✗ Could not read frame")
            return None, None
        
        # Crop to ROI
        x, y, w, h = self.roi['x'], self.roi['y'], self.roi['width'], self.roi['height']
        cropped = frame[y:y+h, x:x+w]
        
        return frame, cropped
    
    def save_verification_images(self):
        """Save verification images"""
        frame, cropped = self.extract_marked_area()
        
        if frame is None:
            print("✗ Could not extract area")
            return
        
        # Save full frame with rectangle
        x, y, w, h = self.roi['x'], self.roi['y'], self.roi['width'], self.roi['height']
        frame_with_rect = frame.copy()
        cv2.rectangle(frame_with_rect, (x, y), (x+w, y+h), (0, 255, 0), 3)
        
        cv2.imwrite("01_full_frame_with_rectangle.jpg", frame_with_rect)
        print("✓ Saved: 01_full_frame_with_rectangle.jpg")
        
        # Save cropped area
        cv2.imwrite("02_cropped_marked_area.jpg", cropped)
        print("✓ Saved: 02_cropped_marked_area.jpg")
        
        # OCR the cropped area to see what text is detected
        print("\n" + "="*70)
        print("TEXT DETECTED IN MARKED AREA (OCR)")
        print("="*70 + "\n")
        
        try:
            from PIL import Image
            import io
            
            # Convert to PIL Image for OCR
            cropped_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(cropped_rgb)
            
            # OCR
            text = pytesseract.image_to_string(pil_image)
            
            if text.strip():
                print("Detected text:")
                print("-" * 70)
                print(text)
                print("-" * 70)
            else:
                print("⚠ No text detected in marked area")
                print("This might mean:")
                print("  - The area doesn't contain the prize category")
                print("  - The text is too small or unclear")
                print("  - The area needs adjustment")
        
        except Exception as e:
            print(f"⚠ OCR error: {e}")
    
    def display_verification(self):
        """Display verification images"""
        frame, cropped = self.extract_marked_area()
        
        if frame is None:
            print("✗ Could not extract area")
            return
        
        print("\n" + "="*70)
        print("VERIFICATION DISPLAY")
        print("="*70 + "\n")
        
        # Show full frame with marked rectangle
        x, y, w, h = self.roi['x'], self.roi['y'], self.roi['width'], self.roi['height']
        frame_with_rect = frame.copy()
        cv2.rectangle(frame_with_rect, (x, y), (x+w, y+h), (0, 255, 0), 3)
        
        # Resize for display
        display_frame = cv2.resize(frame_with_rect, (1280, 720))
        cv2.imshow('Full Frame with Marked Area', display_frame)
        print("Showing full frame (green rectangle = marked area)")
        print("Press any key to see cropped area...")
        cv2.waitKey(0)
        
        # Show cropped area
        display_cropped = cv2.resize(cropped, (800, 200))
        cv2.imshow('Cropped Marked Area (Close-up)', display_cropped)
        print("Showing close-up of marked area")
        print("Press any key to close...")
        cv2.waitKey(0)
        
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # Find video
    video_files = list(Path('.').glob('*.mp4'))
    
    if not video_files:
        print("✗ No video files found")
        exit()
    
    video_path = str(video_files[0])
    
    print("\n" + "="*70)
    print("MARKED AREA VERIFICATION")
    print("="*70)
    print(f"\nVideo: {video_path}\n")
    
    verifier = MarkedAreaVerifier(video_path)
    
    print("[1/2] Saving verification images...")
    verifier.save_verification_images()
    
    print("\n[2/2] Displaying verification...")
    verifier.display_verification()
    
    print("\n" + "="*70)
    print("Verification complete!")
    print("="*70)
    print("\nGenerated files:")
    print("  - 01_full_frame_with_rectangle.jpg (green rectangle = your marked area)")
    print("  - 02_cropped_marked_area.jpg (close-up of marked area)")
    print("  - prize_location.json (coordinates)\n")
    print("Review these images and let me know:")
    print("  1. Is the marked area correct?")
    print("  2. Does it contain the prize category text?")
    print("  3. Should we adjust it?\n")
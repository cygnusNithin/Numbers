import cv2
import json
from pathlib import Path
import numpy as np
import os

class RollerGroupMarker:
    """Mark roller group areas where prize numbers display - Save one by one"""
    
    def __init__(self, video_path: str, output_file: str = "roller_groups.json"):
        self.video_path = video_path
        self.output_file = output_file
        self.frame = None
        self.frame_original = None
        self.drawing = False
        self.start_point = None
        self.marked_rollers = []
        self.current_selection = None
        self.load_existing_rollers()
    
    def load_existing_rollers(self):
        """Load previously marked rollers from JSON"""
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r') as f:
                    data = json.load(f)
                    self.marked_rollers = data.get('roller_groups', [])
                    if self.marked_rollers:
                        print(f"✓ Loaded {len(self.marked_rollers)} existing roller groups from {self.output_file}")
            except:
                pass
    
    def load_frame(self):
        """Load frame at 17:42"""
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        timestamp_sec = 17 * 60 + 42
        frame_num = int(timestamp_sec * fps)
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        cap.release()
        
        if ret:
            self.frame_original = frame.copy()
            self.frame = cv2.resize(frame, (1280, 720))
            height, width = self.frame.shape[:2]
            print(f"✓ Frame loaded at 17:42")
            print(f"  Original size: {frame.shape[1]}x{frame.shape[0]}")
            print(f"  Display size: {width}x{height}")
            return True
        else:
            print("✗ Could not load frame")
            return False
    
    def mouse_callback(self, event, x, y, flags, param):
        """Handle mouse events for rectangle selection"""
        
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.start_point = (x, y)
            print(f"\n  ▼ Started selection at: ({x}, {y})")
        
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            frame_copy = self.frame.copy()
            
            # Draw all previously saved rollers
            for i, roi in enumerate(self.marked_rollers):
                rx, ry, rw, rh = roi['x'], roi['y'], roi['width'], roi['height']
                # Scale to display
                drx = int(rx / (self.frame_original.shape[1] / self.frame.shape[1]))
                dry = int(ry / (self.frame_original.shape[0] / self.frame.shape[0]))
                drw = int(rw / (self.frame_original.shape[1] / self.frame.shape[1]))
                drh = int(rh / (self.frame_original.shape[0] / self.frame.shape[0]))
                
                cv2.rectangle(frame_copy, (drx, dry), (drx+drw, dry+drh), (0, 255, 0), 2)
                cv2.putText(frame_copy, f"R{i+1}", (drx+5, dry+15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
            # Draw current selection in blue
            cv2.rectangle(frame_copy, self.start_point, (x, y), (255, 0, 0), 2)
            cv2.line(frame_copy, (x, 0), (x, frame_copy.shape[0]), (255, 0, 0), 1)
            cv2.line(frame_copy, (0, y), (frame_copy.shape[1], y), (255, 0, 0), 1)
            
            width = abs(x - self.start_point[0])
            height = abs(y - self.start_point[1])
            cv2.putText(frame_copy, f"W: {width} H: {height}", (self.start_point[0] + 10, self.start_point[1] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
            
            cv2.imshow('Mark Roller Groups', frame_copy)
        
        elif event == cv2.EVENT_LBUTTONUP and self.drawing:
            self.drawing = False
            end_point = (x, y)
            
            roi_x = min(self.start_point[0], end_point[0])
            roi_y = min(self.start_point[1], end_point[1])
            roi_w = abs(end_point[0] - self.start_point[0])
            roi_h = abs(end_point[1] - self.start_point[1])
            
            print(f"  ▲ Ended selection at: ({x}, {y})")
            print(f"\n  ✓ Rectangle (Display: 1280x720):")
            print(f"    X: {roi_x}, Y: {roi_y}, W: {roi_w}, H: {roi_h}")
            
            original_h, original_w = self.frame_original.shape[:2]
            display_h, display_w = self.frame.shape[:2]
            
            scale_x = original_w / display_w
            scale_y = original_h / display_h
            
            original_roi = {
                'x': int(roi_x * scale_x),
                'y': int(roi_y * scale_y),
                'width': int(roi_w * scale_x),
                'height': int(roi_h * scale_y)
            }
            
            print(f"  ✓ Rectangle (Original: {original_w}x{original_h}):")
            print(f"    X: {original_roi['x']}, Y: {original_roi['y']}, W: {original_roi['width']}, H: {original_roi['height']}")
            
            # Store current selection
            self.current_selection = original_roi
            
            print(f"\n  ⏳ Selection ready")
            print(f"  Press 's' to save, 'c' to cancel")
            
            # Show updated frame with current selection
            self.show_frame()
    
    def show_frame(self):
        """Display frame with saved and current selection"""
        frame_copy = self.frame.copy()
        
        original_h, original_w = self.frame_original.shape[:2]
        display_h, display_w = self.frame.shape[:2]
        scale_x = original_w / display_w
        scale_y = original_h / display_h
        
        # Draw saved rollers in green
        for i, roi in enumerate(self.marked_rollers):
            rx, ry, rw, rh = roi['x'], roi['y'], roi['width'], roi['height']
            drx = int(rx / scale_x)
            dry = int(ry / scale_y)
            drw = int(rw / scale_x)
            drh = int(rh / scale_y)
            
            cv2.rectangle(frame_copy, (drx, dry), (drx+drw, dry+drh), (0, 255, 0), 3)
            cv2.putText(frame_copy, f"R{i+1}", (drx+5, dry+15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Draw current selection in blue
        if self.current_selection:
            rx, ry, rw, rh = self.current_selection['x'], self.current_selection['y'], \
                             self.current_selection['width'], self.current_selection['height']
            drx = int(rx / scale_x)
            dry = int(ry / scale_y)
            drw = int(rw / scale_x)
            drh = int(rh / scale_y)
            
            cv2.rectangle(frame_copy, (drx, dry), (drx+drw, dry+drh), (255, 0, 0), 3)
            cv2.putText(frame_copy, f"R{len(self.marked_rollers)+1}?", (drx+5, dry+15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            
            cv2.putText(frame_copy, "Press 's' to save, 'c' to cancel, 'r' to redraw", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        else:
            cv2.putText(frame_copy, f"Marked: {len(self.marked_rollers)} | Draw to add new roller, 'q' to finish", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        cv2.imshow('Mark Roller Groups', frame_copy)
    
    def mark_rollers(self):
        """Interactive roller group marking - save one by one"""
        if not self.load_frame():
            return None
        
        print("\n" + "="*70)
        print("MARK ROLLER GROUPS - ONE BY ONE (SAVE INDIVIDUALLY)")
        print("="*70)
        print("\nInstructions:")
        print("  1. Click and drag to draw rectangle around a roller group")
        print("  2. Press 's' to SAVE that roller")
        print("  3. Press 'c' to CANCEL current selection (undo)")
        print("  4. Press 'r' to REDRAW current selection")
        print("  5. Press 'q' to FINISH (done marking all rollers)\n")
        
        self.show_frame()
        cv2.setMouseCallback('Mark Roller Groups', self.mouse_callback)
        
        print("Waiting for first selection...\n")
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                print("\n✓ Finished marking!")
                break
            
            elif key == ord('s'):
                if self.current_selection:
                    self.marked_rollers.append(self.current_selection)
                    print(f"\n✅ SAVED Roller Group #{len(self.marked_rollers)}")
                    print(f"   X: {self.current_selection['x']}, Y: {self.current_selection['y']}")
                    print(f"   Size: {self.current_selection['width']}x{self.current_selection['height']}")
                    
                    # Save to file immediately
                    self.save_rollers()
                    
                    self.current_selection = None
                    print(f"\n✓ Saved to {self.output_file}")
                    print("Ready for next roller group...\n")
                    self.show_frame()
                else:
                    print("\n⚠️  No selection to save")
            
            elif key == ord('c'):
                if self.current_selection:
                    print("\n❌ CANCELLED current selection")
                    print("   Draw again to select a new area\n")
                    self.current_selection = None
                    self.show_frame()
                else:
                    print("\n⚠️  No selection to cancel")
            
            elif key == ord('r'):
                if self.current_selection:
                    print("\n🔄 REDRAW current selection")
                    print("   Click and drag to draw a new rectangle\n")
                    self.current_selection = None
                    self.show_frame()
                else:
                    print("\n⚠️  No selection to redraw")
        
        cv2.destroyAllWindows()
        
        return self.marked_rollers if self.marked_rollers else None
    
    def analyze_roller_group(self, roi: dict):
        """Analyze characteristics of a roller group area"""
        x, y, w, h = roi['x'], roi['y'], roi['width'], roi['height']
        cropped = self.frame_original[y:y+h, x:x+w]
        
        if cropped.size == 0:
            return None
        
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        
        # Edge detection
        edges = cv2.Canny(gray, 100, 200)
        edge_density = (edges > 0).sum() / edges.size * 100
        
        # Contrast
        contrast = gray.std()
        
        # Color
        hsv = cv2.cvtColor(cropped, cv2.COLOR_BGR2HSV)
        avg_color = hsv.mean(axis=0).mean(axis=0)
        brightness = int(avg_color[2])
        
        analysis = {
            'brightness': brightness,
            'contrast': int(contrast),
            'edge_density': round(edge_density, 1),
            'has_detail': contrast > 30,
            'suitable_for_numbers': contrast > 30 and brightness > 50
        }
        
        return analysis
    
    def print_summary(self):
        """Print summary of marked roller groups"""
        if not self.marked_rollers:
            print("\n⚠️  No roller groups marked")
            return
        
        print("\n" + "="*70)
        print("MARKED ROLLER GROUPS SUMMARY")
        print("="*70)
        
        for i, roi in enumerate(self.marked_rollers, 1):
            print(f"\n🎲 Roller Group #{i}:")
            print(f"   Location: X={roi['x']}, Y={roi['y']}")
            print(f"   Size: {roi['width']}x{roi['height']} pixels")
            print(f"   Area: {roi['width'] * roi['height']:,} pixels")
            
            analysis = self.analyze_roller_group(roi)
            if analysis:
                print(f"   Brightness: {analysis['brightness']}/255")
                print(f"   Contrast: {analysis['contrast']}")
                print(f"   Edge Density: {analysis['edge_density']}%")
                print(f"   Suitable for OCR: {'✓ YES' if analysis['suitable_for_numbers'] else '✗ NO'}")
        
        print("\n" + "="*70)
    
    def preview_rollers(self):
        """Show preview of all marked roller groups"""
        if not self.marked_rollers:
            print("\n✗ No rollers to preview")
            return
        
        print("\nShowing full frame with marked roller groups...")
        frame_with_rects = self.frame_original.copy()
        
        for i, roi in enumerate(self.marked_rollers, 1):
            x, y, w, h = roi['x'], roi['y'], roi['width'], roi['height']
            cv2.rectangle(frame_with_rects, (x, y), (x+w, y+h), (0, 255, 0), 3)
            cv2.putText(frame_with_rects, f"R{i}", (x+5, y+20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        
        display_frame = cv2.resize(frame_with_rects, (1280, 720))
        cv2.imshow('All Marked Roller Groups', display_frame)
        print("Press any key to close...")
        cv2.waitKey(0)
        
        # Show close-ups
        for i, roi in enumerate(self.marked_rollers, 1):
            x, y, w, h = roi['x'], roi['y'], roi['width'], roi['height']
            cropped = self.frame_original[y:y+h, x:x+w]
            display_cropped = cv2.resize(cropped, (400, 150))
            cv2.imshow(f'Roller Group #{i} Close-up', display_cropped)
        
        print("Showing close-ups of each roller group...")
        print("Press any key to close...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    
    def save_rollers(self):
        """Save marked roller groups to JSON"""
        if not self.marked_rollers:
            print("✗ No rollers to save")
            return False
        
        try:
            data = {
                'timestamp': '00:17:42',
                'video': str(self.video_path),
                'description': 'Marked roller group areas for prize number extraction',
                'total_rollers': len(self.marked_rollers),
                'roller_groups': self.marked_rollers
            }
            
            with open(self.output_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
        
        except Exception as e:
            print(f"✗ Save failed: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    # Find video
    video_files = list(Path('.').glob('*.mp4'))
    
    if not video_files:
        print("✗ No video files found")
        exit()
    
    video_path = str(video_files[0])
    
    print("\n" + "="*70)
    print("ROLLER GROUP MARKER - SAVE ONE BY ONE")
    print("="*70)
    print(f"\nVideo: {Path(video_path).name}\n")
    
    marker = RollerGroupMarker(video_path)
    
    # Mark rollers
    print("[1/2] Marking roller groups...\n")
    rollers = marker.mark_rollers()
    
    if not rollers:
        print("✗ No roller groups marked")
        exit()
    
    # Preview and summary
    print("\n[2/2] Summary...\n")
    marker.preview_rollers()
    marker.print_summary()
    
    print("\n" + "="*70)
    print("✓ COMPLETE")
    print("="*70)
    print(f"\n✅ Marked {len(marker.marked_rollers)} roller groups")
    print(f"💾 Saved to: roller_groups.json")
    print("\nNext step:")
    print("  python extract_numbers_from_rollers.py")
    print()
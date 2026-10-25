import subprocess
import sys
from pathlib import Path
import cv2

class VideoTimestampFinder:
    """Help identify timestamps in video"""
    
    @staticmethod
    def extract_video_segment(video_path: str, start_time: str, duration: str = "5"):
        """
        Extract and save a video segment for inspection
        start_time: "00:17:42" (HH:MM:SS)
        duration: seconds
        """
        output_path = "segment_preview.mp4"
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-ss', start_time,
            '-t', duration,
            '-c:v', 'copy',
            '-c:a', 'copy',
            '-y',
            output_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            print(f"✓ Extracted segment saved to: {output_path}")
            print(f"  Time: {start_time} (+{duration}s)")
            return output_path
        except Exception as e:
            print(f"✗ Error: {e}")
            return None
    
    @staticmethod
    def get_frame_at_timestamp(video_path: str, timestamp_str: str):
        """
        Get a single frame at specific timestamp
        timestamp_str: "00:17:42" (HH:MM:SS)
        """
        try:
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            # Convert timestamp to seconds
            parts = timestamp_str.split(':')
            seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            frame_num = int(seconds * fps)
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                output_path = f"frame_at_{timestamp_str.replace(':', '-')}.jpg"
                cv2.imwrite(output_path, frame)
                print(f"✓ Frame saved: {output_path}")
                return output_path
            
        except Exception as e:
            print(f"✗ Error: {e}")
        
        return None

if __name__ == "__main__":
    finder = VideoTimestampFinder()
    
    # Find your video
    video_files = list(Path('.').glob('*.mp4'))
    if not video_files:
        print("✗ No video files found")
        sys.exit(1)
    
    video_path = str(video_files[0])
    print(f"Using video: {video_path}\n")
    
    # Example: Extract segment at 17:42
    print("Example 1: Extract 5-second segment at 17:42")
    finder.extract_video_segment(video_path, "00:17:42", "5")
    
    # Example: Get single frame at 17:42
    print("\nExample 2: Get frame at 17:42")
    finder.get_frame_at_timestamp(video_path, "00:17:42")
    
    print("\n" + "="*70)
    print("To extract other segments, modify the script with timestamps:")
    print("finder.extract_video_segment(video_path, 'HH:MM:SS', 'duration')")
    print("="*70)
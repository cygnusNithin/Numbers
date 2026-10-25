# video_parser.py
import cv2
import numpy as np
from typing import List, Tuple, Dict, Optional
import logging
from utils import ColorDetector, seconds_to_mmss

logger = logging.getLogger(__name__)

class VideoParser:
    """Parse lottery video and extract close-up frames using marked roller positions."""
    
    def __init__(self, video_path: str, roller_boxes: Dict):
        self.video_path = video_path
        self.roller_boxes = roller_boxes
        self.cap = cv2.VideoCapture(video_path)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        self.closeup_frames = []  # List of detected close-ups
        self.frame_cache = {}  # Cache frames to avoid re-reading
    
    def detect_closeups(self, max_closeups: int = 36) -> List[Dict]:
        """
        Detect close-up frames by comparing against marked roller tag templates.
        
        Strategy:
        1. Extract all marked tags from first board frame
        2. For each frame, detect yellow tags
        3. Compare detected tags against marked templates using template matching
        4. If tag matches a marked roller, it's a close-up
        5. Track order: 1-18 (Spin 1), 19-36 (Spin 2), etc.
        """
        logger.info("Starting close-up detection...")
        
        # Build tag templates from marked boxes
        tag_templates = self._build_tag_templates()
        if not tag_templates:
            logger.warning("No tag templates built. Returning empty list.")
            return []
        
        logger.info(f"Built {len(tag_templates)} tag templates")
        
        closeup_count = 0
        spin_num = 1
        roller_in_spin = 0
        last_matched_roller = 0
        
        frame_idx = 0
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        while True:
            ret, frame = self.cap.read()
            if not ret:
                break
            
            # Progress indicator
            if frame_idx % 30 == 0:
                logger.info(f"Processing frame {frame_idx}... found {closeup_count} close-ups")
            
            # Detect yellow tags in current frame
            yellow_tags = ColorDetector.detect_yellow_tag(frame, min_size=50, max_size=200)
            
            # Check if this is a close-up by matching against marked templates
            if yellow_tags:
                matched_roller = self._match_tag_to_roller(frame, yellow_tags, tag_templates)
                
                if matched_roller is not None:
                    # Determine expected roller number based on sequence
                    if matched_roller > last_matched_roller or matched_roller == 1:
                        # Normal sequence or wrap-around to next spin
                        if matched_roller < last_matched_roller:
                            # Wrapped to next spin
                            spin_num += 1
                            roller_in_spin = 0
                    
                    roller_in_spin += 1
                    roller_num = (spin_num - 1) * 18 + matched_roller
                    last_matched_roller = matched_roller
                    closeup_count += 1
                    
                    # Extract housing ROI based on marked position
                    housing_roi = self._get_housing_roi(matched_roller, frame.shape)
                    
                    self.closeup_frames.append({
                        'frame_idx': frame_idx,
                        'frame': frame.copy(),
                        'roller_num': roller_num,
                        'spin_num': spin_num,
                        'timestamp': seconds_to_mmss(frame_idx / self.fps),
                        'tag_roi': None,
                        'housing_roi': housing_roi,
                        'marked_roller': matched_roller
                    })
                    
                    logger.info(f"Close-up {closeup_count}: Roller {roller_num} (Spin {spin_num}, Marked Roller {matched_roller}) @ {seconds_to_mmss(frame_idx / self.fps)}")
                    
                    if closeup_count >= max_closeups:
                        break
            
            frame_idx += 1
        
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Reset to start
        logger.info(f"Detected {len(self.closeup_frames)} close-up frames")
        return self.closeup_frames
    
    def _build_tag_templates(self) -> Dict[int, np.ndarray]:
        """
        Extract marked tag positions and build templates from the first frame
        (assumed to be the full board).
        """
        templates = {}
        
        # Seek to start and get first frame
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = self.cap.read()
        if not ret:
            logger.warning("Cannot read first frame for tag templates")
            return templates
        
        # Extract each marked tag
        for box_info in self.roller_boxes.get("boxes", []):
            roller_num = box_info.get("roller")
            tag_info = box_info.get("tag", {})
            
            if not roller_num or not tag_info:
                continue
            
            x, y, w, h = tag_info.get("x"), tag_info.get("y"), tag_info.get("w"), tag_info.get("h")
            
            if x is None or y is None or w is None or h is None:
                continue
            
            # Extract tag crop from frame
            if y + h <= frame.shape[0] and x + w <= frame.shape[1]:
                tag_crop = frame[y:y+h, x:x+w]
                
                if tag_crop.size > 0:
                    templates[roller_num] = tag_crop.copy()
                    logger.info(f"Built template for roller {roller_num}: {w}x{h}")
        
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Reset
        return templates
    
    def _match_tag_to_roller(self, frame: np.ndarray, yellow_tags: List[Tuple], 
                            templates: Dict[int, np.ndarray]) -> Optional[int]:
        """
        Match detected yellow tag against marked roller templates.
        Returns roller number (1-18) or None if no match.
        """
        if not yellow_tags or not templates:
            return None
        
        # Use the largest detected tag (most likely the close-up tag)
        tag = max(yellow_tags, key=lambda t: t[2] * t[3])
        x, y, w, h = tag
        
        if y + h > frame.shape[0] or x + w > frame.shape[1]:
            return None
        
        tag_crop = frame[y:y+h, x:x+w]
        
        if tag_crop.size == 0:
            return None
        
        best_match = None
        best_score = 0.0
        
        # Compare against all templates
        for roller_num, template in templates.items():
            # Resize tag_crop to match template size
            tag_resized = cv2.resize(tag_crop, (template.shape[1], template.shape[0]))
            
            # Compute histogram similarity
            score = self._histogram_similarity(tag_resized, template)
            
            if score > best_score:
                best_score = score
                best_match = roller_num
        
        # Return match if confidence is reasonable
        if best_score > 0.5:  # Threshold for match confidence
            return best_match
        
        return None
    
    def _histogram_similarity(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """Compute histogram similarity between two images (0-1)."""
        if img1.size == 0 or img2.size == 0:
            return 0.0
        
        try:
            # Convert to HSV for better color matching
            if len(img1.shape) == 3:
                hsv1 = cv2.cvtColor(img1, cv2.COLOR_BGR2HSV)
            else:
                hsv1 = cv2.cvtColor(cv2.cvtColor(img1, cv2.COLOR_GRAY2BGR), cv2.COLOR_BGR2HSV)
            
            if len(img2.shape) == 3:
                hsv2 = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)
            else:
                hsv2 = cv2.cvtColor(cv2.cvtColor(img2, cv2.COLOR_GRAY2BGR), cv2.COLOR_BGR2HSV)
            
            # Compute histograms for hue channel
            hist1 = cv2.calcHist([hsv1], [0], None, [256], [0, 256])
            hist2 = cv2.calcHist([hsv2], [0], None, [256], [0, 256])
            
            # Normalize
            cv2.normalize(hist1, hist1, alpha=1, beta=0, norm_type=cv2.NORM_L1)
            cv2.normalize(hist2, hist2, alpha=1, beta=0, norm_type=cv2.NORM_L1)
            
            # Compare using chi-square
            score = cv2.compareHist(hist1, hist2, cv2.HISTCMP_BHATTACHARYYA)
            
            # Convert to similarity (0-1, where 1 is perfect match)
            return max(0.0, 1.0 - score)
        except Exception as e:
            logger.error(f"Error in histogram similarity: {e}")
            return 0.0
    
    def _get_housing_roi(self, marked_roller: int, frame_shape: Tuple) -> Tuple[int, int, int, int]:
        """
        Get housing ROI from marked boxes.
        Returns (x, y, w, h) of the white housing for this roller.
        """
        for box_info in self.roller_boxes.get("boxes", []):
            if box_info.get("roller") == marked_roller:
                housing_info = box_info.get("housing", {})
                x = housing_info.get("x", 0)
                y = housing_info.get("y", 0)
                w = housing_info.get("w", 0)
                h = housing_info.get("h", 0)
                return (x, y, w, h)
        
        return (0, 0, 0, 0)
    
    def get_frame_at(self, frame_idx: int) -> Optional[np.ndarray]:
        """Get frame at specific index."""
        if frame_idx in self.frame_cache:
            return self.frame_cache[frame_idx]
        
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self.cap.read()
        
        if ret:
            self.frame_cache[frame_idx] = frame
            return frame
        
        return None
    
    def close(self):
        """Release video capture."""
        self.cap.release()
        self.frame_cache.clear()
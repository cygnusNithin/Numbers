# utils.py
import cv2
import numpy as np
from typing import Tuple, List, Dict
import json
import logging
import csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────── HELPERS ────────
def seconds_to_mmss(seconds: float) -> str:
    """Convert seconds to MM:SS format."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

# ──────── CLASSES ────────
class ImageProcessor:
    """Preprocess images for digit recognition."""
    
    @staticmethod
    def upscale(image: np.ndarray, factor: int = 2) -> np.ndarray:
        """Upscale image by factor."""
        h, w = image.shape[:2]
        return cv2.resize(image, (w * factor, h * factor), interpolation=cv2.INTER_CUBIC)
    
    @staticmethod
    def apply_clahe(image: np.ndarray, clip_limit: float = 2.0, tile_size: int = 8) -> np.ndarray:
        """Apply Contrast Limited Adaptive Histogram Equalization."""
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size))
        return clahe.apply(image)
    
    @staticmethod
    def binary_threshold(image: np.ndarray, threshold: int = 127) -> np.ndarray:
        """Convert to binary image."""
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY)
        return binary
    
    @staticmethod
    def morphology(image: np.ndarray, kernel_size: int = 3, operation: str = 'close') -> np.ndarray:
        """Apply morphological operations."""
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        if operation == 'close':
            return cv2.morphologyEx(image, cv2.MORPH_CLOSE, kernel)
        elif operation == 'open':
            return cv2.morphologyEx(image, cv2.MORPH_OPEN, kernel)
        elif operation == 'erode':
            return cv2.erode(image, kernel)
        elif operation == 'dilate':
            return cv2.dilate(image, kernel)
        return image
    
    @staticmethod
    def denoise(image: np.ndarray, h: int = 10) -> np.ndarray:
        """Denoise using bilateral filter."""
        if len(image.shape) == 3:
            return cv2.bilateralFilter(image, 9, h, h)
        else:
            return cv2.bilateralFilter(image, 9, h, h)

class ColorDetector:
    """Detect yellow tags and white housings."""
    
    @staticmethod
    def detect_yellow_tag(image: np.ndarray, min_size: int = 50, max_size: int = 200) -> List[Tuple]:
        """Detect yellow tag (HSV range)."""
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        # Yellow range in HSV
        lower_yellow = np.array([15, 100, 100])
        upper_yellow = np.array([35, 255, 255])
        mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        yellow_boxes = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if min_size <= w <= max_size and min_size <= h <= max_size:
                yellow_boxes.append((x, y, w, h))
        return yellow_boxes
    
    @staticmethod
    def detect_white_housing(image: np.ndarray, min_width: int = 200) -> List[Tuple]:
        """Detect white housing (high brightness)."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        white_boxes = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if w >= min_width and h >= 50:
                white_boxes.append((x, y, w, h))
        return white_boxes

class TemplateManager:
    """Manage digit templates and template matching."""
    
    def __init__(self, template_file: str):
        self.template_file = template_file
        self.templates = self.load_templates()
    
    def load_templates(self) -> Dict:
        """Load digit templates from .npz file."""
        try:
            data = np.load(self.template_file, allow_pickle=True)
            return {str(i): data[f'digit_{i}'] for i in range(10) if f'digit_{i}' in data}
        except FileNotFoundError:
            logger.warning(f"Template file {self.template_file} not found. Starting fresh.")
            return {}
    
    def save_templates(self, templates: Dict) -> None:
        """Save digit templates to .npz file."""
        save_dict = {f'digit_{k}': v for k, v in templates.items()}
        np.savez_compressed(self.template_file, **save_dict)
        logger.info(f"Saved {len(templates)} digit templates to {self.template_file}")
    
    def add_template(self, digit: str, image: np.ndarray) -> None:
        """Add or update a digit template."""
        if digit not in self.templates:
            self.templates[digit] = []
        if isinstance(self.templates[digit], list):
            self.templates[digit].append(image)
        else:
            self.templates[digit] = [self.templates[digit], image]
        self.save_templates(self.templates)
    
    def match_digit(self, digit_image: np.ndarray, digit: str) -> float:
        """Match digit image against learned template."""
        if digit not in self.templates or len(self.templates[digit]) == 0:
            return 0.0
        
        # Get template
        if isinstance(self.templates[digit], list):
            template = self.templates[digit][0]
        else:
            template = self.templates[digit]
        
        # Resize digit_image to template size
        digit_resized = cv2.resize(digit_image, (template.shape[1], template.shape[0]))
        
        # Compute similarity (correlation)
        result = cv2.matchTemplate(digit_resized, template, cv2.TM_CCOEFF)
        return float(np.max(result)) if result.size > 0 else 0.0

class FileManager:
    """Manage file I/O for JSON and CSV."""
    
    @staticmethod
    def load_json(filepath: str) -> Dict:
        """Load JSON file."""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    @staticmethod
    def save_json(data: Dict, filepath: str) -> None:
        """Save JSON file."""
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved JSON to {filepath}")
    
    @staticmethod
    def save_csv(entries: List[Dict], filepath: str) -> None:
        """Save CSV file."""
        if not entries:
            logger.warning("No entries to save to CSV")
            return
        
        keys = entries[0].keys()
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(entries)
        logger.info(f"Saved CSV to {filepath}")
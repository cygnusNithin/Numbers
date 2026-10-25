# digit_reader.py
import cv2
import numpy as np
from typing import Tuple, List, Optional
import easyocr
import logging
from utils import ImageProcessor, TemplateManager

logger = logging.getLogger(__name__)

class DigitReader:
    """Read 4-digit numbers from housing ROI."""
    
    def __init__(self, template_file: str, confidence_threshold: float = 0.70):
        self.template_manager = TemplateManager(template_file)
        self.confidence_threshold = confidence_threshold
        self.reader = easyocr.Reader(['en'], gpu=False)
    
    def read_number(self, housing_crop: np.ndarray) -> Tuple[str, float, List[float]]:
        """
        Read 4-digit number from housing crop.
        
        Returns:
            (number_string, overall_confidence, digit_confidences)
        """
        if housing_crop is None or housing_crop.size == 0:
            return "?", 0.0, []
        
        try:
            # Preprocess
            binary = self._preprocess_housing(housing_crop)
            
            # Extract digit windows
            digit_windows = self._extract_digit_windows(binary)
            
            if not digit_windows:
                return "?", 0.0, []
            
            # Classify each digit
            digits = []
            confidences = []
            
            for digit_image in digit_windows:
                digit, confidence = self._classify_digit(digit_image)
                digits.append(digit)
                confidences.append(confidence)
            
            number_string = ''.join(digits)
            overall_confidence = np.mean(confidences) if confidences else 0.0
            
            return number_string, overall_confidence, confidences
        
        except Exception as e:
            logger.error(f"Error reading number: {e}")
            return "?", 0.0, []
    
    def _preprocess_housing(self, housing_crop: np.ndarray) -> np.ndarray:
        """Preprocess housing image for digit extraction."""
        # Upscale
        upscaled = ImageProcessor.upscale(housing_crop, factor=2)
        
        # Convert to grayscale
        gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY) if len(upscaled.shape) == 3 else upscaled
        
        # Apply CLAHE
        enhanced = ImageProcessor.apply_clahe(gray, clip_limit=2.0, tile_size=8)
        
        # Binary threshold
        _, binary = cv2.threshold(enhanced, 150, 255, cv2.THRESH_BINARY)
        
        # Morphology
        binary = ImageProcessor.morphology(binary, kernel_size=3, operation='close')
        
        return binary
    
    def _extract_digit_windows(self, binary_image: np.ndarray) -> List[np.ndarray]:
        """
        Split housing into 4 digit windows.
        Assumes digits are arranged horizontally.
        """
        h, w = binary_image.shape
        
        if w < 100 or h < 50:
            # Image too small, can't extract digits
            return []
        
        digit_width = w // 4
        digits = []
        
        for i in range(4):
            x_start = i * digit_width
            x_end = (i + 1) * digit_width
            digit_crop = binary_image[:, x_start:x_end]
            
            # Remove black borders
            digit_crop = self._remove_black_borders(digit_crop)
            
            if digit_crop.size > 0:
                digits.append(digit_crop)
        
        return digits
    
    def _remove_black_borders(self, image: np.ndarray) -> np.ndarray:
        """Remove black borders from digit crop."""
        coords = cv2.findNonZero(image)
        if coords is not None:
            x, y, w, h = cv2.boundingRect(coords)
            return image[y:y+h, x:x+w]
        return image
    
    def _classify_digit(self, digit_image: np.ndarray) -> Tuple[str, float]:
        """
        Classify single digit using template matching or EasyOCR.
        
        Returns: (digit_char, confidence)
        """
        if digit_image.size == 0:
            return '?', 0.0
        
        best_match = None
        best_confidence = 0.0
        
        # Try template matching against learned templates
        for digit_str in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
            match_score = self.template_manager.match_digit(digit_image, digit_str)
            if match_score > best_confidence:
                best_confidence = match_score
                best_match = digit_str
        
        # If template confidence is low, use EasyOCR
        if best_confidence < self.confidence_threshold:
            digit_3channel = cv2.cvtColor(digit_image, cv2.COLOR_GRAY2BGR) if len(digit_image.shape) == 2 else digit_image
            
            try:
                results = self.reader.readtext(digit_3channel, allowlist='0123456789', detail=1)
                
                if results:
                    ocr_digit = results[0][1]
                    ocr_confidence = results[0][2]
                    
                    if ocr_digit.isdigit():
                        return ocr_digit, ocr_confidence
            except Exception as e:
                logger.warning(f"EasyOCR failed: {e}")
        
        return best_match or '?', best_confidence
    
    def add_learned_digit(self, digit_char: str, digit_image: np.ndarray):
        """Add a confirmed digit to the template memory."""
        if digit_image.size > 0:
            self.template_manager.add_template(digit_char, digit_image)
            logger.info(f"Learned digit template: {digit_char}")
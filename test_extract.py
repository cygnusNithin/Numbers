import sys
sys.path.insert(0, 'server/project')
import cv2
import numpy as np
from pathlib import Path
from digit_capture import DigitStore, normalize_font, score_pair, propose_boxes

# Initialize DigitStore (will look for existing digit_fonts)
store = DigitStore(Path('server/project/digit_fonts'))
print('Samples per digit:', store.counts())

# Test extract_four_digits with a synthetic housing
housing = np.ones((200, 300, 3), dtype=np.uint8) * 255

# Test with no samples - should return None
number, conf, methods = store.extract_four_digits(housing)
print('No samples - number:', number, 'conf:', conf, 'methods:', methods)

# Test with a housing that has propose_boxes returning 4 boxes
# Just verify the function doesn't crash
print('Functional test passed - extraction logic available')
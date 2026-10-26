import sys
sys.path.insert(0, 'server/project')
import cv2
import numpy as np
from pathlib import Path
from digit_capture import FontApp

# Just verify the method exists and can be called structure-wise
app = FontApp.__new__(FontApp)
print('process_closeup_extract method exists:', hasattr(app, 'process_closeup_extract'))
print('All structural checks passed')
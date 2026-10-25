# config.py
import os

# Prize Configuration
PRIZE = 4
EXPECTED_NUMBERS = 19  # Hardcoded for 4th prize

# Video Settings
VIDEO_FORMAT = "mp4"
VIDEO_FPS = 30
VIDEO_RESOLUTION = (1920, 1080)

# Roller Settings
TOTAL_ROLLERS_PER_SPIN = 18
EXPECTED_SPINS = 2  # Spin 1: rollers 1-18, Spin 2: rollers 19-36

# Files
ROLLER_BOXES_FILE = "roller_boxes.json"
DIGIT_TEMPLATES_FILE = "digit_templates.npz"
EXTRACTED_JSON = f"{PRIZE}th_prize_extracted.json"
EXTRACTED_CSV = f"{PRIZE}th_prize_extracted.csv"

# Output Directory
OUTPUT_DIR = "extracted_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Digit Reader Thresholds
DIGIT_CONFIDENCE_THRESHOLD = 0.70  # Use EasyOCR if < 70%
HOUSING_UPSCALE = 2  # Upscale factor for digit recognition
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_SIZE = 8

# Close-up Detection
CLOSEUP_TAG_SIZE_MIN = 50  # Minimum yellow tag size (pixels)
CLOSEUP_TAG_SIZE_MAX = 200  # Maximum yellow tag size
CLOSEUP_HOUSING_WIDTH_MIN = 200  # Minimum white housing width

# MongoDB Configuration
MONGODB_URI = "mongodb://localhost:27017"
DB_NAME = "kerala_lottery"
COLLECTION_NAME = "extraction_data"

# Logging
LOG_LEVEL = "INFO"
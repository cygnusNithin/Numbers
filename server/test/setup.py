# setup.py - Complete setup for Windows

import subprocess
import sys
import os
from pathlib import Path

print("\n" + "="*60)
print("LOTTERY ANALYSIS - WINDOWS SETUP")
print("="*60 + "\n")

# Step 1: Install Python packages
print("[1/3] Installing Python packages...")
packages = [
    'yt-dlp',
    'opencv-python',
    'pillow',
    'pytesseract',
    'moviepy',
    'pydub',
    'PyPDF2',
    'numpy',
    'imageio-ffmpeg'
]

for package in packages:
    print(f"  Installing {package}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", package, "-q"])

print("✓ All Python packages installed\n")

# Step 2: Check Tesseract
print("[2/3] Checking Tesseract OCR...")
tesseract_paths = [
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
]

tesseract_found = False
for path in tesseract_paths:
    if os.path.exists(path):
        print(f"✓ Tesseract found at: {path}")
        tesseract_found = True
        break

if not tesseract_found:
    print("✗ Tesseract not found!")
    print("  Download from: https://github.com/UB-Mannheim/tesseract/wiki")
    print("  Install to: C:\\Program Files\\Tesseract-OCR\\")
else:
    print()

# Step 3: Check FFmpeg
print("[3/3] Checking FFmpeg...")
try:
    subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    print("✓ FFmpeg is installed")
except FileNotFoundError:
    print("✗ FFmpeg not found!")
    print("  Download from: https://ffmpeg.org/download.html")
    print("  Extract to: C:\\ffmpeg\\")
    print("  Then add C:\\ffmpeg\\bin to Windows PATH")

print("\n" + "="*60)
print("Setup Complete! Run: python agent.py")
print("="*60 + "\n")
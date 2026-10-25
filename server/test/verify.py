# verify.py
import sys

print("\nVerifying Installation...\n")

# Test Python packages
tests = {
    'yt-dlp': 'yt_dlp',
    'opencv': 'cv2',
    'pillow': 'PIL',
    'PyPDF2': 'PyPDF2',
    'moviepy': 'moviepy',
    'numpy': 'numpy'
}

all_ok = True
for name, module in tests.items():
    try:
        __import__(module)
        print(f"✓ {name}")
    except ImportError as e:
        print(f"✗ {name} - {e}")
        all_ok = False

# Test Tesseract
print("\nChecking system tools...\n")
try:
    import pytesseract
    pytesseract.pytesseract.pytesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    version = pytesseract.get_tesseract_version()
    print(f"✓ Tesseract - {version}")
except Exception as e:
    print(f"✗ Tesseract - Not found or not configured")
    print(f"  Install from: https://github.com/UB-Mannheim/tesseract/wiki")
    print(f"  Edit agent.py line 13: pytesseract.pytesseract_cmd = r'YOUR_PATH_HERE'")
    all_ok = False

# Test FFmpeg
try:
    import subprocess
    result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
    print(f"✓ FFmpeg")
except Exception as e:
    print(f"✗ FFmpeg - Not found")
    print(f"  Install from: https://ffmpeg.org/download.html")
    print(f"  Add to PATH: C:\\ffmpeg\\bin")
    all_ok = False

print("\n" + "="*60)
if all_ok:
    print("✓ All systems ready! Run: python agent.py")
else:
    print("✗ Some components missing. See above for fixes.")
print("="*60 + "\n")
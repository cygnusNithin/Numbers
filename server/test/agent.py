import os
import sys
import csv
import json
import subprocess
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Set

# Set Tesseract path for Windows
import pytesseract
pytesseract.pytesseract.pytesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

import cv2
import numpy as np
from PIL import Image
import PyPDF2

print("✓ All imports successful\n")

# Configuration
class Config:
    OUTPUT_DIR = Path("lottery_analysis_output")
    FRAMES_DIR = OUTPUT_DIR / "frames"
    OCR_DIR = OUTPUT_DIR / "ocr"
    CSV_OUTPUT = OUTPUT_DIR / "roller_analysis.csv"
    MASTER_CSV = "all_data.csv"  # Your master data file
    FRAMES_SAMPLE_RATE = 1  # Extract every 1 second
    
    # Roller Configuration
    ROLLER_GROUPS = 18
    ROLLERS_PER_GROUP = 4
    TOTAL_ROLLERS = ROLLER_GROUPS * ROLLERS_PER_GROUP
    
    def __init__(self):
        self.OUTPUT_DIR.mkdir(exist_ok=True)
        self.FRAMES_DIR.mkdir(exist_ok=True)
        self.OCR_DIR.mkdir(exist_ok=True)

# CSV Data Manager
class CSVDataManager:
    """Load and manage data from all_data.csv"""
    
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.data = self._load_csv()
    
    def _load_csv(self) -> List[Dict]:
        """Load all_data.csv"""
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                data = list(reader)
            
            print(f"✓ Loaded {len(data)} records from {self.csv_path}")
            return data
            
        except FileNotFoundError:
            print(f"✗ CSV file not found: {self.csv_path}")
            return []
        except Exception as e:
            print(f"✗ Error loading CSV: {e}")
            return []
    
    def find_by_serial_number(self, serial_number: str) -> Optional[Dict]:
        """Find record by serial number"""
        for record in self.data:
            if record.get('serialNumber', '').strip() == serial_number.strip():
                return record
        return None
    
    def find_by_filename(self, filename: str) -> Optional[Dict]:
        """Find record by video/PDF filename"""
        for record in self.data:
            # Match PDF filename
            if record.get('fileName', '').strip() in filename:
                return record
            # Match serial number in filename
            serial = record.get('serialNumber', '').strip()
            if serial and serial in filename:
                return record
        return None
    
    def get_all_records(self) -> List[Dict]:
        """Get all records"""
        return self.data
    
    def print_records(self):
        """Print all records"""
        print(f"\n{'Event':<6} {'Serial':<12} {'Date':<12} {'PDF File':<20} {'Series':<8}")
        print("-" * 70)
        for record in self.data:
            event = record.get('event_order', '')
            serial = record.get('serialNumber', '')
            date = record.get('date', '')
            pdf = record.get('fileName', '')
            series = record.get('series_count', '')
            print(f"{event:<6} {serial:<12} {date:<12} {pdf:<20} {series:<8}")

# Video File Analyzer
class VideoFileAnalyzer:
    """Analyze video files and match with CSV data"""
    
    def __init__(self, csv_manager: CSVDataManager):
        self.csv_manager = csv_manager
    
    def find_video_file(self, search_dir: str = ".") -> Optional[tuple]:
        """Find video file and match with CSV data"""
        video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.flv']
        
        video_files = []
        for file in Path(search_dir).glob('*'):
            if file.suffix.lower() in video_extensions:
                video_files.append(file)
        
        if not video_files:
            print("✗ No video files found")
            return None
        
        print(f"\n✓ Found {len(video_files)} video file(s):")
        for i, video_file in enumerate(video_files, 1):
            print(f"  {i}. {video_file.name}")
        
        # Try to match with CSV data
        for video_file in video_files:
            filename = video_file.name
            
            # Extract serial number from filename
            serial_match = re.search(r'(SM-\d+|KR-\d+|W-\d+)', filename)
            
            if serial_match:
                serial_number = serial_match.group(1)
                record = self.csv_manager.find_by_serial_number(serial_number)
                
                if record:
                    print(f"\n✓ Matched with CSV record:")
                    print(f"  Serial: {record.get('serialNumber')}")
                    print(f"  Date: {record.get('date')}")
                    print(f"  PDF: {record.get('fileName')}")
                    return (str(video_file), record)
        
        # If no serial match, try matching by other patterns
        print("\n⚠ Could not match video with CSV by serial number")
        print("  Returning first video file found")
        return (str(video_files[0]), None)
    
    def extract_metadata(self, filename: str) -> Dict:
        """Extract metadata from video filename"""
        metadata = {
            'serial_number': None,
            'date': None,
            'raw_filename': filename
        }
        
        # Pattern: SM-70, KR-456, W-576, etc.
        serial_match = re.search(r'(SM-\d+|KR-\d+|W-\d+)', filename)
        if serial_match:
            metadata['serial_number'] = serial_match.group(1)
        
        # Pattern: DD.MM.YYYY or DD/MM/YYYY
        date_match = re.search(r'(\d{2}[./]\d{2}[./]\d{4})', filename)
        if date_match:
            metadata['date'] = date_match.group(1)
        
        return metadata

# PDF Prize Extractor
class PrizeExtractor:
    """Extract all 4-digit prizes from PDF"""
    
    @staticmethod
    def extract_prizes_from_pdf(pdf_path: str) -> Dict[str, List[str]]:
        """Extract all prize numbers by category"""
        prizes = {
            '4th_prize': [],
            '5th_prize': [],
            '6th_prize': [],
            '7th_prize': [],
            '8th_prize': [],
            '9th_prize': []
        }
        
        try:
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                full_text = ""
                
                for page in reader.pages:
                    full_text += page.extract_text()
            
            # Parse prize sections
            current_prize = None
            lines = full_text.split('\n')
            
            for line in lines:
                line = line.strip()
                
                # Identify prize sections
                if '4th Prize' in line or '4th Prize-' in line:
                    current_prize = '4th_prize'
                elif '5th Prize' in line or '5th Prize-' in line:
                    current_prize = '5th_prize'
                elif '6th Prize' in line or '6th Prize-' in line:
                    current_prize = '6th_prize'
                elif '7th Prize' in line or '7th Prize-' in line:
                    current_prize = '7th_prize'
                elif '8th Prize' in line or '8th Prize-' in line:
                    current_prize = '8th_prize'
                elif '9th Prize' in line or '9th Prize-' in line:
                    current_prize = '9th_prize'
                elif current_prize and line and line[0].isdigit():
                    # Extract 4-digit numbers
                    numbers = re.findall(r'\b\d{4}\b', line)
                    prizes[current_prize].extend(numbers)
            
            # Remove duplicates and sort
            for key in prizes:
                prizes[key] = sorted(list(set(prizes[key])))
            
            return prizes
            
        except Exception as e:
            print(f"✗ PDF extraction failed: {e}")
            return prizes

# Video Frame Extraction
class FrameExtractor:
    """Extract frames from video"""
    
    def __init__(self, config: Config):
        self.config = config

    def extract_frames(self, video_path: str) -> List[Dict]:
        """Extract frames using OpenCV"""
        frames_data = []
        
        try:
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0
            
            print(f"\n  Video Properties:")
            print(f"    Frames: {total_frames}")
            print(f"    FPS: {fps}")
            print(f"    Duration: {duration:.1f}s")
            
            if fps == 0 or total_frames == 0:
                print("  ✗ Could not read video properties")
                cap.release()
                return []
            
            frame_count = 0
            extracted_count = 0
            interval = int(fps * self.config.FRAMES_SAMPLE_RATE)
            
            print(f"  Extracting frames (every {self.config.FRAMES_SAMPLE_RATE}s)...")
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Extract every N frames
                if frame_count % interval == 0:
                    timestamp = frame_count / fps
                    frame_filename = f"frame_{extracted_count:04d}_{timestamp:.2f}s.jpg"
                    frame_path = self.config.FRAMES_DIR / frame_filename
                    
                    # Resize for better OCR
                    resized = cv2.resize(frame, (1920, 1080))
                    cv2.imwrite(str(frame_path), resized)
                    
                    frames_data.append({
                        'index': extracted_count,
                        'timestamp': timestamp,
                        'path': str(frame_path),
                        'filename': frame_filename
                    })
                    extracted_count += 1
                
                frame_count += 1
                
                if extracted_count % 100 == 0:
                    print(f"    Extracted {extracted_count} frames...")
            
            cap.release()
            print(f"  ✓ Total extracted: {extracted_count} frames")
            return frames_data
            
        except Exception as e:
            print(f"✗ Frame extraction failed: {e}")
            return []

# OCR Processing
class LotteryOCR:
    """Extract 4-digit numbers from frames"""
    
    def __init__(self, config: Config):
        self.config = config

    def extract_4digit_numbers(self, frames_data: List[Dict]) -> Dict[str, Dict]:
        """Extract 4-digit numbers from frames using OCR"""
        ocr_results = {}
        
        print(f"\n  Processing {len(frames_data)} frames with OCR...")
        print(f"  (This may take several minutes)\n")
        
        processed = 0
        for i, frame_data in enumerate(frames_data):
            try:
                image = Image.open(frame_data['path'])
                
                # OCR with high accuracy settings - DIGITS ONLY
                custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789'
                text = pytesseract.image_to_string(image, config=custom_config)
                
                # Extract 4-digit numbers
                numbers = re.findall(r'\b\d{4}\b', text)
                
                if numbers:
                    ocr_results[frame_data['filename']] = {
                        'timestamp': frame_data['timestamp'],
                        'path': frame_data['path'],
                        'numbers': numbers,
                        'raw_text': text,
                        'detection_count': len(numbers)
                    }
                
                processed += 1
                if processed % 50 == 0:
                    print(f"    Processed {processed}/{len(frames_data)} frames - {len(ocr_results)} with numbers found")
                    
            except Exception as e:
                pass
        
        print(f"\n  ✓ OCR Completed")
        print(f"    Total frames processed: {len(frames_data)}")
        print(f"    Frames with detected numbers: {len(ocr_results)}")
        
        return ocr_results

# Roller Analyzer
class RollerAnalyzer:
    """Analyze which roller produced which number"""
    
    def __init__(self, config: Config):
        self.config = config

    def analyze_roller_sequence(self, 
                               ocr_results: Dict,
                               pdf_prizes: Dict) -> List[Dict]:
        """Match detected numbers to roller positions"""
        analysis = []
        all_pdf_numbers = set()
        
        # Collect all PDF prizes
        for prize_type, numbers in pdf_prizes.items():
            all_pdf_numbers.update(numbers)
        
        print(f"\n  Total unique winning numbers in PDF: {len(all_pdf_numbers)}")
        print(f"  Total detections from video: {sum(len(v['numbers']) for v in ocr_results.values())}")
        
        # Process each frame's detections
        for frame_name, frame_ocr in ocr_results.items():
            detected_numbers = frame_ocr['numbers']
            
            for num in detected_numbers:
                roller_info = self._calculate_roller_position(num)
                is_winning = num in all_pdf_numbers
                prize_type = self._find_prize_type(num, pdf_prizes)
                
                analysis.append({
                    'frame_name': frame_name,
                    'timestamp': frame_ocr['timestamp'],
                    'detected_number': num,
                    'is_winning_number': is_winning,
                    'prize_type': prize_type or 'unknown',
                    'roller_group': roller_info['group'],
                    'roller_in_group': roller_info['position'],
                    'roller_id': roller_info['roller_id'],
                    'raw_text': frame_ocr['raw_text'][:100] if frame_ocr['raw_text'] else ''
                })
        
        return analysis

    def _calculate_roller_position(self, number: str) -> Dict:
        """Calculate roller group and position from 4-digit number"""
        num_val = int(number)
        normalized = num_val % 7200
        
        group = normalized // 400
        roller_in_group = (normalized % 400) // 100
        roller_id = group * 4 + roller_in_group
        
        return {
            'group': int(group) % 18,
            'position': int(roller_in_group) % 4,
            'roller_id': int(roller_id) % 72
        }

    def _find_prize_type(self, number: str, pdf_prizes: Dict) -> Optional[str]:
        """Find which prize category this number belongs to"""
        for prize_type, numbers in pdf_prizes.items():
            if number in numbers:
                return prize_type
        return None

# Data Aggregator
class DataAggregator:
    def __init__(self, config: Config):
        self.config = config

    def save_to_csv(self, results: List[Dict], metadata: Dict) -> bool:
        """Save results to CSV"""
        try:
            if not results:
                print("✗ No results to save")
                return False
            
            # Add metadata to each result
            for result in results:
                result['serial_number'] = metadata.get('serialNumber', 'N/A')
                result['event_order'] = metadata.get('event_order', 'N/A')
                result['pdf_file'] = metadata.get('fileName', 'N/A')
                result['draw_date'] = metadata.get('date', 'N/A')
            
            fieldnames = [
                'event_order',
                'serial_number',
                'draw_date',
                'pdf_file',
                'frame_name',
                'timestamp',
                'detected_number',
                'is_winning_number',
                'prize_type',
                'roller_group',
                'roller_in_group',
                'roller_id',
                'raw_text'
            ]
            
            with open(self.config.CSV_OUTPUT, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)
            
            print(f"\n✓ Results saved to: {self.config.CSV_OUTPUT}")
            return True
            
        except Exception as e:
            print(f"✗ Save failed: {e}")
            return False

# Main Agent
class LotteryRollerAnalysisAgent:
    def __init__(self):
        self.config = Config()
        self.csv_manager = CSVDataManager(self.config.MASTER_CSV)
        self.video_analyzer = VideoFileAnalyzer(self.csv_manager)
        self.frame_extractor = FrameExtractor(self.config)
        self.ocr_processor = LotteryOCR(self.config)
        self.roller_analyzer = RollerAnalyzer(self.config)
        self.pdf_analyzer = PrizeExtractor()
        self.data_aggregator = DataAggregator(self.config)

    def analyze_video(self, video_path: str, csv_record: Dict, pdf_path: str) -> bool:
        """Analyze local video file"""
        
        print("\n" + "="*70)
        print("LOTTERY ROLLER ANALYSIS AGENT")
        print("="*70 + "\n")
        
        # Step 1: Display loaded data
        print("[1/6] Loading data from CSV...")
        print(f"✓ Event Order: {csv_record.get('event_order')}")
        print(f"✓ Serial Number: {csv_record.get('serialNumber')}")
        print(f"✓ Date: {csv_record.get('date')}")
        print(f"✓ PDF File: {csv_record.get('fileName')}")
        print(f"✓ Series Count: {csv_record.get('series_count')}")
        
        # Step 2: Extract prizes from PDF
        print("\n[2/6] Extracting prizes from PDF...")
        if not Path(pdf_path).exists():
            print(f"✗ PDF not found: {pdf_path}")
            return False
        
        print(f"✓ PDF found: {pdf_path}")
        pdf_prizes = self.pdf_analyzer.extract_prizes_from_pdf(pdf_path)
        
        # Step 3: Load and extract frames
        print("\n[3/6] Loading video and extracting frames...")
        if not Path(video_path).exists():
            print(f"✗ Video not found: {video_path}")
            return False
        
        filename = Path(video_path).name
        print(f"✓ Video loaded: {filename}")
        frames_data = self.frame_extractor.extract_frames(str(video_path))
        if not frames_data:
            print("✗ No frames extracted")
            return False
        
        # Step 4: OCR to detect lottery numbers
        print("\n[4/6] Running OCR to detect lottery numbers...")
        ocr_results = self.ocr_processor.extract_4digit_numbers(frames_data)
        if not ocr_results:
            print("⚠ No lottery numbers detected in frames")
        
        # Step 5: Analyze roller positions
        print("\n[5/6] Analyzing roller positions and matching with PDF...")
        analysis_results = self.roller_analyzer.analyze_roller_sequence(
            ocr_results, pdf_prizes
        )
        
        # Step 6: Save results
        print("\n[6/6] Saving results...")
        success = self.data_aggregator.save_to_csv(analysis_results, csv_record)
        
        # Summary
        self._print_summary(analysis_results, pdf_prizes, csv_record)
        
        return success

    def _print_summary(self, analysis: List[Dict], pdf_prizes: Dict, csv_record: Dict):
        """Print analysis summary"""
        winning_detections = [r for r in analysis if r['is_winning_number']]
        
        print("\n" + "="*70)
        print("ANALYSIS SUMMARY")
        print("="*70)
        
        print(f"\nEvent Data:")
        print(f"  Event Order: {csv_record.get('event_order')}")
        print(f"  Serial Number: {csv_record.get('serialNumber')}")
        print(f"  Date: {csv_record.get('date')}")
        print(f"  PDF File: {csv_record.get('fileName')}")
        
        print(f"\nDetection Results:")
        print(f"  Total Numbers Detected: {len(analysis)}")
        print(f"  Winning Numbers Detected: {len(winning_detections)}")
        
        if len(analysis) > 0:
            accuracy = len(winning_detections) / len(analysis) * 100
            print(f"  Detection Accuracy: {accuracy:.1f}%")
        
        total_winning = sum(len(v) for v in pdf_prizes.values())
        print(f"\nPDF Data:")
        print(f"  Total Unique Winning Numbers: {total_winning}")
        
        print(f"\nPrize Breakdown:")
        for prize_type in sorted(pdf_prizes.keys()):
            count = len(pdf_prizes[prize_type])
            detected_count = sum(1 for r in analysis if r['prize_type'] == prize_type)
            if count > 0:
                print(f"  {prize_type}: PDF={count} | Detected={detected_count}")
        
        # Roller statistics
        if analysis:
            roller_counts = {}
            winning_roller_counts = {}
            
            for result in analysis:
                roller_id = result['roller_id']
                roller_counts[roller_id] = roller_counts.get(roller_id, 0) + 1
                
                if result['is_winning_number']:
                    winning_roller_counts[roller_id] = winning_roller_counts.get(roller_id, 0) + 1
            
            print(f"\nRoller Activity:")
            print(f"  Active Rollers: {len(roller_counts)}/72")
            
            top_rollers = sorted(roller_counts.items(), key=lambda x: x[1], reverse=True)[:15]
            print(f"\n  Top 15 Active Rollers:")
            print(f"  {'ID':<4} {'Group':<7} {'Pos':<4} {'Total':<8} {'Winning':<8} {'Accuracy':<10}")
            print(f"  {'-'*50}")
            
            for roller_id, count in top_rollers:
                group = roller_id // 4
                pos = roller_id % 4
                winning = winning_roller_counts.get(roller_id, 0)
                accuracy = (winning / count * 100) if count > 0 else 0
                print(f"  {roller_id:<4} {group:<7} {pos:<4} {count:<8} {winning:<8} {accuracy:>6.1f}%")
        
        print("\n" + "="*70 + "\n")

    def analyze_all_videos(self):
        """Analyze all videos matching CSV data"""
        print("\n" + "="*70)
        print("BATCH ANALYSIS - ALL VIDEOS")
        print("="*70)
        
        all_records = self.csv_manager.get_all_records()
        
        if not all_records:
            print("\n✗ No records found in CSV")
            return
        
        print(f"\n✓ Found {len(all_records)} records in CSV\n")
        
        success_count = 0
        
        for record in all_records:
            event_order = record.get('event_order', '')
            serial_number = record.get('serialNumber', '')
            pdf_file = record.get('fileName', '')
            
            print(f"\n{'='*70}")
            print(f"Processing Event {event_order}: {serial_number}")
            print(f"{'='*70}")
            
            # Try to find matching video
            video_path = None
            for video_file in Path('.').glob('*'):
                if video_file.suffix.lower() in ['.mp4', '.avi', '.mkv', '.mov', '.flv']:
                    if serial_number in video_file.name:
                        video_path = str(video_file)
                        break
            
            if not video_path:
                print(f"⚠ No video found for {serial_number}")
                continue
            
            # Check if PDF exists
            if not Path(pdf_file).exists():
                print(f"⚠ PDF not found: {pdf_file}")
                continue
            
            # Analyze this video
            if self.analyze_video(video_path, record, pdf_file):
                success_count += 1
        
        print(f"\n\n{'='*70}")
        print(f"BATCH ANALYSIS COMPLETE")
        print(f"Successfully processed: {success_count}/{len(all_records)} events")
        print(f"{'='*70}\n")

# Run Agent
if __name__ == "__main__":
    agent = LotteryRollerAnalysisAgent()
    
    # Print available data
    print("\n" + "="*70)
    print("AVAILABLE DATA IN all_data.csv")
    print("="*70)
    agent.csv_manager.print_records()
    
    # Option 1: Analyze single video (auto-detect)
    result = agent.video_analyzer.find_video_file(".")
    
    if result:
        video_path, csv_record = result
        
        if csv_record:
            pdf_file = csv_record.get('fileName', '')
            
            if Path(pdf_file).exists():
                agent.analyze_video(video_path, csv_record, pdf_file)
            else:
                print(f"\n✗ PDF not found: {pdf_file}")
        else:
            print("\n⚠ Could not match video with CSV record")
    else:
        print("\n✗ No video file found")
    
    # Option 2: Uncomment to analyze all videos
    # agent.analyze_all_videos()
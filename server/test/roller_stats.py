# roller_stats.py - Generate detailed roller statistics

import csv
from pathlib import Path
from collections import defaultdict

class RollerStatistics:
    """Analyze roller performance"""
    
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.data = self._load_csv()
    
    def _load_csv(self) -> List[Dict]:
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    
    def generate_roller_report(self) -> Dict:
        """Generate detailed roller statistics"""
        report = {
            'total_detections': len(self.data),
            'rollers': {},
            'groups': {},
            'prize_distribution': defaultdict(int)
        }
        
        for record in self.data:
            roller_id = int(record['roller_id'])
            group = int(record['roller_group'])
            prize_type = record['prize_type']
            is_winning = record['is_winning_number'] == 'True'
            
            # Roller stats
            if roller_id not in report['rollers']:
                report['rollers'][roller_id] = {
                    'group': group,
                    'position': roller_id % 4,
                    'total_detections': 0,
                    'winning_detections': 0,
                    'accuracy': 0
                }
            
            report['rollers'][roller_id]['total_detections'] += 1
            if is_winning:
                report['rollers'][roller_id]['winning_detections'] += 1
            
            # Group stats
            if group not in report['groups']:
                report['groups'][group] = {
                    'total_detections': 0,
                    'winning_detections': 0
                }
            
            report['groups'][group]['total_detections'] += 1
            if is_winning:
                report['groups'][group]['winning_detections'] += 1
            
            # Prize distribution
            report['prize_distribution'][prize_type] += 1
        
        # Calculate accuracy
        for roller_id, stats in report['rollers'].items():
            if stats['total_detections'] > 0:
                stats['accuracy'] = stats['winning_detections'] / stats['total_detections']
        
        return report
    
    def print_report(self):
        report = self.generate_roller_report()
        
        print("\n" + "="*70)
        print("DETAILED ROLLER REPORT")
        print("="*70)
        
        print(f"\nTotal Detections: {report['total_detections']}")
        
        print("\n--- Top 10 Rollers by Winning Detections ---")
        top_rollers = sorted(
            report['rollers'].items(),
            key=lambda x: x[1]['winning_detections'],
            reverse=True
        )[:10]
        
        for roller_id, stats in top_rollers:
            acc = stats['accuracy'] * 100
            print(f"Roller {roller_id:2d} (G{stats['group']:2d},P{stats['position']}) | "
                  f"Wins: {stats['winning_detections']:3d} | "
                  f"Total: {stats['total_detections']:3d} | "
                  f"Accuracy: {acc:5.1f}%")
        
        print("\n--- Group Summary ---")
        for group in sorted(report['groups'].keys()):
            stats = report['groups'][group]
            acc = (stats['winning_detections'] / stats['total_detections'] * 100) if stats['total_detections'] > 0 else 0
            print(f"Group {group:2d}: {stats['winning_detections']:3d}/{stats['total_detections']:3d} "
                  f"({acc:5.1f}% accuracy)")
        
        print("\n--- Prize Distribution ---")
        for prize_type in sorted(report['prize_distribution'].keys()):
            count = report['prize_distribution'][prize_type]
            print(f"{prize_type}: {count}")
        
        print("="*70 + "\n")

# Run statistics
if __name__ == "__main__":
    stats = RollerStatistics("lottery_analysis_output/roller_analysis.csv")
    stats.print_report()
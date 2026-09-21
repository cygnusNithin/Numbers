"""
UPDATED Kerala Lottery Scheme Detection
Analyzes each lottery type separately based on serial number prefix
"""

import pymongo
from pymongo import MongoClient
import pandas as pd
import numpy as np
from scipy import stats
from collections import defaultdict
import json

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

class LotteryTypeAnalyzer:
    """Analyzes lottery data separated by lottery type (serial prefix)"""
    
    def __init__(self):
        self.client = MongoClient(MONGO_URI)
        self.db = self.client[DB_NAME]
        self.collection = self.db[COLLECTION]
    
    def load_and_separate_by_type(self):
        """Load data and separate by lottery type (serial prefix)"""
        print("📦 Loading lottery data...")
        
        data = list(self.collection.find({}))
        print(f"✅ Loaded {len(data)} entries\n")
        
        # Separate by lottery type (serial prefix)
        lottery_types = defaultdict(list)
        
        for entry in data:
            serial = entry.get('serialNumber', 'UNKNOWN')
            prefix = serial.split('-')[0] if '-' in serial else 'UNKNOWN'
            
            date = entry.get('date', '')
            series = entry.get('series', [])
            
            for prize_data in series:
                prize = prize_data.get('prize', 0)
                numbers = prize_data.get('numbers', [])
                
                for num_data in numbers:
                    number = num_data.get('number', '').zfill(4)
                    count = num_data.get('count', 1)
                    
                    lottery_types[prefix].append({
                        'date': date,
                        'serial': serial,
                        'prize': prize,
                        'number': number,
                        'count': count
                    })
        
        print("🎰 Lottery Types Detected:")
        print("-" * 60)
        for lottery_type, results in sorted(lottery_types.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"  {lottery_type:15s}: {len(results):6d} results")
        
        return lottery_types
    
    def analyze_lottery_type(self, lottery_name, results):
        """Analyze a single lottery type"""
        print(f"\n{'='*80}")
        print(f"🎯 ANALYZING: {lottery_name} LOTTERY")
        print(f"{'='*80}")
        
        df = pd.DataFrame(results)
        df['number'] = df['number'].astype(str).str.zfill(4)
        
        # Extract digits
        df['digit_1'] = df['number'].str[0].astype(int)
        df['digit_2'] = df['number'].str[1].astype(int)
        df['digit_3'] = df['number'].str[2].astype(int)
        df['digit_4'] = df['number'].str[3].astype(int)
        
        total = len(df)
        unique = df['number'].nunique()
        
        print(f"\n📊 Statistics:")
        print(f"   Total Results: {total}")
        print(f"   Unique Numbers: {unique}")
        print(f"   Coverage: {(unique/10000)*100:.1f}% of all possible numbers")
        
        # Test 1: Digit 7 Bias
        print(f"\n🔍 Digit '7' Frequency Test:")
        bias_score = 0
        
        for pos in [1, 2, 3, 4]:
            col = f'digit_{pos}'
            digit_7_count = (df[col] == 7).sum()
            digit_7_pct = (digit_7_count / total) * 100
            deviation = digit_7_pct - 10.0
            
            status = "✅" if abs(deviation) < 2 else "⚠️" if abs(deviation) < 5 else "🚨"
            print(f"   Position {pos}: {digit_7_pct:5.2f}% {status}")
            
            if abs(deviation) > 5:
                bias_score += 15
            elif abs(deviation) > 2:
                bias_score += 5
        
        # Test 2: Chi-Square
        print(f"\n📈 Chi-Square Uniformity Test:")
        chi_score = 0
        
        for pos in [1, 2, 3, 4]:
            col = f'digit_{pos}'
            observed = np.zeros(10)
            for digit in range(10):
                observed[digit] = (df[col] == digit).sum()
            
            expected = np.full(10, total / 10)
            chi2, p_value = stats.chisquare(observed, expected)
            
            if p_value < 0.001:
                status = "🚨 NOT RANDOM"
                chi_score += 15
            elif p_value < 0.01:
                status = "⚠️ QUESTIONABLE"
                chi_score += 10
            elif p_value < 0.05:
                status = "⚠️ MARGINAL"
                chi_score += 5
            else:
                status = "✅ RANDOM"
            
            print(f"   Position {pos}: p={p_value:.6f} {status}")
        
        # Test 3: Overall Distribution
        print(f"\n📊 Digit Distribution Summary:")
        distribution_score = 0
        
        for pos in [1, 2, 3, 4]:
            col = f'digit_{pos}'
            freq = df[col].value_counts().sort_index()
            
            deviations = []
            for digit in range(10):
                count = freq.get(digit, 0)
                pct = (count / total) * 100
                deviation = abs(pct - 10.0)
                deviations.append(deviation)
                
                if pct > 15 or pct < 5:
                    distribution_score += 8
                elif pct > 12 or pct < 8:
                    distribution_score += 3
            
            max_dev = max(deviations)
            avg_dev = sum(deviations) / len(deviations)
            
            status = "✅" if max_dev < 2 else "⚠️" if max_dev < 5 else "🚨"
            print(f"   Position {pos}: Max deviation ±{max_dev:.1f}%, Avg ±{avg_dev:.1f}% {status}")
        
        # Calculate total fraud score
        fraud_score = bias_score + chi_score + distribution_score
        fraud_pct = min((fraud_score / 100) * 100, 100)
        
        print(f"\n{'='*80}")
        print(f"📊 {lottery_name} LOTTERY FRAUD SCORE: {fraud_score}/100 ({fraud_pct:.1f}%)")
        
        if fraud_pct >= 70:
            verdict = "🚨 HIGHLY SUSPICIOUS"
        elif fraud_pct >= 50:
            verdict = "⚠️ SUSPICIOUS"
        elif fraud_pct >= 30:
            verdict = "⚠️ CONCERNING"
        elif fraud_pct >= 15:
            verdict = "⚠️ SLIGHT CONCERN"
        else:
            verdict = "✅ APPEARS FAIR"
        
        print(f"🏁 VERDICT: {verdict}")
        print(f"{'='*80}")
        
        return {
            'lottery_type': lottery_name,
            'total_results': total,
            'unique_numbers': unique,
            'fraud_score': fraud_score,
            'fraud_percentage': fraud_pct,
            'verdict': verdict,
            'bias_score': bias_score,
            'chi_score': chi_score,
            'distribution_score': distribution_score
        }
    
    def analyze_all(self):
        """Analyze all lottery types"""
        print(f"\n{'='*80}")
        print(f"🎰 KERALA LOTTERY - BY TYPE ANALYSIS")
        print(f"{'='*80}")
        
        lottery_types = self.load_and_separate_by_type()
        
        results = []
        
        for lottery_name, lottery_data in sorted(lottery_types.items()):
            if len(lottery_data) < 100:  # Skip if too few samples
                print(f"\n⏭️  Skipping {lottery_name} (only {len(lottery_data)} results)")
                continue
            
            result = self.analyze_lottery_type(lottery_name, lottery_data)
            results.append(result)
        
        # Summary
        print(f"\n{'='*80}")
        print(f"📋 SUMMARY OF ALL LOTTERY TYPES")
        print(f"{'='*80}\n")
        
        print(f"{'Lottery Type':<20} {'Results':<10} {'Unique #s':<10} {'Score':<8} {'Verdict'}")
        print(f"{'-'*80}")
        
        for r in sorted(results, key=lambda x: x['fraud_score'], reverse=True):
            print(f"{r['lottery_type']:<20} {r['total_results']:<10} "
                  f"{r['unique_numbers']:<10} {r['fraud_score']:<8} {r['verdict']}")
        
        # Save report
        report = {
            'summary': {
                'total_lottery_types': len(results),
                'analysis_date': pd.Timestamp.now().isoformat(),
            },
            'lottery_results': results
        }
        
        with open('lottery_by_type_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n💾 Report saved to: lottery_by_type_report.json")
        
        return results

def main():
    analyzer = LotteryTypeAnalyzer()
    results = analyzer.analyze_all()
    
    print(f"\n{'='*80}")
    print(f"✅ ANALYSIS COMPLETE")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
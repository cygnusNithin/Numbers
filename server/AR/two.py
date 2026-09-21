"""
Kerala Lottery Scheme Detection Tool
=====================================
Analyzes MongoDB lottery data to detect:
- Manipulation patterns
- Statistical anomalies
- Digit bias (especially '7' starting position)
- Set usage patterns
- Temporal fraud indicators
"""

import pymongo
from pymongo import MongoClient
from datetime import datetime
from collections import Counter, defaultdict
import statistics
import json
import pandas as pd
from scipy import stats
import numpy as np

# ============================================================================
# CONFIGURATION
# ============================================================================

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

# ============================================================================
# DATA LOADER
# ============================================================================

class LotteryDataLoader:
    def __init__(self, mongo_uri, db_name, collection_name):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
    
    def load_all_data(self):
        """Load all lottery data from MongoDB"""
        print("📦 Loading data from MongoDB...")
        
        data = list(self.collection.find({}))
        print(f"✅ Loaded {len(data)} lottery entries")
        
        return data
    
    def extract_results(self, data):
        """
        Extract results from nested structure
        Returns: List of dicts with date, prize, number, count
        """
        results = []
        
        for entry in data:
            date = entry.get('date', '')
            serial = entry.get('serialNumber', '')
            series = entry.get('series', [])
            
            for prize_data in series:
                prize = prize_data.get('prize', 0)
                numbers = prize_data.get('numbers', [])
                
                for num_data in numbers:
                    number = num_data.get('number', '').zfill(4)  # Ensure 4 digits
                    count = num_data.get('count', 1)
                    
                    results.append({
                        'date': date,
                        'serial': serial,
                        'prize': prize,
                        'number': number,
                        'count': count
                    })
        
        print(f"📊 Extracted {len(results)} individual results")
        return results
    
    def close(self):
        self.client.close()


# ============================================================================
# SCHEME DETECTOR
# ============================================================================

class SchemeDetector:
    def __init__(self, results):
        self.results = results
        self.df = pd.DataFrame(results)
        
        # Ensure 4-digit format
        self.df['number'] = self.df['number'].astype(str).str.zfill(4)
        
        # Extract individual digits
        self.df['digit_1'] = self.df['number'].str[0].astype(int)
        self.df['digit_2'] = self.df['number'].str[1].astype(int)
        self.df['digit_3'] = self.df['number'].str[2].astype(int)
        self.df['digit_4'] = self.df['number'].str[3].astype(int)
        
        # Parse dates
        try:
            self.df['datetime'] = pd.to_datetime(self.df['date'], format='%d/%m/%Y', errors='coerce')
        except:
            self.df['datetime'] = pd.to_datetime(self.df['date'], errors='coerce')
        
        self.anomalies = []
        self.fraud_score = 0
        self.max_fraud_score = 100
        
        print(f"\n{'='*80}")
        print(f"🔍 SCHEME DETECTION INITIALIZED")
        print(f"{'='*80}")
        print(f"📊 Total Results: {len(self.df)}")
        print(f"📅 Date Range: {self.df['datetime'].min()} to {self.df['datetime'].max()}")
        print(f"🎯 Unique Numbers: {self.df['number'].nunique()}")
        print(f"💰 Prize Categories: {sorted(self.df['prize'].unique())}")
    
    
    # ========================================================================
    # TEST 1: DIGIT '7' STARTING POSITION BIAS
    # ========================================================================
    
    def test_digit_7_bias(self):
        """
        CRITICAL TEST: Check if digit '7' appears more frequently
        (since all roller sequences start with '7')
        """
        print(f"\n{'='*80}")
        print(f"🚨 TEST 1: DIGIT '7' STARTING POSITION BIAS")
        print(f"{'='*80}")
        print("Since all roller sequences start with '7', checking if this creates bias...")
        
        bias_detected = False
        
        for pos in [1, 2, 3, 4]:
            col = f'digit_{pos}'
            total = len(self.df)
            
            digit_7_count = (self.df[col] == 7).sum()
            digit_7_pct = (digit_7_count / total) * 100
            expected_pct = 10.0
            deviation = digit_7_pct - expected_pct
            
            print(f"\n📍 Position {pos}:")
            print(f"   Digit '7' appears: {digit_7_count} times ({digit_7_pct:.2f}%)")
            print(f"   Expected: ~{expected_pct}%")
            print(f"   Deviation: {deviation:+.2f}%")
            
            if abs(deviation) > 5:
                status = "🚨 SIGNIFICANT BIAS DETECTED!"
                severity = "CRITICAL" if abs(deviation) > 10 else "HIGH"
                self.fraud_score += 15 if abs(deviation) > 10 else 10
                bias_detected = True
                
                self.anomalies.append({
                    'test': 'digit_7_bias',
                    'position': pos,
                    'severity': severity,
                    'digit_7_percentage': digit_7_pct,
                    'deviation': deviation,
                    'message': f"Digit '7' appears {digit_7_pct:.1f}% in position {pos} (expected 10%)"
                })
                
            elif abs(deviation) > 2:
                status = "⚠️ ELEVATED (slight bias)"
                severity = "MEDIUM"
                self.fraud_score += 3
                
                self.anomalies.append({
                    'test': 'digit_7_bias',
                    'position': pos,
                    'severity': severity,
                    'digit_7_percentage': digit_7_pct,
                    'deviation': deviation,
                    'message': f"Slight bias toward '7' in position {pos}"
                })
            else:
                status = "✅ NORMAL"
            
            print(f"   Status: {status}")
        
        if bias_detected:
            print(f"\n🚨 CONCLUSION: Rollers favor starting position '7'!")
            print(f"   This suggests physics-based manipulation or biased mechanisms.")
        else:
            print(f"\n✅ CONCLUSION: No significant '7' bias detected.")
    
    
    # ========================================================================
    # TEST 2: OVERALL DIGIT FREQUENCY DISTRIBUTION
    # ========================================================================
    
    def test_digit_frequency(self):
        """Test if all digits 0-9 appear uniformly across positions"""
        print(f"\n{'='*80}")
        print(f"📊 TEST 2: DIGIT FREQUENCY DISTRIBUTION")
        print(f"{'='*80}")
        
        total = len(self.df)
        
        for pos in [1, 2, 3, 4]:
            col = f'digit_{pos}'
            freq = self.df[col].value_counts().sort_index()
            
            print(f"\n🎯 Position {pos} (Thousands/Hundreds/Tens/Units):")
            print(f"   {'Digit':<8} {'Count':<10} {'Percentage':<12} {'Status'}")
            print(f"   {'-'*50}")
            
            expected = total / 10
            
            for digit in range(10):
                count = freq.get(digit, 0)
                pct = (count / total) * 100
                deviation = ((count - expected) / expected) * 100
                
                if abs(deviation) > 20:
                    status = "🚨 EXTREME"
                    self.fraud_score += 8
                    self.anomalies.append({
                        'test': 'digit_frequency',
                        'position': pos,
                        'digit': digit,
                        'severity': 'HIGH',
                        'percentage': pct,
                        'deviation': deviation,
                        'message': f"Digit {digit} in position {pos}: {pct:.1f}% (extreme bias)"
                    })
                elif abs(deviation) > 10:
                    status = "⚠️ HIGH"
                    self.fraud_score += 4
                    self.anomalies.append({
                        'test': 'digit_frequency',
                        'position': pos,
                        'digit': digit,
                        'severity': 'MEDIUM',
                        'percentage': pct,
                        'deviation': deviation,
                        'message': f"Digit {digit} in position {pos}: {pct:.1f}% (moderate bias)"
                    })
                else:
                    status = "✅ OK"
                
                print(f"   {digit:<8} {count:<10} {pct:>6.2f}%      {status}")
    
    
    # ========================================================================
    # TEST 3: CHI-SQUARE UNIFORMITY TEST
    # ========================================================================
    
    def test_chi_square(self):
        """Statistical test for uniform distribution"""
        print(f"\n{'='*80}")
        print(f"📈 TEST 3: CHI-SQUARE UNIFORMITY TEST")
        print(f"{'='*80}")
        print("Tests if digit distribution is statistically random...")
        
        for pos in [1, 2, 3, 4]:
            col = f'digit_{pos}'
            observed = np.zeros(10)
            
            for digit in range(10):
                observed[digit] = (self.df[col] == digit).sum()
            
            expected = np.full(10, len(self.df) / 10)
            
            chi2, p_value = stats.chisquare(observed, expected)
            
            print(f"\n🎯 Position {pos}:")
            print(f"   Chi-square statistic: {chi2:.4f}")
            print(f"   P-value: {p_value:.6f}")
            
            if p_value < 0.001:
                status = "🚨 HIGHLY SIGNIFICANT - NOT RANDOM!"
                self.fraud_score += 15
                self.anomalies.append({
                    'test': 'chi_square',
                    'position': pos,
                    'severity': 'CRITICAL',
                    'chi2': chi2,
                    'p_value': p_value,
                    'message': f"Position {pos} is NOT random (p={p_value:.6f})"
                })
            elif p_value < 0.01:
                status = "🚨 VERY SIGNIFICANT - Likely NOT random"
                self.fraud_score += 10
                self.anomalies.append({
                    'test': 'chi_square',
                    'position': pos,
                    'severity': 'HIGH',
                    'chi2': chi2,
                    'p_value': p_value,
                    'message': f"Position {pos} shows non-random pattern (p={p_value:.6f})"
                })
            elif p_value < 0.05:
                status = "⚠️ SIGNIFICANT - May not be random"
                self.fraud_score += 5
                self.anomalies.append({
                    'test': 'chi_square',
                    'position': pos,
                    'severity': 'MEDIUM',
                    'chi2': chi2,
                    'p_value': p_value,
                    'message': f"Position {pos} marginally non-random (p={p_value:.6f})"
                })
            else:
                status = "✅ NOT SIGNIFICANT - Appears random"
            
            print(f"   Status: {status}")
    
    
    # ========================================================================
    # TEST 4: DUPLICATE & REPETITION ANALYSIS
    # ========================================================================
    
    def test_duplicates(self):
        """Check for suspicious duplicate results"""
        print(f"\n{'='*80}")
        print(f"🔄 TEST 4: DUPLICATE & REPETITION ANALYSIS")
        print(f"{'='*80}")
        
        # Overall duplicates
        total_results = len(self.df)
        unique_numbers = self.df['number'].nunique()
        duplicate_rate = (1 - unique_numbers / total_results) * 100
        
        print(f"\n📊 Overall Statistics:")
        print(f"   Total results: {total_results}")
        print(f"   Unique numbers: {unique_numbers}")
        print(f"   Duplicate rate: {duplicate_rate:.2f}%")
        
        # Expected duplicate rate (birthday paradox)
        total_possible = 10000  # 0000-9999
        expected_unique = total_possible * (1 - (1 - 1/total_possible)**total_results)
        expected_duplicate_rate = (1 - expected_unique / total_results) * 100
        
        print(f"   Expected duplicate rate: ~{expected_duplicate_rate:.2f}%")
        
        if duplicate_rate > expected_duplicate_rate * 1.5:
            print(f"   🚨 EXCESSIVE DUPLICATES DETECTED!")
            self.fraud_score += 10
            self.anomalies.append({
                'test': 'duplicates',
                'severity': 'HIGH',
                'duplicate_rate': duplicate_rate,
                'expected_rate': expected_duplicate_rate,
                'message': f"Duplicate rate {duplicate_rate:.1f}% exceeds expected {expected_duplicate_rate:.1f}%"
            })
        
        # Check for consecutive duplicates (same day/close dates)
        self.df_sorted = self.df.sort_values('datetime')
        consecutive_dupes = 0
        
        for i in range(len(self.df_sorted) - 1):
            if self.df_sorted.iloc[i]['number'] == self.df_sorted.iloc[i + 1]['number']:
                date1 = self.df_sorted.iloc[i]['date']
                date2 = self.df_sorted.iloc[i + 1]['date']
                number = self.df_sorted.iloc[i]['number']
                
                consecutive_dupes += 1
                print(f"\n   🚨 CONSECUTIVE DUPLICATE FOUND:")
                print(f"      Number: {number}")
                print(f"      Dates: {date1} and {date2}")
                
                self.fraud_score += 15
                self.anomalies.append({
                    'test': 'consecutive_duplicate',
                    'severity': 'CRITICAL',
                    'number': number,
                    'dates': [date1, date2],
                    'message': f"Same number {number} appeared on consecutive draws"
                })
        
        if consecutive_dupes == 0:
            print(f"\n   ✅ No consecutive duplicates found")
    
    
    # ========================================================================
    # TEST 5: PRIZE CATEGORY ANALYSIS
    # ========================================================================
    
    def test_prize_distribution(self):
        """Check if different prize categories show different patterns"""
        print(f"\n{'='*80}")
        print(f"💰 TEST 5: PRIZE CATEGORY PATTERN ANALYSIS")
        print(f"{'='*80}")
        
        prizes = sorted(self.df['prize'].unique())
        
        print(f"\nAnalyzing {len(prizes)} prize categories...")
        
        # For each prize, check digit '7' frequency
        for prize in prizes:
            prize_data = self.df[self.df['prize'] == prize]
            total = len(prize_data)
            
            if total < 10:  # Skip if too few samples
                continue
            
            print(f"\n💵 Prize: {prize}")
            print(f"   Sample size: {total}")
            
            # Check digit 7 in position 1
            digit_7_count = (prize_data['digit_1'] == 7).sum()
            digit_7_pct = (digit_7_count / total) * 100
            
            print(f"   Digit '7' in position 1: {digit_7_pct:.1f}%")
            
            if abs(digit_7_pct - 10) > 8:
                print(f"   ⚠️ Different pattern than expected!")
                self.anomalies.append({
                    'test': 'prize_pattern',
                    'prize': prize,
                    'severity': 'MEDIUM',
                    'digit_7_percentage': digit_7_pct,
                    'message': f"Prize {prize} shows unusual digit pattern"
                })
                self.fraud_score += 3
    
    
    # ========================================================================
    # TEST 6: TEMPORAL PATTERN ANALYSIS
    # ========================================================================
    
    def test_temporal_patterns(self):
        """Check for time-based manipulation"""
        print(f"\n{'='*80}")
        print(f"📅 TEST 6: TEMPORAL PATTERN ANALYSIS")
        print(f"{'='*80}")
        
        self.df['year'] = self.df['datetime'].dt.year
        self.df['month'] = self.df['datetime'].dt.month
        self.df['day_of_week'] = self.df['datetime'].dt.dayofweek
        
        # Check if digit patterns change over time
        print(f"\n📊 Digit '7' frequency by year:")
        
        for year in sorted(self.df['year'].dropna().unique()):
            year_data = self.df[self.df['year'] == year]
            if len(year_data) < 10:
                continue
            
            digit_7_count = (year_data['digit_1'] == 7).sum()
            digit_7_pct = (digit_7_count / len(year_data)) * 100
            
            print(f"   {int(year)}: {digit_7_pct:.1f}% (n={len(year_data)})")
            
            if abs(digit_7_pct - 10) > 10:
                self.anomalies.append({
                    'test': 'temporal_pattern',
                    'year': int(year),
                    'severity': 'MEDIUM',
                    'digit_7_percentage': digit_7_pct,
                    'message': f"Year {int(year)} shows unusual pattern"
                })
                self.fraud_score += 5
    
    
    # ========================================================================
    # TEST 7: SEQUENTIAL NUMBER DETECTION
    # ========================================================================
    
    def test_sequential_numbers(self):
        """Detect sequential patterns like 1234, 5678, etc."""
        print(f"\n{'='*80}")
        print(f"🔢 TEST 7: SEQUENTIAL NUMBER DETECTION")
        print(f"{'='*80}")
        
        def is_sequential(num):
            digits = [int(d) for d in str(num).zfill(4)]
            # Ascending
            if all(digits[i+1] == digits[i] + 1 for i in range(3)):
                return 'ascending'
            # Descending
            if all(digits[i+1] == digits[i] - 1 for i in range(3)):
                return 'descending'
            return None
        
        sequential = []
        for idx, row in self.df.iterrows():
            seq_type = is_sequential(row['number'])
            if seq_type:
                sequential.append({
                    'number': row['number'],
                    'date': row['date'],
                    'type': seq_type,
                    'prize': row['prize']
                })
        
        print(f"\n   Sequential numbers found: {len(sequential)}")
        
        # Calculate expected
        total_sequential_combos = 14  # 0123, 1234, ..., 9876
        expected = (total_sequential_combos / 10000) * len(self.df)
        
        print(f"   Expected sequential: ~{expected:.1f}")
        
        if len(sequential) > expected * 3:
            print(f"   🚨 EXCESSIVE sequential numbers!")
            self.fraud_score += 10
            self.anomalies.append({
                'test': 'sequential_numbers',
                'severity': 'HIGH',
                'count': len(sequential),
                'expected': expected,
                'message': f"Found {len(sequential)} sequential numbers (expected ~{expected:.0f})"
            })
        
        if sequential and len(sequential) <= 20:
            print(f"\n   📋 Sequential numbers:")
            for item in sequential[:20]:
                print(f"      {item['number']} ({item['type']}) on {item['date']}")
    
    
    # ========================================================================
    # TEST 8: CORRELATION BETWEEN POSITIONS
    # ========================================================================
    
    def test_correlation(self):
        """Check if digit positions are independent"""
        print(f"\n{'='*80}")
        print(f"🔗 TEST 8: DIGIT POSITION CORRELATION")
        print(f"{'='*80}")
        print("Positions should be independent (correlation ≈ 0)")
        
        corr_matrix = self.df[['digit_1', 'digit_2', 'digit_3', 'digit_4']].corr()
        
        print(f"\n   Correlation Matrix:")
        print(corr_matrix)
        
        # Check for significant correlations
        threshold = 0.15
        found_correlation = False
        
        for i in range(4):
            for j in range(i+1, 4):
                corr = corr_matrix.iloc[i, j]
                if abs(corr) > threshold:
                    found_correlation = True
                    print(f"\n   🚨 CORRELATION DETECTED:")
                    print(f"      Position {i+1} & Position {j+1}: {corr:.3f}")
                    print(f"      Positions are NOT independent!")
                    
                    self.fraud_score += 12
                    self.anomalies.append({
                        'test': 'correlation',
                        'positions': [i+1, j+1],
                        'severity': 'HIGH',
                        'correlation': corr,
                        'message': f"Positions {i+1} and {j+1} are correlated ({corr:.3f})"
                    })
        
        if not found_correlation:
            print(f"\n   ✅ No significant correlations detected")
    
    
    # ========================================================================
    # GENERATE FINAL REPORT
    # ========================================================================
    
    def generate_report(self):
        """Run all tests and generate comprehensive report"""
        print(f"\n{'='*80}")
        print(f"🔍 RUNNING ALL SCHEME DETECTION TESTS")
        print(f"{'='*80}")
        
        # Run all tests
        self.test_digit_7_bias()
        self.test_digit_frequency()
        self.test_chi_square()
        self.test_duplicates()
        self.test_prize_distribution()
        self.test_temporal_patterns()
        self.test_sequential_numbers()
        self.test_correlation()
        
        # Calculate final fraud score
        fraud_percentage = min((self.fraud_score / self.max_fraud_score) * 100, 100)
        
        # Generate verdict
        print(f"\n{'='*80}")
        print(f"🎯 FINAL VERDICT")
        print(f"{'='*80}")
        
        print(f"\n📊 Fraud Risk Score: {self.fraud_score}/{self.max_fraud_score} ({fraud_percentage:.1f}%)")
        
        if fraud_percentage >= 70:
            verdict = "🚨 HIGHLY SUSPICIOUS - Strong evidence of manipulation"
            color = "CRITICAL"
        elif fraud_percentage >= 50:
            verdict = "⚠️ SUSPICIOUS - Multiple anomalies detected"
            color = "HIGH"
        elif fraud_percentage >= 30:
            verdict = "⚠️ CONCERNING - Some irregularities found"
            color = "MEDIUM"
        elif fraud_percentage >= 15:
            verdict = "⚠️ SLIGHT CONCERN - Minor deviations from expected"
            color = "LOW"
        else:
            verdict = "✅ APPEARS FAIR - No significant manipulation detected"
            color = "NORMAL"
        
        print(f"\n🏁 VERDICT: {verdict}")
        
        # Summary of anomalies
        print(f"\n📋 ANOMALIES DETECTED: {len(self.anomalies)}")
        
        if self.anomalies:
            critical = [a for a in self.anomalies if a.get('severity') == 'CRITICAL']
            high = [a for a in self.anomalies if a.get('severity') == 'HIGH']
            medium = [a for a in self.anomalies if a.get('severity') == 'MEDIUM']
            
            if critical:
                print(f"   🚨 CRITICAL: {len(critical)}")
            if high:
                print(f"   🔴 HIGH: {len(high)}")
            if medium:
                print(f"   🟡 MEDIUM: {len(medium)}")
            
            print(f"\n🔍 Top 10 Most Serious Anomalies:")
            sorted_anomalies = sorted(self.anomalies, 
                                    key=lambda x: {'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1}.get(x.get('severity', ''), 0),
                                    reverse=True)
            
            for i, anomaly in enumerate(sorted_anomalies[:10], 1):
                print(f"   {i}. [{anomaly.get('severity')}] {anomaly.get('message')}")
        
        # Save report
        report = {
            'summary': {
                'total_results': len(self.df),
                'unique_numbers': int(self.df['number'].nunique()),
                'date_range': f"{self.df['datetime'].min()} to {self.df['datetime'].max()}",
                'fraud_score': self.fraud_score,
                'fraud_percentage': fraud_percentage,
                'verdict': verdict,
                'verdict_category': color,
            },
            'anomalies': self.anomalies,
            'statistics': {
                'total_anomalies': len(self.anomalies),
                'critical_anomalies': len([a for a in self.anomalies if a.get('severity') == 'CRITICAL']),
                'high_anomalies': len([a for a in self.anomalies if a.get('severity') == 'HIGH']),
                'medium_anomalies': len([a for a in self.anomalies if a.get('severity') == 'MEDIUM']),
            }
        }
        
        # Save to file
        with open('lottery_scheme_report.json', 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\n💾 Full report saved to: lottery_scheme_report.json")
        
        return report


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print(f"\n{'='*80}")
    print(f"🎰 KERALA LOTTERY SCHEME DETECTION SYSTEM")
    print(f"{'='*80}")
    print(f"Analyzing MongoDB data for fraud patterns...\n")
    
    # Load data
    loader = LotteryDataLoader(MONGO_URI, DB_NAME, COLLECTION)
    data = loader.load_all_data()
    results = loader.extract_results(data)
    
    if not results:
        print("❌ No results found in database!")
        return
    
    # Detect schemes
    detector = SchemeDetector(results)
    report = detector.generate_report()
    
    # Close connection
    loader.close()
    
    print(f"\n{'='*80}")
    print(f"✅ ANALYSIS COMPLETE")
    print(f"{'='*80}")
    
    return report


if __name__ == "__main__":
    main()
import pandas as pd
import itertools
from datetime import datetime
import math

FILE_NAME = "all_prizes_number_patterns18.csv"
TARGET_NUMBER = "7396"
CURRENT_DATE = datetime(2026, 1, 12)

def analyze_with_score():
    digits = [d for d in TARGET_NUMBER.zfill(4)]
    perms = set([''.join(p) for p in itertools.permutations(digits)])
    
    try:
        df = pd.read_csv(FILE_NAME)
        df['number'] = df['number'].astype(str).str.zfill(4)
        matched_df = df[df['number'].isin(perms)].copy()
        
        results = []
        for _, row in matched_df.iterrows():
            dates = sorted([datetime.strptime(d, "%d/%m/%Y") for d in str(row['dates']).split('|')])
            last_hit = dates[-1]
            gap = (CURRENT_DATE - last_hit).days
            avg = float(row['avg_gap_days'])
            
            # Confidence Score Calculation
            # Ratio of Gap to Avg weighted by historical frequency
            score = (gap / avg) * math.log10(row['total_hits'] + 1)
            
            results.append({
                "Number": row['number'],
                "Hits": row['total_hits'],
                "Last Hit": last_hit.strftime("%d/%m/%Y"),
                "Gap": gap,
                "Avg": round(avg, 2),
                "Score": round(score, 3),
                "Status": "OVERDUE" if gap > avg else "Normal"
            })

        report = pd.DataFrame(results).sort_values(by="Score", ascending=False)
        print(f"\n--- Scored Permutations for {TARGET_NUMBER} ---")
        print(report.to_string(index=False))
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_with_score()
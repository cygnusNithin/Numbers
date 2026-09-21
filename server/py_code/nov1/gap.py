import csv
from datetime import datetime
import pandas as pd

INPUT = "5000_oct30.csv"
OUTPUT = "recorrected_gaps.csv"
GAP_DETAIL = "gaps_detail.csv"

DATE_FMT = "%d/%m/%Y"

def parse_dates(date_str):
    if not date_str:
        return []
    return sorted([
        datetime.strptime(d.strip(), DATE_FMT)
        for d in date_str.split("|") if d.strip()
    ])

records = []
gap_details = []

with open(INPUT, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    
    for row in reader:
        num = row["number"]
        dates = parse_dates(row["dates"])
        
        # compute all consecutive gaps
        gaps = []
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i-1]).days
            gaps.append(gap)
            
            # store gap detail
            gap_details.append({
                "number": num,
                "from_date": dates[i-1].strftime(DATE_FMT),
                "to_date": dates[i].strftime(DATE_FMT),
                "gap_days": gap
            })

        # compute new average gap
        if len(gaps) > 0:
            avg_gap = sum(gaps) / len(gaps)
        else:
            avg_gap = ""
        
        # update row
        row["avg_gap_days"] = avg_gap
        records.append(row)

# save corrected main file
pd.DataFrame(records).to_csv(OUTPUT, index=False)

# save detailed gap file
pd.DataFrame(gap_details).to_csv(GAP_DETAIL, index=False)

print("Recalculated gaps saved in:")
print(" →", OUTPUT)
print(" →", GAP_DETAIL)

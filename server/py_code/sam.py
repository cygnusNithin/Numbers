import pandas as pd
df = pd.read_csv('all_prizes_number_patterns30.csv')
df.head(200).to_csv('sample_patterns.csv', index=False)
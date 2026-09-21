import pandas as pd

# === Load your CSV (the one you filled manually) ===
df = pd.read_csv("fullRoll.csv")

# Convert sequence strings into tuples of digits
df["seq_list"] = df["sequence"].apply(lambda x: tuple(x.split("|")))

# Normalize function: make rotated versions all look the same
def normalize(seq):
    seq = list(seq)
    rotations = [tuple(seq[i:] + seq[:i]) for i in range(len(seq))]
    return min(rotations)  # pick lexicographically smallest rotation

df["normalized"] = df["seq_list"].apply(normalize)

# Group by normalized pattern
groups = df.groupby("normalized")

# Prepare results
clusters = []
for norm_seq, group in groups:
    clusters.append({
        "pattern": "|".join(norm_seq),
        "count": len(group),
        "members": group[["number_id", "roll_position"]].values.tolist()
    })

# Sort clusters by size (biggest repeated families first)
clusters = sorted(clusters, key=lambda x: x["count"], reverse=True)

# Save to CSV for review
out_df = pd.DataFrame([{
    "pattern": c["pattern"],
    "count": c["count"],
    "members": c["members"]
} for c in clusters])

out_df.to_csv("roller_pattern_clusters.csv", index=False, encoding="utf-8")

print("✅ Clustered rollers saved to roller_pattern_clusters.csv")
print(f"🔎 Found {len(clusters)} unique base patterns across {len(df)} rolls.")

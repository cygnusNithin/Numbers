import pandas as pd

# ==============================
# Config
# ==============================
NUMBERS_LIST = [
    "0182","0192","1131","1773","2529","2903","3363","3448","4504",
    "5163","5425","5799","7414","8136","9201","9273","9316","9926"
]
FULLROLL_CSV = "fullRoll.csv"
OUTPUT_FILE = "cyclic_assignment.csv"

# ==============================
# Helpers
# ==============================
def z4(s): return str(s).zfill(4)

def is_cyclic_permutation(a, b):
    """Check if b is a cyclic permutation of a"""
    a, b = z4(a), z4(b)
    return len(a) == len(b) and b in (a+a)

def same_position_matches(a, b):
    """Count how many rollers match at the same position"""
    a, b = z4(a), z4(b)
    return sum(a[i] == b[i] for i in range(4))

# ==============================
# Step 1: Find cyclic pairs
# ==============================
cyclic_pairs = []
for i, a in enumerate(NUMBERS_LIST):
    for j, b in enumerate(NUMBERS_LIST):
        if i < j and is_cyclic_permutation(a, b):
            cyclic_pairs.append((a, b))

print("🔍 Cyclic permutation pairs:")
for a, b in cyclic_pairs:
    print(f" {a} ↔ {b}")

# ==============================
# Step 2: Load rollers
# ==============================
df = pd.read_csv(FULLROLL_CSV, dtype=str)
rollers = {}
for _, row in df.iterrows():
    nid = int(row["number_id"])
    pos = int(row["roll_position"])
    seq = row["sequence"]
    rollers.setdefault(nid, {})[pos] = seq

slots = sorted(rollers.keys())
slot_candidates = {s: set() for s in slots}

# ==============================
# Step 3: Assign cyclic pairs
# ==============================
# Instead of requiring 4-roller overlap, just seed cyclic numbers into *all* slots
# where they match at least 2 rollers with slot definition
for (a, b) in cyclic_pairs:
    for s in slots:
        roller_pattern = "".join(rollers[s][p] for p in range(1, 5))
        if same_position_matches(a, roller_pattern) >= 2:
            slot_candidates[s].add(a)
        if same_position_matches(b, roller_pattern) >= 2:
            slot_candidates[s].add(b)

# ==============================
# Step 4: Save results
# ==============================
out = []
for s in slots:
    out.append({
        "slot": s,
        "confirmed_numbers": "|".join(sorted(slot_candidates[s])) if slot_candidates[s] else ""
    })

out_df = pd.DataFrame(out)
out_df.to_csv(OUTPUT_FILE, index=False)
print(f"✅ Saved cyclic assignment results → {OUTPUT_FILE}")

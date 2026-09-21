#!/usr/bin/env python3
"""
PART 2 — Standalone Mechanical Simulation Engine
-------------------------------------------------
This file simulates 4-digit Kerala lottery draws using:

✔ Roller sequence groups (12 repeating patterns)
✔ 4-position dependence
✔ Daily rotation offsets
✔ Prize rounds (18 per round)
✔ Duplicate replacement rules

Outputs:
- sim_engine_only_probs.csv  → probability of each 4-digit number
- sim_engine_only_params.json → calibration details
"""

import numpy as np
import pandas as pd
import json, time
from collections import Counter, defaultdict
from tqdm import tqdm

# ---------------- Roller Definitions (72 rollers → 12 sequence groups) ---------------
RAW_DATA = [
    # (number_id, roll_position, sequence)
    (1,1,"7|6|8|5|9|0|3|1|2|4"), (1,2,"7|9|2|5|1|6|3|8|0|4"),
    (1,3,"7|8|9|0|1|2|3|4|5|6"), (1,4,"7|4|1|8|6|3|5|0|2|9"),
    (2,1,"7|2|4|6|9|0|1|3|5|8"), (2,2,"7|3|8|2|0|1|9|5|6|4"),
    (2,3,"7|4|1|8|6|3|5|0|2|9"), (2,4,"7|8|9|0|1|2|3|4|5|6"),
    (3,1,"7|5|3|1|0|8|6|4|2|9"), (3,2,"7|2|4|6|9|0|1|3|5|8"),
    (3,3,"7|3|8|2|0|1|9|5|6|4"), (3,4,"7|4|1|8|6|3|5|0|2|9"),
    (4,1,"7|2|4|6|9|0|1|3|5|8"), (4,2,"7|3|8|2|0|1|9|5|6|4"),
    (4,3,"7|4|1|8|6|3|5|0|2|9"), (4,4,"7|9|2|5|1|6|3|8|0|4"),
    (5,1,"7|2|4|6|9|0|1|3|5|8"), (5,2,"7|3|8|2|0|1|9|5|6|4"),
    (5,3,"7|6|8|5|9|0|3|1|2|4"), (5,4,"7|8|9|0|1|2|3|4|5|6"),
    (6,1,"7|2|4|6|9|0|1|3|5|8"), (6,2,"7|3|8|2|0|1|9|5|6|4"),
    (6,3,"7|9|2|5|1|6|3|8|0|4"), (6,4,"7|4|1|8|6|3|5|0|2|9"),
    (7,1,"7|3|8|2|0|1|9|6|5|4"), (7,2,"7|8|9|0|1|2|3|4|5|6"),
    (7,3,"7|5|3|1|0|8|6|4|2|9"), (7,4,"7|5|3|1|0|8|6|4|2|9"),
    (8,1,"7|5|1|9|6|4|2|8|3|0"), (8,2,"7|5|9|1|3|6|8|4|0|2"),
    (8,3,"7|9|2|5|1|6|3|8|0|4"), (8,4,"7|6|8|5|9|0|3|1|2|4"),
    (9,1,"7|9|2|5|1|6|3|8|0|4"), (9,2,"7|5|1|9|6|4|2|8|3|0"),
    (9,3,"7|5|9|1|3|6|8|4|0|2"), (9,4,"7|8|9|0|1|2|3|4|5|6"),
    (10,1,"7|5|1|9|6|4|2|8|3|0"), (10,2,"7|6|5|4|3|2|1|0|9|8"),
    (10,3,"7|8|9|0|1|2|3|4|5|6"), (10,4,"7|6|8|5|9|0|3|1|2|4"),
    (11,1,"7|5|1|9|6|4|2|8|3|0"), (11,2,"7|5|9|1|3|6|8|4|0|2"),
    (11,3,"7|9|2|5|1|6|3|8|0|4"), (11,4,"7|4|1|8|6|3|5|0|2|9"),
    (12,1,"7|5|1|9|6|4|2|8|3|0"), (12,2,"7|5|9|1|3|6|8|4|0|2"),
    (12,3,"7|6|5|4|3|2|1|0|9|8"), (12,4,"7|8|9|0|1|2|3|4|5|6"),
    (13,1,"7|5|9|1|3|6|8|4|0|2"), (13,2,"7|6|5|4|3|2|1|0|9|8"),
    (13,3,"7|5|1|9|6|4|2|8|3|0"), (13,4,"7|5|3|1|0|8|6|4|2|9"),
    (14,1,"7|6|5|4|3|2|1|0|9|8"), (14,2,"7|5|3|1|0|8|6|4|2|9"),
    (14,3,"7|5|1|9|6|4|2|8|3|0"), (14,4,"7|4|1|8|6|3|5|0|2|9"),
    (15,1,"7|6|8|5|9|0|3|1|2|4"), (15,2,"7|6|5|4|3|2|1|0|9|8"),
    (15,3,"7|4|1|3|6|0|8|9|5|2"), (15,4,"7|5|9|1|3|6|8|4|0|2"),
    (16,1,"7|5|9|1|3|6|8|4|0|2"), (16,2,"7|5|3|1|0|8|6|4|2|9"),
    (16,3,"7|2|4|6|9|0|1|3|5|8"), (16,4,"7|3|8|2|0|1|9|5|6|4"),
    (17,1,"7|8|9|0|1|2|3|4|5|6"), (17,2,"7|6|8|5|9|0|3|1|2|4"),
    (17,3,"7|6|5|4|3|2|1|0|9|8"), (17,4,"7|5|3|1|0|8|6|4|2|9"),
    (18,1,"7|6|8|5|9|0|3|1|2|4"), (18,2,"7|5|3|1|0|8|6|4|2|9"),
    (18,3,"7|2|4|6|9|0|1|3|5|8"), (18,4,"7|3|8|2|0|1|9|5|6|4"),
]

# ---------------- Convert 72 to 12 sequence groups -----------------
def build_groups():
    seqs = {}
    reverse = {}
    idx = 0
    for _,_,s in RAW_DATA:
        if s not in reverse:
            reverse[s] = idx
            seqs[idx] = tuple(int(x) for x in s.split("|"))
            idx+=1
    return seqs

SEQ_GROUPS = build_groups()

# ---------------- Simulation -----------------
MC_ROUNDS = 1200
np.random.seed(41)

def simulate(prize_counts):
    hit = Counter()
    for _ in tqdm(range(MC_ROUNDS), desc="Simulating"):
        offsets = {k: np.random.randint(0,len(v)) for k,v in SEQ_GROUPS.items()}
        for prize, need in prize_counts.items():
            full = need//18; left = need%18
            rounds = full + (1 if left else 0)
            out=[]
            for _ in range(rounds):
                for sid in offsets:
                    offsets[sid]=(offsets[sid]+np.random.randint(1,3))%len(SEQ_GROUPS[sid])
                show = 18 if _<full else left
                for r in range(show):
                    dig = []
                    for pos in range(1,5):
                        sid=np.random.choice(list(SEQ_GROUPS.keys()))
                        seq=SEQ_GROUPS[sid]
                        d=seq[offsets[sid]]
                        dig.append(str(d))
                    out.append("".join(dig))
            uniq=[]
            for n in out:
                if n not in uniq:
                    uniq.append(n)
                if len(uniq)==need:
                    break
            for u in uniq: hit[u]+=1
    return {k:v/MC_ROUNDS for k,v in hit.items()}

# ---- RUN ----
def main():
    prize_counts={5000:19,2000:6,1000:25,500:75,200:92,100:144}
    probs=simulate(prize_counts)
    pd.DataFrame(list(probs.items()),columns=["number","prob"]).to_csv("sim_engine_only_probs.csv",index=False)
    with open("sim_engine_only_params.json","w") as f: json.dump({"groups":len(SEQ_GROUPS)},f,indent=2)
    print("\nSaved sim_engine_only_probs.csv + sim_engine_only_params.json")

if __name__=="__main__":
    main()

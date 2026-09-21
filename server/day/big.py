#!/usr/bin/env python3
"""
Hybrid Predictor (Full) - combines mechanical simulation + calibration + ML ranker

Save as hybrid_predictor_full.py and run:
    python hybrid_predictor_full.py

Adjust MONGO_URI, DB_NAME, COLLECTION, and UPLOADED_CSV as needed.

Outputs:
 - predicted_5000_candidates.csv
 - simulation_probs.csv
 - features_training.csv
 - model_metrics.csv
 - pattern_summary.txt
"""

import os
import sys
import math
import json
import time
from collections import defaultdict, Counter
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from tqdm import tqdm

# ML libs
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, precision_recall_curve, average_precision_score
from sklearn.preprocessing import StandardScaler
import joblib

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except Exception:
    XGBOOST_AVAILABLE = False

# Optional: pymongo for live DB access
try:
    from pymongo import MongoClient
    MONGO_AVAILABLE = True
except Exception:
    MONGO_AVAILABLE = False

# ----------------------------
# CONFIG - EDIT AS NEEDED
# ----------------------------
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "numbergrid"
COLLECTION = "lotterydatas"

# Fallback CSV if you don't want to use DB. Replace path if necessary.
UPLOADED_CSV = "all_prizes_number_patterns8.csv"

# Date window (Indian dd/mm/YYYY style) for analysis
WINDOW_START = "11/07/2020"
WINDOW_END = "14/11/2025"

# Prizes to consider (will detect present prizes in DB too)
DEFAULT_PRIZE_ORDER = [100, 200, 500, 1000, 2000, 5000]

# Monte Carlo settings
MC_ROUNDS = 1200            # number of Monte Carlo simulation runs (increase for better accuracy)
SIM_SEED = 42
np.random.seed(SIM_SEED)

# ML training settings
TEST_SIZE = 0.2
RANDOM_STATE = 42

# Output files
OUT_PREFIX = "hybrid_out"
PRED_CSV = f"{OUT_PREFIX}_predicted_5000_candidates.csv"
SIM_PROB_CSV = f"{OUT_PREFIX}_simulation_probs.csv"
FEATURES_CSV = f"{OUT_PREFIX}_features_training.csv"
MODEL_METRICS = f"{OUT_PREFIX}_model_metrics.csv"
PATTERN_SUMMARY = f"{OUT_PREFIX}_pattern_summary.txt"
MODEL_FILE = f"{OUT_PREFIX}_model.joblib"

# ----------------------------
# Roller sequences (72 rollers) you provided
# Format: list of tuples (number_id (1..18), roll_pos (1..4), seq_list_of_digits)
# ----------------------------
# Paste the 72-line dataset here as structured data:
ROLLER_SEQ_RAW = [
    # number_id, roll_pos, sequence (pipe-separated digits)
    (1,1,"7|6|8|5|9|0|3|1|2|4"),
    (1,2,"7|9|2|5|1|6|3|8|0|4"),
    (1,3,"7|8|9|0|1|2|3|4|5|6"),
    (1,4,"7|4|1|8|6|3|5|0|2|9"),
    (2,1,"7|2|4|6|9|0|1|3|5|8"),
    (2,2,"7|3|8|2|0|1|9|5|6|4"),
    (2,3,"7|4|1|8|6|3|5|0|2|9"),
    (2,4,"7|8|9|0|1|2|3|4|5|6"),
    (3,1,"7|5|3|1|0|8|6|4|2|9"),
    (3,2,"7|2|4|6|9|0|1|3|5|8"),
    (3,3,"7|3|8|2|0|1|9|5|6|4"),
    (3,4,"7|4|1|8|6|3|5|0|2|9"),
    (4,1,"7|2|4|6|9|0|1|3|5|8"),
    (4,2,"7|3|8|2|0|1|9|5|6|4"),
    (4,3,"7|4|1|8|6|3|5|0|2|9"),
    (4,4,"7|9|2|5|1|6|3|8|0|4"),
    (5,1,"7|2|4|6|9|0|1|3|5|8"),
    (5,2,"7|3|8|2|0|1|9|5|6|4"),
    (5,3,"7|6|8|5|9|0|3|1|2|4"),
    (5,4,"7|8|9|0|1|2|3|4|5|6"),
    (6,1,"7|2|4|6|9|0|1|3|5|8"),
    (6,2,"7|3|8|2|0|1|9|5|6|4"),
    (6,3,"7|9|2|5|1|6|3|8|0|4"),
    (6,4,"7|4|1|8|6|3|5|0|2|9"),
    (7,1,"7|3|8|2|0|1|9|6|5|4"),
    (7,2,"7|8|9|0|1|2|3|4|5|6"),
    (7,3,"7|5|3|1|0|8|6|4|2|9"),
    (7,4,"7|5|3|1|0|8|6|4|2|9"),
    (8,1,"7|5|1|9|6|4|2|8|3|0"),
    (8,2,"7|5|9|1|3|6|8|4|0|2"),
    (8,3,"7|9|2|5|1|6|3|8|0|4"),
    (8,4,"7|6|8|5|9|0|3|1|2|4"),
    (9,1,"7|9|2|5|1|6|3|8|0|4"),
    (9,2,"7|5|1|9|6|4|2|8|3|0"),
    (9,3,"7|5|9|1|3|6|8|4|0|2"),
    (9,4,"7|8|9|0|1|2|3|4|5|6"),
    (10,1,"7|5|1|9|6|4|2|8|3|0"),
    (10,2,"7|6|5|4|3|2|1|0|9|8"),
    (10,3,"7|8|9|0|1|2|3|4|5|6"),
    (10,4,"7|6|8|5|9|0|3|1|2|4"),
    (11,1,"7|5|1|9|6|4|2|8|3|0"),
    (11,2,"7|5|9|1|3|6|8|4|0|2"),
    (11,3,"7|9|2|5|1|6|3|8|0|4"),
    (11,4,"7|4|1|8|6|3|5|0|2|9"),
    (12,1,"7|5|1|9|6|4|2|8|3|0"),
    (12,2,"7|5|9|1|3|6|8|4|0|2"),
    (12,3,"7|6|5|4|3|2|1|0|9|8"),
    (12,4,"7|8|9|0|1|2|3|4|5|6"),
    (13,1,"7|5|9|1|3|6|8|4|0|2"),
    (13,2,"7|6|5|4|3|2|1|0|9|8"),
    (13,3,"7|5|1|9|6|4|2|8|3|0"),
    (13,4,"7|5|3|1|0|8|6|4|2|9"),
    (14,1,"7|6|5|4|3|2|1|0|9|8"),
    (14,2,"7|5|3|1|0|8|6|4|2|9"),
    (14,3,"7|5|1|9|6|4|2|8|3|0"),
    (14,4,"7|4|1|8|6|3|5|0|2|9"),
    (15,1,"7|6|8|5|9|0|3|1|2|4"),
    (15,2,"7|6|5|4|3|2|1|0|9|8"),
    (15,3,"7|4|1|3|6|0|8|9|5|2"),
    (15,4,"7|5|9|1|3|6|8|4|0|2"),
    (16,1,"7|5|9|1|3|6|8|4|0|2"),
    (16,2,"7|5|3|1|0|8|6|4|2|9"),
    (16,3,"7|2|4|6|9|0|1|3|5|8"),
    (16,4,"7|3|8|2|0|1|9|5|6|4"),
    (17,1,"7|8|9|0|1|2|3|4|5|6"),
    (17,2,"7|6|8|5|9|0|3|1|2|4"),
    (17,3,"7|6|5|4|3|2|1|0|9|8"),
    (17,4,"7|5|3|1|0|8|6|4|2|9"),
    (18,1,"7|6|8|5|9|0|3|1|2|4"),
    (18,2,"7|5|3|1|0|8|6|4|2|9"),
    (18,3,"7|2|4|6|9|0|1|3|5|8"),
    (18,4,"7|3|8|2|0|1|9|5|6|4"),
]

# Build roller mapping and sequences
ROLLERS = {}   # key: (number_id, roll_pos) -> sequence list of digits
for nid, pos, seq in ROLLER_SEQ_RAW:
    seq_list = [int(x) for x in seq.split("|")]
    ROLLERS[(nid, pos)] = seq_list

# Helper: parse indian style date
def parse_indian_date(d):
    if pd.isna(d):
        return None
    if isinstance(d, datetime):
        return d
    s = str(d).strip()
    # Try common formats (dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy, yyyy-mm-dd)
    fmts = ["%d/%m/%Y","%d-%m-%Y","%d.%m.%Y","%Y-%m-%d","%d/%m/%y","%d-%b-%Y"]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except Exception:
            pass
    # Last attempt: try pandas
    try:
        return pd.to_datetime(s, dayfirst=True)
    except Exception:
        return None

# ----------------------------
# Data loading utilities
# ----------------------------
def load_from_mongo(uri=MONGO_URI, db_name=DB_NAME, collection=COLLECTION):
    if not MONGO_AVAILABLE:
        raise RuntimeError("pymongo not available in environment. Install pymongo or use CSV fallback.")
    print("Connecting to MongoDB...")
    client = MongoClient(uri)
    db = client[db_name]
    coll = db[collection]
    print("Reading documents from collection...")
    docs = list(coll.find({}))
    print(f"Retrieved {len(docs)} documents.")
    # Expect documents contain fields: date, series (list of prize blocks with prize value and numbers)
    rows = []
    for doc in docs:
        date_raw = doc.get("date") or doc.get("drawDate") or doc.get("draw_date")
        dt = parse_indian_date(date_raw)
        if dt is None:
            continue
        series = doc.get("series") or doc.get("prizes") or []
        for s in series:
            prize = s.get("prize") if isinstance(s, dict) else None
            numbers = s.get("numbers") if isinstance(s, dict) else None
            # some layouts: series elements might be dicts with 'prize' and 'numbers' list of dicts
            if prize is None and isinstance(s, dict):
                prize = s.get("prize")
            if numbers is None:
                # maybe it's s['numbers'] or s['list']
                numbers = s.get("numbers") if isinstance(s, dict) else None
            if isinstance(numbers, list):
                for entry in numbers:
                    if isinstance(entry, dict):
                        num = entry.get("number") or entry.get("num") or entry.get("value")
                    else:
                        num = entry
                    if num is None:
                        continue
                    rows.append({"date": dt, "prize": int(prize), "number": str(num).zfill(4)})
            else:
                # numbers might be comma-separated string
                if isinstance(s, dict):
                    v = s.get("numbers") or s.get("list") or ""
                else:
                    v = s
                if not v:
                    continue
                if isinstance(v, str):
                    parts = [p.strip() for p in v.replace(",", " ").split()]
                    for p in parts:
                        if p:
                            rows.append({"date": dt, "prize": int(prize), "number": str(p).zfill(4)})
    df = pd.DataFrame(rows)
    return df

def load_from_csv(path=UPLOADED_CSV):
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV fallback not found at {path}. Please provide DB access or correct file path.")
    print(f"Loading CSV fallback: {path}")
    df_raw = pd.read_csv(path, dtype=str, low_memory=False)
    # Try to detect columns; expected at least: number, dates or timeline or appearances
    # If the CSV is per-number lines with 'dates' pipe-separated, we'll explode them
    if set(['number','dates']).issubset(set(df_raw.columns)):
        rows=[]
        for _, r in df_raw.iterrows():
            num = str(r['number']).zfill(4)
            dates_str = r['dates']
            # dates possibly pipe-separated and may not include prize info; try to infer from other columns
            parts = str(dates_str).split("|")
            for p in parts:
                d = parse_indian_date(p.strip())
                if d:
                    # prize unknown — skip; the CSV might have prize-specific structure elsewhere
                    rows.append({"date": d, "prize": np.nan, "number": num})
        return pd.DataFrame(rows)
    # If CSV has explicit timeline field: appearances_timeline
    if 'appearances_timeline' in df_raw.columns:
        # timeline like "11/07/2020 (₹5000) → 30/09/2020 (₹100) → ..."
        rows = []
        for _, r in df_raw.iterrows():
            num = str(r['number']).zfill(4)
            timeline = r.get('appearances_timeline','') or ''
            parts = [p.strip() for p in str(timeline).split("→")]
            for p in parts:
                if "(" in p and ")" in p:
                    date_part = p.split("(")[0].strip()
                    prize_part = p.split("(")[1].split(")")[0].strip().replace("₹","")
                    dt = parse_indian_date(date_part)
                    try:
                        prize = int(prize_part)
                    except Exception:
                        prize = np.nan
                    if dt:
                        rows.append({"date": dt, "prize": prize, "number": num})
        return pd.DataFrame(rows)
    # Last resort: try common columns
    candidates = [c.lower() for c in df_raw.columns]
    mapping = {}
    for c in df_raw.columns:
        lc = c.lower()
        if 'date' in lc:
            mapping['date'] = c
        if 'prize' in lc:
            mapping['prize'] = c
        if 'number' in lc or 'num' == lc:
            mapping['number'] = c
        if 'timeline' in lc or 'appearances' in lc:
            mapping['timeline'] = c
    if 'timeline' in mapping:
        # parse that timeline similarly
        rows=[]
        for _, r in df_raw.iterrows():
            num = str(r[mapping.get('number')]).zfill(4) if 'number' in mapping else None
            pieces = str(r[mapping['timeline']]).split("→")
            for p in pieces:
                if "(" in p and ")" in p:
                    date_part = p.split("(")[0].strip()
                    prize_part = p.split("(")[1].split(")")[0].strip().replace("₹","")
                    dt = parse_indian_date(date_part)
                    try:
                        prize = int(prize_part)
                    except:
                        prize = np.nan
                    if dt and num:
                        rows.append({"date": dt, "prize": prize, "number": num})
        return pd.DataFrame(rows)
    # If nothing else, return empty and let caller handle
    raise RuntimeError("CSV fallback format not recognized. Provide a CSV that includes 'appearances_timeline' or 'number' & 'dates' columns.")

# ----------------------------
# Data preprocessing
# ----------------------------
def prepare_events(df):
    # df must have columns: date, prize, number
    # normalize number to 4-digit string and parse dates
    df = df.copy()
    df['number'] = df['number'].astype(str).str.zfill(4)
    df['parsed_date'] = df['date'].apply(parse_indian_date)
    df = df[df['parsed_date'].notnull()]
    df['parsed_date'] = pd.to_datetime(df['parsed_date']).dt.normalize()
    # Filter date window
    start = parse_indian_date(WINDOW_START)
    end = parse_indian_date(WINDOW_END)
    mask = (df['parsed_date'] >= start) & (df['parsed_date'] <= end)
    df = df[mask].copy()
    df.sort_values('parsed_date', inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df

def detect_prize_list(df):
    prizes = sorted(df['prize'].dropna().unique().astype(int).tolist())
    if not prizes:
        return DEFAULT_PRIZE_ORDER
    return prizes

# Build per-number timelines: dict[number] = list of (date, prize)
def build_timelines(events_df):
    timelines = defaultdict(list)
    for _, r in events_df.iterrows():
        timelines[r['number']].append((r['parsed_date'].to_pydatetime(), int(r['prize']) if not pd.isna(r['prize']) else np.nan))
    # ensure sorted
    for k in timelines:
        timelines[k] = sorted(timelines[k], key=lambda x: x[0])
    return timelines

# Compute transitions (consecutive appearances for same number)
def compute_transitions(timelines):
    transitions = []
    for num, timeline in timelines.items():
        for i in range(len(timeline)-1):
            d1, p1 = timeline[i]
            d2, p2 = timeline[i+1]
            gap = (d2 - d1).days
            transitions.append({
                "number": num,
                "from_date": d1,
                "to_date": d2,
                "from_prize": p1,
                "to_prize": p2,
                "gap_days": gap
            })
    return pd.DataFrame(transitions)

# ----------------------------
# Simple calibration: estimate distribution of offsets per roll_pos/sequence type
# We'll fit per-position cyclic-step distribution from observed transitions:
# e.g., if digit at position advances X steps most often between appearances, use that
# ----------------------------
def calibrate_offsets(timelines):
    # Very simple approach:
    # For numbers that appear multiple times, inspect digit changes between consecutive same-position appearances
    # We don't know roller assignment per number; so we estimate a global distribution of rotation steps per day.
    # We'll estimate mean daily rotation steps (mod 10) using differences across dates for numbers when prize-change results indicate certain patterns.
    # This is a heuristic; a more advanced EM could be built.
    day_deltas = []
    for num, tl in timelines.items():
        for i in range(len(tl)-1):
            d1, p1 = tl[i]
            d2, p2 = tl[i+1]
            delta_days = max(1, (d2 - d1).days)
            day_deltas.append(delta_days)
    if not day_deltas:
        mean_days = 30.0
    else:
        mean_days = float(np.mean(day_deltas))
    # assume mean daily rotations (full rotations count) -> we map to expected digit-step rates
    # We'll model that each day produces lambda steps per roller; fit a small integer
    daily_step = max(1.0, min(50.0, 10.0 * (30.0 / mean_days)))  # heuristic
    calib = {
        "mean_days_between_events": mean_days,
        "daily_step_rate": daily_step,
        "note": "Heuristic calibration — replace with EM for better fit"
    }
    return calib

# ----------------------------
# Mechanical Monte Carlo Simulator
# ----------------------------
# Idea:
# - We don't know which 4-digit roller corresponds to which position in output mapping (because the PDF is sorted).
# - But we do know there are 18 roller-sets and each set has 4 rollers (positions 1..4).
# - We simulate the roller rotation offset for each roller in each MC run and then produce a resulting set of 4-digit numbers for a prize section (like 5000 prize group)
# - We'll simulate the reveal mechanism: reveal 18 numbers (round 1), then additional numbers if prize needs >18, handle duplicates by pulling next roller outputs from subsequent rounds.
#
# This implementation is a simplified simulator capturing major mechanics you described.
# ----------------------------

# Build a list of 18 roller-set indices in column-major mapping (1..18)
ROLLER_SET_IDS = list(range(1, 19))  # 1..18

# Build mapping of each roller (global id 0..71) to its sequence list
GLOBAL_ROLLERS = []
for nid in range(1, 19):
    for pos in range(1, 5):
        GLOBAL_ROLLERS.append(((nid, pos), ROLLERS[(nid, pos)]))
# GLOBAL_ROLLERS length 72
assert len(GLOBAL_ROLLERS) == 72

def simulate_one_round(roller_offsets):
    """
    Given roller_offsets: list of length 72 specifying offset index into sequence list
    Return: dict mapping roller_global_index -> current digit (0..9)
    """
    out = {}
    for idx, ((nid,pos), seq) in enumerate(GLOBAL_ROLLERS):
        offset = int(round(roller_offsets[idx])) % len(seq)
        out[idx] = seq[offset]
    return out

def build_initial_offsets_random(seed=None):
    rng = np.random.RandomState(seed)
    # offsets per roller between 0..len(seq)-1
    offsets = [rng.randint(0, len(seq)) for (_, seq) in GLOBAL_ROLLERS]
    return offsets

def advance_offsets(offsets, steps):
    # steps may be fractional; we add steps and wrap; using length 10 for sequences
    new = []
    for i, ((nid,pos), seq) in enumerate(GLOBAL_ROLLERS):
        length = len(seq)
        new_off = (offsets[i] + int(round(steps))) % length
        new.append(new_off)
    return new

def monte_carlo_simulate(prize_counts, rounds_needed_hint, calibration, mc_rounds=MC_ROUNDS):
    """
    Prize_counts: dict mapping prize_value -> count of numbers needed for that prize on a particular day
      e.g., {5000: 19, 2000: 6, 1000: 25, 500: 48, 200: 60, 100: ...}
    returns: aggregated probability for each 4-digit number across MC runs
    """
    rng = np.random.RandomState(SIM_SEED)
    # We'll treat each roller as rotating during the "press" event. The press produces an effective random advance per roller.
    # Use calibration to set average steps per press. Simulate per-run offsets and produce prize groups sequentially
    daily_step_rate = calibration.get("daily_step_rate", 6.0)
    # We'll produce a mapping: 4-digit number -> hit count across MC runs
    hit_counter = Counter()
    for run in tqdm(range(mc_rounds), desc="MonteCarlo"):
        # initialize offsets randomly
        offsets = build_initial_offsets_random(seed=rng.randint(0, 1000000))
        # extra randomness per-run: random small extra rotation
        noise = rng.normal(loc=daily_step_rate, scale=max(1.0, daily_step_rate*0.5))
        # For realism, we add tiny per-roller noise
        per_roller_noise = rng.normal(loc=0.0, scale=1.0, size=len(offsets))
        # We'll iterate prize sections in the observed prize order
        for prize, needed in prize_counts.items():
            # compute how many full rounds (18 reveals) and leftover
            full_rounds = needed // 18
            leftover = needed % 18
            # reveal round by round
            selected_numbers = []
            hidden_indices_cycle = list(range(18))  # we will reveal roller-sets 0..17 (representing 18 roller sets)
            # For each round (1..full_rounds + maybe one more if leftover>0)
            total_rounds = full_rounds + (1 if leftover>0 else 0)
            for rr in range(total_rounds):
                # Compute actual number of rollers revealed this round:
                if rr < full_rounds:
                    reveal_count = 18
                else:
                    reveal_count = leftover if leftover>0 else 18
                # For mechanical mapping: reveal first reveal_count roller-sets among 18
                # But when duplicates are replaced in subsequent rounds, only small subset of rollers are revealed (you described hidden shields)
                reveal_rollerset_indices = list(range(reveal_count))
                # Convert these into actual global roller indices for their four positions:
                revealed_global_idxs = []
                for rsi in reveal_rollerset_indices:
                    # each roller-set rsi corresponds to 3 columns? But simpler: roller-set maps to 4 global rollers at positions:
                    # global index = (rsi-1)*4 + (pos-1)
                    base = rsi * 4
                    for p in range(4):
                        idx = base + p
                        if idx < len(GLOBAL_ROLLERS):
                            revealed_global_idxs.append(idx)
                # For all revealed rollers we compute current digit by advancing offsets with noisy steps
                # advance offsets by noise + small per-roller noise
                step = max(1, int(round(noise + rng.normal(0,1))))
                offsets = advance_offsets(offsets, step)
                current_digits = simulate_one_round(offsets)
                # group digits by roller-sets: each roller-set produces a 4-digit number combining its 4 positions
                roller_set_numbers = []
                for rs in reveal_rollerset_indices:
                    base = rs * 4
                    if base+3 >= len(GLOBAL_ROLLERS):
                        continue
                    digits = [str(current_digits[base + pos]) for pos in range(4)]
                    num = "".join(digits)
                    roller_set_numbers.append((rs, num))
                # append to selected
                for (_, num) in roller_set_numbers:
                    selected_numbers.append(num)
                # check duplicates within prize already selected: duplicates should be removed and replaced in next rounds
                # but we will handle duplicate replacement after we collect all rounds for this prize
            # after rounds for this prize: we have candidate numbers (may include duplicates)
            # we need exactly "needed" unique numbers: keep the first occurrences order (as revealed) and replace duplicates by subsequent numbers
            unique_seen = []
            for n in selected_numbers:
                if n not in unique_seen:
                    unique_seen.append(n)
                if len(unique_seen) >= needed:
                    break
            # If still fewer than needed (possible), add random unseen numbers from all 0000-9999 excluding ones chosen
            if len(unique_seen) < needed:
                allnums = [str(i).zfill(4) for i in range(10000)]
                rng.shuffle(allnums)
                for cand in allnums:
                    if cand not in unique_seen:
                        unique_seen.append(cand)
                    if len(unique_seen) >= needed:
                        break
            # record these outcomes for this prize
            for num in unique_seen[:needed]:
                hit_counter[num] += 1
            # Important: continue to next prize — offsets keep rolling (machine doesn't reset)
        # end of one MC run
    # convert counts to probabilities
    total_runs = mc_rounds
    probabilities = {num: count/total_runs for num, count in hit_counter.items()}
    return probabilities

# ----------------------------
# Feature engineering & ML pipeline
# ----------------------------
def make_features(timelines, transitions, events_df, prize_of_interest=5000, lookback_days=180):
    """
    Build per-number features for ML:
     - recent hit counts in each prize
     - days since last seen
     - avg gap days per prize
     - simulation probability placeholder (will be merged)
     - last N timeline tokens encoded
    """
    now = parse_indian_date(WINDOW_END)
    features = {}
    for num, tl in timelines.items():
        # tl is sorted list of (date, prize)
        last_seen_date = tl[-1][0]
        days_since = (now - last_seen_date).days
        counts = Counter([p for (_, p) in tl])
        total_appearances = len(tl)
        avg_gap_per_prize = {}
        # compute gaps inside each prize group
        for pr in set(counts.keys()):
            dates = [d for (d,p) in tl if p==pr]
            if len(dates) > 1:
                gaps = [(dates[i+1]-dates[i]).days for i in range(len(dates)-1)]
                avg_gap_per_prize[f"avg_gap_{int(pr)}"] = np.mean(gaps)
            else:
                avg_gap_per_prize[f"avg_gap_{int(pr)}"] = np.nan
        # last k prizes as one-hot-like features (we'll keep last 6 prizes)
        last_prizes = [p for (d,p) in tl[-6:]]
        feat = {
            "number": num,
            "days_since_seen": days_since,
            "total_appearances": total_appearances,
            "last_seen_date": last_seen_date,
        }
        # counts per expected prize types
        for p in DEFAULT_PRIZE_ORDER:
            feat[f"count_{p}"] = counts.get(p, 0)
        # avg gaps
        for p in DEFAULT_PRIZE_ORDER:
            feat[f"avg_gap_{p}"] = avg_gap_per_prize.get(f"avg_gap_{p}", np.nan)
        # last prizes encoded
        for i in range(6):
            feat[f"last_prize_{i+1}"] = int(last_prizes[-(i+1)]) if i < len(last_prizes) else -1
        features[num] = feat
    # Also build target label: whether number appears in a 5000 prize after its last known event within a horizon
    # We'll create label by looking into events_df: for each number, whether it appears as prize_of_interest at any date after its first low prize appearance.
    label_map = {}
    for num, tl in timelines.items():
        appeared_5000 = any(p==prize_of_interest for (_, p) in tl)
        label_map[num] = int(appeared_5000)
    # Merge into DataFrame
    feats = pd.DataFrame.from_dict(features, orient='index')
    feats['label_5000'] = feats['number'].map(label_map).fillna(0).astype(int)
    return feats

# ----------------------------
# Train ML model (XGBoost preferred else RandomForest)
# ----------------------------
def train_model(X, y):
    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y)
    # Try XGBoost
    if XGBOOST_AVAILABLE:
        dtrain = xgb.DMatrix(X_train, label=y_train)
        dtest = xgb.DMatrix(X_test, label=y_test)
        params = {"objective":"binary:logistic","eval_metric":"auc","seed":RANDOM_STATE, "verbosity":0}
        bst = xgb.train(params, dtrain, num_boost_round=200, evals=[(dtest, "test")], early_stopping_rounds=20, verbose_eval=False)
        # predict probabilities
        ypred = bst.predict(dtest)
        auc = roc_auc_score(y_test, ypred)
        model = ("xgboost", bst)
        print("Trained XGBoost AUC:", auc)
        return model, (X_test, y_test, ypred, auc)
    else:
        clf = RandomForestClassifier(n_estimators=400, n_jobs=-1, random_state=RANDOM_STATE)
        clf.fit(X_train, y_train)
        ypred = clf.predict_proba(X_test)[:,1]
        auc = roc_auc_score(y_test, ypred) if len(np.unique(y_test))>1 else np.nan
        print("Trained RandomForest AUC:", auc)
        return ("rf", clf), (X_test, y_test, ypred, auc)

# ----------------------------
# Main process
# ----------------------------
def main():
    # 1) Load data (prefer DB)
    try:
        if MONGO_AVAILABLE:
            events = load_from_mongo()
            if events is None or events.empty:
                raise RuntimeError("No events from Mongo or empty; fallback to CSV.")
        else:
            raise RuntimeError("Mongo not available -- using CSV fallback.")
    except Exception as ex:
        print("DB load failed or unavailable:", ex)
        print("Falling back to CSV...")
        events = load_from_csv(UPLOADED_CSV)
    print("Normalizing and preparing events...")
    events_df = prepare_events(events)
    print(f"Events after window filter: {len(events_df)}")

    # 2) detect prize list and order
    prize_list = detect_prize_list(events_df)
    print("Observed prizes:", prize_list)
    # Ensure prize order uses requested default ordering intersection
    prize_list_sorted = [p for p in DEFAULT_PRIZE_ORDER if p in prize_list]
    if not prize_list_sorted:
        prize_list_sorted = prize_list
    print("Using prize order:", prize_list_sorted)

    # 3) build timelines and transitions
    timelines = build_timelines(events_df)
    print(f"Built timelines for {len(timelines)} numbers.")
    transitions = compute_transitions(timelines)
    print("Computed transitions rows:", len(transitions))

    # 4) calibration
    calib = calibrate_offsets(timelines)
    print("Calibration:", calib)

    # 5) Build daily prize counts pattern from the most recent draw in events_df (we will simulate using typical prize_counts)
    # Heuristic: take the last date in DB and count number of items per prize on that date
    last_date = events_df['parsed_date'].max()
    last_day_df = events_df[events_df['parsed_date'] == last_date]
    prize_counts = {}
    for p in prize_list_sorted:
        prize_counts[p] = int(last_day_df[last_day_df['prize'] == p].shape[0])
    print("Prize counts on last date (will use as simulation template):", prize_counts)

    # 6) Monte Carlo simulation
    sim_probs = monte_carlo_simulate(prize_counts, None, calib, mc_rounds=MC_ROUNDS)
    # convert to DataFrame and save
    sim_df = pd.DataFrame(list(sim_probs.items()), columns=['number','sim_prob'])
    sim_df.sort_values('sim_prob', ascending=False, inplace=True)
    sim_df.to_csv(SIM_PROB_CSV, index=False)
    print("Saved Monte Carlo probabilities ->", SIM_PROB_CSV)

    # 7) Make features (merge sim_prob)
    feats = make_features(timelines, transitions, events_df, prize_of_interest=5000)
    # merge sim probs
    feats = feats.merge(sim_df, on='number', how='left')
    feats['sim_prob'] = feats['sim_prob'].fillna(0.0)
    feats.to_csv(FEATURES_CSV, index=False)
    print("Saved features ->", FEATURES_CSV)

    # 8) Prepare training data (features -> numeric)
    # choose feature columns
    ignore_cols = ['number','last_seen_date','label_5000']
    feature_cols = [c for c in feats.columns if c not in ignore_cols]
    # fill nan
    X = feats[feature_cols].copy().fillna(-1)
    y = feats['label_5000'].copy().astype(int)

    # if target is imbalanced, we will still train; ensure at least some positives
    if y.sum() == 0:
        print("No positive labels for 5000 in historical data. Using sim_prob as proxy label (unsupervised fallback).")
        X_train = X
        model_desc = "sim_prob_only"
        # generate predictions from sim_prob ranking
        ranked = feats.sort_values('sim_prob', ascending=False)[['number','sim_prob']]
        ranked.to_csv(PRED_CSV, index=False)
        print("Saved predicted ranking (sim_prob) ->", PRED_CSV)
        # write summary
        with open(PATTERN_SUMMARY, "w") as f:
            f.write("No 5000 positives in training label. Saved sim_prob ranking as fallback.\n")
        return

    # Standard scaling (trees don't need it but for robustness)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    # Save feature matrix for inspection
    pd.DataFrame(X_scaled, columns=feature_cols).to_csv(FEATURES_CSV.replace(".csv","_scaled.csv"), index=False)

    # Train model
    model, eval_info = train_model(X_scaled, y)
    X_test, y_test, ypred, auc = eval_info
    # Save model (and scaler)
    if isinstance(model, tuple):
        # xgboost or ('rf', clf)
        if model[0] == "rf":
            joblib.dump({"model_type":"rf","model":model[1],"scaler":scaler,"feature_cols":feature_cols}, MODEL_FILE)
        else:
            # xgboost booster
            joblib.dump({"model_type":"xgboost","model":model[1].save_raw(), "scaler":scaler, "feature_cols":feature_cols}, MODEL_FILE)
    else:
        joblib.dump({"model_type":"rf","model":model, "scaler":scaler, "feature_cols":feature_cols}, MODEL_FILE)
    print("Saved trained model ->", MODEL_FILE)

    # 9) Scoring entire dataset via model or sim fallback
    if XGBOOST_AVAILABLE and isinstance(model, tuple) and model[0]=="xgboost":
        # load xgboost booster from model tuple
        booster = model[1]
        dmat = xgb.DMatrix(X_scaled)
        probs = booster.predict(dmat)
    else:
        clf = model[1] if isinstance(model, tuple) else model
        probs = clf.predict_proba(X_scaled)[:,1]

    feats['model_prob'] = probs
    # Combine with sim_prob for final hybrid score: weighted average
    feats['hybrid_score'] = 0.55 * feats['model_prob'] + 0.45 * feats['sim_prob']
    # Rank and output top candidates
    ranked = feats.sort_values(['hybrid_score','sim_prob','model_prob'], ascending=False)
    ranked[['number','hybrid_score','model_prob','sim_prob'] + [c for c in feature_cols][:10]].head(50).to_csv(PRED_CSV, index=False)
    print("Saved predicted_5000_candidates ->", PRED_CSV)

    # 10) Save model metrics
    metrics = {
        "auc": float(auc) if not np.isnan(auc) else None,
        "n_positives": int(y.sum()),
        "n_negatives": int(len(y)-y.sum()),
        "mc_rounds": MC_ROUNDS
    }
    pd.DataFrame([metrics]).to_csv(MODEL_METRICS, index=False)
    print("Saved model metrics ->", MODEL_METRICS)

        # 11) Pattern interpretation summary (text)
    with open(PATTERN_SUMMARY, "w", encoding="utf-8") as f:
        f.write("HYBRID PREDICTOR PATTERN SUMMARY\n")
        f.write("===============================\n")
        f.write(f"Date window: {WINDOW_START} -> {WINDOW_END}\n")
        f.write(f"Total unique numbers: {len(timelines)}\n")
        positives = int(y.sum())
        f.write(f"Numbers that ever appeared in ₹5000 in history: {positives}\n")
        f.write("\nCalibration:\n")
        f.write(json.dumps(calib, indent=2))
        f.write("\n\nTop 30 hybrid-ranked candidates:\n")
        for i, row in ranked.head(30).iterrows():
            f.write(f"{row['number']}, hybrid_score={row['hybrid_score']:.4f}, "
                    f"sim_prob={row['sim_prob']:.4f}, model_prob={row['model_prob']:.4f}\n")
    print("Saved pattern summary ->", PATTERN_SUMMARY)


if __name__ == "__main__":
    start = time.time()
    main()
    print("Done. Time elapsed: %.1f sec" % (time.time()-start))

import re, math
import numpy as np
import pandas as pd
from collections import Counter, defaultdict

# =======================
# 1) Paste your blocks
# =======================
DATA_RAW = r"""
rollerset1,rollerset2,rollerset3,rollerset4,rollerset5,rollerset6,rollerset7,rollerset8,rollerset9,rollerset10,rollerset11,rollerset12,rollerset13,rollerset14,rollerset15,rollerset16,rollerset17,rollerset18
9427,9509,9636,0490,0054,5278,6484,4338,0934,2047,2064,8419,6707,0650,8760,1770,1830,4695
9692,1758,7806,7330,5325,9562,4487,9837,7944,4095,0426,4737,4374,7121,9949,1609,0793,2842
8901,5622,5927,9887,7028,6733,8299,1175,7000,2540,9345,0727,6157,3601,9331,8600,0267,4805
8189,2327,5440,5506,2460,0820,2701,4074,1897,0157,3543,6356,6307,8534,1481,2718,9703,8667
"""

SEQS_RAW = r"""
1,1,7|6|8|5|9|0|3|1|2|4
1,2,7|9|2|5|1|6|3|8|0|4
1,3,7|8|9|0|1|2|3|4|5|6
1,4,7|4|1|8|6|3|5|0|2|9
2,1,7|2|4|6|9|0|1|3|5|8
2,2,7|3|8|2|0|1|9|5|6|4
2,3,7|4|1|8|6|3|5|0|2|9
2,4,7|8|9|0|1|2|3|4|5|6
3,1,7|5|3|1|0|8|6|4|2|9
3,2,7|2|4|6|9|0|1|3|5|8
3,3,7|3|8|2|0|1|9|5|6|4
3,4,7|4|1|8|6|3|5|0|2|9
4,1,7|2|4|6|9|0|1|3|5|8
4,2,7|3|8|2|0|1|9|5|6|4
4,3,7|4|1|8|6|3|5|0|2|9
4,4,7|9|2|5|1|6|3|8|0|4
5,1,7|2|4|6|9|0|1|3|5|8
5,2,7|3|8|2|0|1|9|5|6|4
5,3,7|6|8|5|9|0|3|1|2|4
5,4,7|8|9|0|1|2|3|4|5|6
6,1,7|2|4|6|9|0|1|3|5|8
6,2,7|3|8|2|0|1|9|5|6|4
6,3,7|9|2|5|1|6|3|8|0|4
6,4,7|4|1|8|6|3|5|0|2|9
7,1,7|3|8|2|0|1|9|6|5|4
7,2,7|8|9|0|1|2|3|4|5|6
7,3,7|5|3|1|0|8|6|4|2|9
7,4,7|5|3|1|0|8|6|4|2|9
8,1,7|5|1|9|6|4|2|8|3|0
8,2,7|5|9|1|3|6|8|4|0|2
8,3,7|9|2|5|1|6|3|8|0|4
8,4,7|6|8|5|9|0|3|1|2|4
9,1,7|9|2|5|1|6|3|8|0|4
9,2,7|5|1|9|6|4|2|8|3|0
9,3,7|5|9|1|3|6|8|4|0|2
9,4,7|8|9|0|1|2|3|4|5|6
10,1,7|5|1|9|6|4|2|8|3|0
10,2,7|6|5|4|3|2|1|0|9|8
10,3,7|8|9|0|1|2|3|4|5|6
10,4,7|6|8|5|9|0|3|1|2|4
11,1,7|5|1|9|6|4|2|8|3|0
11,2,7|5|9|1|3|6|8|4|0|2
11,3,7|9|2|5|1|6|3|8|0|4
11,4,7|4|1|8|6|3|5|0|2|9
12,1,7|5|1|9|6|4|2|8|3|0
12,2,7|5|9|1|3|6|8|4|0|2
12,3,7|6|5|4|3|2|1|0|9|8
12,4,7|8|9|0|1|2|3|4|5|6
13,1,7|5|9|1|3|6|8|4|0|2
13,2,7|6|5|4|3|2|1|0|9|8
13,3,7|5|1|9|6|4|2|8|3|0
13,4,7|5|3|1|0|8|6|4|2|9
14,1,7|6|5|4|3|2|1|0|9|8
14,2,7|5|3|1|0|8|6|4|2|9
14,3,7|5|1|9|6|4|2|8|3|0
14,4,7|4|1|8|6|3|5|0|2|9
15,1,7|6|8|5|9|0|3|1|2|4
15,2,7|6|5|4|3|2|1|0|9|8
15,3,7|4|1|3|6|0|8|9|5|2
15,4,7|5|9|1|3|6|8|4|0|2
16,1,7|5|9|1|3|6|8|4|0|2
16,2,7|5|3|1|0|8|6|4|2|9
16,3,7|2|4|6|9|0|1|3|5|8
16,4,7|3|8|2|0|1|9|5|6|4
17,1,7|8|9|0|1|2|3|4|5|6
17,2,7|6|8|5|9|0|3|1|2|4
17,3,7|6|5|4|3|2|1|0|9|8
17,4,7|5|3|1|0|8|6|4|2|9
18,1,7|6|8|5|9|0|3|1|2|4
18,2,7|5|3|1|0|8|6|4|2|9
18,3,7|2|4|6|9|0|1|3|5|8
18,4,7|3|8|2|0|1|9|5|6|4
"""

# =======================
# 2) Helpers
# =======================
def parse_rows(text: str):
    rows = []
    for ln in text.strip().splitlines():
        ln = ln.strip()
        if not ln or ln.lower().startswith('rollerset'):
            continue
        parts = [p.strip() for p in ln.split(',')]
        if len(parts) != 18: 
            continue
        cleaned = []
        for p in parts:
            if re.fullmatch(r'\d{4}', p):
                cleaned.append(p)
            else:
                cleaned.append('nan')
        rows.append(cleaned)
    return rows  # list[list[str]]

def parse_sequences(text: str):
    idx = {}
    seqs = {}
    for ln in text.strip().splitlines():
        ln = ln.strip()
        if not ln: continue
        a, b, c = [t.strip() for t in ln.split(',')]
        rs, pos = int(a), int(b)
        seq = [int(x) for x in c.split('|')]
        seqs[(rs,pos)] = seq
        idx[(rs,pos)] = {d:i for i,d in enumerate(seq)}
    return seqs, idx

def delta_I(d_from: int, d_to: int, idx_map, rs_id: int, pos: int):
    imap = idx_map[(rs_id,pos)]
    if d_from not in imap or d_to not in imap: return np.nan
    return (imap[d_to] - imap[d_from]) % 10

def dI_int_or_none(a, b, rs, pos, idx_map):
    d = delta_I(a, b, idx_map, rs, pos)
    try:
        return int(d)
    except (TypeError, ValueError):
        return None

def next_digit(d_from: int, dI: int, seq_map, idx_map, rs_id: int, pos: int):
    seq = seq_map[(rs_id,pos)]
    imap = idx_map[(rs_id,pos)]
    if d_from not in imap: return None
    i = (imap[d_from] + dI) % 10
    return seq[i]

def build_transitions(rows, idx_map):
    n = len(rows)
    full_idxs = [i for i,r in enumerate(rows) if all(v!='nan' for v in r)]
    if len(full_idxs) < 2:
        raise ValueError("Need at least two complete rows at the end.")
    r_last2, r_last1 = full_idxs[-2], full_idxs[-1]

    dI_pairs = defaultdict(list)
    for i in range(n-2):
        r0, r1, r2 = rows[i], rows[i+1], rows[i+2]
        for rs in range(1,19):
            s1, s2, s3 = r0[rs-1], r1[rs-1], r2[rs-1]
            if s1=='nan' or s2=='nan' or s3=='nan': 
                continue
            for pos in range(1,5):
                a = int(s1[pos-1]); b = int(s2[pos-1]); c = int(s3[pos-1])
                dI_prev = dI_int_or_none(a,b,rs,pos,idx_map)
                dI_next = dI_int_or_none(b,c,rs,pos,idx_map)
                if dI_prev is None or dI_next is None:
                    continue
                dI_pairs[(rs,pos)].append((dI_prev, dI_next))

    prev_dI_at_end = {}
    rA, rB = rows[r_last2], rows[r_last1]
    for rs in range(1,19):
        if rA[rs-1]=='nan' or rB[rs-1]=='nan': 
            continue
        for pos in range(1,5):
            a = int(rA[pos-1]); b = int(rB[pos-1])
            val = dI_int_or_none(a,b,rs,pos,idx_map)
            if val is not None:
                prev_dI_at_end[(rs,pos)] = val

    return dI_pairs, prev_dI_at_end, (r_last2, r_last1)

def predict_next_row(rows, seq_map, idx_map, dI_pairs, prev_dI_at_end, min_mkv=2):
    mkv = defaultdict(lambda: defaultdict(int))
    next_counts = defaultdict(Counter)

    for key, pairs in dI_pairs.items():
        for pv, nx in pairs:
            mkv[key][(pv,nx)] += 1
            next_counts[key][nx] += 1

    full_idxs = [i for i,r in enumerate(rows) if all(v!='nan' for v in r)]
    r_last_idx = full_idxs[-1]
    S_last = rows[r_last_idx]

    pred_dI = {}
    pred_digits = [[] for _ in range(18)]

    for rs in range(1,19):
        base = S_last[rs-1]
        if base=='nan':
            for _ in range(4): pred_digits[rs-1].append(None)
            continue
        for pos in range(1,5):
            prev_dI = prev_dI_at_end.get((rs,pos), None)
            cand = None
            if prev_dI is not None:
                candidates = {nx: cnt for (pv,nx),cnt in mkv[(rs,pos)].items() if pv==prev_dI}
                if candidates:
                    nx, cnt = max(candidates.items(), key=lambda kv: (kv[1], -kv[0]))
                    if cnt >= min_mkv:
                        cand = nx
            if cand is None:
                cnts = next_counts[(rs,pos)]
                if cnts:
                    cand = min(cnts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            if cand is None and prev_dI is not None:
                cand = prev_dI
            if cand is None:
                cand = 0

            pred_dI[(rs,pos)] = int(cand)

            a = int(base[pos-1])
            b = next_digit(a, cand, seq_map, idx_map, rs, pos)
            pred_digits[rs-1].append(b)

    pred_numbers = ["".join(str(d) if d is not None else "" for d in digits) for digits in pred_digits]
    return pred_dI, pred_numbers, r_last_idx

def evaluate_latest_pair(rows, idx_map, dI_pairs, prev_dI_at_end):
    full_idxs = [i for i,r in enumerate(rows) if all(v!='nan' for v in r)]
    if len(full_idxs) < 2:
        return None
    rA, rB = full_idxs[-2], full_idxs[-1]
    A, B = rows[rA], rows[rB]

    mkv = defaultdict(lambda: defaultdict(int))
    next_counts = defaultdict(Counter)

    for i in range(max(0, rA-1)):
        r0, r1, r2 = rows[i], rows[i+1], rows[i+2]
        for rs in range(1,19):
            s1,s2,s3 = r0[rs-1], r1[rs-1], r2[rs-1]
            if s1=='nan' or s2=='nan' or s3=='nan': continue
            for pos in range(1,5):
                a,b,c = int(s1[pos-1]), int(s2[pos-1]), int(s3[pos-1])
                dI_prev = dI_int_or_none(a,b,rs,pos,idx_map)
                dI_next = dI_int_or_none(b,c,rs,pos,idx_map)
                if dI_prev is None or dI_next is None:
                    continue
                mkv[(rs,pos)][(dI_prev,dI_next)] += 1
                next_counts[(rs,pos)][dI_next] += 1

    triples = []
    for i in range(len(rows)-2):
        if i+2 > rA: break
        r0, r1, r2 = rows[i], rows[i+1], rows[i+2]
        for rs in range(1,19):
            s1,s2,s3 = r0[rs-1], r1[rs-1], r2[rs-1]
            if s1=='nan' or s2=='nan' or s3=='nan': continue
            for pos in range(1,5):
                a,b,c = int(s1[pos-1]), int(s2[pos-1]), int(s3[pos-1])
                d_prev = dI_int_or_none(a,b,rs,pos,idx_map)
                d_true = dI_int_or_none(b,c,rs,pos,idx_map)
                if d_prev is None or d_true is None:
                    continue
                candidates = {nx: cnt for (pv,nx),cnt in mkv[(rs,pos)].items() if pv==d_prev}
                if candidates:
                    d_pred = max(candidates.items(), key=lambda kv:(kv[1], -kv[0]))[0]
                else:
                    cnts = next_counts[(rs,pos)]
                    d_pred = min(cnts.items(), key=lambda kv:(-kv[1], kv[0]))[0] if cnts else d_prev
                triples.append((d_true, d_pred))

    if not triples:
        return None

    def circ_delta(a,b):
        d = abs((a-b) % 10)
        return min(d, 10-d)

    exact = sum(1 for t,p in triples if t==p) / len(triples)
    within1 = sum(1 for t,p in triples if circ_delta(t,p) <= 1) / len(triples)
    mae = sum(circ_delta(t,p) for t,p in triples) / len(triples)

    return {"n": len(triples), "acc_exact": round(exact,4), "acc_within1": round(within1,4), "circ_mae": round(mae,3)}

# =======================
# 3) Run
# =======================
def main():
    rows = parse_rows(DATA_RAW)
    seq_map, idx_map = parse_sequences(SEQS_RAW)

    dI_pairs, prev_dI_at_end, (r_last2, r_last1) = build_transitions(rows, idx_map)

    pred_dI, pred_numbers, r_last_idx = predict_next_row(rows, seq_map, idx_map, dI_pairs, prev_dI_at_end, min_mkv=2)

    out_df = pd.DataFrame([{
        "FromStep": r_last_idx+1, "ToStep": r_last_idx+2,
        **{f"rollerset{i}": pred_numbers[i-1] for i in range(1,19)}
    }])
    out_df.to_csv("predicted_next_row.csv", index=False)
    print("Wrote predicted_next_row.csv")
    print("Predicted next 18 numbers:")
    print(", ".join(pred_numbers))

    metrics = evaluate_latest_pair(rows, idx_map, dI_pairs, prev_dI_at_end)
    if metrics:
        pd.DataFrame([metrics]).to_csv("metrics_latest.csv", index=False)
        print("Wrote metrics_latest.csv:", metrics)
    else:
        print("Not enough triples for a backtest; prediction still produced from Markov/persistence.")

if __name__ == "__main__":
    main()
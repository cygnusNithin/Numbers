import re
import numpy as np
import pandas as pd

# =======================
# 1) Paste your blocks
# =======================
DATA_RAW = r"""
rollerset1,rollerset2,rollerset3,rollerset4,rollerset5,rollerset6,rollerset7,rollerset8,rollerset9,rollerset10,rollerset11,rollerset12,rollerset13,rollerset14,rollerset15,rollerset16,rollerset17,rollerset18
9316,0223,4125,3683,9328,7832,2659,4571,1186,3441,2145,4529,8984,0587,2090,5912,6433,6214
1783,0536,1310,6057,2491,9330,1316,6571,0897,3781,6320,3808,4775,5488,1126,7629,1696,0286
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
0943,0614,6248,8127,1166,6869,7515,3874,5995,2075,3012,5367,6848,2875,0874,1906,6620,6936
2161,4357,8469,4635,1994,1779,8029,2603,2972,5282,2711,5920,5970,8292,5348,7916,0234,1314
7369,9955,2668,7678,2834,8025,8270,3535,9345,6838,0412,5598,4017,2793,7483,2586,5886,4613
3207,1287,8360,7067,4485,1390,9729,1510,3358,3217,6492,8372,4098,2251,0641,3697,0191,6497
8287,5392,6246,2177,4741,5702,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
4402,1550,4248,1315,0592,2036,5317,8580,6377,8014,6768,0480,8372,2185,6191,8310,5733,4194
3181,9639,2585,7754,1093,5693,6841,4252,4427,3776,9284,0301,2020,4811,4830,7207,9613,7212
9459,7446,3074,4552,3833,7306,2432,7990,4895,4981,9961,1750,6457,7498,6715,1257,6149,5748
2700,2313,2666,0215,5819,7346,2524,9357,4153,8545,9582,0782,9356,4250,6095,7236,0828,0242
3920,8665,1042,2681,5780,7508,3323,0857,3169,8004,7654,2198,5268,4816,5352,9123,3239,3015
4685,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
1684,2920,6426,9851,2829,7673,7535,8109,1529,0036,6386,nan,3427,7126,4025,9003,1237,5124
9007,3325,3204,3268,5483,1800,6019,9515,5137,5484,7467,3566,1902,3499,9556,3858,4623,0807
5584,0265,1717,nan,5746,5245,8387,7993,6386,2085,9806,8633,6912,4479,4105,1311,8786,5040
7271,0379,7336,8630,nan,5300,9878,7852,4916,7605,3260,9551,8472,4432,8823,1245,8716,5092
1322,9317,8296,3029,1315,7040,9066,9915,4470,3448,6685,8628,2310,0271,5948,7420,4660,3144
5408,5339,8136,0096,1632,8866,2348,5283,4621,5029,6902,1555,9038,3273,1314,6187,4682,9464
9038,5583,9187,6875,4157,9217,6672,0471,0340,0448,7962,6149,9329,7621,2537,8600,3935,8227
7639,8288,8044,3653,4037,6325,3188,9539,2122,8323,3671,2157,nan,nan,nan,nan,nan,nan
2491,0253,3524,8312,2231,6219,3755,1482,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
3239,5920,5903,7316,5844,6625,0195,4110,4055,6391,0811,0064,4778,0189,6085,6887,9193,4347
3328,6030,9047,8006,4621,6519,6063,4491,9705,3192,7288,0147,7977,1192,2623,3530,9190,5575
5310,2958,4527,7007,1520,6117,1745,2067,2650,9045,6734,7284,3297,3121,8208,1914,1192,7799
9262,3319,0697,8126,1892,5378,9574,4374,8165,2594,2817,1516,3607,1592,6475,3028,7423,7455
6304,8477,9855,9727,8359,2865,0750,4548,4809,4015,3174,9850,8467,3775,7218,0785,7403,2305
8603,1359,1902,0131,5995,6547,9243,7881,1672,5929,6791,6154,5345,5358,8193,6981,9159,2611
2100,0427,2317,9292,3984,5893,0848,0871,9004,9629,3940,9403,9216,4993,9016,6007,5422,1390
9679,3975,3113,3183,8218,4197,1842,3271,6801,9077,9926,1467,5698,1655,5133,nan,4763,9952
2263,5548,7912,9804,0176,9289,6088,4909,5685,3002,6712,8221,4053,8768,2967,3642,5377,7731
5888,8097,nan,7791,5298,3315,2413,9518,4174,8007,4631,0095,3967,4895,6869,8600,6893,3332
5734,6625,7222,1743,8125,4613,7653,8032,8959,9993,2539,2205,9372,6760,0014,3232,7347,2125
7339,3551,8346,6620,1845,5331,4846,2685,8324,6877,2167,0270,8598,9124,9296,8436,1248,nan
2887,4855,1632,0942,7731,4758,3877,4479,9330,nan,6332,9347,8568,7798,8610,0567,5537,1991
3217,9214,5408,3104,1067,1139,2998,5675,1636,4424,8317,3365,3050,2405,6069,1838,4852,5764
9320,0908,5093,9370,5696,5127,7343,6107,8913,9600,7221,3727,9215,7300,0714,5883,9346,1187
9153,5750,6822,8115,4237,6269,9816,0833,6897,6525,8947,0513,7589,9849,1894,0674,8059,4691
9215,1021,7816,6639,2359,9058,8913,8831,7417,8784,7117,7895,7779,4190,4857,1538,3302,6840
5166,8287,0452,6011,2844,7339,2910,1823,6827,1003,9278,0224,2049,6745,3064,3641,9685,8804
6336,3408,6065,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
3609,0368,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan,nan
"""

SEQS_RAW = r"""
number_id,roll_position,sequence
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
# 2) Parsing
# =======================
def parse_sequences(text: str):
    """
    Returns:
      - seq_map[(rs_id,pos)] = [10 digits in sequence order]
      - idx_map[(rs_id,pos)] = {digit -> index}
    Skips headers or any non-numeric lines gracefully.
    """
    seq_map, idx_map, bad = {}, {}, []
    for ln in text.strip().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        parts = [t.strip() for t in ln.split(',')]
        if len(parts) < 3:
            continue
        a, b, c = parts[0], parts[1], parts[2]
        if not a.isdigit() or not b.isdigit():
            # skip header like "number_id,roll_position,sequence"
            continue
        rs_id, pos = int(a), int(b)
        seq = [int(x) for x in c.split('|') if x.strip() != ""]
        seq_map[(rs_id, pos)] = seq
        if len(seq) != 10:
            bad.append((rs_id, pos, len(seq), seq))
        idx_map[(rs_id, pos)] = {d: i for i, d in enumerate(seq)}
    if bad:
        print(f"⚠ Some sequences are not length 10 (first few): {bad[:5]} ...")
    # Optional: sanity check coverage
    missing = [(s, p) for s in range(1, 19) for p in range(1, 5) if (s, p) not in seq_map]
    if missing:
        print(f"⚠ Missing sequences for {len(missing)} keys (first few): {missing[:10]}")
    return seq_map, idx_map

def parse_rows(text: str):
    """
    Returns rows: list of lists, 18 strings each ('nan' or 4-digit number).
    Skips header line(s) starting with 'rollerset'.
    """
    rows = []
    for ln in text.strip().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith('#') or ln.lower().startswith('rollerset'):
            continue
        parts = [p.strip() for p in ln.split(',')]
        if len(parts) != 18:
            # ignore malformed lines
            continue
        cleaned = []
        for p in parts:
            if re.fullmatch(r'\d{4}', p):
                cleaned.append(p)
            elif p == '' or p.lower() == 'nan':
                cleaned.append('nan')
            else:
                cleaned.append('nan')
        rows.append(cleaned)
    return rows

# =======================
# 3) Core ΔI calculator
# =======================
def delta_I(d_from: int, d_to: int, idx_map, rs_id: int, pos: int):
    key = (rs_id, pos)
    if key not in idx_map:
        return np.nan
    imap = idx_map[key]
    if d_from not in imap or d_to not in imap:
        return np.nan
    return (imap[d_to] - imap[d_from]) % 10

def di_vector_for_pair(value_from: str, value_to: str, rs_id: int, idx_map):
    """
    Compute 4-position ΔI for one rollerset (rs_id) between two 4-digit strings.
    Returns [dI1,dI2,dI3,dI4] (ints) or NaNs if missing.
    """
    if value_from == 'nan' or value_to == 'nan':
        return [np.nan, np.nan, np.nan, np.nan]
    out = []
    for pos in range(1, 5):
        d_from = int(value_from[pos - 1])
        d_to = int(value_to[pos - 1])
        out.append(int(delta_I(d_from, d_to, idx_map, rs_id, pos)))
    return out

# =======================
# 4) Gap computations
# =======================
def first_pair_gaps(rows, idx_map):
    """
    First numeric row -> second numeric row, across all 18 rollersets.
    Returns dict rs_id -> [dI1,dI2,dI3,dI4]
    """
    if len(rows) < 2:
        raise ValueError("Need at least 2 data rows")
    r0, r1 = rows[0], rows[1]
    gaps = {}
    for rs_id in range(1, 19):
        gaps[rs_id] = di_vector_for_pair(r0[rs_id - 1], r1[rs_id - 1], rs_id, idx_map)
    return gaps

def all_transitions_per_rs(rows):
    """
    For each RS, collect successive numeric observations: (row_index, value).
    Returns a dict rs_id -> list of (row_idx, 'NNNN')
    """
    per_rs = {rs_id: [] for rs_id in range(1, 19)}
    for r_i, row in enumerate(rows):
        for rs_id in range(1, 19):
            v = row[rs_id - 1]
            if v != 'nan' and re.fullmatch(r'\d{4}', v):
                per_rs[rs_id].append((r_i, v))
    return per_rs

def all_gap_rows(rows, idx_map):
    """
    Build a rectangular CSV:
    - Row k = the k-th transition per RS, for all RS.
      If a given RS has fewer than k transitions, that cell is 'nan'.
    - Columns: gap1..gap18 (each a '[a,b,c,d]' string)
    Also returns a second DataFrame with the ranges (Sx->Sy) per RS per k.
    """
    per_rs = all_transitions_per_rs(rows)
    # Build transitions per RS
    transitions = {rs_id: [] for rs_id in range(1, 19)}  # list of dicts per rs_id
    max_len = 0
    for rs_id in range(1, 19):
        obs = per_rs[rs_id]
        for j in range(1, len(obs)):
            i0, v0 = obs[j - 1]
            i1, v1 = obs[j]
            di_vec = di_vector_for_pair(v0, v1, rs_id, idx_map)
            step_range = f"S{i0 + 1} -> S{i1 + 1} ({i1 - i0} steps)"
            transitions[rs_id].append({
                "range": step_range,
                "from": v0,
                "to": v1,
                "di": di_vec
            })
        max_len = max(max_len, len(transitions[rs_id]))

    # Make a table with K rows (K = max_len), columns gap1..gap18, plus range columns
    rows_gap = []
    rows_range = []
    for k in range(max_len):
        row_gap = {}
        row_range = {}
        row_gap["GapIndex"] = k + 1
        row_range["GapIndex"] = k + 1
        for rs_id in range(1, 19):
            if k < len(transitions[rs_id]):
                di_vec = transitions[rs_id][k]["di"]
                row_gap[f"gap{rs_id}"] = str(di_vec)
                row_range[f"range{rs_id}"] = transitions[rs_id][k]["range"]
            else:
                row_gap[f"gap{rs_id}"] = "nan"
                row_range[f"range{rs_id}"] = "nan"
        rows_gap.append(row_gap)
        rows_range.append(row_range)

    df_gaps = pd.DataFrame(rows_gap)
    df_ranges = pd.DataFrame(rows_range)
    return df_gaps, df_ranges

# =======================
# 5) Run and output
# =======================
def main():
    seq_map, idx_map = parse_sequences(SEQS_RAW)
    rows = parse_rows(DATA_RAW)

    # A) First-pair gaps
    gaps = first_pair_gaps(rows, idx_map)
    headers = [f"gap{i}" for i in range(1, 19)]
    row_vals = [str(gaps[i]) for i in range(1, 19)]
    print(",".join(headers))
    print(",".join([f'"{v}"' for v in row_vals]))  # CSV-friendly

    # Save first pair
    df_first = pd.DataFrame([{"GapIndex": 1, **{f"gap{i}": str(gaps[i]) for i in range(1, 19)}}])
    df_first.to_csv("gaps_first_pair.csv", index=False)

    # B) All gaps across whole dataset
    df_all, df_ranges = all_gap_rows(rows, idx_map)
    df_all.to_csv("gaps_all.csv", index=False)
    df_ranges.to_csv("gaps_all_ranges.csv", index=False)

    print("\nWrote:")
    print(" - gaps_first_pair.csv (one row: gap1..gap18)")
    print(" - gaps_all.csv (K rows: each k-th transition per RS, with gap1..gap18)")
    print(" - gaps_all_ranges.csv (same K rows: per-RS step ranges for reference)")

if __name__ == "__main__":
    main()
import pandas as pd
from collections import Counter
import numpy as np
import os # Import os for file path handling

# --- 1. SEQUENCE MAPS (The Genetic Code) ---
# Maps a Digit (value) to its Index (position 0-9)
# Sequence: [Digit at Index 0, Digit at Index 1, ..., Digit at Index 9]

# Dictionary to hold all sequence maps
SEQUENCES = {}

# Parse the provided sequence data
sequence_data_raw = """
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

for line in sequence_data_raw.strip().split('\n'):
    if not line: continue
    rs_id, pos, seq_str = line.split(',')
    key = (int(rs_id), int(pos))
    SEQUENCES[key] = [int(d) for d in seq_str.split('|')]

# --- 2. THE MAIN DATA ---
# List of lists, where each inner list is a full step (18 rollerset values)
data_raw = """
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
"""

# Process data into a list of steps (lists of 4-digit strings)
data_steps = []
for line in data_raw.strip().split('\n'):
    data_steps.append(line.split(','))

# --- 3. CORE CALCULATION LOGIC ---

def calculate_delta_I(digit_from, digit_to, rs_id, pos):
    """Calculates the Index Jump (Delta I) using the specific sequence map."""
    key = (rs_id, pos)
    if key not in SEQUENCES:
        return np.nan
    
    seq = SEQUENCES[key]
    
    try:
        I_from = seq.index(digit_from)
        I_to = seq.index(digit_to)
    except ValueError:
        return np.nan

    delta_I = (I_to - I_from + 10) % 10
    return delta_I

def get_mode(delta_I_list):
    """Finds the mode of a list, handling multiple modes."""
    clean_list = [x for x in delta_I_list if not pd.isna(x)]
    if not clean_list:
        return 'N/A'
    
    counts = Counter(clean_list)
    max_count = max(counts.values())
    modes = [k for k, v in counts.items() if v == max_count]
    
    if len(modes) == 4:
        return f'{modes[0]}/{modes[-1]}'
    elif len(modes) > 1:
        return f'{modes[0]},{modes[1]}'
    else:
        return modes[0]

def calculate_combined_jump(rs_id, start_step_index):
    """
    Finds the next non-nan data point and calculates the total jump and average jump.
    Returns: (Step_Range, Delta_I_Combined_List, Delta_I_Average_List, Num_Steps) or None
    """
    start_row = data_steps[start_step_index]
    rs_str_start = start_row[rs_id - 1]
    
    if rs_str_start.lower() == 'nan':
        return None 

    for end_step_index in range(start_step_index + 1, num_steps):
        end_row = data_steps[end_step_index]
        rs_str_end = end_row[rs_id - 1]
        
        if rs_str_end.lower() != 'nan':
            num_steps_jumped = end_step_index - start_step_index
            step_range = f'S{start_step_index + 1} -> S{end_step_index + 1} ({num_steps_jumped} steps)'
            
            delta_Is_combined = []
            delta_Is_average = []
            
            for pos in range(1, 5):
                digit_start = int(rs_str_start[pos - 1])
                digit_end = int(rs_str_end[pos - 1])
                
                delta_I = calculate_delta_I(digit_start, digit_end, rs_id, pos)
                delta_Is_combined.append(delta_I)
                
                if delta_I is not np.nan:
                    avg_I = round(delta_I / num_steps_jumped, 2)
                    delta_Is_average.append(avg_I)
                else:
                    delta_Is_average.append(np.nan)
            
            return (step_range, delta_Is_combined, delta_Is_average, num_steps_jumped)

    return None


# --- 4. MAIN ANALYSIS LOOP ---

full_analysis = []
combined_analysis = []
num_steps = len(data_steps)

# A. Single-Step Delta I Analysis
for step_index in range(num_steps - 1):
    step_name = f'S{step_index + 1} -> S{step_index + 2}'
    from_row = data_steps[step_index]
    to_row = data_steps[step_index + 1]
    
    step_results = {'Step': step_name}
    
    for rs_id in range(1, 19):
        rs_str_from = from_row[rs_id - 1]
        rs_str_to = to_row[rs_id - 1]
        
        # Check for NaN entries
        is_nan = rs_str_from.lower() == 'nan' or rs_str_to.lower() == 'nan'

        delta_Is = []
        for pos in range(1, 5):
            if not is_nan:
                digit_from = int(rs_str_from[pos - 1])
                digit_to = int(rs_str_to[pos - 1])
                delta_I = calculate_delta_I(digit_from, digit_to, rs_id, pos)
                delta_Is.append(delta_I)
                step_results[f'RS {rs_id} R{pos}'] = delta_I
            else:
                delta_Is.append(np.nan)
                step_results[f'RS {rs_id} R{pos}'] = np.nan

        step_results[f'RS {rs_id} Cluster'] = get_mode(delta_Is) if not is_nan else 'SKIPPED (nan)'
        
    full_analysis.append(step_results)

# B. Combined Jump Analysis (for steps affected by 'nan')
for step_index in range(num_steps - 1):
    from_row = data_steps[step_index]
    
    is_gap_start = False
    for rs_id in range(1, 19):
        if (data_steps[step_index][rs_id - 1].lower() != 'nan' and 
            (step_index + 1 < num_steps and data_steps[step_index + 1][rs_id - 1].lower() == 'nan')):
            is_gap_start = True
            break
            
    if is_gap_start:
        combined_results = {'Transition': f'S{step_index + 1} -> NEXT VALID'}
        gap_was_found = False
        
        for rs_id in range(1, 19):
            combined_jump_data = calculate_combined_jump(rs_id, step_index)
            
            if combined_jump_data:
                gap_was_found = True
                step_range, dI_combined, dI_average, num_steps_jumped = combined_jump_data
                
                # Format Delta I Combined and Average for CSV
                dI_combined_str = [str(int(x)) if not pd.isna(x) else 'nan' for x in dI_combined]
                dI_average_str = [str(x) if not pd.isna(x) else 'nan' for x in dI_average]
                
                combined_results[f'RS {rs_id} Range'] = step_range
                combined_results[f'RS {rs_id} DeltaI Combined'] = "/".join(dI_combined_str)
                combined_results[f'RS {rs_id} Avg DeltaI per Step'] = "/".join(dI_average_str)
            else:
                combined_results[f'RS {rs_id} Range'] = 'No Next Data'
                combined_results[f'RS {rs_id} DeltaI Combined'] = 'nan'
                combined_results[f'RS {rs_id} Avg DeltaI per Step'] = 'nan'

        if gap_was_found:
            combined_analysis.append(combined_results)


# --- 5. DATA EXPORT AND OUTPUT ---

df_single_step = pd.DataFrame(full_analysis)
df_combined = pd.DataFrame(combined_analysis)

# Define column order for the Single-Step output
single_step_cols = ['Step'] + [col for i in range(1, 19) for col in [f'RS {i} R1', f'RS {i} R2', f'RS {i} R3', f'RS {i} R4', f'RS {i} Cluster']]
df_single_step = df_single_step.reindex(columns=single_step_cols)

# Define column order for the Combined Jump output
if not df_combined.empty:
    combined_jump_cols = ['Transition'] + [col for i in range(1, 19) for col in [f'RS {i} Range', f'RS {i} DeltaI Combined', f'RS {i} Avg DeltaI per Step']]
    df_combined = df_combined.reindex(columns=[col for col in combined_jump_cols if col in df_combined.columns])

# --- SAVE TO CSV FILES ---
single_csv_name = 'Single_Step_DeltaI_Analysis.csv'
combined_csv_name = 'Combined_Jump_Analysis.csv'

df_single_step.to_csv(single_csv_name, index=False)
print(f"### ✅ Output Saved!")
print(f"* Single-Step Delta I Analysis saved to: **{os.path.abspath(single_csv_name)}**")

if not df_combined.empty:
    df_combined.to_csv(combined_csv_name, index=False)
    print(f"* Combined Jump Analysis saved to: **{os.path.abspath(combined_csv_name)}**")
else:
    print("* Combined Jump Analysis file was skipped (no relevant data gaps found).")

print("\n---")
print("### Preview of Single-Step Analysis:")
print(df_single_step.head(10).to_string())
"""
analyze_6digit_sequences.py

Usage:
    - Prepare a prizes CSV (e.g. prizes.csv) with at least:
        draw_date, prize1, prize2, ... prizeN
      prize columns should be six-digit numbers (strings) or numeric (script will zero-pad to 6).
    - Prepare sequences CSV (e.g. sequences.csv) with:
        number_id,sequence
      where sequence is like: 1,7|1|4|9|5|2|8|6|3

    Run:
        python analyze_6digit_sequences.py prizes.csv sequences.csv

Outputs:
    - sequence_movements_detailed.csv
    - sequence_movements_summary.csv
    - sequence_predictions.csv
"""

import sys
import pandas as pd
from collections import Counter, defaultdict
import csv

def read_sequences(seq_csv):
    df = pd.read_csv(seq_csv, dtype=str).fillna("")
    seq_map = {}
    for _, r in df.iterrows():
        nid = str(r['number_id']).strip()
        seq_text = str(r['sequence']).strip()
        if seq_text == "" or nid == "":
            continue
        seq = [int(x) for x in seq_text.split("|")]
        # Make index map for quick lookup
        index_map = {d:i for i,d in enumerate(seq)}
        seq_map[nid] = {
            'seq': seq,
            'index': index_map,
            'raw': seq_text
        }
    return seq_map

def normalize_prize(x):
    if pd.isna(x):
        return None
    s = str(int(x)) if (isinstance(x, float) or isinstance(x, int) or (isinstance(x,str) and x.isdigit())) else str(x).strip()
    # Remove any non digits
    s = "".join(ch for ch in s if ch.isdigit())
    if s == "":
        return None
    # zero-pad to 6
    if len(s) > 6:
        s = s[-6:]  # keep last 6 if longer
    return s.zfill(6)

def compute_steps_for_sequence(prev6, curr6, seq_info):
    """
    prev6, curr6: 6-char strings of digits
    seq_info: {'seq': [..], 'index': {digit:pos}, 'raw': '7|...' }
    Returns: list of 6 ints (0..9) representing steps moved under this sequence.
             step = (pos(curr) - pos(prev)) mod 10
    If a digit is missing in sequence -> None for that position.
    """
    idx = seq_info['index']
    res = []
    for i in range(6):
        a = int(prev6[i])
        b = int(curr6[i])
        if a not in idx or b not in idx:
            res.append(None)
        else:
            pos_a = idx[a]
            pos_b = idx[b]
            # forward movement modulo len(seq) (normally 10)
            L = len(seq_info['seq'])
            step = (pos_b - pos_a) % L
            res.append(step)
    return res

def steps_to_pipe(steps):
    return "|".join(str(s) if s is not None else "" for s in steps)

def apply_steps_to_number(start6, steps, seq_info):
    # produce new number by moving each digit forward in the sequence by given steps
    seq = seq_info['seq']
    idx = seq_info['index']
    L = len(seq)
    out_digits = []
    for i in range(6):
        d = int(start6[i])
        if d not in idx or steps[i] is None:
            out_digits.append("?")
        else:
            pos = idx[d]
            newpos = (pos + steps[i]) % L
            out_digits.append(str(seq[newpos]))
    return "".join(out_digits)

def main(prizes_csv, sequences_csv):
    seq_map = read_sequences(sequences_csv)
    if not seq_map:
        print("No sequences loaded. Check sequences CSV.")
        return

    # read prizes
    df = pd.read_csv(prizes_csv, dtype=str)
    df = df.fillna("")
    # detect prize columns: any column that looks like a prize (6-digit) besides draw date
    # We'll treat all non-draw_date columns as prize columns
    cols = list(df.columns)
    # assume first column is draw date if it isn't numeric-like; else user can edit
    if len(cols) >= 1 and ('date' in cols[0].lower() or 'draw' in cols[0].lower()):
        draw_col = cols[0]
        prize_cols = cols[1:]
    else:
        draw_col = cols[0]  # still treat as draw
        prize_cols = cols[1:] if len(cols)>1 else cols

    # normalize prize values
    for c in prize_cols:
        df[c] = df[c].apply(lambda x: normalize_prize(x) if x != "" else None)

    detailed_rows = []
    summary = defaultdict(lambda: {'transitions':0, 'identical_count':0, 'step_vectors':Counter(), 'total_steps_sum':0, 'total_positions':0})

    # iterate transitions prev->curr rowwise
    for i in range(len(df)-1):
        prev_row = df.iloc[i]
        curr_row = df.iloc[i+1]
        draw_prev = prev_row[draw_col] if draw_col in df.columns else i
        draw_curr = curr_row[draw_col] if draw_col in df.columns else i+1

        for prize_col in prize_cols:
            prev_val = prev_row[prize_col]
            curr_val = curr_row[prize_col]
            if prev_val is None or curr_val is None:
                continue

            for nid, seq_info in seq_map.items():
                steps = compute_steps_for_sequence(prev_val, curr_val, seq_info)
                # textual representation
                steps_pipe = steps_to_pipe(steps)
                total = sum(s for s in steps if s is not None)
                # store detailed
                detailed_rows.append({
                    'draw_prev_index': i,
                    'draw_prev_date': draw_prev,
                    'draw_curr_index': i+1,
                    'draw_curr_date': draw_curr,
                    'prize_col': prize_col,
                    'prev': prev_val,
                    'curr': curr_val,
                    'sequence_id': nid,
                    'sequence_text': seq_info['raw'],
                    'steps_pipe': steps_pipe,
                    'total_steps': total
                })
                # update summary
                key = nid
                summary[key]['transitions'] += 1
                summary[key]['step_vectors'][steps_pipe] += 1
                summary[key]['total_steps_sum'] += total
                # count defined positions
                summary[key]['total_positions'] += sum(1 for s in steps if s is not None)
                # identical_count: count how often this exact steps_pipe repeats (we'll compute later)

    # post process summary: find most frequent vector and consistency metric
    summary_rows = []
    for nid, info in seq_map.items():
        s = summary.get(nid, None)
        if not s:
            summary_rows.append({
                'sequence_id': nid,
                'sequence_text': info['raw'],
                'transitions': 0,
                'most_common_steps': '',
                'most_common_count': 0,
                'consistency_pct': 0.0,
                'avg_total_steps': 0.0
            })
            continue
        total_trans = s['transitions']
        most_common_steps, most_common_count = ("",0)
        if s['step_vectors']:
            most_common_steps, most_common_count = s['step_vectors'].most_common(1)[0]
        consistency = (most_common_count / total_trans) * 100 if total_trans>0 else 0.0
        avg_total = s['total_steps_sum'] / total_trans if total_trans>0 else 0.0
        summary_rows.append({
            'sequence_id': nid,
            'sequence_text': info['raw'],
            'transitions': total_trans,
            'most_common_steps': most_common_steps,
            'most_common_count': most_common_count,
            'consistency_pct': round(consistency,2),
            'avg_total_steps': round(avg_total,3)
        })

    # Save detailed CSV
    det_df = pd.DataFrame(detailed_rows)
    if len(det_df)>0:
        det_df.to_csv("sequence_movements_detailed.csv", index=False)
    else:
        print("No detailed rows to save - maybe prize CSV too short or missing values.")

    # Save summary CSV
    sum_df = pd.DataFrame(summary_rows)
    sum_df.to_csv("sequence_movements_summary.csv", index=False)

    # Simple prediction: apply most common steps for each (prize_col, sequence) to last known prize value
    predictions = []
    last_row = df.iloc[-1]
    for prize_col in prize_cols:
        last_val = last_row[prize_col]
        if last_val is None:
            continue
        # for each sequence, find its most common steps pattern (from summary data) and apply to last_val
        for nid, info in seq_map.items():
            # find most common vector for this sequence from detailed_rows (we already counted in summary)
            row = next((r for r in summary_rows if r['sequence_id']==nid), None)
            if not row or row['most_common_steps']=="":
                continue
            steps_pipe = row['most_common_steps']
            steps = []
            for part in steps_pipe.split("|"):
                if part=="":
                    steps.append(None)
                else:
                    steps.append(int(part))
            predicted = apply_steps_to_number(last_val, steps, info)
            predictions.append({
                'prize_col': prize_col,
                'last_value': last_val,
                'sequence_id': nid,
                'sequence_text': info['raw'],
                'used_steps': steps_pipe,
                'predicted_next': predicted,
                'consistency_pct': row['consistency_pct']
            })

    if predictions:
        pd.DataFrame(predictions).to_csv("sequence_predictions.csv", index=False)

    print("Done. Files produced:")
    print("- sequence_movements_detailed.csv")
    print("- sequence_movements_summary.csv")
    print("- sequence_predictions.csv")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python analyze_6digit_sequences.py prizes.csv sequences.csv")
    else:
        main(sys.argv[1], sys.argv[2])

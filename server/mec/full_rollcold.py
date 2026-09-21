import re, math
import numpy as np
import pandas as pd
from collections import Counter, defaultdict

GAPS = "gaps_norm_flat_compact.csv"
MAP  = "rollers_mapping.csv"
CONS = "rr_consensus_per_step.csv"

# thresholds (tune these)
MIN_SUPPORT = 2       # step-consensus minimum support
MIN_RATIO   = 0.5     # step-consensus support/total
MIN_MKV     = 3       # min Markov count for (rr,pos,prev)->next

def parse_rs_pos(col):
    m = re.match(r"gap(\d+)_norm_R(\d+)$", col)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)

def melt_norm(gaps_csv):
    df = pd.read_csv(gaps_csv)
    norm_cols = [c for c in df.columns if c.startswith("gap") and "_norm_R" in c]
    long = df.melt(id_vars=["FromStep","ToStep"], value_vars=norm_cols,
                   var_name="col", value_name="val")
    rspos = long["col"].apply(parse_rs_pos)
    long["rs_id"] = rspos.apply(lambda t: t[0]).astype("Int64")
    long["pos"]   = rspos.apply(lambda t: t[1]).astype("Int64")
    long["val"]   = pd.to_numeric(long["val"], errors="coerce")
    long = long.dropna(subset=["rs_id","pos"]).copy()
    long["rs_id"] = long["rs_id"].astype(int)
    long["pos"]   = long["pos"].astype(int)
    return long

def attach_groups(long, map_csv):
    mp = pd.read_csv(map_csv, dtype={"rs_id":int,"roll_position":int})
    return long.merge(mp[["rs_id","roll_position","rotrev_group_id"]],
                      left_on=["rs_id","pos"], right_on=["rs_id","roll_position"],
                      how="left")

def load_consensus(cons_csv):
    d = {}
    cons = pd.read_csv(cons_csv)
    for _, r in cons.iterrows():
        fs, ts = int(r.FromStep), int(r.ToStep)
        rr, pos = r.rotrev_group_id, int(r.pos)
        d[(fs, ts, rr, pos)] = (int(r.consensus), int(r.support), int(r.total))
    return d

def class_modes(long):
    gm = {}
    for (rr,pos), sub in long.dropna(subset=["val","rotrev_group_id"]).groupby(["rotrev_group_id","pos"]):
        vals = sub["val"].astype(int).tolist()
        c = Counter(vals)
        gm[(rr,pos)] = min(c.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return gm

def personal_modes(long):
    pm = {}
    for (rs,pos), sub in long.dropna(subset=["val"]).groupby(["rs_id","pos"]):
        vals = sub["val"].astype(int).tolist()
        c = Counter(vals)
        pm[(rs,pos)] = min(c.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return pm

def add_prev_value(long):
    """
    For each (rs,pos), align prev ΔI by matching previous row where ToStep of prev == FromStep of curr.
    """
    long = long.sort_values(["rs_id","pos","FromStep","ToStep"]).copy()
    # prev for same (rs,pos): prev_ToStep == curr_FromStep
    long["prev_val"] = np.nan
    # Build mapping: (rs,pos,ToStep) -> val
    key_prev = {(int(r.rs_id), int(r.pos), int(r.ToStep)): int(r.val)
                for _, r in long.dropna(subset=["val"]).iterrows()}
    prev_list = []
    for _, r in long.iterrows():
        k = (int(r.rs_id), int(r.pos), int(r.FromStep))
        prev_list.append(key_prev.get(k, np.nan))
    long["prev_val"] = prev_list
    return long

def train_markov(long):
    """
    Train counts of next | prev per (rr,pos). Return: dict[(rr,pos)][prev][next] = count
    """
    mkv = defaultdict(lambda: defaultdict(Counter))
    df = long.dropna(subset=["val","prev_val","rotrev_group_id"]).copy()
    for _, r in df.iterrows():
        rr, pos = r.rotrev_group_id, int(r.pos)
        pv, nv = int(r.prev_val), int(r.val)
        mkv[(rr,pos)][pv][nv] += 1
    return mkv

def argmax_with_count(cnt: Counter):
    if not cnt: return (None, 0)
    return min(cnt.items(), key=lambda kv: (-kv[1], kv[0]))  # tie -> smaller

def circ_delta(a, b):
    # circular distance on Z10 (0..9)
    d = abs((int(a) - int(b)) % 10)
    return min(d, 10 - d)

def predict_one(fs, ts, rs, pos, rr, prev_val, cons_dict, p_modes, c_modes, mkv,
                min_support=MIN_SUPPORT, min_ratio=MIN_RATIO, min_mkv=MIN_MKV):
    # 1) Markov on prev_val
    if rr is not None and not pd.isna(prev_val):
        pv = int(prev_val)
        cnts = mkv.get((rr,pos), {}).get(pv, Counter())
        if sum(cnts.values()) >= min_mkv:
            nxt, _ = argmax_with_count(cnts)
            if nxt is not None:
                return nxt, "markov"

    # 2) Step consensus
    key = (fs, ts, rr, pos)
    if key in cons_dict:
        val, sup, tot = cons_dict[key]
        ratio = sup / tot if tot else 0.0
        if sup >= min_support and ratio >= min_ratio:
            return val, "step_consensus"

    # 3) Personal mode
    if (rs, pos) in p_modes:
        return p_modes[(rs,pos)], "personal_mode"

    # 4) Class mode
    if (rr, pos) in c_modes:
        return c_modes[(rr,pos)], "class_mode"

    return np.nan, "none"

def evaluate_predictions(long, preds):
    """
    long: rows with columns (FromStep,ToStep,rs_id,pos,val)
    preds: dict[(FromStep,ToStep,rs_id,pos)] -> pred
    """
    rows = []
    for _, r in long.dropna(subset=["val"]).iterrows():
        key = (int(r.FromStep), int(r.ToStep), int(r.rs_id), int(r.pos))
        actual = int(r.val)
        pred = preds.get(key, np.nan)
        if pd.isna(pred):
            continue
        rows.append((actual, int(pred), r.rotrev_group_id, int(r.pos)))
    if not rows:
        return pd.DataFrame(columns=["actual","pred","rr","pos","match","within1","circ_err"])

    df = pd.DataFrame(rows, columns=["actual","pred","rr","pos"])
    df["match"] = (df["actual"] == df["pred"]).astype(int)
    df["within1"] = df.apply(lambda s: int(circ_delta(s["actual"], s["pred"]) <= 1), axis=1)
    df["circ_err"] = df.apply(lambda s: circ_delta(s["actual"], s["pred"]), axis=1)
    return df

def main():
    # Load + prepare
    long = melt_norm(GAPS)
    long = attach_groups(long, MAP)
    long = add_prev_value(long)

    cons = load_consensus(CONS)
    c_modes = class_modes(long)
    p_modes = personal_modes(long)
    mkv = train_markov(long)

    # Predict
    preds = {}
    srcs = {}
    for _, r in long.iterrows():
        fs, ts = int(r.FromStep), int(r.ToStep)
        rs, pos = int(r.rs_id), int(r.pos)
        rr = r.rotrev_group_id
        prev_val = r.prev_val
        pred, src = predict_one(fs, ts, rs, pos, rr, prev_val, cons, p_modes, c_modes, mkv)
        preds[(fs, ts, rs, pos)] = pred
        srcs[(fs, ts, rs, pos)] = src

    # Write wide predicted
    step_pairs = sorted({(int(fs), int(ts)) for fs, ts in zip(long.FromStep, long.ToStep)})
    rows = []
    for fs, ts in step_pairs:
        rec = {"FromStep": fs, "ToStep": ts}
        for rs in range(1, 19):
            for pos in range(1, 5):
                rec[f"gap{rs}_pred_R{pos}"] = preds.get((fs, ts, rs, pos), np.nan)
        rows.append(rec)
    pd.DataFrame(rows).to_csv("predicted_norm_gaps_markov.csv", index=False)

    # Evaluate
    eval_df = evaluate_predictions(long, preds)
    overall = {
        "scope":"overall",
        "n": int(len(eval_df)),
        "acc_exact": round(eval_df["match"].mean(), 4) if len(eval_df) else None,
        "acc_within1": round(eval_df["within1"].mean(), 4) if len(eval_df) else None,
        "circ_mae": round(eval_df["circ_err"].mean(), 3) if len(eval_df) else None,
    }
    rows = [overall]
    for (rr,pos), sub in eval_df.groupby(["rr","pos"]):
        rows.append({
            "scope": f"{rr}_pos{pos}",
            "n": int(len(sub)),
            "acc_exact": round(sub["match"].mean(), 4),
            "acc_within1": round(sub["within1"].mean(), 4),
            "circ_mae": round(sub["circ_err"].mean(), 3),
        })
    pd.DataFrame(rows).to_csv("prediction_accuracy_markov.csv", index=False)

    # Where predictions came from (mix diagnostics)
    src_counts = Counter(srcs.values())
    pd.DataFrame([{"source":k,"count":v} for k,v in src_counts.items()]).to_csv("prediction_sources_markov.csv", index=False)

    print("Wrote predicted_norm_gaps_markov.csv, prediction_accuracy_markov.csv, prediction_sources_markov.csv")

if __name__ == "__main__":
    main()
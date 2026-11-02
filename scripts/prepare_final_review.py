"""
BPI Challenge 2012 - extract the "final review" cases and build the networks.

Steps
 1. Load the event log (.xes.gz from 4TU.ResearchData)
 2. Keep only COMPLETE events (one event = one finished task)
 3. Label every case with its outcome: approved / declined / cancelled
 4. Keep only cases that reached the final review step (W_Valideren aanvraag)
 5. Keep only approved and declined cases
 6. Remove events with no resource (empty org:resource) and the system resource (112)
 7. Take the same number of cases from each group (fair comparison)
 8. Build the handover-of-work network per group (working together is
    computed in analyse_networks.py, following the paper's definition)
 9. Save everything as CSV (for Gephi / NetworkX)

Download the log here and save it in data/raw/ (run from anywhere: python scripts/prepare_final_review.py):
https://data.4tu.nl/articles/dataset/BPI_Challenge_2012/12689204
"""
from pathlib import Path

import pandas as pd
import pm4py

ROOT = Path(__file__).resolve().parent.parent      # repository root
RAW, PROCESSED, EDGES = ROOT / "data" / "raw", ROOT / "data" / "processed", ROOT / "results" / "edges"
for d in (PROCESSED, EDGES):
    d.mkdir(parents=True, exist_ok=True)

# The log in data/raw/: the compressed file (stored on GitHub) or the unzipped one
LOG_FILE = next((f for f in [RAW / "BPI_Challenge_2012.xes.gz", RAW / "BPI_Challenge_2012.xes"] if f.exists()),
                RAW / "BPI_Challenge_2012.xes.gz")
REVIEW_ACTIVITY = "W_Valideren aanvraag"   # final review step (validation of the application)
SEED = 42                                   # fixed seed -> same sample every time (reliability)
SYSTEM_RESOURCES = ["112"]                  # records every A_SUBMITTED event -> the system, not a person

CASE, ACT, RES, TIME, LIFE = ("case:concept:name", "concept:name",
                              "org:resource", "time:timestamp", "lifecycle:transition")


def load_log(path):
    df = pm4py.read_xes(str(path))              # returns a pandas DataFrame
    print(f"Loaded: {df[CASE].nunique()} cases, {len(df)} events")
    return df


def explore(df):
    """Look at the data before filtering: which activities exist and how often."""
    print("\nActivities (count of events):")
    print(df[ACT].value_counts().to_string())
    print("\nLifecycle transitions:", df[LIFE].value_counts().to_dict())
    print("Events without resource:", df[RES].isna().sum())


def label_outcome(df):
    """One row per case: outcome + whether it reached the final review."""
    acts = df.groupby(CASE)[ACT].apply(set)

    def outcome(s):
        if "A_APPROVED" in s:
            return "approved"
        if "A_DECLINED" in s:
            return "declined"
        if "A_CANCELLED" in s:
            return "cancelled"
        return "open"                       # case still running at the end of the log

    cases = pd.DataFrame({
        "outcome": acts.apply(outcome),
        "reached_review": acts.apply(lambda s: REVIEW_ACTIVITY in s),
    })
    print("\nAll cases by outcome:\n", cases["outcome"].value_counts().to_string())
    print("\nOutcome x reached final review:\n",
          pd.crosstab(cases["outcome"], cases["reached_review"]).to_string())
    return cases


def select_cases(df, cases, balance=True):
    keep = cases[cases["reached_review"] & cases["outcome"].isin(["approved", "declined"])]
    if balance:                             # same number of cases in both groups
        n = keep["outcome"].value_counts().min()
        keep = keep.groupby("outcome", group_keys=False).sample(n=n, random_state=SEED)
    print("\nSelected cases:\n", keep["outcome"].value_counts().to_string())
    out = df[df[CASE].isin(keep.index)].copy()
    out["outcome"] = out[CASE].map(keep["outcome"])
    return out


def build_networks(df_group, name):
    """Handover of work, saved as an edge list."""
    df_group = df_group.sort_values([CASE, TIME])
    nets = {
        "handover": pm4py.discover_handover_of_work_network(df_group),
    }
    for kind, sna in nets.items():
        edges = pd.DataFrame([(a, b, w) for (a, b), w in sna.connections.items() if w > 0],
                             columns=["Source", "Target", "Weight"])
        edges.to_csv(EDGES / f"edges_{kind}_{name}.csv", index=False)   # Gephi reads this directly
        print(f"{name:9s} {kind:17s}: {edges[['Source','Target']].stack().nunique()} people, {len(edges)} edges")


if __name__ == "__main__":
    df = load_log(LOG_FILE)
    df = df[df[LIFE] == "COMPLETE"]         # 1 event per finished task
    explore(df)
    cases = label_outcome(df)               # outcome is decided on ALL events of the case
    df = select_cases(df, cases)
    df = df[df[RES].notna()]                # drop events without a person (after labelling!)
    df[RES] = df[RES].astype(str)
    system = df[df[RES].isin(SYSTEM_RESOURCES)]
    print("\nActivities recorded by the system resource(s)", SYSTEM_RESOURCES, ":")
    print(system[ACT].value_counts().to_string())
    df = df[~df[RES].isin(SYSTEM_RESOURCES)]  # keep only human employees
    print(f"Removed {len(system)} system events; {df[RES].nunique()} employees left\n")
    df.to_csv(PROCESSED / "final_review_events.csv", index=False)
    for group in ["approved", "declined"]:
        build_networks(df[df["outcome"] == group], group)

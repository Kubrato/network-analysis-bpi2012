"""
BPI Challenge 2012 - network measures and statistical tests.

Run this AFTER prepare_final_review.py:  python scripts/analyse_networks.py
It reads the files that prepare_final_review.py created:
  edges_handover_approved.csv, edges_handover_declined.csv,
  final_review_events.csv  (working together is recomputed from the events)

What it does
 STEP 1  Load the four networks (removing self-loops; symmetrising and
         thresholding the working-together network)
 STEP 2  Whole-network measures (Lecture 6) + comparison with random graphs
 STEP 3  Node measures (Lecture 5): degree, betweenness, closeness,
         HITS and weighted PageRank (handover), eigenvector (working
         together), communities
 STEP 4  QAP test (Lecture 4): are the approved and declined handover
         networks similar?
 STEP 5  Permutation test (Lecture 4): are the differences in the
         whole-network measures larger than chance?
 STEP 6  Same key people in both groups? (rank correlation of betweenness)
 STEP 7  PageRank vs HITS authority: do they rank employees the same way?

Output files: network_summary.csv, nodes_<network>_<group>.csv,
              <network>_<group>.gexf (open in Gephi), tests.csv
"""
import random
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx
from networkx.algorithms import community as nxcom
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent.parent      # repository root
EVENTS_FILE = ROOT / "data" / "processed" / "final_review_events.csv"
EDGES = ROOT / "results" / "edges"
TABLES, GEPHI = ROOT / "results" / "tables", ROOT / "results" / "gephi"
for d in (TABLES, GEPHI):
    d.mkdir(parents=True, exist_ok=True)

GROUPS = ["approved", "declined"]
SEED = 42                # fixed seed -> same results every time (reliability)
WT_THRESHOLD = 0.2       # keep working-together ties with weight >= this (dichotomisation)
# Optional: another threshold from the command line, e.g.  python scripts/analyse_networks.py 0.1
# Results for a non-default threshold get a suffix (e.g. network_summary_wt0.1.csv),
# so the main results are never overwritten (robustness check).
TAG = ""
if len(sys.argv) > 1:
    WT_THRESHOLD = float(sys.argv[1])
    if WT_THRESHOLD != 0.2:
        TAG = f"_wt{WT_THRESHOLD}"
N_RANDOM = 20            # random graphs per network for the small-world comparison
N_QAP = 5000             # QAP permutations
N_PERM = 500             # label permutations for the whole-network test

CASE, ACT, RES, TIME = "case:concept:name", "concept:name", "org:resource", "time:timestamp"
warnings.filterwarnings("ignore")   # hide library warnings; results are not affected
rng = np.random.default_rng(SEED)
random.seed(SEED)


# ---------------------------------------------------------------- STEP 1
def load_handover(group):
    """Directed, weighted network: who passes work to whom."""
    e = pd.read_csv(EDGES / f"edges_handover_{group}.csv", dtype={"Source": str, "Target": str})
    G = nx.DiGraph()
    G.add_nodes_from(sorted(set(e.Source) | set(e.Target)))   # fixed order -> same communities every run
    for s, t, w in e.sort_values(["Source", "Target"]).itertuples(index=False):
        if s != t:                                   # self-loops = same person continues
            G.add_edge(s, t, weight=float(w))
    return G, int((e.Source == e.Target).sum())


def load_events():
    ev = pd.read_csv(EVENTS_FILE, dtype={RES: str, CASE: str})
    ev[TIME] = pd.to_datetime(ev[TIME], utc=True, errors="coerce")
    return ev.sort_values([CASE, TIME], kind="stable")


EVENTS = None


def load_working_together(group, threshold):
    """Undirected network, computed as in the paper (Def. 4.5):
    w(a->b) = cases a and b share / cases of a.  The two directions are
    averaged (symmetrisation), then weak ties below the threshold are
    dropped (dichotomisation).  (PM4Py divides by the number of events
    instead, which is hard to interpret, so we compute it ourselves.)"""
    global EVENTS
    if EVENTS is None:
        EVENTS = load_events()
    ev = EVENTS[EVENTS["outcome"] == group]
    people_per_case = ev.groupby(CASE)[RES].apply(lambda r: sorted(set(r)))
    n_cases, joint = Counter(), Counter()
    for people in people_per_case:
        n_cases.update(people)
        for i, a in enumerate(people):
            for b in people[i + 1:]:
                joint[(a, b)] += 1
    G = nx.Graph()
    G.add_nodes_from(sorted(n_cases))                          # fixed order -> same communities every run
    for (a, b), j in sorted(joint.items()):
        w = (j / n_cases[a] + j / n_cases[b]) / 2
        if w >= threshold:
            G.add_edge(a, b, weight=w, joint_cases=j)
    return G


def threshold_check(group):
    """Density of the working-together network for different thresholds."""
    return {thr: round(nx.density(load_working_together(group, thr)), 3)
            for thr in [0, 0.05, 0.1, 0.2, 0.3]}


# ---------------------------------------------------------------- STEP 2
def largest_component(U):
    return U.subgraph(max(nx.connected_components(U), key=len)).copy()


def degree_centralisation(U):
    """Freeman centralisation: 1 = star, 0 = everyone has the same degree."""
    n = U.number_of_nodes()
    if n < 3:
        return float("nan")
    d = [deg for _, deg in U.degree()]
    return sum(max(d) - x for x in d) / ((n - 1) * (n - 2))


def whole_network(G):
    U = G.to_undirected() if G.is_directed() else G
    if U.number_of_edges() == 0:
        raise SystemExit("Network has no ties - lower WT_THRESHOLD and run again.")
    n, m = G.number_of_nodes(), G.number_of_edges()
    L = largest_component(U)
    comms = nxcom.greedy_modularity_communities(U, weight="weight")
    C, Lpath = nx.average_clustering(U), nx.average_shortest_path_length(L)
    # random graphs with the same number of nodes and ties (Erdos-Renyi G(n, m))
    Cr, Lr = [], []
    for k in range(N_RANDOM):
        R = nx.gnm_random_graph(U.number_of_nodes(), U.number_of_edges(), seed=SEED + k)
        Cr.append(nx.average_clustering(R))
        Lr.append(nx.average_shortest_path_length(largest_component(R)))
    Cr, Lr = float(np.mean(Cr)), float(np.mean(Lr))
    res = {
        "nodes": n, "ties": m,
        "density": nx.density(G),
        "avg_degree": 2 * U.number_of_edges() / n,
        "components": nx.number_connected_components(U),
        "largest_component": L.number_of_nodes(),
        "diameter": nx.diameter(L),
        "avg_path_length": Lpath,
        "avg_clustering": C,
        "transitivity": nx.transitivity(U),
        "degree_centralisation": degree_centralisation(U),
        "communities": len(comms),
        "modularity": nxcom.modularity(U, comms, weight="weight"),
        "random_clustering": Cr, "random_path_length": Lr,
        "sigma_small_world": (C / Cr) / (Lpath / Lr) if Cr > 0 else float("nan"),
    }
    if G.is_directed():
        res["reciprocity"] = nx.reciprocity(G)
    return res, comms


# ---------------------------------------------------------------- STEP 3
def node_measures(G, comms):
    comm_of = {v: i for i, c in enumerate(comms) for v in c}
    t = pd.DataFrame(index=sorted(G.nodes()))
    t["community"] = pd.Series(comm_of)
    t["betweenness"] = pd.Series(nx.betweenness_centrality(G))
    t["closeness"] = pd.Series(nx.closeness_centrality(G))
    if G.is_directed():
        t["in_degree"] = pd.Series(dict(G.in_degree()))
        t["out_degree"] = pd.Series(dict(G.out_degree()))
        hubs, auth = nx.hits(G, max_iter=1000)
        t["hub"], t["authority"] = pd.Series(hubs), pd.Series(auth)
        # Weighted PageRank: a person's score is split over the people they hand
        # work to, in proportion to the weights. Weight(A->B) / all handovers of A
        # = probability that a case goes from A to B, so PageRank ~ share of time
        # a case "spends" with each employee (random walk over the handovers).
        t["pagerank"] = pd.Series(nx.pagerank(G, alpha=0.85, weight="weight"))
    else:
        t["degree"] = pd.Series(dict(G.degree()))
        t["eigenvector"] = pd.Series(nx.eigenvector_centrality_numpy(G, weight="weight"))
    return t.round(4)


def save_for_gephi(G, table, path):
    H = G.copy()
    for col in table.columns:
        nx.set_node_attributes(H, {v: float(x) for v, x in table[col].items()}, col)
    nx.write_gexf(H, path)


# ---------------------------------------------------------------- STEP 4
def qap(G1, G2, n_perm):
    """Correlate the two adjacency matrices, then shuffle the rows+columns of
    one matrix many times to see how often a random relabelling gives a
    correlation as large as the observed one."""
    nodes = sorted(set(G1) | set(G2))
    H1, H2 = G1.copy(), G2.copy()
    H1.add_nodes_from(nodes); H2.add_nodes_from(nodes)
    out = {}
    for kind, w in [("weighted", "weight"), ("binary", None)]:
        A = nx.to_numpy_array(H1, nodelist=nodes, weight=w)
        B = nx.to_numpy_array(H2, nodelist=nodes, weight=w)
        mask = ~np.eye(len(nodes), dtype=bool)
        r_obs = np.corrcoef(A[mask], B[mask])[0, 1]
        hits = 0
        for _ in range(n_perm):
            p = rng.permutation(len(nodes))
            if np.corrcoef(A[mask], B[p][:, p][mask])[0, 1] >= r_obs:
                hits += 1
        out[kind] = (r_obs, (hits + 1) / (n_perm + 1))
    return out


# ---------------------------------------------------------------- STEP 5
def case_handover_pairs():
    """For every case: the set of direct handovers (A -> B, A != B)."""
    ev = EVENTS if EVENTS is not None else load_events()
    pairs, label = {}, {}
    for case, g in ev.groupby(CASE, sort=False):
        r = g[RES].tolist()
        pairs[case] = {(a, b) for a, b in zip(r, r[1:]) if a != b}
        label[case] = g["outcome"].iloc[0]
    return pairs, label


def quick_stats(cases, pairs):
    cnt = Counter(p for c in cases for p in pairs[c])
    G = nx.DiGraph()
    G.add_edges_from(cnt)
    U = G.to_undirected()
    return {"density": nx.density(G), "reciprocity": nx.reciprocity(G),
            "avg_clustering": nx.average_clustering(U),
            "degree_centralisation": degree_centralisation(U)}


def permutation_test(n_perm):
    """Shuffle the outcome labels between cases and rebuild the networks:
    how often is the random difference as large as the real one?"""
    pairs, label = case_handover_pairs()
    cases = list(pairs)
    labs = np.array([label[c] for c in cases])

    def diff(lb):
        a = quick_stats([c for c, l in zip(cases, lb) if l == "approved"], pairs)
        d = quick_stats([c for c, l in zip(cases, lb) if l == "declined"], pairs)
        return {k: a[k] - d[k] for k in a}, a, d

    obs, a, d = diff(labs)
    extreme = Counter()
    for _ in range(n_perm):
        pd_ = diff(rng.permutation(labs))[0]
        for k in obs:
            if abs(pd_[k]) >= abs(obs[k]):
                extreme[k] += 1
    return pd.DataFrame({"approved": a, "declined": d, "difference": obs,
                         "p_value": {k: (extreme[k] + 1) / (n_perm + 1) for k in obs}}).round(4)


# ---------------------------------------------------------------- MAIN
if __name__ == "__main__":
    pd.set_option("display.width", 140)

    print(f"Working-together threshold: {WT_THRESHOLD}")
    print("STEP 1 - loading networks")
    for g in GROUPS:
        print(f"  working-together density by threshold ({g}):", threshold_check(g))
    nets = {}
    for g in GROUPS:
        H, loops = load_handover(g)
        print(f"  handover {g}: {loops} self-loops removed")
        nets[("handover", g)] = H
        nets[("working_together", g)] = load_working_together(g, WT_THRESHOLD)

    print("\nSTEP 2 - whole-network measures")
    summary, tables = {}, {}
    for (kind, g), G in nets.items():
        res, comms = whole_network(G)
        summary[f"{kind}_{g}"] = res
        tables[(kind, g)] = node_measures(G, comms)          # STEP 3
        tables[(kind, g)].to_csv(TABLES / f"nodes_{kind}_{g}{TAG}.csv", index_label="employee")
        save_for_gephi(G, tables[(kind, g)], GEPHI / f"{kind}_{g}{TAG}.gexf")
    summary = pd.DataFrame(summary).round(3)
    summary.to_csv(TABLES / f"network_summary{TAG}.csv")
    print(summary.to_string())

    print("\nSTEP 3 - top 5 employees per network")
    for (kind, g), t in tables.items():
        cols = ["betweenness", "authority", "pagerank", "hub"] if kind == "handover" else ["betweenness", "eigenvector"]
        print(f"\n  {kind} / {g}")
        print(t.sort_values("betweenness", ascending=False)[cols + ["community"]].head(5).to_string())

    print("\nSTEP 4 - QAP: approved vs declined handover networks")
    q = qap(nets[("handover", "approved")], nets[("handover", "declined")], N_QAP)
    for kind, (r, p) in q.items():
        print(f"  {kind:8s}: correlation r = {r:.3f}, p = {p:.4f}")

    print("\nSTEP 5 - permutation test on whole-network measures (handover)")
    perm = permutation_test(N_PERM)
    print(perm.to_string())

    print("\nSTEP 6 - same key people? (Spearman correlation of betweenness)")
    rows = []
    for kind in ["handover", "working_together"]:
        a, d = tables[(kind, "approved")], tables[(kind, "declined")]
        common = a.index.intersection(d.index)
        rho, p = spearmanr(a.loc[common, "betweenness"], d.loc[common, "betweenness"])
        print(f"  {kind:17s}: rho = {rho:.3f}, p = {p:.4f} ({len(common)} employees in both)")
        rows.append({"test": f"spearman_betweenness_{kind}", "value": rho, "p_value": p})

    print("\nSTEP 7 - PageRank vs HITS authority (handover)")
    for g in GROUPS:
        t = tables[("handover", g)]
        rho, p = spearmanr(t["pagerank"], t["authority"])
        top_pr = set(t["pagerank"].nlargest(10).index)
        top_au = set(t["authority"].nlargest(10).index)
        print(f"  {g:8s}: rho = {rho:.3f}, p = {p:.4f}; top-10 overlap = {len(top_pr & top_au)}/10")
        rows.append({"test": f"spearman_pagerank_authority_{g}", "value": rho, "p_value": p})

    tests = [{"test": f"qap_{k}", "value": r, "p_value": p} for k, (r, p) in q.items()]
    tests += [{"test": f"perm_{k}", "value": row.difference, "p_value": row.p_value} for k, row in perm.iterrows()]
    pd.DataFrame(tests + rows).round(4).to_csv(TABLES / f"tests{TAG}.csv", index=False)
    print("\nDone. Tables in results/tables/, Gephi files in results/gephi/")

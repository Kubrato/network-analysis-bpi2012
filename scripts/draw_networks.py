"""Render the Gephi GEXF networks as report figures (approved vs declined side by side)."""
import sys
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

GEXF = sys.argv[1]
OUT = sys.argv[2]

PALETTE = ["#2a6fdb", "#e07a1f", "#2e9e5b", "#c0392b", "#8e44ad", "#7f8c8d", "#b8860b"]
KEY = {"10913", "11180", "10138", "10609", "10629", "11049", "10899", "11259"}


def align_communities(ref, other):
    """Map community ids of `other` onto ids of `ref` by largest overlap, for consistent colours."""
    mapping, used = {}, set()
    groups = {}
    for n, c in other.items():
        groups.setdefault(c, []).append(n)
    for c, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        votes = Counter(ref[n] for n in members if n in ref)
        best = next((k for k, _ in votes.most_common() if k not in used), None)
        if best is None:
            best = max(list(ref.values()) + list(mapping.values())) + 1 + len(mapping)
        mapping[c] = best
        used.add(best)
    return {n: mapping[c] for n, c in other.items()}


def draw(name, size_attr, size_label, key, seed=7):
    Ga = nx.read_gexf(f"{GEXF}/{name}_approved.gexf")
    Gd = nx.read_gexf(f"{GEXF}/{name}_declined.gexf")

    # common layout so that the same employee sits in the same place in both panels
    U = nx.Graph()
    for G in (Ga, Gd):
        for u, v, d in G.edges(data=True):
            w = d.get("weight", 1.0)
            if U.has_edge(u, v):
                U[u][v]["weight"] += w
            else:
                U.add_edge(u, v, weight=w)
    U.add_nodes_from(list(Ga) + list(Gd))
    pos = nx.spring_layout(U, weight="weight", seed=seed, k=0.5, iterations=500)

    comm_a = {n: int(d["community"]) for n, d in Ga.nodes(data=True)}
    comm_d = align_communities(comm_a, {n: int(d["community"]) for n, d in Gd.nodes(data=True)})

    smax = max(max(d[size_attr] for _, d in G.nodes(data=True)) for G in (Ga, Gd))

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    for ax, G, comm, title in ((axes[0], Ga, comm_a, "Approved"), (axes[1], Gd, comm_d, "Declined")):
        ws = [d.get("weight", 1.0) for _, _, d in G.edges(data=True)]
        wmax = max(ws)
        nx.draw_networkx_edges(
            G, pos, ax=ax, edge_color="#9aa3ad",
            width=[0.2 + 1.8 * (w / wmax) for w in ws],
            alpha=0.25, arrows=False,
        )
        nodes = list(G.nodes())
        sizes = [40 + 900 * (G.nodes[n][size_attr] / smax) for n in nodes]
        colors = [PALETTE[comm[n] % len(PALETTE)] for n in nodes]
        nx.draw_networkx_nodes(G, pos, nodelist=nodes, node_size=sizes, node_color=colors,
                               edgecolors="white", linewidths=0.8, ax=ax)
        import math
        cx = sum(p[0] for p in pos.values()) / len(pos); cy = sum(p[1] for p in pos.values()) / len(pos)
        R = 1.0 * max(math.hypot(p[0] - cx, p[1] - cy) for p in pos.values())
        ks = [n for n in key if n in G]
        ang = {n: math.atan2(pos[n][1] - cy, pos[n][0] - cx) for n in ks}
        order = sorted(ks, key=lambda n: ang[n])
        gap = 2 * math.pi / max(len(order), 1) * 0.8
        for i in range(1, len(order)):  # push apart labels that are too close in angle
            if ang[order[i]] - ang[order[i - 1]] < gap:
                ang[order[i]] = ang[order[i - 1]] + gap
        for n in ks:
            tx, ty = cx + R * math.cos(ang[n]), cy + R * math.sin(ang[n])
            ax.annotate(n, pos[n], xytext=(tx, ty), textcoords="data", fontsize=16,
                        family="serif", ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#444", lw=0.6),
                        arrowprops=dict(arrowstyle="-", color="#444", lw=0.7, shrinkA=0, shrinkB=3))
        ax.set_xlim(cx - R * 1.08, cx + R * 1.08); ax.set_ylim(cy - R * 1.08, cy + R * 1.08)
        ax.set_aspect("equal")
        ax.set_title(f"{title} ({G.number_of_nodes()} nodes, {G.number_of_edges()} ties)",
                     fontsize=20, family="serif")
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(f"{OUT}/{name}.pdf", bbox_inches="tight")
    fig.savefig(f"{OUT}/{name}.png", dpi=110, bbox_inches="tight")


draw("handover", "authority", "HITS authority",
     {"10138": (45, 25), "10609": (50, -25), "10629": (45, 55), "10913": (-50, 35), "11180": (-50, -35)})
draw("working_together", "betweenness", "betweenness",
     {"11049": (-55, 40), "10899": (55, -35), "11259": (55, 40), "10138": (-55, -40), "10609": (0, -60)})

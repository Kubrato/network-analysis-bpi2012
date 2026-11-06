# Collaboration Networks in a Loan Application Process (BPI Challenge 2012)

Group project for the **Network Analysis** course (MA Digital Humanities and Digital Knowledge, University of Bologna).

**Group:** Kübra Topçuoğlu, Daria Talanova, Maria Grigoryeva, Aizana Kuular

## Research questions
1. What does the collaboration network of the bank look like (central employees, brokers, groups)?
2. Among applications that reached the final review, do approved and declined applications show different collaboration patterns?

The project builds on van der Aalst & Song (2004), *Mining Social Networks: Uncovering Interaction Patterns in Business Processes*, and its follow-up van der Aalst, Reijers & Song (2005), *Discovering Social Networks from Event Logs*, CSCW 14(6).

## Data
BPI Challenge 2012 event log (loan applications at a Dutch financial institute):
van Dongen, B. (2012). *BPI Challenge 2012*. 4TU.ResearchData. https://doi.org/10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f

The log is included in this repository as `data/raw/BPI_Challenge_2012.xes.gz` (3 MB), so the analysis can be run directly.
It is redistributed for research and teaching purposes; the original dataset, its licence (4TU General Terms of Use) and the official download are at the DOI above. Please cite the original source.
Check: the log contains 13,087 cases, 262,200 events and 68 resources.

Where our copy comes from: the official 4TU page was not available when we downloaded the data, so we took the file from a mirror on the GitLab server of CiTIUS (University of Santiago de Compostela). This is the same address that the Verona process mining library uses to download BPI Challenge 2012:
https://gitlab.citius.usc.es/efren.rama/pmdlcompararator/-/raw/crossvalidation/raw_datasets/BPI_Challenge_2012.xes.gz?ref_type=heads
We checked the file against the official numbers above (cases, events, resources); all matched.
SHA-256 of our file: `0429a18ed3d9dec715ee2e76c36114edfdec059f5bb765aa29458a267e74feac`

## How to run
```bash
pip install -r requirements.txt
python scripts/prepare_final_review.py   # filter the log, build handover networks
python scripts/analyse_networks.py 0.1   # robustness check: working-together threshold 0.1 (files with _wt0.1)
python scripts/analyse_networks.py       # main analysis (threshold 0.2): measures, QAP and permutation tests
```

1. Keep only `COMPLETE` events.
2. Label each application: approved / declined / cancelled.
3. Keep applications that reached the final review step (`W_Valideren aanvraag`, validating the application) and were approved or declined.
4. Remove events without a resource and the system resource `112` (it only records `A_SUBMITTED`, `A_PARTLYSUBMITTED`, `A_PREACCEPTED`).
5. Sample the same number of approved and declined applications (754 each, seed 42).
6. Build two networks per group:
   - **handover of work** (directed): A → B if, in the same case, a task of A is directly followed by a task of B;
   - **working together** (undirected): shared cases / cases of the person (paper, Def. 4.5), symmetrised and thresholded (`WT_THRESHOLD`, default 0.2).
7. Measures: density, reciprocity, components, diameter, path length, clustering, centralisation, modularity, comparison with random graphs (σ); betweenness, closeness, HITS and weighted PageRank (handover; compared with each other), eigenvector centrality (working together).
8. Tests: QAP correlation, label-permutation test on whole-network measures, Spearman correlation of betweenness.

## Repository structure
```
data/raw/            original event log (BPI_Challenge_2012.xes.gz)
data/processed/      filtered events (created by the scripts, not on GitHub)
scripts/             Python scripts
results/edges/       edge lists of the handover networks
results/tables/      network_summary.csv, nodes_*.csv, tests.csv
results/gephi/       .gexf files with node measures and communities (open in Gephi)
report/              report drafts and final PDF
```

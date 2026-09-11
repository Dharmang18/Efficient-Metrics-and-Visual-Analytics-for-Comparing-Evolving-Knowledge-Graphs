# Efficient Metrics and Visual Analytics for Comparing Evolving Knowledge Graphs

Bachelor's thesis (TUM). Compute **metrics over knowledge graphs** — two versions of YAGO and
three of DBpedia — and compare them **across versions and across KGs** in a dashboard. The graphs
are served with **QLever**, the metrics are computed as a mix of **SPARQL + Rust** (mirroring the
Knowgly approach), and results are shown in an interactive **niceGUI** dashboard.

**The five snapshots:** YAGO 4 (2020), YAGO 4.5.0.2 (2024), DBpedia 2015-10, DBpedia 2022.12.01,
DBpedia 2025-12-01. The three DBpedia releases are built from a **matched five-role file subset**
(direct+transitive types, ontology-mapped properties, raw infobox properties, labels, redirects)
so that measured differences are real evolution, not artefacts of which files each release
shipped. See `qlever-workspace/dbpedia-matched/MATCHED_SUBSET.md`.

> Examiner: Prof. Maribel Acosta · Supervisor: M.Sc. Samuel García (TUM)

## Pipeline

```
YAGO / DBpedia index (local, not in repo)
      │  SPARQL
      ▼
QLever  ──►  :9005 YAGO 4 · :9006 YAGO 4.5 · :9008 DBpedia 2015 · :9010 DBpedia 2025
             (all four on the home server) · :7014 DBpedia 2022-matched (TUM VM)
      │  counting queries (GROUP BY / COUNT) + formula in Rust
      ▼
rust_metrics/  (Rust + SPARQL)      # 13 metrics, dictionaries + formulas
      │  writes
      ▼
results/[<label>/]<metric>.{json,csv}
      │  reads
      ▼
dashboard.py  (niceGUI)  ──►  localhost:8080
```

The `<label>` is what makes evolution work: run the same metric against two versions with
different labels, and metric 11 lines the two result sets up and reports the deltas.

## The 13 metrics

All are implemented in `qlever-workspace/rust_metrics/`, one module per metric plus a
subcommand. Run `cargo run --release help` for the full usage.

### Class-level

| # | Metric | Command | Formula |
|---|---|---|---|
| 1 | Class population & share | `population` | `share(t) = \|E_t\| / \|E\|` |
| 2 | Property entropy per type | `entf` | `EntF(p,t) = −Σ P(o) log2 P(o)` |
| 3 | Entropy-weighted type importance | `entetimp` | `EntF^w · ETImp^(1−w)`, w = 0.75 |
| 4 | Class entropy | `classentropy` | `H(t)` over all object values of the class |

### Entity-level

| # | Metric | Command | Formula |
|---|---|---|---|
| 5 | Entity informativeness | `inforank` | `IR(v) = dtp(v) / Σ dtp(u)` |
| 6 | Object diversity | `diversity` | `OD(p,t) = ` distinct objects of p in t |

### Global

| # | Metric | Command | Formula |
|---|---|---|---|
| 7 | **Entropy-weighted PageRank** (own variant) | `entropy-pagerank` | `PR(v) = (1−d) + d·Σ w(p)·PR(u)/outdeg(u)` |
| 8 | Graph size & shape | `shape` | `density = \|T\|/\|E\|` |
| 9 | Class-level churn | `churn` | `(\|A_t\|+\|D_t\|) / \|T_t(v1)\|` |
| 10 | Triple diff, integer-encoded | `diff` | `Added = T2−T1`, … |
| 11 | Metric trajectories | `trajectories` | `Δm(v_i) = m(v_i+1) − m(v_i)` |
| 12 | Vocabulary / schema evolution | `vocab` | `C_added = C2−C1`, … |
| 13 | Cross-KG class comparison | `crosskg` | `Δm(t) = m_A(t) − m_B(t)` |

`etimp` and `pagerank` are also available — those are the **provided Knowgly baselines**, not
thesis contributions. Metric 7 is the thesis's own variant: PageRank in which each edge is
weighted by the property entropy of its predicate, so rank flows preferentially through
informative predicates.

## Repository layout

```
qlever-workspace/
  rust_metrics/              # THE METRICS (Rust + SPARQL, mirrors Knowgly)
    src/qlever_client.rs     #   SPARQL client — supports two endpoints at once
    src/common.rs            #   shared queries + the entropy helpers
    src/out.rs               #   results/[<label>/]<metric>.{json,csv}
    src/<metric>.rs          #   one module per metric (13 + 2 baselines)
    src/main.rs              #   subcommand dispatch — `help` lists everything
  dashboard.py               # niceGUI dashboard (reads the results JSON)
  sparql.py                  # small Python SPARQL helper (reference)
  Qleverfiles/               # QLever recipes (yago-4, dbpedia, olympics)
  RUNBOOK.md                 # start/stop/query commands
docs/                        # metrics list + PDF generators
Thesis_Setup_Explained.pdf   # written explanation of the whole setup
```

> **Not in the repo**: the Python `.venv/`, the Rust `target/` and the generated `results/`
> are git-ignored, as is the TUM VPN profile (`vpn/`). The bulk data now lives OUTSIDE the
> thesis folder entirely (moved 2026-09-09): the 39 GB YAGO 4.5.0.2 index at `~/yago/`, the
> 3.9 GB of downloaded DBpedia parts at `~/dbpedia/rdf-input/`, and the Knowgly reference
> clone at `~/reference/`. The small files that let anyone rebuild the DBpedia index —
> `Qleverfile`, `download.sh`, `rdf-input.urls`, `DATASET.md` — stay tracked in the repo.

## Quick start

```bash
# 1. Serve a graph (or point at one that is already running)
export PATH="$HOME/.local/bin:$PATH"
colima start
cd ~/yago && qlever --qleverfile Qleverfile start   # -> :9004

# 2. Compute metrics (Rust + SPARQL) -> writes results/
source "$HOME/.cargo/env"
cd ../rust_metrics
export QLEVER_ENDPOINT=http://localhost:9004
export QLEVER_LABEL=yago-4.5.0.2          # names this snapshot
cargo run --release all 8                 # every single-endpoint metric, top-8 classes

# 3. Compare two versions (needs a second endpoint)
export QLEVER_ENDPOINT_B=http://localhost:9005
cargo run --release diff 'http://schema.org/Person' 5000
cargo run --release trajectories graph_shape yago-4 yago-4.5.0.2

# 4. Launch the dashboard
cd .. && source .venv/bin/activate
python dashboard.py                       # open http://localhost:8080
```

No local index? Every metric runs against a public endpoint too:

```bash
export QLEVER_ENDPOINT=https://qlever.dev/api/olympics
cargo run --release all 5
```

## Notes on the implementation

- **Entropy is computed from a count-of-counts histogram.** Entropy depends only on the multiset
  of counts, so a nested `GROUP BY` has QLever fold millions of object values into a few hundred
  rows. The result is exact, not sampled.
- **The triple diff uses a subject window,** not `ORDER BY ?s ?p ?o LIMIT n` — the latter makes
  the server sort the entire graph. It takes the lexicographically first *n* subjects of each
  version, cuts both at the smaller bound, and fetches those subjects' triples by name. Exact
  inside the window, and no global sort. Scope metrics 9 and 10 to a class.
- **Metric 10 compares two versions of one KG,** not two different KGs: YAGO and DBpedia have
  disjoint subject IRIs, so a triple diff between them is meaningless. Metric 13 does that job.
- The diff benchmark runs the integer-encoded and naive string paths and asserts they agree.
  Measured on real data: **5.7–6.0× faster, 16.5× less memory.**

## The dashboard (niceGUI)

`dashboard.py` reads the pre-computed JSON — no SPARQL runs at view time, so the page is instant.
It shows, for any entity type, a type dropdown and Top-N selector, an interactive ECharts bar
chart of the most characteristic predicates, and a full ranked table.

```bash
source qlever-workspace/.venv/bin/activate
cd qlever-workspace && python dashboard.py      # http://localhost:8080
```

The JSON is loaded once at startup — re-run a metric and **restart the dashboard** to see new
data. All **13 metrics** are wired in (2026-09-11), grouped into three phase tabs mirroring
`run_phase.sh`: Phase 1 class-level (population, entf, entetimp, classentropy) reads
`results/<label>/`; Phase 2 entity-level (inforank, diversity) does the same; Phase 3 global
metrics mix single-snapshot (entropy-pagerank, shape) and two-endpoint comparisons (churn,
diff, vocab, crosskg) read from `results/<pair>/`, plus trajectories (metric 11) read from
`results/<evolution>/`. Each tab opens with the metric's name, a one-line explanation and its
formula, then charts and a table. Chart type follows the data shape rather than forcing every
metric into the same mold — grouped bars for class/predicate comparisons, small-multiple bars
for per-snapshot rankings (inforank, pagerank, shape), stacked bars for churn, donuts for
diff/vocab proportions, and line charts for trajectories.

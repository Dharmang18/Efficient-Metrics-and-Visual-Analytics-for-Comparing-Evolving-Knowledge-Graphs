# Knowledge-Graph Metrics over YAGO (Bachelor's Thesis)

Compute **metrics over a knowledge graph** (YAGO 4.5) and visualize them in a dashboard.
The knowledge graph is served locally with **QLever**, metrics are computed as a mix of
**SPARQL + Rust** (mirroring the Knowgly approach), and results are shown in an interactive
**niceGUI** dashboard.

> Advisor: Samuel García (TUM)

## Pipeline

```
YAGO 4.5 index (local, not in repo)
      │  SPARQL
      ▼
QLever  ──►  localhost:9004        # SPARQL endpoint
      │  per-type COUNT queries + formula
      ▼
rust_metrics/  (Rust + SPARQL)     # computes the metric into dictionaries
      │  writes
      ▼
results/entity_type_importance.{json,csv}
      │  reads
      ▼
dashboard.py  (niceGUI)  ──►  localhost:8080   # interactive charts
```

## Repository layout

```
qlever-workspace/
  rust_metrics/            # THE METRICS (Rust + SPARQL, mirrors Knowgly)
    src/qlever_client.rs   #   SPARQL endpoint client
    src/common.rs          #   reusable queries (types, |E_t|)
    src/entity_type_importance.rs   # the metric: ETImp(p,t) = EF_p * log2(|E_t| / EF_p)
    src/main.rs            #   runs it, writes results/*.json + *.csv
  dashboard.py             # niceGUI dashboard (reads the results JSON)
  sparql.py                # small Python SPARQL helper (reference / future use)
  metrics_examples.py      # Python example metrics (reference)
  Qleverfiles/             # QLever recipes (yago-4, dbpedia, olympics)
  RUNBOOK.md               # full start/stop/query/metrics commands
Thesis_Setup_Explained.pdf # written explanation of the whole setup
```

> **Not in the repo:** the 41 GB YAGO index (`qlever-workspace/yago/`), the Python `.venv/`,
> and the Rust `target/` build dir — all git-ignored. See below for how to obtain the index.

## Prerequisites

- **The YAGO 4.5.0.2 QLever index** (pre-built, ~41 GB) placed in `qlever-workspace/yago/`.
- **A Docker engine** to run QLever (this project uses Colima, installed user-space).
- **Rust** (`rustup`) and **Python 3.12** (a `.venv` with `qlever`, `requests`, `nicegui`).

Full, copy-paste setup and run commands are in [`qlever-workspace/RUNBOOK.md`](qlever-workspace/RUNBOOK.md).

## Quick start

```bash
# 1. Start the QLever engine + server (serves localhost:9004)
export PATH="$HOME/.local/bin:$PATH"
colima start
cd qlever-workspace/yago && qlever --qleverfile Qleverfile start

# 2. Compute the metric (Rust + SPARQL) -> writes results/
source "$HOME/.cargo/env"
cd ../rust_metrics
export QLEVER_ENDPOINT=http://localhost:9004
cargo run --release 10        # top 10 most-populated types

# 3. Launch the dashboard
cd ..
source .venv/bin/activate
python dashboard.py            # open http://localhost:8080
```

## The metric: Entity Type Importance

For each entity type `t` and predicate `p`:

```
ETImp(p, t) = EF_p(p, t) * log2( |E_t| / EF_p(p, t) )
  EF_p(p,t) = # distinct entities of type t that use predicate p   (SPARQL COUNT DISTINCT)
  |E_t|     = # distinct entities of type t
```

A TF-IDF for predicates: properties everyone has (e.g. `rdf:type`) score ~0; characteristic
properties (e.g. `birthDate` for Person, `radialVelocity` for Star) score high.

## The dashboard (niceGUI)

`dashboard.py` is a [niceGUI](https://nicegui.io) web app that visualizes the metric. It reads the
Rust metric's `rust_metrics/results/entity_type_importance.json` — **no SPARQL runs at view time**,
it just reads the pre-computed JSON, so the page is instant.

```bash
source qlever-workspace/.venv/bin/activate
cd qlever-workspace
python dashboard.py        # open http://localhost:8080
```

It shows, for any entity type:

- a **type dropdown** and a **Top-N selector** (3–40 predicates);
- an interactive **horizontal bar chart** (ECharts) of that type's most characteristic predicates,
  ranked by ETImp score, with the value labelled on each bar;
- a **full ranked, paginated table** of every predicate for that type.

IRIs are trimmed to their readable last segment (e.g. `…#birthDate` → `birthDate`). The JSON is
loaded once at startup, so re-run the Rust metric and **restart the dashboard** to see new data.
If it reports "No results found", generate the data first (step 2 of the quick start).

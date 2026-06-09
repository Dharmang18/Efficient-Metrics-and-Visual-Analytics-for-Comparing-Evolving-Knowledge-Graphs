# QLever + YAGO local setup — runbook

Local SPARQL endpoint serving the pre-built **YAGO 4.5.0.2** index (~1.3B triples).

## Locations
- Workspace: `~/thesis/qlever-workspace`  (moved OFF the iCloud-synced Desktop on purpose — do NOT move it back to Desktop/Documents, iCloud will corrupt it)
- Index:     `~/thesis/qlever-workspace/yago`  (~41.6 GB, 28 files)
- Python venv: `~/thesis/qlever-workspace/.venv`  (Python 3.12)
- Engine tools (no sudo, user-space): `~/.local/bin/{colima,limactl,docker}`
- Endpoint:  http://localhost:9004   |  Access token: `yago-4.5.0.2`

## Every session: set up the shell
```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/thesis/qlever-workspace/.venv/bin/activate
```

## Start everything (e.g. after a reboot)
```bash
colima start                              # boots the Docker VM (remembers 4 CPU / 10G / 80G)
cd ~/thesis/qlever-workspace/yago
qlever --qleverfile Qleverfile start      # serves localhost:9004 (auto-skips indexing, index already exists)
```
The container is `--restart=unless-stopped`, so once Colima is up it comes back on its own too.

## Check / stop
```bash
docker ps                                 # should show qlever.server.yago-4.5.0.2, port 9004
qlever --qleverfile Qleverfile stop       # stop the QLever server
colima stop                               # stop the whole Docker VM (frees RAM)
```

## Metrics — Rust + SPARQL (the thesis implementation)
The metrics are implemented the Knowgly way: **SPARQL does the counting, Rust holds the
dictionaries (HashMaps) and applies the formula.** Project: `rust_metrics/`.
```bash
source "$HOME/.cargo/env"                  # put cargo/rustc on PATH
cd ~/thesis/qlever-workspace/rust_metrics
export QLEVER_ENDPOINT=http://localhost:9004
cargo run --release 8                      # Entity Type Importance for the top 8 types
# (the number is how many of the most-populated types to compute; default 10)
```
Layout (mirrors Knowgly):
- `src/qlever_client.rs` — global SPARQL endpoint + `query()` (reads results via a streaming
  reader, so large result sets are fine).
- `src/common.rs` — reusable queries (`fetch_top_type_iris`, `entity_count_per_type`).
- `src/entity_type_importance.rs` — the metric: `ETImp(p,t) = EF_p(p,t) * log2(|E_t| / EF_p(p,t))`,
  per-type SPARQL `GROUP BY` queries run in parallel (rayon), results in nested HashMaps.
- `src/main.rs` — runs the metric and writes `results/entity_type_importance.json` + `.csv`
  (the JSON is what the dashboard reads).

## Dashboard — niceGUI (the visualization)
`dashboard.py` reads the Rust metric's `results/entity_type_importance.json` and charts it in the
browser. It runs **no SPARQL at view time** — it just reads the pre-computed JSON, so it's instant.
```bash
source ~/thesis/qlever-workspace/.venv/bin/activate
cd ~/thesis/qlever-workspace
python dashboard.py                        # then open http://localhost:8080
```
What it shows:
- A **type dropdown** + a **Top-N selector** (3–40).
- An interactive **horizontal bar chart** (ECharts) of the selected type's most characteristic
  predicates, ranked by ETImp score.
- A **full ranked, paginated table** of every predicate for that type.

Notes:
- The JSON is loaded **once at startup**, so after re-running the Rust metric, restart `dashboard.py`
  to pick up the new data.
- IRIs are shown trimmed to their readable last segment (e.g. `…#birthDate` → `birthDate`).
- If it shows "No results found", run the Rust metric first (above) to generate `results/`.

## (Optional) quick Python querying
The Python files `sparql.py` / `metrics_examples.py` are a lightweight SPARQL reference for quick
checks. Not the thesis metric implementation (that's Rust, above) nor the dashboard.
```bash
export QLEVER_ENDPOINT=http://localhost:9004
python metrics_examples.py
```

## Web UI (browser query interface)
- Open **http://localhost:8176/yago-4** — full QLever UI (autocomplete + result tables), its `yago-4` backend is repointed to your local `localhost:9004`.
- Note: `http://localhost:9004` itself is the raw SPARQL **API**, not a web page — visiting it bare shows "Unknown path". That's normal; it answers queries, e.g. `localhost:9004/?query=<urlencoded SPARQL>`.
- Restarting the UI later: `qlever --qleverfile Qleverfile ui`. If its yago-4 backend resets to the public URL, repoint it:
  `docker exec -i qlever.ui.yago-4.5.0.2 bash -c "python manage.py shell -c \"from backend.models import Backend; Backend.objects.filter(slug='yago-4').update(baseUrl='http://localhost:9004')\""`

## Quick curl sanity check
```bash
curl -s localhost:9004 --data-urlencode 'query=SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }' \
     -H 'Accept: application/sparql-results+json'
```

## Notes / gotchas
- Engine image is PINNED to `adfreiburg/qlever:commit-e5f6724` (the exact build that made this index). Do not switch to `:latest` — a newer build may reject this 2024-format index.
- MEMORY_FOR_QUERIES is 5G (VM has ~10G). Heavy queries may be slow because the 41 GB index is memory-mapped over a virtiofs mount on a 16 GB laptop. That's expected.
- If you ever want max speed, the native macOS QLever package avoids the container penalty — but then you can't pin to the index's exact build as easily.

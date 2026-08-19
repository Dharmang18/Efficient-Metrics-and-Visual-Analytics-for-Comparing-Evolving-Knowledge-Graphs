# CLAUDE.md — Thesis project guide

Bachelor thesis (TUM): **"Efficient Metrics and Visual Analytics for Comparing Evolving
Knowledge Graphs"** — Dharmang Pambhar. Examiner Prof. Maribel Acosta, supervisor
M.Sc. Samuel García. Timeline: June–September 2026.

> Volatile state lives in the auto-memory (`thesis-kg-metrics.md`), which every session
> loads. This file holds the stable facts. (An earlier `docs/SESSION_STATE.md` was
> deliberately deleted — don't recreate it.)

## What the thesis does

Compute metrics over multiple versions of multiple KGs (YAGO 4 + YAGO 4.5, DBpedia later)
and compare them across versions/KGs in a dashboard. Pattern (from Knowgly): **SPARQL does
the counting → Rust holds dictionaries and applies the formula → niceGUI visualizes.**

**Status: all 13 metrics are implemented in Rust** (2026-08-19) and verified against live
endpoints. What is left is wiring them into the dashboard and running them on real
second versions. See "The metrics" below.

- Final metric list (13 metrics, 3 proposal levels): `docs/metrics_final.pdf` —
  **source of truth is the generator** `docs/make_metrics_visual_pdf.py` (rerun to
  regenerate; `docs/metrics_final.md` is a stale older draft). Metric 7 =
  **Entropy-weighted PageRank**, Dharmang's own variant (edge weight = normalized EntF
  of the predicate), compared across versions/KGs; novelty pending Samuel's check.
- ETImp and classic PageRank are **provided baselines** (from Knowgly), NOT thesis
  contributions. Exposé PDF: in `~/Downloads/`.

## The three machines

| Machine | Role | Details |
|---|---|---|
| MacBook Air (this one) | client: Rust metrics + dashboard | 16 GB RAM, limited disk |
| Windows laptop `dharmang128` | QLever KG server (home) | WSL2 Ubuntu, 1 TB ext4, 16 GB RAM |
| TUM VM `cdevm2` | QLever KG server (university) | Ubuntu 24.04, 6 CPU, 8 GB RAM, ~86 GB disk |

### Windows laptop (home server)

- Connected via **Tailscale**: server `100.113.106.12`, Mac `100.123.31.73`.
- SSH: `ssh dharmang@100.113.106.12` (WSL password; **no passwordless sudo** — for sudo
  steps give Dharmang a `! ssh -t ...` one-liner to run himself).
- Server endpoints: YAGO 4.5.0.2 on **:9004** (image pinned `adfreiburg/qlever:commit-e5f6724`,
  never `:latest` for this index), YAGO 4 (2020) on **:9005** once indexed.
- Server paths: indexes in `~/qlever/<name>/` (ext4 only, NEVER `/mnt/c|d`),
  qlever CLI venv at `~/qlever/.venv`. Docker auto-starts via `/etc/wsl.conf`.
- The Windows laptop sleeps → if Tailscale shows it offline, Dharmang must wake it.

### TUM VM (university server, from Samuel, set up 2026-07-10)

- **131.159.130.53**, reachable ONLY over the CIT VPN: Tunnelblick on the Mac,
  profile `~/thesis/vpn/vpn-cde-standard.ovpn`. VPN/VM login is the **CIT account
  `pamd`** — its password is NOT the TUMonline (`ge84tid`) one; reset at
  https://ucentral.in.tum.de/cgi-bin/activate.cgi if lost.
- SSH: `ssh pamd@131.159.130.53` (passwordless via the Mac's ed25519 key).
- **No sudo, no Docker** → QLever runs as the **native engine, user-space install**:
  `qlever-bin` deb (+ 4 lib debs) extracted into `~/opt/qlever-engine`;
  PATH/LD_LIBRARY_PATH exported at the TOP of `~/.bashrc` (above the interactive
  guard); `~/.local/bin/unzip` is a python-zipfile shim. Qleverfiles here need
  `SYSTEM = native`.
- qlever CLI venv: `~/qlever/.venv` (alias `qenv`). Verified end-to-end with the
  olympics dataset (port 7019, stopped; files kept in `~/qlever/olympics`).
- Sizing: fits the 39 GB YAGO 4.5 index; a fresh YAGO-4 build (~110 GB peak) does
  NOT fit — build big indexes on the Windows server, or ask Samuel (he offers to
  host indexes on the group server and to run RAM-heavy metrics). His SharePoint
  trick: stash index zips on tumde-my.sharepoint.com, pull on demand.

## Local layout (Mac)

```
~/thesis/
  qlever-workspace/        # main workspace (NOT under Desktop/Documents — iCloud corrupts!)
    .venv/                 # Python 3.12 (nicegui, reportlab; NO matplotlib)
    yago/                  # local 41.6 GB YAGO 4.5.0.2 index (backup copy, still serving)
    rust_metrics/          # cargo project: ETImp + PageRank (+ future metrics)
    dashboard.py           # niceGUI dashboard -> http://localhost:8080
    sparql.py              # small Python SPARQL client (QLEVER_ENDPOINT env var)
    RUNBOOK.md             # local Colima/QLever serving runbook
  docs/                    # metrics docs, PDF generators, server runbooks
  vpn/                     # TUM CIT OpenVPN profile (vpn-cde-standard.ovpn)
  reference/Knowgly/       # cloned reference repo (Java) — understand, don't copy (git-ignored)
```

`rust_metrics/results/` is git-ignored — regenerate it, never commit it.

## Key commands

```bash
# local QLever (fallback; primary serving is the Windows server)
export PATH="$HOME/.local/bin:$PATH"      # colima/limactl/docker live here (no Homebrew!)
colima start && cd ~/thesis/qlever-workspace/yago && qlever --qleverfile Qleverfile start

# metrics — see `cargo run --release help` for the full list
source "$HOME/.cargo/env" && cd ~/thesis/qlever-workspace/rust_metrics
export QLEVER_ENDPOINT=http://localhost:9004      # or http://100.113.106.12:9004
export QLEVER_LABEL=yago-4.5.0.2                  # -> results/<label>/, metric 11 reads these
cargo run --release all 8        # every single-endpoint metric (1-8), top-8 classes
cargo run --release entf 8 10    # one metric: property entropy, 8 classes x 10 predicates
cargo run --release entropy-pagerank 200000       # metric 7 — the thesis's own variant

# cross-version / cross-KG metrics need a SECOND endpoint
export QLEVER_ENDPOINT_B=http://100.113.106.12:9005
cargo run --release diff 'http://schema.org/Person' 5000   # metric 10 — ALWAYS scope to a class
cargo run --release churn 8 5000                           # metric 9
cargo run --release crosskg person 40                      # metric 13
cargo run --release trajectories graph_shape yago-4 yago-4.5.0.2   # metric 11

# TUM VM (VPN must be connected first: Tunnelblick menu-bar icon -> vpn-cde-standard)
ssh pamd@131.159.130.53                   # engine + venv on PATH via .bashrc
# on the VM: qenv && cd ~/qlever/<name> && qlever start   (Qleverfile: SYSTEM = native)

# dashboard
source ~/thesis/qlever-workspace/.venv/bin/activate
cd ~/thesis/qlever-workspace && python dashboard.py     # -> :8080, reads results/ JSONs

# PDFs
cd ~/thesis/docs && python make_metrics_visual_pdf.py   # metrics_final.pdf (illustrated)
python md_to_pdf.py <in.md> <out.pdf>                   # plain md->pdf (no tables/italics)
```

## The metrics (rust_metrics/, ~2350 lines, 19 modules)

One module per metric plus a subcommand in `main.rs`. Baselines (`etimp`, `pagerank`) are
Knowgly's, not thesis contributions.

| # | Command | Module |
|---|---|---|
| 1 | `population` | class_population.rs |
| 2 | `entf` | property_entropy.rs |
| 3 | `entetimp` | ent_etimp.rs |
| 4 | `classentropy` | class_entropy.rs |
| 5 | `inforank` | entity_informativeness.rs |
| 6 | `diversity` | object_diversity.rs |
| 7 | `entropy-pagerank` | entropy_pagerank.rs ← **own variant** |
| 8 | `shape` | graph_shape.rs |
| 9 | `churn` | class_churn.rs |
| 10 | `diff` | triple_diff.rs |
| 11 | `trajectories` | trajectories.rs |
| 12 | `vocab` | vocab_evolution.rs |
| 13 | `crosskg` | cross_kg.rs |

Env contract: `QLEVER_ENDPOINT` (graph to measure), `QLEVER_ENDPOINT_B` (second graph, for
9/10/12/13), `QLEVER_LABEL` (names the snapshot → `results/<label>/`, which is exactly what
metric 11 reads back). Every metric writes `<dir>/<metric>.{json,csv}`.

### Design decisions — do not undo these

1. **Entropy comes from a count-of-counts histogram**, never from streaming object values.
   Entropy depends only on the multiset of counts, so a nested `GROUP BY` folds millions of
   values into a few hundred rows: `H = log2 N − (1/N) Σ m_c·c·log2 c`. Exact, not sampled.
2. **`COUNT(*)` not `COUNT(DISTINCT ?s)`** when grouping `?s a ?type` — set semantics makes
   `(s,type)` unique so the counts are identical, and DISTINCT only buys a sort (~1.6× slower,
   measured on YAGO).
3. **Metric 10 uses a subject window, not `ORDER BY ?s ?p ?o LIMIT n`.** The latter makes the
   server sort the whole graph — QLever asked for 12.7 GB on dblp and refused. The window takes
   the lexicographically first *n* subjects from each side, cuts both at the smaller bound, and
   fetches their triples by `VALUES` in batches of 1000. Exact inside the window, no global sort.
   **Consequence: always scope metrics 9 and 10 to a class**; whole-graph windows are infeasible
   on large graphs and the code says so with the command to use instead.
4. **Metric 10 is cross-VERSION only.** YAGO and DBpedia have disjoint subject IRIs, so the
   window lands inside one graph and reports everything as "added" — right arithmetic, no
   meaning. The code warns; metric 13 is the tool for two different KGs.
5. The benchmark in metric 10 runs **both** the integer and naive paths and `assert_eq`s that
   they agree, so the speedup number can never drift away from being correct
   (measured 5.7–6.0× faster, 16.5× less memory).

## Hard-won gotchas (do not re-learn these)

1. **iCloud**: `~/Desktop` & `~/Documents` are synced — they corrupted a venv once.
   Keep everything under `~/thesis/`.
2. **No Docker Desktop / Homebrew / sudo on the Mac** — user-space Colima only.
3. QLever engine is Linux-only; the `qlever` pip package is just the controller.
4. macOS `unzip`/Python 3.9 mishandle large Zip64 archives.
5. ureq `into_string()` silently truncates at 10 MB — always use `into_reader()`.
6. WSL DNS on the server was broken (fec0:: nameservers) — fixed with static
   resolv.conf 1.1.1.1/8.8.8.8 + `generateResolvConf = false`. Don't re-debug.
7. yago-knowledge.org supports HTTP resume; `qlever get-data` is safe to re-run.
8. Colima occasionally dies on the Mac — `colima start` brings the container back
   automatically (`--restart=unless-stopped`).
9. The machines' Claude sessions can't talk — coordinate via files/docs that
   Dharmang relays (like `~/Downloads/MAC_CLIENT_SETUP.md` came FROM the Windows side).
10. **CIT password ≠ TUMonline password.** VPN/VM want the CIT one (`pamd`); TUM
    portal/email/SharePoint want `ge84tid`. This cost an afternoon once.
11. On the TUM VM, env exports must sit at the TOP of `~/.bashrc` — Ubuntu's
    interactive-guard `return`s early, so lines appended at the bottom are invisible
    to non-interactive SSH commands.
12. No root needed for the QLever engine on Ubuntu: `apt-get download` + `dpkg -x`
    into `~/opt` + `LD_LIBRARY_PATH` works fine (done on the TUM VM).
13. **The public QLever host moved to `qlever.dev`** — `qlever.cs.uni-freiburg.de` now
    308-redirects, and `sparql.py` still has the old URL. Public datasets usable for testing
    without any local server: `/api/yago-4`, `/api/dbpedia`, `/api/olympics`, `/api/dblp`.
14. That public server caps query memory (~770 MB–10 GB) and is shared, so the biggest classes
    (`schema:Thing`, 66 M entities) fail there. Not our bug — they run on our own servers
    (`MEMORY_FOR_QUERIES=5G`).
15. QLever reports *why* a query failed in the JSON body (`exception`), not in the status code.
    The client digs it out — never swallow it, it is the difference between a one-line fix and
    an afternoon.
16. A failed query must **abort loudly**. An empty dictionary looks exactly like a real answer,
    and a metric computed from nothing is worse than no metric at all.
17. `reference/` (the Knowgly clone, has its own `.git`) and `vpn/` (TUM CIT profile) are
    git-ignored: **the GitHub repo is public.**

## Conventions

- New metrics go into `rust_metrics/src/` as their own module + a subcommand in
  `main.rs`, writing `results/<metric>.{json,csv}`; the dashboard reads the JSON at
  startup (restart to refresh). Mirror the existing module style.
- Docs that Samuel sees: simple, minimal, no internal jargon; generate PDFs from the
  scripts in `docs/`.
- Update the auto-memory (`thesis-kg-metrics.md`) before ending a session.

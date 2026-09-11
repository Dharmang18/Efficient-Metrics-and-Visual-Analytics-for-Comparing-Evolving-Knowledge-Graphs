# CLAUDE.md — Thesis project guide

Bachelor thesis (TUM): **"Efficient Metrics and Visual Analytics for Comparing Evolving
Knowledge Graphs"** — Dharmang Pambhar. Examiner Prof. Maribel Acosta, supervisor
M.Sc. Samuel García. Timeline: June–September 2026.

> Volatile state lives in the auto-memory (`thesis-kg-metrics.md`), which every session
> loads. This file holds the stable facts. (An earlier `docs/SESSION_STATE.md` was
> deliberately deleted — don't recreate it.)

## What the thesis does

Compute metrics over multiple versions of multiple KGs and compare them across
versions/KGs in a dashboard. Pattern (from Knowgly): **SPARQL does the counting → Rust
holds dictionaries and applies the formula → niceGUI visualizes.**

**Five snapshots** (2026-08-27): YAGO 4 (2020) and YAGO 4.5.0.2 (2024) give within-KG
evolution for YAGO; DBpedia **2015-10 / 2022.12.01 / 2025-12-01** give a decade of
within-KG evolution for DBpedia; and any YAGO-vs-DBpedia pair gives cross-KG comparison.
The three DBpedia releases are built from a **matched five-role file subset** so that
metric 10/12 differences are real, not artefacts of which files each release shipped —
see `qlever-workspace/dbpedia-matched/MATCHED_SUBSET.md`. Note the snapshots are not
date-aligned (YAGO 4.5 = 2024, DBpedia core = 2022), which the cross-KG chapter states.

**Status: all 13 metrics are implemented in Rust** (2026-08-19) and verified against live
endpoints. The dashboard is rebuilt metric-first for phase-1 results across snapshots
(2026-08-26). **Phases 1–3 are now complete across all five snapshots** (2026-09-11): DBpedia
2015 + 2025 are indexed and serving on the home server, the DBpedia trajectory series covers
the full 2015→2022→2025 decade (metric 11 originally skipped the 2022 point — fixed), and
metric 13 (crosskg) auto-matched 8 shared classes between YAGO 4.5.0.2 and DBpedia 2025, not
just Person. What's left is the Chapter 4 write-up (`writing/include/experiment.tex` is still
an outline with the numbers to cite, not finished prose). See "The metrics" below.

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

### Which snapshot is served where (2026-08-27)

| snapshot | machine | port | triples |
|---|---|---|---|
| YAGO 4 (2020) | home server | 9005 | 2,489,858,800 |
| YAGO 4.5.0.2 | home server (+ 39 GB backup on the Mac) | 9006 | 1,305,431,407 |
| DBpedia 2022 — full `latest-core` (86 files) | TUM VM | 7013 | 526,462,483 |
| DBpedia 2022 — **matched** subset | TUM VM | 7014 | 237,155,678 |
| DBpedia 2015-10 — matched | home server | 9008 | 169,621,442 |
| DBpedia 2025-12-01 — matched | home server | 9010 | 347,497,387 |

The full 2022 index (`:7013`) is a cross-check, NOT one of the five compared snapshots.
16 GB RAM means the home server serves at most two endpoints at once — fine, since every
cross-version/cross-KG metric needs exactly two.

### Windows laptop (home server)

- Connected via **Tailscale**: server `100.113.106.12`, Mac `100.123.31.73`.
- SSH is currently **BROKEN** (2026-08-27): port 22 is now answered by *Windows* OpenSSH,
  not WSL's sshd, so the Mac's key is rejected (the key lives in WSL's `authorized_keys`,
  which Windows sshd does not read). The old `ssh dharmang@100.113.106.12` no longer works.
  The QLever endpoints on :9005/:9006 are unaffected. **Fix (needs Dharmang at the laptop):**
  add the Mac key to the Windows account — standard account →
  `%USERPROFILE%\.ssh\authorized_keys`, admin account →
  `C:\ProgramData\ssh\administrators_authorized_keys` (then restrict its ACL). SSH auth is
  the **Windows account password**, NOT the Windows Hello PIN and NOT the old WSL password.
  Once in Windows, run WSL work via `wsl -d Ubuntu -- bash -lc '...'`.
- Server endpoints: YAGO 4.5.0.2 on **:9006** (image pinned `adfreiburg/qlever:commit-e5f6724`,
  never `:latest` for this index — moved off :9004 because a stale Windows port-proxy
  intercepts :9004 from outside the box), YAGO 4 (2020) on **:9005**.
- Server paths: indexes in `~/qlever/<name>/` (ext4 only, NEVER `/mnt/c|d`),
  qlever CLI venv at `~/qlever/.venv`. Docker auto-starts via `/etc/wsl.conf`.
- The Windows laptop sleeps → if Tailscale shows it offline, Dharmang must wake it.
- **The Windows laptop can now also act as a client** (2026-09-11), not just a QLever server:
  OpenVPN (`OpenVPNTechnologies.OpenVPN` via winget) is installed with the TUM CDE profile in
  `C:\Program Files\OpenVPN\config\vpn-cde-windows.ovpn`, giving it direct access to the TUM VM
  (`131.159.130.53`) — login is the CIT account `pamd`, same as the Mac. A Rust toolchain is also
  installed here (`rustup`, host default set to **`stable-x86_64-pc-windows-gnu`** — the MSVC
  host toolchain fails to link because Git Bash's `/usr/bin/link` shadows MSVC's `link.exe`, and
  no Visual Studio Build Tools are installed; MinGW-w64 GCC came from winget package
  `BrechtSanders.WinLibs.POSIX.UCRT`). This means `rust_metrics` can now be built and run
  directly on the home server, which is how phases 1-3 were completed and how the DBpedia
  trajectory gap got fixed — no dependency on the Mac or working SSH into this laptop.

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
    rust_metrics/          # cargo project: ETImp + PageRank (+ future metrics)
    dashboard.py           # niceGUI dashboard -> http://localhost:8080
    sparql.py              # small Python SPARQL client (QLEVER_ENDPOINT env var)
    RUNBOOK.md             # local Colima/QLever serving runbook
  docs/                    # metrics docs, PDF generators, server runbooks
  vpn/                     # TUM CIT OpenVPN profile (git-ignored)
  writing/                 # THE THESIS DOCUMENT (LaTeX, TUM tumthesis class)

~/                         # BULK DATA — moved out of the thesis folder 2026-09-09
  yago/                    # 39 GB YAGO 4.5.0.2 index (backup copy; serve with `cd ~/yago`)
  dbpedia/rdf-input/       # 3.9 GB DBpedia latest-core parts, 86 .ttl.bz2 (not indexed)
  reference/Knowgly/       # cloned reference repo (Java) — understand, don't copy
```

`rust_metrics/results/` is git-ignored — regenerate it, never commit it.

## Key commands

```bash
# local QLever (fallback; primary serving is the Windows server)
export PATH="$HOME/.local/bin:$PATH"      # colima/limactl/docker live here (no Homebrew!)
colima start && cd ~/yago && qlever --qleverfile Qleverfile start

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
2. **No Docker Desktop on the Mac** — user-space Colima only. (Homebrew WAS absent
   until ~Aug 2026; it is now installed, v6.0.14, so `brew install` is available.)
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
17. `vpn/` (TUM CIT profile) is git-ignored: **the GitHub repo is public.** The Knowgly clone
    now lives at `~/reference/Knowgly/`, outside the thesis folder (moved 2026-09-09) —
    understand it, don't copy from it.
18. **On Windows, `cargo build` with the default MSVC toolchain fails to link** inside Git Bash:
    `link` resolves to `/usr/bin/link` (coreutils hardlink tool, "extra operand" error), and
    separately there's no Visual Studio Build Tools installed anyway. Fix: install MinGW-w64
    (winget `BrechtSanders.WinLibs.POSIX.UCRT`), `rustup target add x86_64-pc-windows-gnu`, then
    `rustup default stable-x86_64-pc-windows-gnu` — the default must be the GNU *host* toolchain,
    not just the target, or build-script/proc-macro compilation still reaches for MSVC's linker.
19. `trajectories`/`out::write_json` needs **`QLEVER_SUFFIX=_<metric>`** set explicitly per call,
    or every metric's output silently overwrites the same generic `trajectories.json` instead of
    `trajectories_<metric>.json`. Cost a wasted run on 2026-09-11 — always check
    `results/<label>/` after a trajectories batch for the expected per-metric filenames.
20. GitHub push over HTTPS from this Windows account fails with `Unable to persist credentials
    with the 'wincredman' credential store` — Git Credential Manager can't reach Windows
    Credential Manager in this (headless/sandboxed) session. Workaround: a one-time
    `git -c credential.helper="store --file=<tmp file>" push`, where the tmp file holds
    `https://x-access-token:<PAT>@github.com` — never put the token directly in the push URL or
    command line (the auto-mode classifier blocks that, correctly). Delete the tmp file right
    after. The push itself still succeeds despite the wincredman warning printing first.

## Writing the thesis

`writing/` holds the LaTeX source (TUM `tumthesis` class, based on `report` — so
no `\backmatter`). Chapter outlines are in `writing/include/`, bibliography in
`writing/bib/literature.bib`.

LaTeX **is** installed: **TinyTeX** at `~/Library/TinyTeX` (user-space TeX Live —
this Mac has no passwordless sudo, so `brew --cask basictex` would stall on a
password prompt). Build with `cd writing && ./build.sh`; add packages with
`tlmgr install <name>`, no sudo. `~/.zshrc` exports the bin directory.
Two template fixes were needed for TeX Live 2026: `etex` is commented out of
`packages.sty` (removed from TL, kernel-provided since 2019), and `thesis.tex`
must avoid `\backmatter` (class is `report`-based) and `\bstctlcite`.

Scale to aim for, calibrated against a March 2026 bachelor thesis from the same
chair (advisor Johannes Mäkelburg, cloned at `~/Desktop/Thesis_writing`):
~16,000 words, ~57 pages, 12 figures, 12 tables, ~95 citations. Chapter 4
(Experiments) is **more than half the body**, and each experiment follows
Objective and Methodology / Results / Discussion. Read that thesis for structure
and depth — never reuse its prose, tables or bibliography.

## Conventions

- New metrics go into `rust_metrics/src/` as their own module + a subcommand in
  `main.rs`, writing `results/<metric>.{json,csv}`; the dashboard reads the JSON at
  startup (restart to refresh). Mirror the existing module style.
- Docs that Samuel sees: simple, minimal, no internal jargon; generate PDFs from the
  scripts in `docs/`.
- Update the auto-memory (`thesis-kg-metrics.md`) before ending a session.

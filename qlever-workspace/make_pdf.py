"""
Generates 'Thesis_Setup_Explained.pdf' in ~/thesis — a full written explanation
of the QLever + YAGO + metrics setup. Re-run any time: python make_pdf.py
"""
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Preformatted, PageBreak, HRFlowable,
)

OUT = "../Thesis_Setup_Explained.pdf"  # run from qlever-workspace/, on any machine

# ---- styles ----
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=16, spaceBefore=14,
                    spaceAfter=8, textColor=colors.HexColor("#1a3e6e"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12.5, spaceBefore=10,
                    spaceAfter=5, textColor=colors.HexColor("#244c7a"))
BODY = ParagraphStyle("BODY", parent=ss["BodyText"], fontSize=10, leading=14,
                      spaceAfter=6)
BULLET = ParagraphStyle("BULLET", parent=BODY, leftIndent=14, bulletIndent=4,
                        spaceAfter=2)
CODE = ParagraphStyle("CODE", parent=ss["Code"], fontSize=8.3, leading=10.5,
                      textColor=colors.HexColor("#0b3d0b"),
                      backColor=colors.HexColor("#f1f4f0"),
                      borderColor=colors.HexColor("#d4dccd"), borderWidth=0.6,
                      borderPadding=5, spaceBefore=3, spaceAfter=8)
TITLE = ParagraphStyle("TITLE", parent=ss["Title"], fontSize=24,
                       textColor=colors.HexColor("#16314f"))
SUB = ParagraphStyle("SUB", parent=ss["Title"], fontSize=12, spaceBefore=4,
                     textColor=colors.HexColor("#5a5a5a"))
NOTE = ParagraphStyle("NOTE", parent=BODY, fontSize=9, textColor=colors.HexColor("#6b4b00"),
                      backColor=colors.HexColor("#fff6df"),
                      borderColor=colors.HexColor("#e8d28a"), borderWidth=0.6,
                      borderPadding=6, spaceBefore=4, spaceAfter=8)

story = []
def P(t, s=BODY): story.append(Paragraph(t, s))
def gap(h=4): story.append(Spacer(1, h))
# Preformatted escapes its own input; escaping first double-escapes and prints
# literal &lt; / &gt; in every code block (it did, for 20 lines, until 2026-08-19).
def code(t): story.append(Preformatted(t, CODE))
def bullets(items):
    for it in items:
        story.append(Paragraph(it, BULLET, bulletText="•"))
    gap(4)
def hr(): story.append(HRFlowable(width="100%", thickness=0.6,
                                  color=colors.HexColor("#c9d3df"),
                                  spaceBefore=6, spaceAfter=8))

def table(data, col_w, header=True):
    t = Table(data, colWidths=col_w, hAlign="LEFT")
    sty = [
        ("FONTSIZE", (0,0), (-1,-1), 8.6),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cfd8e3")),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, colors.HexColor("#f5f8fc")]),
    ]
    if header:
        sty += [("BACKGROUND", (0,0), (-1,0), colors.HexColor("#244c7a")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold")]
    t.setStyle(TableStyle(sty))
    story.append(t); gap(8)

def cells(rows):  # wrap each cell string in a Paragraph for wrapping
    cs = ParagraphStyle("cell", parent=BODY, fontSize=8.6, leading=11, spaceAfter=0)
    ch = ParagraphStyle("cellh", parent=cs, textColor=colors.white, fontName="Helvetica-Bold")
    out = []
    for i, r in enumerate(rows):
        st = ch if i == 0 else cs
        out.append([Paragraph(escape(str(c)), st) for c in r])
    return out

# ============================================================ TITLE
P("Thesis Setup — Full Explanation", TITLE)
P("Deploying knowledge graphs with QLever, computing all 13 thesis metrics in Rust + SPARQL, and a niceGUI dashboard", SUB)
gap(6)
P("Author: Dharmang Pambhar &nbsp;|&nbsp; Updated: 11 September 2026 &nbsp;|&nbsp; "
  "Advisor: Samuel García (TUM)", SUB)
hr()
P("This document explains, from the ground up, what the thesis task is, the tools involved, "
  "everything that was set up on the machine, how the pieces fit together, and what remains. "
  "It is meant to be readable on its own and useful to bring to an advisor meeting.")
gap(2)

# ============================================================ 1. GOAL
P("1. What this project is about", H1)
P("The thesis goal is to <b>compute metrics over a knowledge graph</b> (YAGO or DBpedia) and "
  "present them in a dashboard. A <i>knowledge graph</i> is a large set of facts written as "
  "<b>triples</b> — <i>subject &ndash; predicate &ndash; object</i>, e.g. "
  "<font face='Courier'>Einstein &ndash; bornIn &ndash; Ulm</font>. The pipeline has four layers:")
code(
"KNOWLEDGE GRAPH DATA      YAGO / DBpedia  (RDF triples)\n"
"        |  loaded into\n"
"        v\n"
"QLever  = the database / RDF store\n"
"        - 'index' once -> builds fast lookup structures on disk\n"
"        - 'start'      -> serves a SPARQL endpoint (a server on a port)\n"
"        |  queried via SPARQL over HTTP\n"
"        v\n"
"YOUR METRICS CODE (Rust + SPARQL, like Knowgly)\n"
"        - SPARQL counts -> Rust HashMaps -> compute metrics\n"
"        |  display\n"
"        v\n"
"niceGUI = the dashboard (Python -> charts, tables in the browser)")
P("The four tools map cleanly onto these layers:")
table(cells([
    ["Tool", "Role", "Analogy"],
    ["YAGO / DBpedia", "The data (a knowledge graph of facts)", "the raw material"],
    ["QLever", "The database that stores & queries it via SPARQL", "like Postgres, but for graphs"],
    ["Knowgly", "A reference metrics project (to understand, not copy)", "a worked example"],
    ["niceGUI", "The dashboard to display your metrics", "the front-end"],
]), [90, 250, 150])

# ============================================================ 2. QLEVER
P("2. What QLever actually is", H1)
bullets([
    "<b>Triples & SPARQL:</b> RDF data is triples; <b>SPARQL</b> is its query language "
    "(like SQL is for tables).",
    "<b>QLever</b> is a very fast SPARQL engine from the University of Freiburg.",
    "<b>qlever index</b> reads the raw triple files <i>once</i> and builds an optimized index on disk "
    "(the slow, one-time step).",
    "<b>qlever start</b> launches a server that answers SPARQL queries over HTTP — so you can query it "
    "from Python.",
    "A <b>Qleverfile</b> is the recipe/config: which dataset, how to index it, which port, etc.",
    "The <font face='Courier'>qlever</font> command you install via pip is only the <b>controller</b>; "
    "the heavy engine runs separately (here, inside a container).",
])

# ============================================================ 3. ENVIRONMENT
P("3. The machine and its constraints", H1)
P("Knowing the hardware explains several decisions made during setup.")
table(cells([
    ["Property", "Value", "Why it mattered"],
    ["Computer", "MacBook Air, Apple Silicon (arm64), 16 GB RAM", "Limited RAM -> can't index 1.3B triples from scratch comfortably"],
    ["Disk free", "~140 GB at start", "Enough for the 24 GB zip + 41.6 GB index"],
    ["Docker", "Not installed; no Homebrew; no admin sudo in tooling", "Had to install a Docker engine without a password"],
    ["Python", "System Python 3.9 (too old)", "qlever needs Python 3.12+"],
]), [80, 210, 200])

# ============================================================ 4. STEPS
P("4. Everything that was set up (in order)", H1)
table(cells([
    ["Step", "What & why"],
    ["1. uv + Python 3.12", "Installed 'uv' (user-space Python manager) and created a Python 3.12 virtual environment, because the system Python 3.9 was too old for qlever."],
    ["2. qlever CLI", "Installed the qlever control tool into the venv (uv pip install qlever)."],
    ["3. Qleverfiles", "Downloaded the YAGO, DBpedia and olympics recipes from the qlever-control repo."],
    ["4. Pre-built YAGO index", "Downloaded the advisor's ready-made YAGO 4.5.0.2 index (skips the hours-long 'index' step)."],
    ["5. Verified the download", "First download was truncated by ~1 GB; proved it via Zip64 analysis and re-downloaded the full 23.88 GB, then extracted 41.6 GB."],
    ["6. Docker engine (Colima)", "Installed Colima + Lima + Docker CLI into ~/.local/bin with NO admin password, and booted a lightweight Linux VM."],
    ["7. qlever start", "Served the index at localhost:9004 using a QLever image pinned to the exact build that created the index."],
    ["8. Python querying", "Wrote sparql.py + metrics_examples.py and confirmed real results against the local index."],
    ["9. Web UI", "Launched the QLever UI at localhost:8176 and pointed it at the local index."],
    ["10. Moved off iCloud", "Discovered the Desktop is iCloud-synced (it corrupted the venv); moved the whole project to ~/thesis (not synced)."],
    ["11. First Rust + SPARQL metric", "Built rust_metrics/ (Entity Type Importance), writing results to JSON + CSV."],
    ["12. niceGUI dashboard", "Built dashboard.py — reads the metric's JSON and charts each type's characteristic predicates at localhost:8080."],
]), [110, 380])

# ============================================================ 5. THE INDEX
P("5. The YAGO index (the data)", H1)
P("The advisor shared a finished QLever index, so the slow 'qlever index' step was skipped. "
  "It is <b>YAGO version 4.5.0.2</b>. Key facts read from its metadata:")
table(cells([
    ["Property", "Value"],
    ["Triples (normal)", "1,305,431,407  (~1.3 billion)"],
    ["Distinct subjects (entities)", "49,688,174"],
    ["Distinct objects", "645,362,721"],
    ["Distinct predicates", "123"],
    ["On-disk size", "~41.6 GB (28 files)"],
    ["Index build commit", "e5f672 (Oct 2024)"],
    ["Vocabulary", "on-disk compressed dictionary (IRIs <-> integer IDs)"],
]), [200, 290])
P("An index is made of <b>six permutations</b> (the triples sorted in every order: SPO, SOP, "
  "PSO, POS, OSP, OPS) so QLever can look up data quickly in any direction, plus the "
  "<b>vocabulary</b> (the dictionary that maps every IRI/string to an integer ID).")
story.append(PageBreak())

# ============================================================ 6. ENGINE
P("6. The query engine (Colima / Docker)", H1)
P("QLever's engine is a Linux C++ server with <b>no native macOS binary</b>, so it runs in a "
  "container. Docker was installed <b>without any admin password</b> using user-space binaries:")
bullets([
    "<b>Colima</b> + <b>Lima</b> + <b>Docker CLI</b> placed in ~/.local/bin (no Homebrew, no sudo).",
    "Colima boots a small Linux VM using macOS's built-in Virtualization framework (vz).",
    "Your ~/thesis folder is shared into the VM (virtiofs) so the container can read the 41.6 GB index.",
    "The QLever image is <b>pinned</b> to commit-e5f6724 — the exact build that made the index — "
    "so the index format is guaranteed compatible (':latest' could reject a 2024-format index).",
])
P("Endpoint: <b>http://localhost:9004</b> &nbsp; | &nbsp; Access token: "
  "<font face='Courier'>yago-4.5.0.2</font>")
gap(2)
story.append(Paragraph("Note: visiting http://localhost:9004 in a browser shows \"Unknown path\". "
    "That is normal — it is a SPARQL API, not a web page; it answers queries, not page requests.", NOTE))

# ============================================================ 7. FOLDERS
P("7. The project files and folders", H1)
code(
"~/thesis/\n"
"  qlever-workspace/            <- project root\n"
"    rust_metrics/              <- THESIS METRICS (Rust + SPARQL, mirrors Knowgly)\n"
"      Cargo.toml\n"
"      src/qlever_client.rs     <- SPARQL client (can hold TWO endpoints at once)\n"
"      src/common.rs            <- shared queries + entropy helpers\n"
"      src/out.rs               <- writes results/[<label>/]<metric>.{json,csv}\n"
"      src/<metric>.rs          <- ONE MODULE PER METRIC (13 + 2 baselines)\n"
"      src/main.rs              <- subcommand dispatch ('help' lists everything)\n"
"      results/[<label>/]*.{json,csv}  <- metric output, one folder per snapshot\n"
"    dashboard.py               <- niceGUI dashboard (reads results JSON, charts at :8080)\n"
"    sparql.py                  <- lightweight Python query reference\n"
"    metrics_examples.py        <- Python example metrics (reference)\n"
"    make_pdf.py                <- generates this PDF\n"
"    RUNBOOK.md                 <- start/stop/query/metrics commands\n"
"    Qleverfiles/               <- recipes (yago-4, dbpedia, olympics)\n"
"    yago/                      <- THE DATABASE (41.6 GB index, not code)\n"
"    .venv/                     <- isolated Python 3.12 + qlever + requests\n"
"  Thesis_Setup_Explained.pdf   <- this document")
P("Categories: <b>thesis metrics</b> (the Rust project rust_metrics/), the <b>dashboard</b> "
  "(dashboard.py), <b>config</b> (Qleverfiles), <b>data + tooling</b> (yago/, .venv/ — set up "
  "once), and a small <b>Python reference</b> (sparql.py, metrics_examples.py).")

# ============================================================ 8. CODE
P("8. The metric implementation (Rust + SPARQL)", H1)
P("Per the advisor and the Knowgly reference, the metrics are implemented as a <b>mix of SPARQL "
  "and Rust working with dictionaries (HashMaps)</b>: SPARQL does the heavy counting on the "
  "server, and Rust holds the aggregated counts and applies the formula. The project is "
  "<font face='Courier'>rust_metrics/</font> and mirrors Knowgly's structure. "
  "<b>All 13 metrics of the final metrics list are implemented</b> — about 2350 lines across 19 "
  "modules, one module per metric plus a subcommand.")
table(cells([
    ["File", "Role"],
    ["src/qlever_client.rs", "SPARQL client. Holds a global endpoint for the per-snapshot metrics and can build a second one for the cross-version metrics. Surfaces QLever's own error text, and aborts on a failed query rather than returning an empty result."],
    ["src/common.rs", "Shared queries (top types, |E_t|, class and predicate lists) and the entropy helpers."],
    ["src/out.rs", "Result writing: results/[<label>/]<metric>.json + .csv."],
    ["src/<metric>.rs", "One module per metric — the formula and its queries."],
    ["src/main.rs", "Subcommand dispatch, environment handling, and the 'all' runner."],
]), [150, 340])

P("<b>The 13 metrics</b> (baselines <font face='Courier'>etimp</font> and "
  "<font face='Courier'>pagerank</font> come from Knowgly and are not thesis contributions):", H2)
table(cells([
    ["#", "Metric", "Command", "Level"],
    ["1", "Class population & share", "population", "class"],
    ["2", "Property entropy per type", "entf", "class"],
    ["3", "Entropy-weighted type importance", "entetimp", "class"],
    ["4", "Class entropy", "classentropy", "class"],
    ["5", "Entity informativeness", "inforank", "entity"],
    ["6", "Object diversity", "diversity", "entity"],
    ["7", "Entropy-weighted PageRank (own variant)", "entropy-pagerank", "global"],
    ["8", "Graph size & shape", "shape", "global"],
    ["9", "Class-level change rate (churn)", "churn", "global, 2 endpoints"],
    ["10", "Triple diff, integer-encoded", "diff", "global, 2 endpoints"],
    ["11", "Metric trajectories", "trajectories", "global, stored results"],
    ["12", "Vocabulary / schema evolution", "vocab", "global, 2 endpoints"],
    ["13", "Cross-KG class comparison", "crosskg", "global, 2 endpoints"],
]), [20, 230, 130, 110])

P("<b>How to run them</b>", H2)
code('source "$HOME/.cargo/env"\n'
     "cd ~/thesis/qlever-workspace/rust_metrics\n"
     "export QLEVER_ENDPOINT=http://localhost:9004\n"
     "export QLEVER_LABEL=yago-4.5.0.2        # names this snapshot -> results/<label>/\n"
     "cargo run --release all 8               # every single-endpoint metric, top-8 classes\n"
     "cargo run --release help                # the full list\n"
     "\n"
     "# comparing two versions needs a second endpoint\n"
     "export QLEVER_ENDPOINT_B=http://localhost:9005\n"
     "cargo run --release diff 'http://schema.org/Person' 5000\n"
     "cargo run --release trajectories graph_shape yago-4 yago-4.5.0.2")
P("The <font face='Courier'>QLEVER_LABEL</font> is what makes evolution work: the same metric run "
  "against two versions under two labels lands in two folders, and metric 11 reads both back and "
  "reports the deltas.")

P("<b>Three implementation decisions worth knowing</b>", H2)
P("<b>1. Entropy is computed from a count-of-counts histogram.</b> Shannon entropy depends only "
  "on the multiset of counts, never on the values themselves, so there is no reason to stream "
  "millions of object values over HTTP. A nested GROUP BY makes QLever fold them into a histogram "
  "of a few hundred rows, and the entropy is recovered exactly:")
code("H = log2 N - (1/N) * sum_c  m_c * c * log2 c\n"
     "  m_c = how many distinct values occur exactly c times\n"
     "  N   = total value occurrences        (exact, not sampled)")
P("<b>2. The triple diff uses a subject window.</b> The obvious way to take a comparable slice of "
  "two versions is ORDER BY ?s ?p ?o LIMIT n, but that forces the server to sort the entire graph "
  "before it can take n rows — on a 1.5 billion triple graph QLever asked for 12.7 GB and refused. "
  "Instead the diff takes the lexicographically first n subjects of each version (ordering a "
  "subject list is an index scan, not a sort of every triple), cuts both lists at the smaller "
  "upper bound, and fetches those subjects' triples by name. Inside that window both versions are "
  "covered completely, so the diff is exact there — including entities that appear or vanish — "
  "and nothing needs a global sort. Metrics 9 and 10 should therefore always be scoped to a class.")
P("<b>3. Metric 10 compares two versions of one KG, not two different KGs.</b> YAGO and DBpedia "
  "use disjoint subject IRIs, so the window falls entirely inside one of them and every triple of "
  "the other is reported as 'added' — arithmetically correct and completely meaningless. The code "
  "detects this and says so. Comparing two different KGs is metric 13's job, which matches classes "
  "by name and compares their metric values instead.")

P("<b>The efficiency contribution, measured</b>", H2)
P("Metric 10 encodes every term into a u32 so a triple becomes 12 bytes and the comparison is a "
  "sort plus a linear merge over integers, instead of hashing three strings per triple. Both the "
  "integer path and the naive string path are implemented and timed against each other, and the "
  "code asserts that the two agree — so the benchmark cannot drift away from being correct. "
  "Measured on real data:")
table(cells([
    ["Path", "Time", "Memory"],
    ["integer-encoded sets", "43 ms", "3.3 MB"],
    ["naive string hash sets", "259 ms", "53.9 MB"],
    ["ratio", "6.0x faster", "16.5x smaller"],
]), [200, 145, 145])

P("<b>Verification</b>", H2)
P("All 13 metrics were run against live endpoints. Metrics 1-8 on the olympics dataset and on "
  "YAGO; metrics 9 and 10 self-tested against a single endpoint, where the diff must be exactly "
  "zero, and then at scale on YAGO; metric 12 across two different graphs; metric 13 on YAGO "
  "versus DBpedia (Person: 6.43 M entities at 20.6 bits of class entropy against DBpedia's "
  "1.86 M at 17.4 bits); metric 11 across two stored snapshots.")
P("Metric 7 also demonstrates its own premise on the olympics graph: the predicate weights come "
  "out as athlete = 1.000 against type = 0.008, so the low-entropy class nodes drop out of the top "
  "ranks and every athlete rises exactly five places against the unweighted baseline.")
gap(2)
P("<b>Python files (reference only).</b> <font face='Courier'>sparql.py</font> and "
  "<font face='Courier'>metrics_examples.py</font> are a small Python query helper kept for quick "
  "checks — they are <i>not</i> the thesis metric implementation (that is the Rust project above).")

# ============================================================ 9. DASHBOARD
P("9. The dashboard (niceGUI)", H1)
P("The final layer visualises the metric. <font face='Courier'>dashboard.py</font> is a "
  "<b>niceGUI</b> web app (Python) that reads the Rust metric's output "
  "(<font face='Courier'>rust_metrics/results/entity_type_importance.json</font>) and presents it "
  "interactively in the browser — no SPARQL is run at view time, it simply reads the pre-computed "
  "JSON, so the page is instant.")
P("<b>What it shows:</b>")
bullets([
    "A <b>dropdown</b> to pick any entity type that the metric was computed for (Person, Galaxy, "
    "Politician, ...).",
    "A <b>Top-N selector</b> (3&ndash;40) controlling how many predicates are charted.",
    "An interactive <b>horizontal bar chart</b> (ECharts) of that type's most characteristic "
    "predicates, ranked by ETImp score, with the value labelled on each bar.",
    "A <b>full ranked table</b> of every predicate for the type (rank, predicate, ETImp score), "
    "paginated and sortable.",
])
P("<b>How it is built:</b> long IRIs are trimmed to their readable last segment (e.g. "
  "<font face='Courier'>...#birthDate</font> -> <font face='Courier'>birthDate</font>); the chart "
  "and table are wrapped in an <font face='Courier'>@ui.refreshable</font> block so changing the "
  "type or Top-N redraws them without reloading the page. The JSON is read once at startup, so to "
  "pick up regenerated data you restart the app.")
P("Run it (after the metric has produced results/):")
code("cd ~/thesis/qlever-workspace\n"
     "source .venv/bin/activate\n"
     "python dashboard.py            # then open http://localhost:8080")
gap(2)
story.append(Paragraph("This completes the full pipeline end to end: "
    "YAGO index -> QLever (:9004) -> Rust + SPARQL metric -> results JSON -> niceGUI dashboard (:8080).",
    NOTE))
story.append(PageBreak())

# ============================================================ 10. RUNBOOK
P("10. How to start / stop / query (runbook)", H1)
P("Set up the shell each session:")
code('export PATH="$HOME/.local/bin:$PATH"\n'
     'source ~/thesis/qlever-workspace/.venv/bin/activate')
P("Start everything (e.g. after a reboot):")
code("colima start\n"
     "cd ~/yago\n"
     "qlever --qleverfile Qleverfile start        # serves localhost:9004")
P("Check / stop:")
code("docker ps                                   # see the running server\n"
     "qlever --qleverfile Qleverfile stop         # stop QLever\n"
     "colima stop                                 # stop the Docker VM (frees RAM)")
P("Query from the browser UI: <b>http://localhost:8176/yago-4</b>")
story.append(PageBreak())

# ============================================================ 11. KNOWGLY
P("11. The Knowgly metrics — the idea", H1)
P("The advisor asked you to <b>understand</b> Knowgly's metrics (not reimplement them). The whole "
  "approach is one pattern:")
story.append(Paragraph("Metric = SPARQL does the counting (GROUP BY ... COUNT) -> code plugs the "
    "counts into a formula -> results stored in nested dictionaries (Type -> Predicate -> value). "
    "The \"Rust for dictionaries\" the advisor mentioned is just bookkeeping of those counts; in "
    "Python it is a plain dict.", NOTE))
P("Knowgly implements two metrics that rank how important each predicate is for each entity type:")
bullets([
    "<b>Entity Type Importance</b> (a TF-IDF for predicates): "
    "ETImp(p,t) = EF_p(p,t) &times; log2( |E_t| / EF_p(p,t) ), where EF_p(p,t) is the number of "
    "entities of type t that use predicate p, and |E_t| is the total entities of type t. Predicates "
    "used by <i>every</i> entity of a type score 0 (uninformative); characteristic predicates score high.",
    "<b>Entropy Type Importance</b> (Shannon entropy of a predicate's object values): "
    "H = -&Sigma; P(o) log P(o). High entropy = diverse, informative values (name, birthDate); "
    "low entropy = near-constant values.",
])
P("Engineering lessons worth reusing even for simple metrics:")
bullets([
    "Do NOT write one giant query; split into many small per-type queries (avoids query-planner blowups).",
    "Run them in parallel.",
    "Aggregate the counts in dictionaries.",
    "Optionally cluster predicates by their scores into importance groups.",
])
P("Your thesis metrics are <b>simpler than Knowgly's</b> but implemented the <b>same way — SPARQL "
  "+ Rust dictionaries</b>. The first one, Entity Type Importance, is already built in "
  "<font face='Courier'>rust_metrics/</font> (see Section 8) and runs against your local YAGO.")

# ============================================================ 11b. SNAPSHOTS
story.append(PageBreak())
P("The five snapshots and the matched DBpedia subset", H1)
P("The thesis compares <b>five snapshots</b>: two versions of YAGO for within-KG evolution, "
  "three versions of DBpedia for a decade of within-KG evolution, and any YAGO-vs-DBpedia pair "
  "for cross-KG comparison.")
table(cells([
    ["Snapshot", "Served on", "Port", "Triples"],
    ["YAGO 4 (2020)", "home server", "9005", "2,489,858,800"],
    ["YAGO 4.5.0.2 (2024)", "home server (+ Mac backup)", "9006", "1,305,431,407"],
    ["DBpedia 2015-10 (matched)", "home server", "9008", "169,621,442"],
    ["DBpedia 2022.12.01 (matched)", "TUM VM", "7014", "237,155,678"],
    ["DBpedia 2025-12-01 (matched)", "home server", "9010", "347,497,387"],
]), [200, 150, 55, 105])
P("Every DBpedia release ships a <b>different set of files</b> from a different extraction "
  "pipeline (2015: the classic core-i18n dump; 2022: the Databus latest-core collection, the "
  "last classic release; 2025: the new wikipedia-kg-dump, partitioned by predicate family). If "
  "each were indexed as-shipped, the vocabulary-evolution and triple-diff metrics would report "
  "our download choices as change. So all three are built from the <b>same five roles</b> and "
  "nothing else:")
bullets([
    "Direct + transitive types (<font face='Courier'>?s a ?type</font>) — BOTH inference levels, "
    "so a footballer counts under dbo:Person, comparable to YAGO's direct schema:Person typing. "
    "Specific-only would collapse Person from 1.92 M to 0.30 M and Species from 1.98 M to 360.",
    "Ontology-mapped object + literal properties (the clean dbo: facts).",
    "Raw infobox properties (the messy dbp: predicates).",
    "Labels (rdfs:label) and redirects (dbo:wikiPageRedirects).",
])
P("Excluded everywhere: categories, abstracts, page metadata, interlanguage/external/Freebase "
  "links, and the stale 2016-2019 link dumps latest-core drags in. The full 86-file 2022 index "
  "(TUM VM :7013) is kept only as an independent cross-check, not as one of the five compared "
  "snapshots. Full spec: <font face='Courier'>qlever-workspace/dbpedia-matched/MATCHED_SUBSET.md</font>. "
  "Caveat for the cross-KG chapter: the snapshots are not date-aligned (YAGO 4.5 = 2024, "
  "DBpedia core = 2022).")

# ============================================================ 12. SUPERVISOR MAP
P("12. Does this cover the supervisor's instructions?", H1)
table(cells([
    ["Supervisor's instruction", "Status"],
    ["Explore / use QLever to deploy YAGO locally", "DONE"],
    ["Install qlever via pip", "DONE (in a Python 3.12 venv)"],
    ["Grab a Qleverfile", "DONE (yago / dbpedia / olympics)"],
    ["qlever ... index", "SKIPPED ON PURPOSE - used the pre-built index instead"],
    ["Use the pre-built YAGO index (SharePoint)", "DONE (downloaded, verified, extracted)"],
    ["qlever ... start", "DONE (serving localhost:9004)"],
    ["Query as a SPARQL endpoint with Python", "DONE (sparql.py + metrics_examples.py)"],
]), [320, 170])
P("Everything in the message is implemented. The only line not literally executed is "
  "<font face='Courier'>qlever index</font> — intentionally, because the advisor's pre-built index "
  "exists precisely so you can skip that slow step.")

# ============================================================ 13. NEXT
P("13. Current status and next steps", H1)
table(cells([
    ["Thesis piece", "Status"],
    ["Deploy a KG locally with QLever", "DONE"],
    ["Query SPARQL (Python + Rust)", "DONE"],
    ["Understand the Knowgly metrics", "DONE"],
    ["Final metrics list agreed (13 metrics, 3 levels)", "DONE"],
    ["All 13 metrics implemented in Rust + SPARQL", "DONE"],
    ["Metrics verified against live endpoints", "DONE"],
    ["Efficiency benchmark for the triple diff", "DONE (6.0x faster, 16.5x smaller)"],
    ["Results written as JSON + CSV, one folder per snapshot", "DONE"],
    ["Second YAGO version indexed + cross-version metrics run", "DONE (YAGO 4 vs 4.5)"],
    ["niceGUI dashboard rebuilt metric-first across snapshots (phase 1)", "DONE"],
    ["DBpedia 2022 indexed (full + matched subset) on the TUM VM", "DONE"],
    ["DBpedia 2015 + 2025 indexed on the home server", "DONE (ports 9008, 9010)"],
    ["Run phases 1-3 (class/entity/global metrics) across all five snapshots", "DONE"],
    ["Metric 11 (trajectories): full 3-point DBpedia series, 2015-2022-2025", "DONE"],
    ["Metric 13 (crosskg): YAGO 4.5.0.2 vs DBpedia 2025, all shared classes", "DONE (8 classes)"],
]), [320, 170])
P("The computation side of the thesis is now complete end to end: every metric is implemented, "
  "runs against a real endpoint, and writes its results; all five snapshots are indexed and "
  "served (YAGO 4 and 4.5.0.2 on the home server, DBpedia 2015/2025 on the home server, DBpedia "
  "2022 matched on the TUM VM); and phases 1-3 have all been run, including the cross-version "
  "and cross-KG metrics. The DBpedia trajectory series originally skipped the 2022 snapshot "
  "(only 2015 and 2025 were passed to metric 11) — that has been corrected, so it now reports the "
  "full three-point decade. Metric 13 originally covered only the Person class; re-run with "
  "automatic class matching it found 8 classes shared between YAGO 4.5.0.2 and DBpedia 2025 "
  "(administrativearea, album, building, movie, organization, person, politician, village). "
  "What remains is the write-up: Chapter 4 (Experiments and Results) is still an outline with the "
  "numbers to cite, not finished prose.")

SimpleDocTemplate(OUT, pagesize=A4, topMargin=18*mm, bottomMargin=16*mm,
                  leftMargin=18*mm, rightMargin=16*mm,
                  title="Thesis Setup - Full Explanation",
                  author="Dharmang Pambhar").build(story)
print("WROTE", OUT)

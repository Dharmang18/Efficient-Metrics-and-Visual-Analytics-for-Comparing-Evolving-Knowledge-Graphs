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

OUT = "/Users/dharmangpambhar/thesis/Thesis_Setup_Explained.pdf"

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
def code(t): story.append(Preformatted(escape(t), CODE))
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
P("Deploying YAGO locally with QLever, computing metrics in Rust + SPARQL, and a niceGUI dashboard", SUB)
gap(6)
P("Author: Dharmang Pambhar &nbsp;|&nbsp; Date: 9 June 2026 &nbsp;|&nbsp; "
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
"      src/qlever_client.rs     <- SPARQL endpoint client\n"
"      src/common.rs            <- reusable queries\n"
"      src/entity_type_importance.rs  <- the metric\n"
"      src/main.rs              <- runs it, writes results/*\n"
"      results/entity_type_importance.{json,csv}  <- the metric output\n"
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
  "server, and Rust holds the aggregated counts in nested HashMaps and applies the formula. "
  "The project is <font face='Courier'>rust_metrics/</font> and mirrors Knowgly's structure.")
table(cells([
    ["File", "Role"],
    ["src/qlever_client.rs", "One global SPARQL endpoint; query() sends a SELECT and returns rows as var->value maps (reads results via a streaming reader so large result sets work)."],
    ["src/common.rs", "Reusable queries: fetch_top_type_iris(N) and entity_count_per_type() (|E_t|)."],
    ["src/entity_type_importance.rs", "The metric. Per-type SPARQL GROUP BY queries run in parallel (rayon); results stored in HashMap<Type, HashMap<Predicate, score>>."],
    ["src/main.rs", "Initialises the endpoint, runs the metric, and writes results/entity_type_importance.json + .csv (which the dashboard reads)."],
]), [150, 340])
P("<b>The implemented metric — Entity Type Importance</b> (a TF-IDF for predicates):")
code("ETImp(p, t) = EF_p(p, t) * log2( |E_t| / EF_p(p, t) )\n"
     "  EF_p(p,t) = # distinct entities of type t that use predicate p   (SPARQL COUNT DISTINCT)\n"
     "  |E_t|     = # distinct entities of type t")
P("Run it against your local index:")
code('source "$HOME/.cargo/env"\n'
     "cd ~/thesis/qlever-workspace/rust_metrics\n"
     "export QLEVER_ENDPOINT=http://localhost:9004\n"
     "cargo run --release 8        # top 8 most-populated types")
P("Example output (characteristic predicates surface correctly): <b>Person</b> -> deathDate, "
  "birthDate, children, spouse; &nbsp; <b>Galaxy</b> -> radialVelocity, distanceFromEarth, parallax; "
  "&nbsp; <b>Politician</b> -> memberOf, birthPlace, deathPlace.")
P("<b>Note on scope:</b> Knowgly computes this for <i>all</i> types; on a 16 GB laptop one query "
  "per type over 1.3B triples is slow, so we restrict to the top-N most-populated types (the "
  "<font face='Courier'>cargo run --release N</font> argument). Same metric, tractable scope.")
gap(2)
P("<b>Python files (reference only).</b> <font face='Courier'>sparql.py</font> and "
  "<font face='Courier'>metrics_examples.py</font> are a small Python query helper kept for quick "
  "checks and to feed the future niceGUI dashboard — they are <i>not</i> the thesis metric "
  "implementation (that is the Rust project above).")

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
     "cd ~/thesis/qlever-workspace/yago\n"
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
    ["Deploy YAGO locally with QLever", "DONE"],
    ["Query SPARQL (Python + Rust)", "DONE"],
    ["Understand the Knowgly metrics", "DONE"],
    ["First metric in Rust + SPARQL (Entity Type Importance)", "DONE"],
    ["Rust metric writes results as JSON + CSV", "DONE"],
    ["niceGUI dashboard (charts the metric at :8080)", "DONE"],
    ["Add more metrics (e.g. entropy-based)", "TODO"],
]), [320, 170])
P("The full pipeline now works end to end — YAGO index, QLever endpoint, Rust + SPARQL metric, "
  "results JSON, and the niceGUI dashboard. What remains: add a few more metrics in the same "
  "Rust + SPARQL style (e.g. the entropy-based one) and surface them in the dashboard alongside "
  "Entity Type Importance.")

SimpleDocTemplate(OUT, pagesize=A4, topMargin=18*mm, bottomMargin=16*mm,
                  leftMargin=18*mm, rightMargin=16*mm,
                  title="Thesis Setup - Full Explanation",
                  author="Dharmang Pambhar").build(story)
print("WROTE", OUT)

"""
niceGUI dashboard for the thesis metrics — all 13 metrics, phases 1-3.

One tab per metric, grouped into three phases (class-level, entity-level,
global), mirroring run_phase.sh. Snapshots are selected inside each tab so
the same metric can be read across YAGO 4, YAGO 4.5.0.2 and DBpedia in a
single chart — that is the comparison the thesis is about.

Phase-1/2/8 (single-endpoint) metrics read rust_metrics/results/<label>/<metric>.json
and are loaded eagerly (small files). Phase-3 two-endpoint metrics (churn, diff,
vocab, crosskg) and trajectories (metric 11) read results/<pair-or-evolution>/...
lazily, on tab/selector change, since some of those files run several MB.

Run:   python dashboard.py     then open http://localhost:8080
"""
import json
import re
from pathlib import Path
from nicegui import ui

RESULTS_DIR = Path(__file__).parent / "rust_metrics" / "results"

# The five thesis snapshots, in evolution order. Older demo runs (yago-3,
# dbpedia-2016, yago4-public, ...) remain discoverable but unselected.
PREFERRED = ["yago-3", "yago-4", "yago-4.5.0.2",
             "dbpedia-2015", "dbpedia-2016", "dbpedia-2022-matched", "dbpedia-2025"]

# Pair/evolution folders belonging to the official comparisons, shown first.
OFFICIAL_PAIRS = ["yago-4-vs-yago-4.5.0.2", "dbpedia-2015-vs-2025",
                   "yago-4.5.0.2-vs-dbpedia-2025"]
OFFICIAL_EVOLUTIONS = ["yago-evolution", "dbpedia-evolution"]

# Classes carry different local names in different KGs (CLASS_MAPPING.md pins
# Taxon->Species and Chemical_compound->ChemicalCompound for DBpedia), so the
# comparison key folds the known synonyms together.
SYNONYMS = {"species": "taxon"}

PALETTE = ["#3b82f6", "#f59e0b", "#10b981", "#8b5cf6", "#ef4444", "#14b8a6"]
PAIR_COLORS = ["#3b82f6", "#ef4444"]  # A / B, added / deleted, etc.


def short(iri: str) -> str:
    """Trim a long IRI to its readable last segment."""
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def canon(iri: str) -> str:
    """Comparison key for a class or predicate: local name, case- and
    underscore-insensitive, with cross-KG synonyms folded together."""
    key = short(iri).lower().replace("_", "")
    return SYNONYMS.get(key, key)


def traj_label(key: str) -> str:
    """A trajectory series key is `<prefix>/<...>/<field>`, where the middle
    part may itself be a full IRI (slashes and all). Split off the last path
    segment as the field name and shorten whatever remains as an IRI."""
    head, sep, field = key.rpartition("/")
    return f"{short(head)} · {field}" if sep else key


# ============================================================ metric metadata

METRICS = [
    {"id": "population", "num": 1, "phase": 1, "level": "class",
     "name": "Class population & share",
     "blurb": "How many entities each class has, and what share of the whole "
              "snapshot that is.",
     "formula": "share(t) = |E_t| / |E|"},
    {"id": "entf", "num": 2, "phase": 1, "level": "class",
     "name": "Property entropy per type",
     "blurb": "How informative (varied) each predicate's values are for a "
              "given class — near-constant values score low, diverse ones high.",
     "formula": "EntF(p,t) = −Σ P(o)·log2 P(o)"},
    {"id": "entetimp", "num": 3, "phase": 1, "level": "class",
     "name": "Entropy-weighted type importance",
     "blurb": "Ranks predicates by how characteristic they are of a class — "
              "a TF-IDF for predicates, blended with entropy.",
     "formula": "ETImp(p,t) = EntF(p,t)^w · ETImp_base(p,t)^(1−w),  w = 0.75"},
    {"id": "classentropy", "num": 4, "phase": 1, "level": "class",
     "name": "Class entropy",
     "blurb": "Overall diversity of a class's data: how varied are ALL of its "
              "object values combined, across every predicate.",
     "formula": "H(t) = −Σ P(v)·log2 P(v)  over all object values of class t"},
    {"id": "inforank", "num": 5, "phase": 2, "level": "entity",
     "name": "Entity informativeness",
     "blurb": "Ranks individual entities by how many distinct literal "
              "properties describe them, relative to the whole graph.",
     "formula": "IR(v) = dtp(v) / Σ_u dtp(u)"},
    {"id": "diversity", "num": 6, "phase": 2, "level": "entity",
     "name": "Object diversity",
     "blurb": "For a class + predicate pair, how many distinct object values "
              "are actually used in practice.",
     "formula": "OD(p,t) = |{ distinct objects of p among entities of t }|"},
    {"id": "entropy_pagerank", "num": 7, "phase": 3, "level": "global",
     "name": "Entropy-weighted PageRank (own variant)",
     "blurb": "PageRank where each edge is weighted by how informative its "
              "predicate is, so importance flows through meaningful relations, "
              "not just raw link count.",
     "formula": "PR(v) = (1−d) + d·Σ w(p)·PR(u)/outdeg(u),  w(p) = normalized EntF(p)"},
    {"id": "shape", "num": 8, "phase": 3, "level": "global",
     "name": "Graph size & shape",
     "blurb": "The vital statistics of a snapshot: triples, entities, "
              "predicates, classes, density, and average degree.",
     "formula": "density = |T| / |E|"},
    {"id": "churn", "num": 9, "phase": 3, "level": "global · 2 endpoints",
     "name": "Class-level churn",
     "blurb": "For one class, what fraction of its triples changed between "
              "two versions of the same KG.",
     "formula": "churn(t) = (|added_t| + |deleted_t|) / |T_t(v1)|"},
    {"id": "diff", "num": 10, "phase": 3, "level": "global · 2 endpoints",
     "name": "Triple diff (integer-encoded)",
     "blurb": "Exact added / deleted / unchanged triples between two versions "
              "of a class, computed fast via integer-encoded sets.",
     "formula": "Added = T2 − T1,   Deleted = T1 − T2   (integer-encoded, benchmarked vs. naive strings)"},
    {"id": "trajectories", "num": 11, "phase": 3, "level": "global · stored results",
     "name": "Metric trajectories",
     "blurb": "Tracks how any other metric's value moved across three or more "
              "snapshots, not just a before/after pair.",
     "formula": "Δm(v_i) = m(v_i+1) − m(v_i)"},
    {"id": "vocab", "num": 12, "phase": 3, "level": "global · 2 endpoints",
     "name": "Vocabulary / schema evolution",
     "blurb": "Which classes and predicates were newly introduced or dropped "
              "between two versions of the same KG.",
     "formula": "C_added = C2 − C1,   C_removed = C1 − C2"},
    {"id": "crosskg", "num": 13, "phase": 3, "level": "global · 2 endpoints",
     "name": "Cross-KG class comparison",
     "blurb": "The same class, matched by local name, compared across two "
              "DIFFERENT knowledge graphs — not two versions of one.",
     "formula": "Δm(t) = m_A(t) − m_B(t)"},
]
META = {m["id"]: m for m in METRICS}


# ---------------- snapshot (phase 1/2/8) data loading ----------------

def read(label: str, name: str):
    """Load results/<label>/<name>.json, or None if that metric was not run."""
    path = RESULTS_DIR / label / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def discover() -> list[str]:
    """Snapshot labels that have phase-1 output, preferred ones first."""
    found = sorted(d.name for d in RESULTS_DIR.iterdir()
                   if d.is_dir() and (d / "class_population.json").exists())
    return ([l for l in PREFERRED if l in found]
            + [l for l in found if l not in PREFERRED])


LABELS = discover()
DEFAULT = [l for l in LABELS if l in PREFERRED] or LABELS[:1]
COLOR = {l: PALETTE[i % len(PALETTE)] for i, l in enumerate(LABELS)}

# data[label][file] -> parsed JSON (None when that file is absent)
FILES = ["class_population", "class_entropy", "class_entropy_pinned",
         "property_entropy", "property_entropy_pinned",
         "ent_etimp", "ent_etimp_pinned",
         "object_diversity", "object_diversity_pinned",
         "entity_informativeness", "entropy_pagerank", "graph_shape"]
data = {l: {f: read(l, f) for f in FILES} for l in LABELS}


def entries(label: str, file: str) -> dict:
    """The class -> value mapping inside one snapshot's file. class_population
    nests its classes under a "classes" key, beside the snapshot total; the
    other class-keyed metrics are keyed by class IRI directly."""
    raw = data[label].get(file)
    if raw is None:
        return {}
    return raw.get("classes", {}) if file == "class_population" else raw


def display_name(key: str, labels: list[str], file: str) -> str:
    """Prettiest local name for a comparison key, taken from the first snapshot
    that has it (so YAGO's Taxon names the row, not DBpedia's Species)."""
    for label in labels:
        for iri in entries(label, file):
            if canon(iri) == key:
                return short(iri)
    return key


def class_keys(labels: list[str], file: str) -> list[str]:
    """Every class present in any selected snapshot, most populated first."""
    keys = {}
    for label in labels:
        pop = (data[label]["class_population"] or {}).get("classes", {})
        for iri in entries(label, file):
            keys[canon(iri)] = max(keys.get(canon(iri), 0),
                                   pop.get(iri, {}).get("population", 0))
    return sorted(keys, key=lambda k: keys[k], reverse=True)


def lookup(label: str, file: str, key: str):
    """The entry for class `key` in one snapshot's file, or None."""
    for iri, value in entries(label, file).items():
        if canon(iri) == key:
            return iri, value
    return None


# ---------------- pair (2-endpoint) and evolution data loading ----------------

def discover_pairs(required_file: str) -> list[str]:
    found = sorted(d.name for d in RESULTS_DIR.iterdir()
                   if d.is_dir() and (d / required_file).exists())
    order = {n: i for i, n in enumerate(OFFICIAL_PAIRS)}
    return sorted(found, key=lambda n: (order.get(n, 999), n))


def discover_evolutions() -> list[str]:
    found = sorted(d.name for d in RESULTS_DIR.iterdir()
                   if d.is_dir() and any(d.glob("trajectories_*.json")))
    order = {n: i for i, n in enumerate(OFFICIAL_EVOLUTIONS)}
    return sorted(found, key=lambda n: (order.get(n, 999), n))


def read_pair(pair: str, name: str):
    path = RESULTS_DIR / pair / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def read_traj(evolution: str, metric: str):
    path = RESULTS_DIR / evolution / f"trajectories_{metric}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def is_cross_kg_pair(pair: str) -> bool:
    """Heuristic: the only pairs mixing 'yago' and 'dbpedia' in their name are
    genuinely cross-KG; version pairs only ever mix same-KG labels."""
    return "yago" in pair and "dbpedia" in pair


CHURN_PAIRS = discover_pairs("class_churn.json")
DIFF_PAIRS = discover_pairs("triple_diff.json")
VOCAB_PAIRS = discover_pairs("vocab_evolution.json")
CROSSKG_PAIRS = discover_pairs("cross_kg.json")
EVOLUTIONS = discover_evolutions()
TRAJ_METRICS = ["graph_shape", "class_population", "property_entropy",
                "class_entropy", "entity_informativeness", "entropy_pagerank"]


# ---------------- shared UI helpers ----------------

def metric_header(mid: str):
    """Name, one-line explanation and formula card at the top of every tab."""
    m = META[mid]
    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md "
                            "bg-blue-50 dark:bg-slate-800"):
        with ui.row().classes("items-baseline gap-2 no-wrap"):
            ui.label(f"{m['num']}. {m['name']}").classes("text-lg font-bold")
            ui.badge(m["level"]).props("color=indigo outline")
        ui.label(m["blurb"]).classes("text-sm text-gray-600 dark:text-gray-300 q-mt-xs")
        ui.label(m["formula"]).classes(
            "font-mono text-sm bg-white dark:bg-slate-900 rounded-lg "
            "q-pa-sm q-mt-xs inline-block")


def grouped_bar(title, categories, series, unit, axis="value", height=460):
    """Horizontal bars, one series per snapshot, categories shared."""
    ui.echart({
        "title": {"text": title, "left": "center",
                  "textStyle": {"fontSize": 15, "fontWeight": 600}},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"bottom": 0, "type": "scroll"},
        "toolbox": {"feature": {"saveAsImage": {"title": "save"}}, "right": 10},
        "grid": {"left": 200, "right": 80, "top": 46, "bottom": 46,
                 "containLabel": False},
        "xAxis": {"type": axis, "name": unit,
                  "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}},
        "yAxis": {"type": "category", "data": categories,
                  "axisLabel": {"fontSize": 11}},
        "series": [{"name": name, "type": "bar", "data": values,
                    "barMaxWidth": 14,
                    "itemStyle": {"borderRadius": [0, 6, 6, 0],
                                  "color": COLOR.get(name, PALETTE[0])}}
                   for name, values in series],
    }).classes("w-full").style(f"height: {height}px")


def small_multiples(title, panels, render_one, min_w="260px"):
    """A titled card holding a wrapping row of small charts, one per panel."""
    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        if title:
            ui.label(title).classes("text-base font-semibold q-mb-sm text-center")
        with ui.row().classes("w-full gap-4 flex-wrap justify-center"):
            for panel in panels:
                with ui.column().classes("flex-1").style(f"min-width:{min_w}"):
                    render_one(panel)


def small_bar(subtitle, categories, values, color, unit="", height=None):
    height = height or max(220, 22 * len(categories) + 70)
    ui.echart({
        "title": {"text": subtitle, "left": "center", "textStyle": {"fontSize": 12}},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 140, "right": 20, "top": 34, "bottom": 20},
        "xAxis": {"type": "value", "name": unit},
        "yAxis": {"type": "category", "data": categories,
                  "axisLabel": {"fontSize": 10}},
        "series": [{"type": "bar", "data": values, "barMaxWidth": 12,
                    "itemStyle": {"color": color, "borderRadius": [0, 4, 4, 0]}}],
    }).classes("w-full").style(f"height:{height}px")


def stat_bar(subtitle, categories, values, colors, height=210):
    ui.echart({
        "title": {"text": subtitle, "left": "center", "textStyle": {"fontSize": 12}},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 46, "right": 16, "top": 34, "bottom": 46},
        "xAxis": {"type": "category", "data": categories,
                  "axisLabel": {"fontSize": 9, "interval": 0, "rotate": 20}},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": [
            {"value": v, "itemStyle": {"color": c}} for v, c in zip(values, colors)],
            "barMaxWidth": 34}],
    }).classes("w-full").style(f"height:{height}px")


def line_chart(title, x_labels, series, unit="", height=380):
    ui.echart({
        "title": {"text": title, "left": "center",
                  "textStyle": {"fontSize": 13, "fontWeight": 600}},
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0, "type": "scroll"},
        "grid": {"left": 60, "right": 30, "top": 40, "bottom": 56},
        "xAxis": {"type": "category", "data": x_labels},
        "yAxis": {"type": "value", "name": unit},
        "series": [{"name": name, "type": "line", "data": vals,
                    "symbolSize": 7, "smooth": False}
                   for name, vals in series],
    }).classes("w-full").style(f"height:{height}px")


def donut(title, items, height=280):
    """items: list of (name, value)."""
    ui.echart({
        "title": {"text": title, "left": "center", "textStyle": {"fontSize": 13}},
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"bottom": 0},
        "series": [{"type": "pie", "radius": ["38%", "68%"],
                    "avoidLabelOverlap": True,
                    "label": {"formatter": "{b}\n{c}"},
                    "data": [{"name": n, "value": v} for n, v in items]}],
    }).classes("w-full").style(f"height:{height}px")


def kpi_row(items):
    """items: list of (value, caption)."""
    with ui.row().classes("gap-4 justify-center w-full"):
        for value, caption in items:
            with ui.card().classes("items-center q-pa-md rounded-2xl min-w-[160px]"):
                ui.label(str(value)).classes("text-xl font-bold")
                ui.label(caption).classes(
                    "text-xs text-gray-500 uppercase tracking-wide text-center")


def table(columns, rows, caption):
    """A dense, sortable result table under a chart."""
    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        ui.label(caption).classes("text-base font-semibold q-mb-sm")
        ui.table(columns=columns, rows=rows, pagination=12) \
            .classes("w-full").props("flat bordered dense")


def empty(message: str):
    with ui.card().classes("w-full items-center q-pa-xl rounded-2xl shadow-md"):
        ui.icon("inbox", size="42px").classes("text-gray-400")
        ui.label(message).classes("text-lg font-medium")


def controls(state, refresh, *, passes=True, extra=None):
    """The control strip every snapshot-based tab shares: snapshots, pass,
    and a tab-specific widget built by `extra`."""
    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        with ui.row().classes("items-center gap-6 w-full"):
            ui.icon("tune").classes("text-gray-400")
            ui.select(LABELS, value=state["labels"], multiple=True,
                      label="Snapshots",
                      on_change=lambda e: (state.update(labels=e.value), refresh())) \
                .classes("w-96").props("outlined dense options-dense use-chips")
            if passes:
                ui.toggle({"_pinned": "pinned", "": "descriptive"},
                          value=state["pass"],
                          on_change=lambda e: (state.update({"pass": e.value}),
                                               refresh())) \
                    .props("dense")
            if extra:
                extra()
        if passes and state["pass"] == "":
            ui.label("Descriptive pass: each snapshot picks its own top-8 classes, "
                     "so classes may be missing from a snapshot and the sets are "
                     "not comparable — use the pinned pass to compare.") \
                .classes("text-xs text-orange-600 q-mt-sm")


def pair_controls(state, refresh, pairs, *, extra=None):
    """Control strip for the 2-endpoint tabs: pick one comparison pair."""
    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        with ui.row().classes("items-center gap-6 w-full"):
            ui.icon("compare_arrows").classes("text-gray-400")
            ui.select(pairs, value=state["pair"], label="Comparison",
                      on_change=lambda e: (state.update({"pair": e.value}), refresh())) \
                .classes("w-96").props("outlined dense options-dense")
            if extra:
                extra()


# ============================================================ metric 1: class population

pop_state = {"labels": list(DEFAULT), "pass": "_pinned", "topn": 15}


@ui.refreshable
def population_view():
    labels = pop_state["labels"]
    if not labels:
        return empty("No snapshot selected")

    keys = class_keys(labels, "class_population")[: pop_state["topn"]]
    names = [display_name(k, labels, "class_population") for k in keys]
    series = []
    for label in labels:
        classes = entries(label, "class_population")
        values = []
        for key in keys:
            hit = next((v for i, v in classes.items() if canon(i) == key), None)
            values.append(hit["population"] if hit else None)
        series.append((label, list(reversed(values))))

    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        grouped_bar(f"Class population — top {len(keys)} classes",
                    list(reversed(names)), series, "entities (log scale)",
                    axis="log", height=max(360, 34 * len(keys) + 120))

    rows = []
    for key, name in zip(keys, names):
        row = {"class": name}
        for label in labels:
            classes = entries(label, "class_population")
            hit = next(((i, v) for i, v in classes.items() if canon(i) == key), None)
            row[label] = f"{hit[1]['population']:,} ({hit[1]['share'] * 100:.2f}%)" \
                if hit else "—"
            row[f"iri_{label}"] = hit[0] if hit else ""
        rows.append(row)
    cols = [{"name": "class", "label": "Class", "field": "class", "align": "left"}]
    cols += [{"name": l, "label": l, "field": l, "align": "right"} for l in labels]
    table(cols, rows, "Population and share of all typed entities")

    kpi_row([((f"{(data[l]['class_population'] or {}).get('total_entities'):,}"
               if (data[l]["class_population"] or {}).get("total_entities") else "—"),
              f"{l} — typed entities") for l in labels])


# ============================================================ metric 4: class entropy

ent_state = {"labels": list(DEFAULT), "pass": "_pinned", "which": "object_entropy"}

ENTROPY_FIELDS = {"object_entropy": "object entropy",
                  "predicate_entropy": "predicate entropy"}


@ui.refreshable
def class_entropy_view():
    labels, file = ent_state["labels"], "class_entropy" + ent_state["pass"]
    if not labels:
        return empty("No snapshot selected")

    keys = class_keys(labels, file)
    if not keys:
        return empty("class_entropy was not computed for these snapshots")
    names = [display_name(k, labels, file) for k in keys]
    field = ent_state["which"]
    series = [(label, list(reversed([
        (lookup(label, file, k) or (None, {}))[1].get(field) for k in keys])))
        for label in labels]

    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        grouped_bar(f"Class entropy — {ENTROPY_FIELDS[field]}",
                    list(reversed(names)), series, "bits",
                    height=max(360, 40 * len(keys) + 120))

    rows = []
    for key, name in zip(keys, names):
        for label in labels:
            hit = lookup(label, file, key)
            if not hit:
                continue
            iri, v = hit
            rows.append({
                "class": name, "snapshot": label, "iri": iri,
                "object_entropy": round(v["object_entropy"], 3),
                "predicate_entropy": round(v["predicate_entropy"], 3),
                "triples": f"{int(v['triples']):,}",
                "distinct_objects": f"{int(v['distinct_objects']):,}",
                "distinct_predicates": int(v["distinct_predicates"]),
            })
    cols = [
        {"name": "class", "label": "Class", "field": "class", "align": "left"},
        {"name": "snapshot", "label": "Snapshot", "field": "snapshot", "align": "left"},
        {"name": "object_entropy", "label": "H(objects) bits",
         "field": "object_entropy", "align": "right", "sortable": True},
        {"name": "predicate_entropy", "label": "H(predicates) bits",
         "field": "predicate_entropy", "align": "right", "sortable": True},
        {"name": "triples", "label": "Triples", "field": "triples", "align": "right"},
        {"name": "distinct_objects", "label": "Distinct objects",
         "field": "distinct_objects", "align": "right"},
        {"name": "distinct_predicates", "label": "Preds",
         "field": "distinct_predicates", "align": "right"},
        {"name": "iri", "label": "Class IRI", "field": "iri", "align": "left"},
    ]
    table(cols, rows, "Per-class entropy (the IRI column shows namespace "
                      "differences between snapshots)")


# ============================================================ metrics 2, 3 & 6: per-predicate values

def per_predicate_view(state, file_base, title, unit, decimals):
    """Metrics 2, 3 and 6 share a shape: class -> predicate -> value."""
    labels, file = state["labels"], file_base + state["pass"]
    if not labels:
        return empty("No snapshot selected")

    keys = class_keys(labels, file)
    if not keys:
        return empty(f"{file_base} was not computed for these snapshots")
    if state["class"] not in keys:
        state["class"] = keys[0]
    key = state["class"]

    # predicates ranked by their best value across the selected snapshots
    best: dict[str, float] = {}
    names: dict[str, str] = {}
    for label in labels:
        hit = lookup(label, file, key)
        for pred, value in (hit[1] if hit else {}).items():
            best[canon(pred)] = max(best.get(canon(pred), 0.0), float(value))
            names.setdefault(canon(pred), short(pred))
    ranked = sorted(best, key=lambda p: best[p], reverse=True)[: state["topn"]]

    series = []
    for label in labels:
        hit = lookup(label, file, key)
        values = {canon(p): float(v) for p, v in (hit[1] if hit else {}).items()}
        series.append((label, list(reversed([values.get(p) for p in ranked]))))

    class_name = display_name(key, labels, file)
    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        grouped_bar(f"{title} — {class_name}, top {len(ranked)} predicates",
                    list(reversed([names[p] for p in ranked])), series, unit,
                    height=max(360, 34 * len(ranked) + 120))

    rows = []
    for pred in ranked:
        row = {"predicate": names[pred]}
        for label in labels:
            hit = lookup(label, file, key)
            values = {canon(p): float(v) for p, v in (hit[1] if hit else {}).items()}
            row[label] = round(values[pred], decimals) if pred in values else "—"
        rows.append(row)
    cols = [{"name": "predicate", "label": "Predicate", "field": "predicate",
             "align": "left"}]
    cols += [{"name": l, "label": l, "field": l, "align": "right", "sortable": True}
             for l in labels]
    table(cols, rows, f"{title} for {class_name} ({len(ranked)} predicates)")


entf_state = {"labels": list(DEFAULT), "pass": "_pinned", "class": None, "topn": 12}
etimp_state = {"labels": list(DEFAULT), "pass": "_pinned", "class": None, "topn": 12}
diversity_state = {"labels": list(DEFAULT), "pass": "_pinned", "class": None, "topn": 12}


@ui.refreshable
def entf_view():
    per_predicate_view(entf_state, "property_entropy",
                       "Property entropy H(p,t)", "bits", 3)


@ui.refreshable
def etimp_view():
    per_predicate_view(etimp_state, "ent_etimp",
                       "Entropy-weighted type importance", "EntETImp", 2)


@ui.refreshable
def diversity_view():
    per_predicate_view(diversity_state, "object_diversity",
                       "Object diversity OD(p,t)", "distinct objects", 0)


def class_picker(state, file_base, refresh):
    """Class dropdown for the per-predicate tabs."""
    keys = class_keys(state["labels"], file_base + state["pass"])
    options = {k: display_name(k, state["labels"], file_base + state["pass"])
               for k in keys}
    ui.select(options, value=state["class"] if state["class"] in keys
              else (keys[0] if keys else None), label="Class",
              on_change=lambda e: (state.update({"class": e.value}), refresh())) \
        .classes("w-64").props("outlined dense options-dense")
    ui.number(label="Top N", value=state["topn"], min=3, max=40, format="%d",
              on_change=lambda e: (state.update(topn=int(e.value or 12)), refresh())) \
        .classes("w-28").props("outlined dense")


# ============================================================ metric 5: entity informativeness

inforank_state = {"labels": list(DEFAULT), "topn": 10}


@ui.refreshable
def inforank_view():
    labels, topn = inforank_state["labels"], inforank_state["topn"]
    if not labels:
        return empty("No snapshot selected")

    def panel(label):
        raw = (data[label].get("entity_informativeness") or {}).get("entities", {})
        ranked = sorted(raw.items(), key=lambda kv: kv[1]["inforank"], reverse=True)[:topn]
        cats = list(reversed([short(iri) for iri, _ in ranked]))
        vals = list(reversed([v["inforank"] for _, v in ranked]))
        small_bar(label, cats, vals, COLOR.get(label, PALETTE[0]), "IR(v)")

    have = [l for l in labels if (data[l].get("entity_informativeness") or {}).get("entities")]
    if not have:
        return empty("entity_informativeness was not computed for these snapshots")
    small_multiples(f"Entity informativeness — top {topn} entities per snapshot",
                     have, panel, min_w="300px")

    rows = []
    for label in have:
        raw = (data[label].get("entity_informativeness") or {}).get("entities", {})
        ranked = sorted(raw.items(), key=lambda kv: kv[1]["inforank"], reverse=True)[:topn]
        for iri, v in ranked:
            rows.append({"snapshot": label, "entity": short(iri),
                         "inforank": round(v["inforank"], 8),
                         "literal_properties": int(v["literal_properties"]),
                         "iri": iri})
    cols = [{"name": "snapshot", "label": "Snapshot", "field": "snapshot", "align": "left"},
            {"name": "entity", "label": "Entity", "field": "entity", "align": "left"},
            {"name": "inforank", "label": "IR(v)", "field": "inforank",
             "align": "right", "sortable": True},
            {"name": "literal_properties", "label": "Literal properties",
             "field": "literal_properties", "align": "right", "sortable": True},
            {"name": "iri", "label": "IRI", "field": "iri", "align": "left"}]
    table(cols, rows, f"Top {topn} entities by informativeness, per snapshot")


# ============================================================ metric 7: entropy-weighted PageRank

pagerank_state = {"labels": list(DEFAULT), "topn": 10, "which": "entropy_weighted"}
PR_FIELDS = {"entropy_weighted": "entropy-weighted PageRank (own variant)",
             "unweighted": "classic PageRank (baseline)"}


@ui.refreshable
def pagerank_view():
    labels, topn = pagerank_state["labels"], pagerank_state["topn"]
    field = pagerank_state["which"]
    rank_field = "rank_weighted" if field == "entropy_weighted" else "rank_unweighted"
    if not labels:
        return empty("No snapshot selected")

    def panel(label):
        raw = (data[label].get("entropy_pagerank") or {}).get("nodes", {})
        ranked = sorted(raw.items(), key=lambda kv: kv[1].get(rank_field, 1e18))[:topn]
        cats = list(reversed([short(iri) for iri, _ in ranked]))
        vals = list(reversed([v.get(field, 0.0) for _, v in ranked]))
        small_bar(label, cats, vals, COLOR.get(label, PALETTE[0]), PR_FIELDS[field])

    have = [l for l in labels if (data[l].get("entropy_pagerank") or {}).get("nodes")]
    if not have:
        return empty("entropy_pagerank was not computed for these snapshots")
    small_multiples(f"Top {topn} nodes by {PR_FIELDS[field]}", have, panel, min_w="300px")

    rows = []
    for label in have:
        raw = (data[label].get("entropy_pagerank") or {}).get("nodes", {})
        ranked = sorted(raw.items(), key=lambda kv: kv[1].get(rank_field, 1e18))[:topn]
        for iri, v in ranked:
            rows.append({"snapshot": label, "node": short(iri),
                         "entropy_weighted": round(v.get("entropy_weighted", 0.0), 4),
                         "unweighted": round(v.get("unweighted", 0.0), 4),
                         "rank_weighted": v.get("rank_weighted"),
                         "rank_unweighted": v.get("rank_unweighted"),
                         "rank_shift": v.get("rank_shift")})
    cols = [{"name": "snapshot", "label": "Snapshot", "field": "snapshot", "align": "left"},
            {"name": "node", "label": "Node", "field": "node", "align": "left"},
            {"name": "entropy_weighted", "label": "PR (weighted)",
             "field": "entropy_weighted", "align": "right", "sortable": True},
            {"name": "unweighted", "label": "PR (unweighted)",
             "field": "unweighted", "align": "right", "sortable": True},
            {"name": "rank_weighted", "label": "Rank (w)",
             "field": "rank_weighted", "align": "right", "sortable": True},
            {"name": "rank_unweighted", "label": "Rank (unw)",
             "field": "rank_unweighted", "align": "right", "sortable": True},
            {"name": "rank_shift", "label": "Rank shift",
             "field": "rank_shift", "align": "right", "sortable": True}]
    table(cols, rows, "Entropy-weighted vs. classic PageRank — rank_shift shows "
                      "the thesis's own contribution moving nodes up or down")


# ============================================================ metric 8: graph shape

SHAPE_FIELDS = [
    ("triples", "Triples"), ("typed_entities", "Typed entities"),
    ("distinct_subjects", "Distinct subjects"), ("distinct_objects", "Distinct objects"),
    ("predicates", "Predicates"), ("classes", "Classes"),
    ("avg_in_degree", "Avg in-degree"), ("avg_out_degree", "Avg out-degree"),
    ("density_triples_per_entity", "Density (triples/entity)"),
]

shape_state = {"labels": list(DEFAULT)}


@ui.refreshable
def shape_view():
    labels = shape_state["labels"]
    if not labels:
        return empty("No snapshot selected")
    have = [l for l in labels if data[l].get("graph_shape")]
    if not have:
        return empty("graph_shape was not computed for these snapshots")

    def panel(field_title):
        field, title = field_title
        vals = [data[l]["graph_shape"].get(field) for l in have]
        colors = [COLOR.get(l, PALETTE[0]) for l in have]
        stat_bar(title, have, vals, colors)

    small_multiples("Graph size & shape — vital statistics", SHAPE_FIELDS, panel,
                     min_w="240px")

    rows = [{"snapshot": l, **{title: (f"{data[l]['graph_shape'].get(field):,.2f}"
                                        if data[l]["graph_shape"].get(field) is not None else "—")
                                for field, title in SHAPE_FIELDS}}
            for l in have]
    cols = [{"name": "snapshot", "label": "Snapshot", "field": "snapshot", "align": "left"}]
    cols += [{"name": title, "label": title, "field": title, "align": "right"}
             for _, title in SHAPE_FIELDS]
    table(cols, rows, "All shape statistics, per snapshot")


# ============================================================ metric 9: churn

churn_state = {"pair": CHURN_PAIRS[0] if CHURN_PAIRS else None, "topn": 15}


@ui.refreshable
def churn_view():
    pair = churn_state["pair"]
    if not pair:
        return empty("No churn results found — run metric 9 for a version pair")
    raw = read_pair(pair, "class_churn") or {}
    if not raw:
        return empty(f"class_churn.json not found for {pair}")
    items = sorted(raw.items(), key=lambda kv: kv[1]["churn"], reverse=True)[:churn_state["topn"]]
    cats = list(reversed([short(i) for i, _ in items]))

    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        grouped_bar(f"Class-level churn — {pair}", cats,
                    [("churn %", list(reversed([v["churn"] * 100 for _, v in items])))],
                    "% of v1 triples changed",
                    height=max(360, 32 * len(items) + 120))

    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        ui.label(f"Added / deleted / unchanged triples per class — {pair}") \
            .classes("text-base font-semibold q-mb-sm")
        ui.echart({
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {"bottom": 0},
            "grid": {"left": 160, "right": 60, "top": 20, "bottom": 40},
            "xAxis": {"type": "value", "name": "triples"},
            "yAxis": {"type": "category", "data": cats, "axisLabel": {"fontSize": 11}},
            "series": [
                {"name": "added", "type": "bar", "stack": "t",
                 "data": list(reversed([v["added"] for _, v in items])),
                 "itemStyle": {"color": "#10b981"}},
                {"name": "unchanged", "type": "bar", "stack": "t",
                 "data": list(reversed([v["unchanged"] for _, v in items])),
                 "itemStyle": {"color": "#94a3b8"}},
                {"name": "deleted", "type": "bar", "stack": "t",
                 "data": list(reversed([v["deleted"] for _, v in items])),
                 "itemStyle": {"color": "#ef4444"}},
            ],
        }).classes("w-full").style(f"height:{max(360, 32 * len(items) + 120)}px")

    rows = [{"class": short(i), "churn": f"{v['churn'] * 100:.1f}%",
             "added": f"{v['added']:,}", "deleted": f"{v['deleted']:,}",
             "unchanged": f"{v['unchanged']:,}",
             "triples_v1": f"{v['triples_v1']:,}", "triples_v2": f"{v['triples_v2']:,}",
             "iri": i} for i, v in items]
    cols = [{"name": c, "label": c.replace("_", " ").title(), "field": c,
             "align": "left" if c in ("class", "iri") else "right",
             "sortable": c not in ("class", "iri")}
            for c in ["class", "churn", "added", "deleted", "unchanged",
                      "triples_v1", "triples_v2", "iri"]]
    table(cols, rows, f"Class churn, {pair} (top {len(items)} by churn rate)")


# ============================================================ metric 10: triple diff

diff_state = {"pair": DIFF_PAIRS[0] if DIFF_PAIRS else None}


@ui.refreshable
def diff_view():
    pair = diff_state["pair"]
    if not pair:
        return empty("No triple-diff results found")
    d = read_pair(pair, "triple_diff")
    if not d:
        return empty(f"triple_diff.json not found for {pair}")

    if is_cross_kg_pair(pair):
        with ui.card().classes(
                "w-full q-pa-md rounded-2xl bg-orange-50 dark:bg-orange-900/30"):
            ui.label("⚠ Metric 10 (triple diff) compares two VERSIONS of one KG. "
                     f"'{pair}' mixes YAGO and DBpedia, whose subject IRIs are "
                     "disjoint — every triple of one side reports as 'added', which "
                     "is arithmetically correct but not meaningful. Use metric 13 "
                     "(cross-KG comparison) for cross-KG pairs instead.") \
                .classes("text-sm text-orange-800 dark:text-orange-200")

    kpi_row([
        (f"{d['added']:,}", "added"), (f"{d['deleted']:,}", "deleted"),
        (f"{d['unchanged']:,}", "unchanged"), (f"{d['churn'] * 100:.1f}%", "churn"),
        (d.get("scope", "—"), "scope class"),
        (f"{d.get('subjects_compared', 0):,}", "subjects compared"),
    ])

    with ui.row().classes("w-full gap-4 flex-wrap"):
        with ui.column().classes("flex-1").style("min-width:320px"):
            with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
                donut(f"Triple diff — {pair} ({d.get('scope', '')})",
                      [("added", d["added"]), ("deleted", d["deleted"]),
                       ("unchanged", d["unchanged"])])
        bench = d.get("benchmark")
        if bench:
            with ui.column().classes("flex-1").style("min-width:320px"):
                with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
                    ui.label("Efficiency: integer-encoded vs. naive string sets") \
                        .classes("text-sm font-semibold text-center q-mb-sm")
                    stat_bar("time (ms)", ["integer-encoded", "naive strings"],
                             [bench["encoded_ms"], bench["naive_ms"]], PAIR_COLORS, height=180)
                    stat_bar("memory (bytes)", ["integer-encoded", "naive strings"],
                             [bench["encoded_bytes"], bench["naive_bytes"]], PAIR_COLORS, height=180)
                    ui.label(f"{bench['speedup']:.1f}× faster").classes(
                        "text-center text-sm text-gray-500 q-mt-xs")

    rows = [{"field": k, "value": (f"{v:,}" if isinstance(v, (int, float)) and
                                    not isinstance(v, bool) and abs(v) >= 1 else str(v))}
            for k, v in d.items() if k != "benchmark"]
    table([{"name": "field", "label": "Field", "field": "field", "align": "left"},
           {"name": "value", "label": "Value", "field": "value", "align": "right"}],
          rows, f"All triple_diff fields — {pair}")


# ============================================================ metric 12: vocabulary evolution

vocab_state = {"pair": VOCAB_PAIRS[0] if VOCAB_PAIRS else None}
VOCAB_ROW_CAP = 300


@ui.refreshable
def vocab_view():
    pair = vocab_state["pair"]
    if not pair:
        return empty("No vocabulary-evolution results found")
    d = read_pair(pair, "vocab_evolution")
    if not d:
        return empty(f"vocab_evolution.json not found for {pair}")

    classes, preds = d.get("classes", {}), d.get("predicates", {})

    with ui.row().classes("w-full gap-4 flex-wrap"):
        for section, raw in (("Classes", classes), ("Predicates", preds)):
            added, removed = raw.get("added", []), raw.get("removed", [])
            kept = raw.get("kept", 0)
            with ui.column().classes("flex-1").style("min-width:320px"):
                with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
                    donut(f"{section} — {pair}",
                          [("added", len(added)), ("kept", kept), ("removed", len(removed))])

    for section, raw in (("Classes", classes), ("Predicates", preds)):
        added, removed = raw.get("added", []), raw.get("removed", [])
        rows = ([{"change": "added", "term": short(i), "iri": i} for i in added[:VOCAB_ROW_CAP]]
                + [{"change": "removed", "term": short(i), "iri": i} for i in removed[:VOCAB_ROW_CAP]])
        cap_note = ""
        if len(added) > VOCAB_ROW_CAP or len(removed) > VOCAB_ROW_CAP:
            cap_note = f" (showing first {VOCAB_ROW_CAP} of each — {len(added):,} added, {len(removed):,} removed total)"
        table([{"name": "change", "label": "Change", "field": "change", "align": "left"},
               {"name": "term", "label": "Term", "field": "term", "align": "left"},
               {"name": "iri", "label": "IRI", "field": "iri", "align": "left"}],
              rows, f"{section} added/removed — {pair}{cap_note}")


# ============================================================ metric 13: cross-KG

crosskg_state = {"pair": CROSSKG_PAIRS[0] if CROSSKG_PAIRS else None}


@ui.refreshable
def crosskg_view():
    pair = crosskg_state["pair"]
    if not pair:
        return empty("No cross-KG results found")
    d = read_pair(pair, "cross_kg")
    if not d:
        return empty(f"cross_kg.json not found for {pair}")
    classes = d.get("classes", {})
    if not classes:
        return empty(f"No matched classes in {pair}")
    cats = list(classes.keys())
    kg_a, kg_b = d.get("kg_a", "A"), d.get("kg_b", "B")

    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        grouped_bar(f"Population — {kg_a} vs {kg_b}",
                    [c.title() for c in cats],
                    [(kg_a, [classes[c]["a"]["population"] for c in cats]),
                     (kg_b, [classes[c]["b"]["population"] for c in cats])],
                    "entities", axis="log", height=max(320, 34 * len(cats) + 120))

    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        grouped_bar(f"Class entropy — {kg_a} vs {kg_b}",
                    [c.title() for c in cats],
                    [(kg_a, [classes[c]["a"]["class_entropy"] for c in cats]),
                     (kg_b, [classes[c]["b"]["class_entropy"] for c in cats])],
                    "bits", height=max(320, 34 * len(cats) + 120))

    rows = [{"class": c.title(), "iri_a": classes[c]["a"]["iri"],
             "population_a": f"{classes[c]['a']['population']:,.0f}",
             "iri_b": classes[c]["b"]["iri"],
             "population_b": f"{classes[c]['b']['population']:,.0f}",
             "delta_share": f"{classes[c]['delta_share']:+.3f}",
             "H_a": round(classes[c]["a"]["class_entropy"], 2),
             "H_b": round(classes[c]["b"]["class_entropy"], 2)} for c in cats]
    cols = [{"name": "class", "label": "Class", "field": "class", "align": "left"},
            {"name": "population_a", "label": f"Pop. A", "field": "population_a", "align": "right"},
            {"name": "population_b", "label": f"Pop. B", "field": "population_b", "align": "right"},
            {"name": "delta_share", "label": "Δ share", "field": "delta_share", "align": "right"},
            {"name": "H_a", "label": "H(A)", "field": "H_a", "align": "right"},
            {"name": "H_b", "label": "H(B)", "field": "H_b", "align": "right"},
            {"name": "iri_a", "label": "IRI (A)", "field": "iri_a", "align": "left"},
            {"name": "iri_b", "label": "IRI (B)", "field": "iri_b", "align": "left"}]
    table(cols, rows, f"Cross-KG class comparison — {kg_a} (A) vs {kg_b} (B)")


# ============================================================ metric 11: trajectories

traj_state = {"evolution": EVOLUTIONS[0] if EVOLUTIONS else None,
              "metric": "graph_shape", "topk": 8}


@ui.refreshable
def trajectories_view():
    ev, m = traj_state["evolution"], traj_state["metric"]
    if not ev:
        return empty("No trajectory results found — run metric 11 across 3+ snapshots")
    d = read_traj(ev, m)
    if not d:
        return empty(f"trajectories_{m}.json not found for {ev}")
    snaps, series = d["snapshots"], d["series"]

    if m == "graph_shape":
        def panel(field_title):
            field, title = field_title
            s = series.get(field)
            if not s:
                return
            line_chart(title, snaps, [(title, s["values"])], height=260)
        small_multiples(f"Graph shape trajectory — {ev}", SHAPE_FIELDS, panel,
                         min_w="260px")
        ranked = [(f, series[f]) for f, _ in SHAPE_FIELDS if f in series]
    else:
        ranked = sorted(series.items(),
                        key=lambda kv: abs(kv[1].get("relative_change") or 0),
                        reverse=True)[: traj_state["topk"]]
        with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
            line_chart(f"{m} trajectory — top {len(ranked)} by |relative change| — {ev}",
                       snaps, [(traj_label(k), s["values"]) for k, s in ranked],
                       height=420)

    rows = []
    for key, s in ranked:
        row = {"series": traj_label(key) if m != "graph_shape" else key}
        for snap, val in zip(snaps, s["values"]):
            row[snap] = round(val, 4) if isinstance(val, (int, float)) else val
        row["relative_change"] = f"{s.get('relative_change', 0) * 100:+.1f}%" \
            if s.get("relative_change") is not None else "—"
        rows.append(row)
    cols = [{"name": "series", "label": "Series", "field": "series", "align": "left"}]
    cols += [{"name": s, "label": s, "field": s, "align": "right"} for s in snaps]
    cols += [{"name": "relative_change", "label": "Δ relative",
              "field": "relative_change", "align": "right", "sortable": True}]
    table(cols, rows, f"{m} trajectory across {' → '.join(snaps)}")


# ---------------- page ----------------

@ui.page("/")
def index():
    dark = ui.dark_mode()

    with ui.header().classes(
            "items-center q-py-md q-px-lg shadow-lg "
            "bg-gradient-to-r from-blue-700 via-indigo-700 to-violet-700"):
        ui.icon("hub", size="34px").classes("text-white")
        with ui.column().classes("gap-0"):
            ui.label("KG Metrics Dashboard").classes(
                "text-2xl font-bold text-white leading-tight")
            ui.label("All 13 thesis metrics — phases 1-3 across snapshots") \
                .classes("text-xs text-blue-100")
        ui.space()
        ui.chip(f"{len(LABELS)} snapshots", icon="storage") \
            .classes("bg-white/15 text-white")
        ui.switch(on_change=lambda e: dark.enable() if e.value else dark.disable()) \
            .props('checked-icon="dark_mode" unchecked-icon="light_mode" color="amber"') \
            .tooltip("dark mode")

    with ui.column().classes("w-full max-w-6xl mx-auto q-pa-md gap-4"):
        if not LABELS:
            empty(f"No results found under {RESULTS_DIR}")
            return

        with ui.tabs().classes("w-full") as phases:
            p1 = ui.tab("Phase 1 · Class-level", icon="category")
            p2 = ui.tab("Phase 2 · Entity-level", icon="person")
            p3 = ui.tab("Phase 3 · Global", icon="public")

        with ui.tab_panels(phases, value=p1).classes("w-full bg-transparent"):

            # ---------------- phase 1 ----------------
            with ui.tab_panel(p1).classes("q-pa-none gap-4"):
                with ui.tabs().classes("w-full") as t1:
                    t_pop = ui.tab("1 · Population", icon="groups")
                    t_entf = ui.tab("2 · Property entropy", icon="insights")
                    t_etimp = ui.tab("3 · EntETImp", icon="star_rate")
                    t_ent = ui.tab("4 · Class entropy", icon="scatter_plot")
                with ui.tab_panels(t1, value=t_pop).classes("w-full bg-transparent"):
                    with ui.tab_panel(t_pop).classes("q-pa-none gap-4"):
                        metric_header("population")
                        controls(pop_state, population_view.refresh, passes=False,
                                 extra=lambda: ui.number(
                                     label="Top N", value=pop_state["topn"], min=3, max=40,
                                     format="%d",
                                     on_change=lambda e: (
                                         pop_state.update(topn=int(e.value or 15)),
                                         population_view.refresh())
                                 ).classes("w-28").props("outlined dense"))
                        population_view()

                    with ui.tab_panel(t_entf).classes("q-pa-none gap-4"):
                        metric_header("entf")
                        controls(entf_state, entf_view.refresh,
                                 extra=lambda: class_picker(entf_state, "property_entropy",
                                                            entf_view.refresh))
                        entf_view()

                    with ui.tab_panel(t_etimp).classes("q-pa-none gap-4"):
                        metric_header("entetimp")
                        controls(etimp_state, etimp_view.refresh,
                                 extra=lambda: class_picker(etimp_state, "ent_etimp",
                                                            etimp_view.refresh))
                        etimp_view()

                    with ui.tab_panel(t_ent).classes("q-pa-none gap-4"):
                        metric_header("classentropy")
                        controls(ent_state, class_entropy_view.refresh,
                                 extra=lambda: ui.toggle(
                                     ENTROPY_FIELDS, value=ent_state["which"],
                                     on_change=lambda e: (ent_state.update(which=e.value),
                                                          class_entropy_view.refresh())
                                 ).props("dense"))
                        class_entropy_view()

            # ---------------- phase 2 ----------------
            with ui.tab_panel(p2).classes("q-pa-none gap-4"):
                with ui.tabs().classes("w-full") as t2:
                    t_info = ui.tab("5 · Entity informativeness", icon="person_search")
                    t_div = ui.tab("6 · Object diversity", icon="scatter_plot")
                with ui.tab_panels(t2, value=t_info).classes("w-full bg-transparent"):
                    with ui.tab_panel(t_info).classes("q-pa-none gap-4"):
                        metric_header("inforank")
                        with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
                            with ui.row().classes("items-center gap-6 w-full"):
                                ui.icon("tune").classes("text-gray-400")
                                ui.select(LABELS, value=inforank_state["labels"], multiple=True,
                                          label="Snapshots",
                                          on_change=lambda e: (inforank_state.update(labels=e.value),
                                                               inforank_view.refresh())) \
                                    .classes("w-96").props("outlined dense options-dense use-chips")
                                ui.number(label="Top N", value=inforank_state["topn"], min=3, max=30,
                                          format="%d",
                                          on_change=lambda e: (
                                              inforank_state.update(topn=int(e.value or 10)),
                                              inforank_view.refresh())
                                          ).classes("w-28").props("outlined dense")
                        inforank_view()

                    with ui.tab_panel(t_div).classes("q-pa-none gap-4"):
                        metric_header("diversity")
                        controls(diversity_state, diversity_view.refresh,
                                 extra=lambda: class_picker(diversity_state, "object_diversity",
                                                            diversity_view.refresh))
                        diversity_view()

            # ---------------- phase 3 ----------------
            with ui.tab_panel(p3).classes("q-pa-none gap-4"):
                with ui.tabs().classes("w-full") as t3:
                    t_pr = ui.tab("7 · Entropy PageRank", icon="account_tree")
                    t_shape = ui.tab("8 · Graph shape", icon="hub")
                    t_churn = ui.tab("9 · Churn", icon="autorenew")
                    t_diff = ui.tab("10 · Triple diff", icon="difference")
                    t_traj = ui.tab("11 · Trajectories", icon="timeline")
                    t_vocab = ui.tab("12 · Vocab evolution", icon="menu_book")
                    t_cross = ui.tab("13 · Cross-KG", icon="compare")
                with ui.tab_panels(t3, value=t_pr).classes("w-full bg-transparent"):

                    with ui.tab_panel(t_pr).classes("q-pa-none gap-4"):
                        metric_header("entropy_pagerank")
                        with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
                            with ui.row().classes("items-center gap-6 w-full"):
                                ui.icon("tune").classes("text-gray-400")
                                ui.select(LABELS, value=pagerank_state["labels"], multiple=True,
                                          label="Snapshots",
                                          on_change=lambda e: (pagerank_state.update(labels=e.value),
                                                               pagerank_view.refresh())) \
                                    .classes("w-80").props("outlined dense options-dense use-chips")
                                ui.toggle(PR_FIELDS, value=pagerank_state["which"],
                                          on_change=lambda e: (pagerank_state.update(which=e.value),
                                                               pagerank_view.refresh())) \
                                    .props("dense")
                                ui.number(label="Top N", value=pagerank_state["topn"], min=3, max=30,
                                          format="%d",
                                          on_change=lambda e: (
                                              pagerank_state.update(topn=int(e.value or 10)),
                                              pagerank_view.refresh())
                                          ).classes("w-28").props("outlined dense")
                        pagerank_view()

                    with ui.tab_panel(t_shape).classes("q-pa-none gap-4"):
                        metric_header("shape")
                        controls(shape_state, shape_view.refresh, passes=False)
                        shape_view()

                    with ui.tab_panel(t_churn).classes("q-pa-none gap-4"):
                        metric_header("churn")
                        if not CHURN_PAIRS:
                            empty("No churn results found")
                        else:
                            pair_controls(churn_state, churn_view.refresh, CHURN_PAIRS,
                                          extra=lambda: ui.number(
                                              label="Top N", value=churn_state["topn"],
                                              min=3, max=50, format="%d",
                                              on_change=lambda e: (
                                                  churn_state.update(topn=int(e.value or 15)),
                                                  churn_view.refresh())
                                          ).classes("w-28").props("outlined dense"))
                            churn_view()

                    with ui.tab_panel(t_diff).classes("q-pa-none gap-4"):
                        metric_header("diff")
                        if not DIFF_PAIRS:
                            empty("No triple-diff results found")
                        else:
                            pair_controls(diff_state, diff_view.refresh, DIFF_PAIRS)
                            diff_view()

                    with ui.tab_panel(t_traj).classes("q-pa-none gap-4"):
                        metric_header("trajectories")
                        if not EVOLUTIONS:
                            empty("No trajectory results found")
                        else:
                            with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
                                with ui.row().classes("items-center gap-6 w-full"):
                                    ui.icon("tune").classes("text-gray-400")
                                    ui.select(EVOLUTIONS, value=traj_state["evolution"],
                                              label="Evolution series",
                                              on_change=lambda e: (
                                                  traj_state.update({"evolution": e.value}),
                                                  trajectories_view.refresh())) \
                                        .classes("w-56").props("outlined dense options-dense")
                                    ui.select(TRAJ_METRICS, value=traj_state["metric"],
                                              label="Underlying metric",
                                              on_change=lambda e: (
                                                  traj_state.update({"metric": e.value}),
                                                  trajectories_view.refresh())) \
                                        .classes("w-56").props("outlined dense options-dense")
                                    ui.number(label="Top K series", value=traj_state["topk"],
                                              min=3, max=30, format="%d",
                                              on_change=lambda e: (
                                                  traj_state.update(topk=int(e.value or 8)),
                                                  trajectories_view.refresh())
                                              ).classes("w-32").props("outlined dense")
                            trajectories_view()

                    with ui.tab_panel(t_vocab).classes("q-pa-none gap-4"):
                        metric_header("vocab")
                        if not VOCAB_PAIRS:
                            empty("No vocabulary-evolution results found")
                        else:
                            pair_controls(vocab_state, vocab_view.refresh, VOCAB_PAIRS)
                            vocab_view()

                    with ui.tab_panel(t_cross).classes("q-pa-none gap-4"):
                        metric_header("crosskg")
                        if not CROSSKG_PAIRS:
                            empty("No cross-KG results found")
                        else:
                            pair_controls(crosskg_state, crosskg_view.refresh, CROSSKG_PAIRS)
                            crosskg_view()

        ui.label("Bachelor thesis — Efficient Metrics and Visual Analytics for "
                 "Comparing Evolving Knowledge Graphs") \
            .classes("text-xs text-gray-400 self-center q-mt-md")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(port=8080, title="KG Metrics Dashboard", reload=False, show=False)

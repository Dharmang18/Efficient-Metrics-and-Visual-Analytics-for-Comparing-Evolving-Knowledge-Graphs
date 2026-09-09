"""
niceGUI dashboard for the thesis metrics — phase 1 (class-level metrics).

One tab per metric, snapshots selected inside it, so the same metric can be read
across YAGO 4, YAGO 4.5.0.2 and DBpedia in a single chart. That is the comparison
the thesis is about; a tab per snapshot would hide it.

Reads rust_metrics/results/<label>/<metric>.json — the layout run_phase.sh writes.
Per-class metrics exist in two passes (see CLASS_MAPPING.md):
  descriptive  each snapshot's own top-N classes   <metric>.json
  pinned       the fixed, comparable class list     <metric>_pinned.json
Only the pinned pass is comparable across snapshots, so the pass toggle warns
when descriptive numbers from different snapshots are put side by side.

Run:   python dashboard.py     then open http://localhost:8080
"""
import json
from pathlib import Path
from nicegui import ui

RESULTS_DIR = Path(__file__).parent / "rust_metrics" / "results"

# Snapshots shown first and selected by default; anything else found on disk
# (older demo runs) is offered but unselected.
# The five thesis snapshots, in evolution order. `dbpedia` (the old full 86-file
# :7013 index) and `olympics`/`yago4-public` remain discoverable but unselected —
# only these five are the compared set.
PREFERRED = ["yago-3", "yago-4", "yago-4.5.0.2",
             "dbpedia-2015", "dbpedia-2016", "dbpedia-2022-matched", "dbpedia-2025"]

# Classes carry different local names in different KGs (CLASS_MAPPING.md pins
# Taxon->Species and Chemical_compound->ChemicalCompound for DBpedia), so the
# comparison key folds the known synonyms together.
SYNONYMS = {"species": "taxon"}

PALETTE = ["#3b82f6", "#f59e0b", "#10b981", "#8b5cf6", "#ef4444", "#14b8a6"]


def short(iri: str) -> str:
    """Trim a long IRI to its readable last segment."""
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def canon(iri: str) -> str:
    """Comparison key for a class or predicate: local name, case- and
    underscore-insensitive, with cross-KG synonyms folded together."""
    key = short(iri).lower().replace("_", "")
    return SYNONYMS.get(key, key)


# ---------------- data loading ----------------

def read(label: str, name: str):
    """Load results/<label>/<name>.json, or None if that metric was not run."""
    path = RESULTS_DIR / label / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


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
         "ent_etimp", "ent_etimp_pinned"]
data = {l: {f: read(l, f) for f in FILES} for l in LABELS}


def entries(label: str, file: str) -> dict:
    """The class -> value mapping inside one snapshot's file. class_population
    nests its classes under a "classes" key, beside the snapshot total; the
    other metrics are keyed by class IRI directly."""
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


# ---------------- shared UI helpers ----------------

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
                                  "color": COLOR[name]}}
                   for name, values in series],
    }).classes("w-full").style(f"height: {height}px")


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
    """The control strip every tab shares: snapshots, pass, and a tab-specific
    widget built by `extra`."""
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


# ---------------- metric 1: class population ----------------

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

    with ui.row().classes("gap-4 justify-center w-full"):
        for label in labels:
            total = (data[label]["class_population"] or {}).get("total_entities")
            with ui.card().classes("items-center q-pa-md rounded-2xl min-w-[180px]"):
                ui.label(f"{total:,}" if total else "—") \
                    .classes("text-xl font-bold")
                ui.label(f"{label} — typed entities") \
                    .classes("text-xs text-gray-500 uppercase tracking-wide")


# ---------------- metric 4: class entropy ----------------

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


# ---------------- metrics 2 & 3: per-predicate values ----------------

def per_predicate_view(state, file_base, title, unit, decimals):
    """Metrics 2 and 3 share a shape: class -> predicate -> value."""
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


@ui.refreshable
def entf_view():
    per_predicate_view(entf_state, "property_entropy",
                       "Property entropy H(p,t)", "bits", 3)


@ui.refreshable
def etimp_view():
    per_predicate_view(etimp_state, "ent_etimp",
                       "Entropy-weighted type importance", "EntETImp", 2)


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
            ui.label("Phase 1 — class-level metrics across snapshots") \
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

        with ui.tabs().classes("w-full") as tabs:
            t_pop = ui.tab("1 · Population", icon="groups")
            t_entf = ui.tab("2 · Property entropy", icon="insights")
            t_etimp = ui.tab("3 · EntETImp", icon="star_rate")
            t_ent = ui.tab("4 · Class entropy", icon="scatter_plot")

        with ui.tab_panels(tabs, value=t_pop).classes("w-full bg-transparent"):
            with ui.tab_panel(t_pop).classes("q-pa-none gap-4"):
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
                controls(entf_state, entf_view.refresh,
                         extra=lambda: class_picker(entf_state, "property_entropy",
                                                    entf_view.refresh))
                entf_view()

            with ui.tab_panel(t_etimp).classes("q-pa-none gap-4"):
                controls(etimp_state, etimp_view.refresh,
                         extra=lambda: class_picker(etimp_state, "ent_etimp",
                                                    etimp_view.refresh))
                etimp_view()

            with ui.tab_panel(t_ent).classes("q-pa-none gap-4"):
                controls(ent_state, class_entropy_view.refresh,
                         extra=lambda: ui.toggle(
                             ENTROPY_FIELDS, value=ent_state["which"],
                             on_change=lambda e: (ent_state.update(which=e.value),
                                                  class_entropy_view.refresh())
                         ).props("dense"))
                class_entropy_view()

        ui.label("Bachelor thesis — Efficient Metrics and Visual Analytics for "
                 "Comparing Evolving Knowledge Graphs") \
            .classes("text-xs text-gray-400 self-center q-mt-md")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(port=8080, title="KG Metrics Dashboard", reload=False, show=False)

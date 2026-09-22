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
import math
from html import escape
import re
from pathlib import Path
import asyncio
from nicegui import app, background_tasks, context, ui
from nicegui.awaitable_response import AwaitableResponse
import copy
from collections.abc import MutableMapping

RESULTS_DIR = Path(__file__).parent / "rust_metrics" / "results"


# ------------------------------------------------------------ per-viewer state
# Every control writes into a module-level dict. Shared, that dict made one
# viewer's toggle change what every other viewer saw, so each state dict keeps
# a private copy per browser tab (NiceGUI client), created from the defaults on
# first use and dropped when the tab goes away.
class PerClient(MutableMapping):
    def __init__(self, defaults: dict):
        self._defaults = defaults
        self._by_client: dict[str, dict] = {}

    def _mine(self) -> dict:
        client = context.client
        d = self._by_client.get(client.id)
        if d is None:
            d = self._by_client[client.id] = copy.deepcopy(self._defaults)
            client.on_delete(lambda cid=client.id: self._by_client.pop(cid, None))
        return d

    def __getitem__(self, key): return self._mine()[key]
    def __setitem__(self, key, value): self._mine()[key] = value
    def __delitem__(self, key): del self._mine()[key]
    def __iter__(self): return iter(self._mine())
    def __len__(self): return len(self._mine())


class client_refreshable(ui.refreshable):
    """ui.refreshable re-renders the view in every open tab; with per-viewer
    state that is wasted work and a visible flicker for the others. Refresh only
    the targets that belong to the tab whose control fired. The tab is captured
    here, in the event handler: the re-render itself runs later in a background
    task where NiceGUI no longer knows which client asked."""
    def refresh(self, *args, **kwargs) -> AwaitableResponse:
        try:
            me = context.client
        except RuntimeError:          # called outside any page: refresh them all
            me = None
        self.prune()
        instance = self.instance

        def run():
            every = self.targets
            if me is not None:
                self.targets = [t for t in every if t.container.client is me]
            try:
                return self._execute_refresh(args, kwargs, instance=instance)
            finally:
                self.targets = every

        def fire_and_forget() -> None:
            if awaitables := run():
                background_tasks.create_or_defer(asyncio.gather(*awaitables),
                                                 name=f"refresh {self.func.__name__}")

        async def wait_for_completion() -> None:
            if awaitables := run():
                await asyncio.gather(*awaitables)

        return AwaitableResponse(fire_and_forget, wait_for_completion)

# The five thesis snapshots, in evolution order. Older demo runs (yago-3,
# dbpedia-2016, yago4-public, ...) remain discoverable but unselected.
PREFERRED = ["yago-3", "yago-4", "yago-4.5.0.2",
             "dbpedia-2015", "dbpedia-2016", "dbpedia-2022-matched", "dbpedia-2025"]

# Early scratch runs that are not thesis snapshots: `olympics` is the QLever
# tutorial dataset used to smoke-test the pipeline, `dbpedia` an unmatched
# full-core run superseded by the dated, matched releases, and `yago4-public`
# a partial run against the public qlever.dev endpoint whose query-memory cap
# left the largest classes unanswered -- superseded by `yago-4` on the home
# server. Their result files are kept on disk; they just never reach the
# snapshot picker.
EXCLUDED = {"olympics", "dbpedia", "yago4-public"}

# Superseded comparison runs. `yago-vs-dbpedia` queried the PUBLIC qlever.dev
# endpoints, whose query-memory cap allowed only one class to be matched; the
# local run `yago-4.5.0.2-vs-dbpedia-2025` replaces it with eight. Keeping the
# old one in the picker invites reading a one-class result as the whole finding.
EXCLUDED_PAIRS = {"yago-vs-dbpedia", "yago4-vs-yago45", "yago4-vs-yago45-local"}

# Pair/evolution folders belonging to the official comparisons, shown first.
# Dropdown order: YAGO first, then DBpedia's consecutive release steps in date
# order, then the decade-wide jump, then cross-KG pairs by release date.
OFFICIAL_PAIRS = ["yago-3-vs-yago-4", "yago-4-vs-yago-4.5.0.2",
                  "dbpedia-2015-vs-2016", "dbpedia-2015-vs-2022",
                  "dbpedia-2022-vs-2025", "dbpedia-2015-vs-2025",
                  "yago-4.5.0.2-vs-dbpedia-2015", "yago-4.5.0.2-vs-dbpedia-2016",
                  "yago-4.5.0.2-vs-dbpedia-2022", "yago-4.5.0.2-vs-dbpedia-2025",
                  "yago-4-vs-dbpedia-2015", "yago-4-vs-dbpedia-2016",
                  "yago-4-vs-dbpedia-2022", "yago-4-vs-dbpedia-2025"]
OFFICIAL_EVOLUTIONS = ["yago-evolution", "dbpedia-evolution"]

# Classes carry different local names in different KGs (CLASS_MAPPING.md pins
# Taxon->Species and Chemical_compound->ChemicalCompound for DBpedia), so the
# comparison key folds the known synonyms together.
SYNONYMS = {"species": "taxon"}

# Okabe-Ito: the colour-blind-safe palette standard in scientific publishing,
# and the same colours the thesis figures use, so a snapshot looks the same in
# the dashboard and in the PDF. Assigned in fixed order, never cycled; a ninth
# snapshot falls back to GREY rather than sharing a colour.
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00",
           "#56B4E9", "#7F6F00", "#1B2430"]
GREY = "#9aa0a6"

# Sequential ramp for the heatmaps: one hue, light -> dark. Magnitude is a
# quantity, so it gets a single-hue ramp, never a categorical rainbow.
SEQ_RAMP = ["#EFF5FB", "#C6DBEF", "#9ECAE1", "#6BAED6", "#4292C6",
            "#2171B5", "#08519C", "#08306B"]
PAIR_COLORS = ["#3b82f6", "#ef4444"]  # A / B, added / deleted, etc.


def short(iri: str) -> str:
    """Trim a long IRI to its readable last segment."""
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


PREFIXES = {
    "http://dbpedia.org/ontology/": "dbo",
    "http://schema.org/": "schema",
    "http://xmlns.com/foaf/0.1/": "foaf",
    "http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#": "dul",
    "http://www.wikidata.org/entity/": "wd",
    "http://www.w3.org/2002/07/owl#": "owl",
    "http://yago-knowledge.org/resource/": "yago",
    "http://bioschemas.org/": "bioschemas",
    "http://www.w3.org/2004/02/skos/core#": "skos",
}


def qname(iri: str) -> str:
    """prefix:local for known namespaces, else the bare local name."""
    for ns, pre in PREFIXES.items():
        if iri.startswith(ns):
            return f"{pre}:{iri[len(ns):]}"
    return short(iri)


_ESCAPE = re.compile(r"_u([0-9A-Fa-f]{4})_")


def pretty_node(iri: str) -> str:
    """An entity IRI as a person would write it. YAGO escapes punctuation inside
    local names (Washington_u002C__D_u002E_C_u002E_), which is unreadable."""
    name = _ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), short(iri))
    return re.sub(r"\s+", " ", name.replace("_", " ")).strip()


def distinct_names(iris: list[str]) -> list[str]:
    """Short names, except where two IRIs share one: DBpedia carries dbo:Person,
    foaf:Person and schema:Person side by side, and three rows all reading
    'Person' look like a bug. Only the colliding names get their prefix."""
    shorts = [short(i) for i in iris]
    clash = {n for n in shorts if shorts.count(n) > 1}
    names = [qname(i) if n in clash else n for i, n in zip(iris, shorts)]
    # YAGO escapes punctuation: Painting__u0028_object_u0029_ -> Painting (object)
    return [_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), n).replace("_(", " (")
            for n in names]


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
# LaTeX for every metric, copied from the equation environments of
# writing/include/approach.tex so the dashboard and Chapter 3 cannot drift apart.
TEX = {
    "population": r"\mathrm{share}(t) = \frac{|E_t|}{|E|}",
    "entf": r"\mathrm{EntF}(p, t) = -\sum_{o} P(o) \log_2 P(o)",
    "entetimp": r"\mathrm{EntETImp}(p, t) = \mathrm{EntF}(p, t)^{w} \cdot "
                r"\mathrm{ETImp}(p, t)^{1 - w}, \qquad w = 0.75",
    "classentropy": r"H(t) = -\sum_{o} P(o) \log_2 P(o)",
    "inforank": r"\mathrm{IR}(v) = \frac{\mathrm{dtp}(v)}{\sum_{u} \mathrm{dtp}(u)}",
    "diversity": r"\mathrm{OD}(p, t) = \bigl|\{\, o : (e, p, o) \in T "
                 r"\text{ and } e \in E_t \,\}\bigr|",
    # multi-part formulas sit on one line: the header puts the formula beside
    # its description, and a stacked block made the card tall with dead space
    "entropy_pagerank": r"\mathrm{PR}(v) = (1 - d) + d \sum_{u \rightarrow v} "
                        r"w(p_{uv}) \cdot \frac{\mathrm{PR}(u)}{\mathrm{outdeg}(u)},"
                        r"\qquad w(p) = \frac{\mathrm{EntF}(p)}"
                        r"{\max_{q \in P} \mathrm{EntF}(q)}",
    "shape": r"\mathrm{density} = \frac{|T|}{|E|}, \qquad "
             r"\overline{\deg}^{\,+} = \frac{|T|}{|S|}, \qquad "
             r"\overline{\deg}^{\,-} = \frac{|T|}{|O|}",
    "churn": r"\mathrm{churn}(t) = \frac{|A_t| + |D_t|}{|T_t(v_1)|}",
    "diff": r"\mathrm{Added} = T_2 \setminus T_1, \qquad "
            r"\mathrm{Deleted} = T_1 \setminus T_2, \qquad "
            r"\mathrm{Unchanged} = T_1 \cap T_2",
    "trajectories": r"\Delta m(v_i) = m(v_{i+1}) - m(v_i)",
    "vocab": r"C_{\mathrm{added}} = C_2 \setminus C_1, \qquad "
             r"C_{\mathrm{removed}} = C_1 \setminus C_2",
    "crosskg": r"\Delta m(t) = m_A(t) - m_B(t)",
}

META = {m["id"]: m for m in METRICS}


# ---------------- snapshot (phase 1/2/8) data loading ----------------

def read(label: str, name: str):
    """Load results/<label>/<name>.json, or None if that metric was not run."""
    path = RESULTS_DIR / label / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def discover() -> list[str]:
    """Snapshot labels that have phase-1 output, preferred ones first."""
    found = sorted(d.name for d in RESULTS_DIR.iterdir()
                   if d.is_dir() and d.name not in EXCLUDED
                   and (d / "class_population.json").exists())
    return ([l for l in PREFERRED if l in found]
            + [l for l in found if l not in PREFERRED])


LABELS = discover()
DEFAULT = [l for l in LABELS if l in PREFERRED] or LABELS[:1]
COLOR = {l: (PALETTE[i] if i < len(PALETTE) else GREY)
         for i, l in enumerate(LABELS)}

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

def from_public_endpoint(path) -> bool:
    """True if a comparison was measured against the shared public QLever host.

    That server caps query memory, so the largest classes fail and the run comes
    back partial. Such a result is not wrong, but showing it beside a complete
    local run invites reading a truncated class list as the whole finding."""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any("qlever.dev" in str(d.get(k, "")) or "qlever.cs" in str(d.get(k, ""))
               for k in ("kg_a", "kg_b", "version_1", "version_2"))


def has_content(path) -> bool:
    """A cross-KG comparison that matched no class has nothing to draw (YAGO 3's
    WordNet names match nothing in DBpedia). The file stays on disk as the
    measured zero; it just does not reach the dropdown."""
    if path.name != "cross_kg.json":
        return True
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("classes"))
    except (OSError, ValueError):
        return False


def discover_pairs(required_file: str) -> list[str]:
    found = sorted(d.name for d in RESULTS_DIR.iterdir()
                   if d.is_dir() and d.name not in EXCLUDED_PAIRS
                   and (d / required_file).exists()
                   and not from_public_endpoint(d / required_file)
                   and has_content(d / required_file))
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
    with ui.card().classes("w-full kg-card q-pa-md "
                            "kg-card-head"):
        with ui.row().classes("items-baseline gap-2 no-wrap"):
            ui.label(f"{m['num']}. {m['name']}").classes("text-lg font-bold")
            ui.badge(m["level"]).props("color=primary outline")
        # explanation and formula side by side: the formula is the definition of
        # the sentence next to it, and stacking them left a dead band between
        with ui.row().classes("w-full items-center gap-8 q-mt-sm"):
            ui.label(m["blurb"]).classes(
                "text-sm text-gray-600 dark:text-gray-300").style(
                "flex: 1 1 320px; max-width: 62ch; line-height: 1.55")
            formula(mid)


def formula(mid: str):
    """The metric's formula, typeset by KaTeX from the same LaTeX source as
    Chapter 3. Falls back to the plain-text form if KaTeX cannot load."""
    tex = TEX.get(mid)
    if not tex:
        ui.label(META[mid]["formula"]).classes(
            "font-mono text-sm bg-white dark:bg-slate-900 rounded-lg "
            "q-pa-sm q-mt-xs inline-block")
        return
    ui.html(f'<div class="tex-pending formula-box" data-tex="{escape(tex, True)}">'
            f'{escape(META[mid]["formula"])}</div>')


def grouped_bar(title, categories, series, unit, axis="value", height=460):
    """Horizontal bars, one series per snapshot, categories shared."""
    ui.echart({
        "title": {"text": title, "left": "center",
                  "textStyle": {"fontSize": 15, "fontWeight": 600}},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"bottom": 0, "type": "scroll"},
        "toolbox": {"feature": {"saveAsImage": {"title": "save"}}, "right": 10},
        "grid": {"left": 12, "right": 80, "top": 46, "bottom": 78,
                 "containLabel": True},
        "xAxis": {"type": axis, "name": unit, "nameLocation": "middle",
                  "nameGap": 26,
                  "nameTextStyle": {"fontSize": 11, "color": "#6B7280"},
                  "min": 0 if axis == "value" else None,
                  "axisLabel": {"fontSize": 10, TICK_FMT[0]: TICK_FMT[1]},
                  "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}},
        "yAxis": {"type": "category", "data": categories,
                  "axisLabel": {"fontSize": 11}},
        "series": [{"name": name, "type": "bar", "data": values,
                    "barMaxWidth": 14,
                    "itemStyle": {"borderRadius": [0, 6, 6, 0],
                                  "color": COLOR.get(name, PALETTE[0])}}
                   for name, values in series],
    }).classes("w-full").style(f"height: {height}px")


def heatmap(title, x_labels, y_labels, cells, unit="", height=None,
            scale="auto", decimals=None):
    """Classes down, snapshots across, population as colour.

    Populations here span four orders of magnitude (66.9M down to a few
    thousand), which is exactly what a grouped bar chart cannot show: the
    small series collapse onto the axis. Colour is therefore scaled by
    log10 while every cell still prints its real value, and a snapshot that
    lacks a class simply has no cell."""
    reals = [v for _, _, v in cells if v is not None]
    if not reals:
        return empty("nothing to draw for this selection")

    # Counts span four orders of magnitude and need a log colour scale; bits of
    # entropy span a factor of two and would be flattened by one. Decide from
    # the data rather than per call site.
    if scale == "auto":
        positive = [v for v in reals if v > 0]
        span = (max(positive) / min(positive)) if positive else 1
        scale = "log" if len(positive) == len(reals) and span > 100 else "linear"

    if scale == "log":
        usable = [(xi, yi, v) for xi, yi, v in cells if v is not None and v > 0]
        colour = lambda v: math.log10(v)
    else:
        usable = [(xi, yi, v) for xi, yi, v in cells if v is not None]
        colour = lambda v: v

    if not usable:
        return empty("nothing to draw for this selection")
    scaled = [colour(v) for _, _, v in usable]
    lo, hi = min(scaled), max(scaled)
    if hi - lo < 1e-9:              # a flat range would map everything to one colour
        lo, hi = lo - 0.5, hi + 0.5

    data = [{"value": [xi, yi, colour(v)], "real": v} for xi, yi, v in usable]

    xs, ys = json.dumps(x_labels), json.dumps(y_labels)
    if decimals is None:
        compact = ("(n => n >= 1e9 ? (n/1e9).toFixed(1).replace(/\\.0$/,'') + 'B' "
                   ": n >= 1e6 ? (n/1e6).toFixed(1).replace(/\\.0$/,'') + 'M' "
                   ": n >= 1e3 ? (n/1e3).toFixed(0) + 'k' : String(Math.round(n)))")
    else:
        compact = f"(n => n.toFixed({decimals}))"
    back = ("(v => Math.pow(10, v))" if scale == "log" else "(v => v)")

    height = height or max(380, 34 * len(y_labels) + 150)
    ui.echart({
        "title": {"text": title, "left": "center",
                  "textStyle": {"fontSize": 15, "fontWeight": 600}},
        "tooltip": {
            "borderWidth": 0,
            ":formatter": f"p => {{const X={xs}, Y={ys}, f={compact};"
                          "return `<b>${Y[p.value[1]]}</b><br/>${X[p.value[0]]}"
                          " &nbsp; <b>${f(p.data.real)}</b>`;}"},
        "toolbox": {"feature": {"saveAsImage": {"title": "save"}}, "right": 10},
        "grid": {"left": 8, "right": 24, "top": 52, "bottom": 74,
                 "containLabel": True},
        "xAxis": {"type": "category", "data": x_labels, "position": "top",
                  "splitArea": {"show": True},
                  "axisLine": {"show": False}, "axisTick": {"show": False},
                  "axisLabel": {"fontSize": 11, "fontWeight": 600,
                                "interval": 0, "hideOverlap": False}},
        "yAxis": {"type": "category", "data": y_labels,
                  "splitArea": {"show": True},
                  "axisLine": {"show": False}, "axisTick": {"show": False},
                  "axisLabel": {"fontSize": 11}},
        "visualMap": {
            "min": lo, "max": hi, "calculable": False, "orient": "horizontal",
            "left": "center", "bottom": 8, "itemWidth": 13, "itemHeight": 150,
            "text": [f"more {unit}", f"fewer {unit}"],
            "textStyle": {"fontSize": 10},
            "inRange": {"color": SEQ_RAMP},
            ":formatter": f"v => {compact}({back}(v))"},
        "series": [{
            "type": "heatmap", "data": data,
            "label": {"show": True, "fontSize": 10,
                      ":formatter": f"p => {compact}(p.data.real)"},
            "itemStyle": {"borderColor": "rgba(255,255,255,.85)",
                          "borderWidth": 2, "borderRadius": 3},
            "emphasis": {"itemStyle": {"borderColor": "#111", "borderWidth": 2}},
        }],
    }).classes("w-full").style(f"height:{height}px")


def small_multiples(title, panels, render_one, min_w="260px"):
    """A titled card holding a wrapping row of small charts, one per panel."""
    with ui.card().classes("w-full kg-card q-pa-md"):
        if title:
            ui.label(title).classes("text-base font-semibold q-mb-sm text-center")
        # a grid, not a wrapping flex row: with flex-1 a panel left alone on the
        # last row stretches to full width and its scale no longer matches
        with ui.element("div").classes("w-full").style(
                f"display:grid; gap:16px; "
                f"grid-template-columns:repeat(auto-fill, minmax({min_w}, 1fr))"):
            for panel in panels:
                with ui.column().classes("w-full gap-0"):
                    render_one(panel)


TICK_FMT = (":formatter", "v => v == null ? '' : "
            "Math.abs(v) >= 1e9 ? (v/1e9).toFixed(1).replace(/\\.0$/,'') + 'B' : "
            "Math.abs(v) >= 1e6 ? (v/1e6).toFixed(1).replace(/\\.0$/,'') + 'M' : "
            "Math.abs(v) >= 1e3 ? (v/1e3).toFixed(0) + 'k' : "
            "Number.isInteger(v) ? v : "
            # InfoRank scores sit near 0.000001; toFixed(2) printed every tick as
            # 0.00. Full decimals, trailing zeros trimmed, no e-notation.
            "Math.abs(v) < 0.01 ? v.toFixed(12).replace(/0+$/, '') : v.toFixed(2)")

VALUE_FMT = ("p => p.value == null ? '' : "
             "(Math.abs(p.value) >= 1000 "
             "? p.value.toLocaleString(undefined, {maximumFractionDigits: 0}) "
             ": Math.abs(p.value) < 0.01 && p.value != 0 ? p.value.toFixed(12).replace(/0+$/, '') "
             ": p.value.toLocaleString(undefined, {maximumFractionDigits: 2}))")


def nice_max(value):
    """Round a maximum up to a readable axis bound, so ticks land on 70M rather
    than 70,250,687.84999995. Leaves headroom for the value label on the
    longest bar."""
    if not value or value <= 0:
        return None
    padded = value * 1.18
    exp = math.floor(math.log10(padded))
    base = 10.0 ** exp
    for step in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8):
        if padded <= step * base:
            return step * base
    return 10 * base


def small_bar(subtitle, categories, values, color, unit="", height=None,
              axis="value", vmax=None, labels=False):
    """One panel of a small-multiples row. `vmax` pins the value axis so panels
    drawn side by side share a scale and stay visually comparable."""
    height = height or max(240, 22 * len(categories) + 86)
    # Axis name under the axis, not at its end: at the end it needs ~200px the
    # grid never reserves. splitNumber + hideOverlap stop ticks piling up in a
    # narrow panel ("30609012150").
    x_axis = {"type": axis, "name": unit, "nameLocation": "middle", "nameGap": 24,
              "nameTextStyle": {"fontSize": 10, "color": "#6B7280"},
              "splitNumber": 4,
              "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.35}},
              "axisLabel": {"fontSize": 10, "hideOverlap": True,
                            TICK_FMT[0]: TICK_FMT[1]}}
    if axis == "value":
        x_axis["min"] = 0
    tiny = [v for v in values if isinstance(v, (int, float))]
    if tiny and 0 < max(tiny) < 0.01:
        # full decimals like 0.0000015 are wide: tilt them so they don't collide
        x_axis["axisLabel"]["rotate"] = 30
        x_axis["axisLabel"]["hideOverlap"] = False
        x_axis["nameGap"] = 52
        height += 28
    if vmax is not None:
        x_axis["max"] = vmax
    ui.echart({
        "title": {"text": subtitle, "left": "center", "textStyle": {"fontSize": 12}},
        "tooltip": {"trigger": "axis",
                    ":valueFormatter": "v => v != 0 && Math.abs(v) < 0.01 "
                                       "? v.toFixed(12).replace(/0+$/, '') : v.toLocaleString()"},
        # containLabel measures the category names instead of assuming 140px;
        # names past 150px are truncated, and the tooltip still shows them whole
        "grid": {"left": 6, "right": 64 if labels else 22,
                 "top": 34, "bottom": 40 + (28 if x_axis["axisLabel"].get("rotate") else 0),
                 "containLabel": True},
        "xAxis": x_axis,
        "yAxis": {"type": "category", "data": categories,
                  "axisLabel": {"fontSize": 10, "width": 150,
                                "overflow": "truncate"}},
        "series": [{"type": "bar", "data": values, "barMaxWidth": 12,
                    "itemStyle": {"color": color, "borderRadius": [0, 4, 4, 0]},
                    "label": {"show": labels, "position": "right",
                              "fontSize": 10, "color": "#4B5563",
                              ":formatter": VALUE_FMT}}],
    }).classes("w-full").style(f"height:{height}px")


def draw_combined(title, categories, series, unit, *, decimals=None,
                  scale="linear"):
    """The combined view of a phase-1 metric: snapshots across, categories down,
    value as colour, every cell carrying its own number.

    A grouped bar chart cannot serve this shape -- seven series against values
    spanning several orders of magnitude collapse the small ones onto the axis,
    and a missing category is indistinguishable from a zero. A heatmap shows
    magnitude by colour, the exact figure as a label, and absence as no cell."""
    cells = [(xi, yi, values[yi])
             for xi, (_, values) in enumerate(series)
             for yi in range(len(categories))]
    with ui.card().classes("w-full kg-card q-pa-md"):
        heatmap(title, [label for label, _ in series], categories, cells,
                unit=unit, decimals=decimals, scale=scale)


def draw_own_panels(title, per_snapshot, unit, *, row_h=26, min_w="360px",
                    shared_scale=True):
    """One panel per snapshot, each ranking its OWN classes by entity count.

    The rows differ from panel to panel, so reading across a row means nothing
    -- but the value axis is still shared, so bar lengths stay comparable in
    magnitude: YAGO 4's largest class really is bigger than DBpedia's."""
    everything = [v for _, pairs in per_snapshot for _, v in pairs]
    # own scale: each panel fits its own largest bar, so a small snapshot such as
    # YAGO 3 (668k) is not a row of slivers beside YAGO 4 (66.9M)
    vmax = nice_max(max(everything)) if everything and shared_scale else None
    rows = max((len(pairs) for _, pairs in per_snapshot), default=0)
    height = max(300, row_h * rows + 90)

    def panel(item):
        label, pairs = item
        if not pairs:
            with ui.column().classes("items-center justify-center gap-1 w-full") \
                    .style(f"height:{height}px"):
                ui.label(label).classes("text-sm font-semibold")
                ui.label("no class data").classes("text-xs text-gray-500")
            return
        cats = [n for n, _ in reversed(pairs)]
        vals = [v for _, v in reversed(pairs)]
        small_bar(label, cats, vals, COLOR.get(label, PALETTE[0]), unit,
                  height=height, vmax=vmax, labels=True)

    small_multiples(title, per_snapshot, panel, min_w=min_w)


def draw_panels(title, categories, series, unit, *, axis="value",
                row_h=26, min_w="320px", shared_scale=True):
    """Render one chart per snapshot instead of a single grouped chart.

    All panels share the same category order and the same value axis, pinned to
    the largest value across the selected snapshots, so bar lengths mean the
    same thing in every panel."""
    vals = [v for _, values in series for v in values if v is not None]
    vmax = nice_max(max(vals)) if vals and shared_scale else None
    height = max(300, row_h * len(categories) + 90)

    def panel(item):
        label, values = item
        if not any(v is not None for v in values):
            # The snapshot was measured, but shares no class with the ranking --
            # YAGO 3 types against WordNet synsets and Wikipedia categories, so
            # it overlaps nothing in a schema.org-derived top-N. Say so, rather
            # than drawing an empty axis that reads as missing data.
            with ui.column().classes("items-center justify-center gap-1 w-full") \
                    .style(f"height:{height}px"):
                ui.label(label).classes("text-sm font-semibold")
                ui.icon("filter_alt_off", size="26px").classes("text-gray-400")
                ui.label("no class in common with the ranking above") \
                    .classes("text-xs text-gray-500 text-center")
                ui.label("this snapshot uses a different class vocabulary") \
                    .classes("text-xs text-gray-400 text-center")
            return
        small_bar(label, categories, values, COLOR.get(label, PALETTE[0]),
                  unit, height=height, axis=axis, vmax=vmax, labels=True)

    small_multiples(title, series, panel, min_w=min_w)


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


def line_chart(title, x_labels, series, unit="", height=380, end_labels=False,
               x_name=None):
    """Multi-series line chart.

    `end_labels` writes each series name where its line ends instead of relying
    on the legend. With more than a handful of series the legend paginates and
    stops being usable, and a name beside the line needs no lookup at all."""
    ui.echart({
        "title": {"text": title, "left": "center",
                  "textStyle": {"fontSize": 13, "fontWeight": 600}},
        "tooltip": {"trigger": "axis", "order": "valueDesc"},
        "legend": {"show": not end_labels and len(series) > 1,
                   "bottom": 0, "type": "scroll"},
        "toolbox": {"feature": {"saveAsImage": {"title": "save"}}, "right": 10},
        "grid": {"left": 12, "right": 150 if end_labels else 30, "top": 40,
                 "bottom": 30 if len(series) > 1 and not end_labels else 8,
                 "containLabel": True},
        "xAxis": {"type": "category", "data": x_labels,
                  "name": x_name or "", "nameLocation": "middle", "nameGap": 24,
                  "nameTextStyle": {"fontSize": 11, "color": "#6B7280"},
                  # show every release; the default hides labels it thinks crowd
                  "axisLabel": {"interval": 0, "fontSize": 10, "rotate": 20}},
        # name starts at the axis and runs right; centred it was clipped at the left
        "yAxis": {"type": "value", "name": unit,
                  "nameTextStyle": {"align": "left", "color": "#6B7280"}},
        "series": [{"name": name, "type": "line", "data": vals,
                    "symbolSize": 7, "smooth": False,
                    "emphasis": {"focus": "series"},
                    "endLabel": {"show": end_labels, "fontSize": 10,
                                 "distance": 6,
                                 ":formatter": "p => p.seriesName"},
                    # nudge end labels apart vertically when lines finish close together
                    "labelLayout": {"moveOverlap": "shiftY"}}
                   for name, vals in series],
    }).classes("w-full").style(f"height:{height}px")


# change categories keep one meaning everywhere: the churn chart uses the same
DIFF_COLORS = {"added": "#10b981", "unchanged": "#94a3b8", "kept": "#94a3b8",
               "deleted": "#ef4444", "removed": "#ef4444"}


def donut(title, items, height=320):
    """items: list of (name, value).

    A zero-value slice has no width, so its label has nowhere to go but the top
    of the ring, straight into the title. Zero slices stay in the legend but get
    no label; the title sits at the very top and the ring sits lower."""
    data = []
    for i, (n, v) in enumerate(items):
        entry = {"name": n, "value": v,
                 "itemStyle": {"color": DIFF_COLORS.get(n, PALETTE[i % len(PALETTE)])}}
        if not v:
            entry["label"] = {"show": False}
            entry["labelLine"] = {"show": False}
        data.append(entry)
    ui.echart({
        "title": {"text": title, "left": "center", "top": 2,
                  "textStyle": {"fontSize": 13}},
        "tooltip": {"trigger": "item",
                    ":formatter": "p => `${p.name}: ${p.value.toLocaleString()} (${p.percent}%)`"},
        "legend": {"bottom": 0},
        "series": [{"type": "pie", "radius": ["36%", "58%"], "center": ["50%", "53%"],
                    "avoidLabelOverlap": True,
                    "label": {":formatter": "p => `${p.name}\n${p.value.toLocaleString()}`",
                              "color": "#4B5563"},
                    "data": data}],
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
    with ui.card().classes("w-full kg-card q-pa-md"):
        ui.label(caption).classes("text-base font-semibold q-mb-sm")
        ui.table(columns=columns, rows=rows, pagination=12) \
            .classes("w-full").props("flat bordered dense")


def empty(message: str):
    with ui.card().classes("w-full items-center q-pa-xl kg-card"):
        ui.icon("inbox", size="42px").classes("text-gray-400")
        ui.label(message).classes("text-lg font-medium")


def controls(state, refresh, *, passes=True, extra=None):
    """The control strip every snapshot-based tab shares: snapshots, pass,
    and a tab-specific widget built by `extra`."""
    with ui.card().classes("w-full kg-card q-pa-md"):
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
            if "split" in state:
                ui.toggle({"separate": "separate", "combined": "combined"},
                          value=state["split"],
                          on_change=lambda e: (state.update(split=e.value),
                                               refresh())) \
                    .props("dense").tooltip(
                        "separate: one chart per snapshot, shared scale  ·  "
                        "combined: all snapshots grouped in one chart")
            if extra:
                extra()
        if passes and state["pass"] == "":
            ui.label("Descriptive pass: each snapshot picks its own top-8 classes, "
                     "so classes may be missing from a snapshot and the sets are "
                     "not comparable — use the pinned pass to compare.") \
                .classes("text-xs text-orange-600 q-mt-sm")


def pair_controls(state, refresh, pairs, *, extra=None):
    """Control strip for the 2-endpoint tabs: pick one comparison pair."""
    with ui.card().classes("w-full kg-card q-pa-md"):
        with ui.row().classes("items-center gap-6 w-full"):
            ui.icon("compare_arrows").classes("text-gray-400")
            ui.select(pairs, value=state["pair"], label="Comparison",
                      on_change=lambda e: (state.update({"pair": e.value}), refresh())) \
                .classes("w-96").props("outlined dense options-dense")
            if extra:
                extra()


# ============================================================ metric 1: class population

# Default to each snapshot's own ranking: with the full snapshot selection the
# shared-class intersection is empty, so "shared" would open on an empty state.
pop_state = PerClient({"labels": list(DEFAULT), "pass": "_pinned", "topn": 10,
             "split": "separate", "scope": "own", "scale": "own"})

SCOPE_OPTIONS = {"shared": "shared classes",
                 "own": "each snapshot's own top N"}


def in_snapshot(key: str, label: str) -> bool:
    return any(canon(iri) == key for iri in entries(label, "class_population"))


@client_refreshable
def population_view():
    labels = pop_state["labels"]
    if not labels:
        return empty("No snapshot selected")
    topn = pop_state["topn"]

    # ---- each snapshot ranks its own classes -------------------------------
    if pop_state["scope"] == "own":
        per_snapshot = []
        for label in labels:
            classes = entries(label, "class_population")
            ranked = sorted(classes.items(),
                            key=lambda kv: -kv[1]["population"])[:topn]
            names = distinct_names([iri for iri, _ in ranked])
            per_snapshot.append(
                (label, [(n, v["population"]) for n, (_, v) in zip(names, ranked)]))

        draw_own_panels(f"Class population — each snapshot's own top {topn}",
                        per_snapshot, "entities",
                        shared_scale=pop_state["scale"] == "shared")

        rows = []
        for label, pairs in per_snapshot:
            classes = entries(label, "class_population")
            ranked_iris = [i for i, _ in sorted(classes.items(),
                           key=lambda kv: -kv[1]["population"])[:topn]]
            by_name = {n: (i, classes[i]) for n, i in
                       zip(distinct_names(ranked_iris), ranked_iris)}
            for rank, (name, pop) in enumerate(pairs, 1):
                iri, v = by_name[name]
                rows.append({"snapshot": label, "rank": rank, "class": name,
                             "population": f"{pop:,.0f}",
                             "share": f"{v['share'] * 100:.2f}%", "iri": iri})
        table([{"name": "snapshot", "label": "Snapshot", "field": "snapshot",
                "align": "left", "sortable": True},
               {"name": "rank", "label": "#", "field": "rank", "align": "right"},
               {"name": "class", "label": "Class", "field": "class",
                "align": "left", "sortable": True},
               {"name": "population", "label": "Entities", "field": "population",
                "align": "right"},
               {"name": "share", "label": "Share", "field": "share",
                "align": "right"},
               {"name": "iri", "label": "Class IRI", "field": "iri",
                "align": "left"}],
              rows,
              f"Each snapshot's {topn} most populated classes, ranked "
              "independently. Rows are not aligned across snapshots -- this "
              "view shows what each graph contains, not how they compare.")

        kpi_row([((f"{(data[l]['class_population'] or {}).get('total_entities'):,}"
                   if (data[l]["class_population"] or {}).get("total_entities")
                   else "—"),
                  f"{l} — typed entities") for l in labels])
        return

    # ---- one shared ranking, most widely shared classes first --------------
    # A strict intersection is empty here: every snapshot stores only its own
    # top classes, and across all seven none survives. So rank by how many
    # snapshots carry the class, then by population, and put that coverage in
    # the row label -- a blank cell is then obviously "not in this snapshot's
    # stored list", not a zero.
    coverage = {k: sum(in_snapshot(k, l) for l in labels)
                for k in class_keys(labels, "class_population")}
    keys = sorted(coverage, key=lambda k: -coverage[k])[:topn]

    if not keys:
        return empty("No class data for the selected snapshots")

    n = len(labels)
    full = [k for k in keys if coverage[k] == n]
    names = [f"{display_name(k, labels, 'class_population')}"
             + ("" if coverage[k] == n else f"  ({coverage[k]}/{n})")
             for k in keys]

    if len(full) < len(keys):
        with ui.card().classes("w-full rounded-xl q-pa-sm bg-blue-50 "
                               "dark:bg-slate-800"):
            ui.label(
                f"{len(full)} of these {len(keys)} classes are present in all "
                f"{n} snapshots. Where a row is marked (k/{n}) the class is "
                "missing from some snapshot's stored top-class list — that is "
                "not a count of zero, and the class may still exist in that "
                "graph. Rows are ordered by how widely they are shared."
            ).classes("text-xs text-blue-700 dark:text-blue-300")
    series = []
    for label in labels:
        classes = entries(label, "class_population")
        values = []
        for key in keys:
            hit = next((v for i, v in classes.items() if canon(i) == key), None)
            values.append(hit["population"] if hit else None)
        series.append((label, list(reversed(values))))

    cats = list(reversed(names))
    title = f"Class population — {len(keys)} most widely shared classes"
    if pop_state["split"] == "separate":
        draw_panels(title, cats, series, "entities", row_h=26, min_w="360px",
                    shared_scale=pop_state["scale"] == "shared")
    else:
        draw_combined(title, cats, series, "entities", scale="log")

    rows = []
    for key, name in zip(keys, names):
        row = {"class": name}
        for label in labels:
            classes = entries(label, "class_population")
            hit = next(((i, v) for i, v in classes.items()
                        if canon(i) == key), None)
            row[label] = (f"{hit[1]['population']:,} "
                          f"({hit[1]['share'] * 100:.2f}%)") if hit else "—"
            row[f"iri_{label}"] = hit[0] if hit else ""
        rows.append(row)
    cols = [{"name": "class", "label": "Class", "field": "class", "align": "left"}]
    cols += [{"name": l, "label": l, "field": l, "align": "right"} for l in labels]
    table(cols, rows,
          "Population and share of all typed entities, ordered by how many "
          "snapshots carry the class. A dash means the class is absent from "
          "that snapshot's stored class list, not that it has no entities.")

    kpi_row([((f"{(data[l]['class_population'] or {}).get('total_entities'):,}"
               if (data[l]["class_population"] or {}).get("total_entities")
               else "—"),
              f"{l} — typed entities") for l in labels])


# ============================================================ metric 4: class entropy

ent_state = PerClient({"labels": list(DEFAULT), "pass": "_pinned",
             "which": "object_entropy", "split": "separate"})

ENTROPY_FIELDS = {"object_entropy": "object entropy",
                  "predicate_entropy": "predicate entropy"}


@client_refreshable
def class_entropy_view():
    labels, file = ent_state["labels"], "class_entropy" + ent_state["pass"]
    if not labels:
        return empty("No snapshot selected")

    keys = class_keys(labels, file)
    if not keys:
        return empty("class_entropy was not computed for these snapshots")
    field = ent_state["which"]

    # Descriptive pass: every snapshot measured its OWN top classes, so a shared
    # class axis is the union of all their lists -- 37 rows per panel for 5-8
    # values each. Give each panel its own classes instead, ranked by entropy.
    if ent_state["pass"] == "" and ent_state["split"] == "separate":
        per_snapshot = []
        for label in labels:
            got = [(iri, v.get(field)) for iri, v in entries(label, file).items()
                   if v.get(field) is not None]
            got.sort(key=lambda kv: -kv[1])
            names = distinct_names([iri for iri, _ in got])
            per_snapshot.append((label, [(n, v) for n, (_, v) in zip(names, got)]))
        draw_own_panels(f"Class entropy — {ENTROPY_FIELDS[field]}, each snapshot's own classes",
                        per_snapshot, "bits", row_h=30)
    own_panels = ent_state["pass"] == "" and ent_state["split"] == "separate"

    names = [display_name(k, labels, file) for k in keys]
    series = [(label, list(reversed([
        (lookup(label, file, k) or (None, {}))[1].get(field) for k in keys])))
        for label in labels]

    cats = list(reversed(names))
    title = f"Class entropy — {ENTROPY_FIELDS[field]}"
    if own_panels:
        pass                      # drawn above, on per-snapshot axes
    elif ent_state["split"] == "separate":
        draw_panels(title, cats, series, "bits", row_h=30, min_w="320px")
    else:
        draw_combined(title, cats, series, "bits", decimals=2)

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
    cats = list(reversed([names[p] for p in ranked]))
    chart_title = f"{title} — {class_name}, top {len(ranked)} predicates"
    if state.get("split") == "separate":
        draw_panels(chart_title, cats, series, unit, row_h=26, min_w="320px")
    else:
        draw_combined(chart_title, cats, series, unit, decimals=decimals)

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


entf_state = PerClient({"labels": list(DEFAULT), "pass": "_pinned", "class": None,
              "topn": 12, "split": "separate"})
etimp_state = PerClient({"labels": list(DEFAULT), "pass": "_pinned", "class": None,
               "topn": 12, "split": "separate"})
diversity_state = PerClient({"labels": list(DEFAULT), "pass": "_pinned", "class": None, "topn": 12})


@client_refreshable
def entf_view():
    per_predicate_view(entf_state, "property_entropy",
                       "Property entropy H(p,t)", "bits", 3)


@client_refreshable
def etimp_view():
    per_predicate_view(etimp_state, "ent_etimp",
                       "Entropy-weighted type importance", "EntETImp", 2)


@client_refreshable
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

inforank_state = PerClient({"labels": list(DEFAULT), "topn": 10})


@client_refreshable
def inforank_view():
    labels, topn = inforank_state["labels"], inforank_state["topn"]
    if not labels:
        return empty("No snapshot selected")

    def panel(label):
        raw = (data[label].get("entity_informativeness") or {}).get("entities", {})
        ranked = sorted(raw.items(), key=lambda kv: kv[1]["inforank"], reverse=True)[:topn]
        cats = list(reversed([pretty_node(iri) for iri, _ in ranked]))
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

pagerank_state = PerClient({"labels": list(DEFAULT), "topn": 10, "which": "entropy_weighted"})
PR_FIELDS = {"entropy_weighted": "entropy-weighted PageRank (own variant)",
             "unweighted": "classic PageRank (baseline)"}


@client_refreshable
def pagerank_view():
    labels, topn = pagerank_state["labels"], pagerank_state["topn"]
    field = pagerank_state["which"]
    rank_field = "rank_weighted" if field == "entropy_weighted" else "rank_unweighted"
    if not labels:
        return empty("No snapshot selected")

    def panel(label):
        raw = (data[label].get("entropy_pagerank") or {}).get("nodes", {})
        ranked = sorted(raw.items(), key=lambda kv: kv[1].get(rank_field, 1e18))[:topn]
        cats = list(reversed([pretty_node(iri) for iri, _ in ranked]))
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
            rows.append({"snapshot": label, "node": pretty_node(iri),
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

shape_state = PerClient({"labels": list(DEFAULT)})


@client_refreshable
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

churn_state = PerClient({"pair": CHURN_PAIRS[0] if CHURN_PAIRS else None, "topn": 15})


@client_refreshable
def churn_view():
    pair = churn_state["pair"]
    if not pair:
        return empty("No churn results found — run metric 9 for a version pair")
    raw = read_pair(pair, "class_churn") or {}
    if not raw:
        return empty(f"class_churn.json not found for {pair}")
    measured = len(raw)
    items = sorted(raw.items(), key=lambda kv: kv[1]["churn"], reverse=True)[:churn_state["topn"]]
    names = distinct_names([i for i, _ in items])
    cats = list(reversed(names))

    # Top N can only show what the run measured; say so instead of silently
    # capping, or a larger N looks like a broken control.
    if churn_state["topn"] > measured:
        ui.label(f"This comparison measured {measured} classes, so {measured} are shown. "
                 f"Metric 9 was run as `churn {measured} 50000`; re-run it with a larger "
                 "class count to see more.") \
            .classes("text-xs text-gray-600 dark:text-gray-300 q-px-sm")

    with ui.card().classes("w-full kg-card q-pa-md"):
        grouped_bar(f"Class-level churn — {pair}", cats,
                    [("churn %", list(reversed([v["churn"] * 100 for _, v in items])))],
                    "churn: changed triples as % of the class's triples in the older snapshot",
                    height=max(360, 32 * len(items) + 120))

    with ui.card().classes("w-full kg-card q-pa-md"):
        ui.label(f"Added / deleted / unchanged triples per class — {pair}") \
            .classes("text-base font-semibold q-mb-sm")
        ui.echart({
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {"bottom": 0},
            "grid": {"left": 8, "right": 30, "top": 20, "bottom": 64,
                     "containLabel": True},
            "xAxis": {"type": "value", "name": "triples", "nameLocation": "middle",
                      "nameGap": 26, "axisLabel": {TICK_FMT[0]: TICK_FMT[1]}},
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

    rows = [{"class": n, "churn": f"{v['churn'] * 100:.1f}%",
             "added": f"{v['added']:,}", "deleted": f"{v['deleted']:,}",
             "unchanged": f"{v['unchanged']:,}",
             "triples_v1": f"{v['triples_v1']:,}", "triples_v2": f"{v['triples_v2']:,}",
             "iri": i} for n, (i, v) in zip(names, items)]
    cols = [{"name": c, "label": c.replace("_", " ").title(), "field": c,
             "align": "left" if c in ("class", "iri") else "right",
             "sortable": c not in ("class", "iri")}
            for c in ["class", "churn", "added", "deleted", "unchanged",
                      "triples_v1", "triples_v2", "iri"]]
    table(cols, rows, f"Class churn, {pair} (top {len(items)} by churn rate)")


# ============================================================ metric 10: triple diff

diff_state = PerClient({"pair": DIFF_PAIRS[0] if DIFF_PAIRS else None})


@client_refreshable
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
            with ui.card().classes("w-full kg-card q-pa-md"):
                donut(f"Triple diff — {pair} ({d.get('scope', '')})",
                      [("added", d["added"]), ("deleted", d["deleted"]),
                       ("unchanged", d["unchanged"])])
        bench = d.get("benchmark")
        if bench:
            with ui.column().classes("flex-1").style("min-width:320px"):
                with ui.card().classes("w-full kg-card q-pa-md"):
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

vocab_state = PerClient({"pair": VOCAB_PAIRS[0] if VOCAB_PAIRS else None})
VOCAB_ROW_CAP = 300


@client_refreshable
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
                with ui.card().classes("w-full kg-card q-pa-md"):
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

crosskg_state = PerClient({"pair": CROSSKG_PAIRS[0] if CROSSKG_PAIRS else None})


def dumbbell(title, categories, a_label, a_vals, b_label, b_vals, unit,
             axis="value", height=None):
    """One row per category, the two graphs as dots joined by a line.

    A grouped bar shows two lengths and leaves the reader to subtract them. Here
    the connecting line IS the difference, which is what a cross-graph
    comparison is actually about, and the dot order shows its direction."""
    height = height or max(320, 30 * len(categories) + 130)
    ca = COLOR.get(a_label, PALETTE[0]); cb = COLOR.get(b_label, PALETTE[3])
    links = [{"type": "line", "silent": True, "symbol": "none",
              "lineStyle": {"color": "#cbd5e1", "width": 2},
              "data": [[a, i], [b, i]], "z": 1,
              "tooltip": {"show": False}}
             for i, (a, b) in enumerate(zip(a_vals, b_vals))
             if a is not None and b is not None]
    dots = [{"name": a_label, "type": "scatter", "symbolSize": 11, "z": 3,
             "itemStyle": {"color": ca},
             "data": [[v, i] for i, v in enumerate(a_vals) if v is not None]},
            {"name": b_label, "type": "scatter", "symbolSize": 11, "z": 3,
             "itemStyle": {"color": cb},
             "data": [[v, i] for i, v in enumerate(b_vals) if v is not None]}]
    ui.echart({
        "title": {"text": title, "left": "center",
                  "textStyle": {"fontSize": 15, "fontWeight": 600}},
        "tooltip": {"trigger": "item",
                    ":formatter": "p => `${p.seriesName}<br/><b>` + "
                                  "p.value[0].toLocaleString() + `</b>`"},
        "legend": {"bottom": 0, "data": [a_label, b_label]},
        "toolbox": {"feature": {"saveAsImage": {"title": "save"}}, "right": 10},
        "grid": {"left": 12, "right": 40, "top": 46, "bottom": 70,
                 "containLabel": True},
        "xAxis": {"type": axis, "name": unit, "nameLocation": "middle",
                  "nameGap": 26,
                  "axisLabel": {"fontSize": 10, TICK_FMT[0]: TICK_FMT[1]},
                  "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}},
        "yAxis": {"type": "category", "data": categories,
                  "axisLabel": {"fontSize": 11},
                  "splitLine": {"show": True,
                                "lineStyle": {"opacity": 0.25, "type": "dotted"}}},
        "series": links + dots,
    }).classes("w-full").style(f"height:{height}px")


def parity_scatter(title, labels, xs, ys, x_label, y_label, unit, height=470):
    """Each class as one point, with the line of equality drawn.

    A point on the diagonal means the two graphs report the same value; distance
    from the line is the disagreement, and which side it falls on says which
    graph is higher. No bar chart shows agreement as a position."""
    pts = [(l, x, y) for l, x, y in zip(labels, xs, ys)
           if x is not None and y is not None]
    if not pts:
        return empty("nothing to plot")
    lo = min(min(x for _, x, _ in pts), min(y for _, _, y in pts))
    hi = max(max(x for _, x, _ in pts), max(y for _, _, y in pts))
    pad = (hi - lo) * 0.08 or 1
    # whole-bit bounds: an axis ending at 20.776027043948474 is noise
    lo, hi = math.floor(lo - pad), math.ceil(hi + pad)
    near = [p for p in pts if abs(p[1] - p[2]) < (hi - lo) * 0.02]

    ui.echart({
        "title": {"text": title, "left": "center",
                  "textStyle": {"fontSize": 15, "fontWeight": 600}},
        "tooltip": {"trigger": "item",
                    ":formatter": "p => p.data[2] ? `<b>${p.data[2]}</b><br/>` + "
                                  "`${p.data[0].toFixed(3)} vs ${p.data[1].toFixed(3)}"
                                  "<br/>gap ${Math.abs(p.data[0]-p.data[1]).toFixed(3)}` : ''"},
        "toolbox": {"feature": {"saveAsImage": {"title": "save"}}, "right": 10},
        "grid": {"left": 48, "right": 28, "top": 52, "bottom": 52,
                 "containLabel": True},
        "xAxis": {"type": "value", "name": f"{x_label} ({unit})", "min": lo, "max": hi,
                  "nameLocation": "middle", "nameGap": 28,
                  "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.35}}},
        "yAxis": {"type": "value", "name": f"{y_label} ({unit})", "min": lo, "max": hi,
                  "nameLocation": "middle", "nameGap": 38,
                  "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.35}}},
        "series": [
            {"type": "line", "silent": True, "symbol": "none", "z": 1,
             "lineStyle": {"color": "#94a3b8", "width": 1.5, "type": "dashed"},
             "data": [[lo, lo], [hi, hi]],
             "markPoint": {"silent": True, "symbol": "none"}},
            {"type": "scatter", "symbolSize": 13, "z": 3,
             "itemStyle": {"color": PALETTE[0], "opacity": .85,
                           "borderColor": "#fff", "borderWidth": 1.5},
             "label": {"show": True, "position": "right", "fontSize": 9,
                       "color": "inherit",
                       ":formatter": "p => p.data[2]"},
             "data": [[x, y, l] for l, x, y in pts]},
            {"type": "scatter", "symbolSize": 17, "z": 4,
             "itemStyle": {"color": "transparent", "borderColor": PALETTE[4],
                           "borderWidth": 2},
             "data": [[x, y, l] for l, x, y in near]},
        ],
    }).classes("w-full").style(f"height:{height}px")


def gap_trajectory(pair: str, kg_a: str):
    """How far apart the two graphs are, across every release of the OTHER graph
    measured against the same fixed side.

    With `kg_a` held constant, a class whose gap shrinks between releases is one
    where the two graphs grew more alike; a class whose gap grows is one where
    they diverged. This is the view that turns two separate comparisons into a
    statement about direction."""
    siblings = [p for p in CROSSKG_PAIRS if sides(p)[0] == kg_a]
    if len(siblings) < 2:
        return

    # x axis: the varying side, ordered by the release name it carries
    others = sorted(siblings, key=lambda p: sides(p)[1])
    gaps: dict[str, list] = {}
    for p in others:
        d = read_pair(p, "cross_kg") or {}
        for cls, v in d.get("classes", {}).items():
            gaps.setdefault(cls, []).append(
                abs(v["a"]["class_entropy"] - v["b"]["class_entropy"]))
    # keep only classes measured in every pairing, or the lines would jump
    complete = {c: g for c, g in gaps.items() if len(g) == len(others)}
    if not complete:
        return

    x_labels = [sides(p)[1] for p in others]
    moved = sorted(complete.items(), key=lambda kv: abs(kv[1][-1] - kv[1][0]),
                   reverse=True)
    series = [(c.title(), g) for c, g in moved]

    narrowed = sum(1 for _, g in moved if g[-1] < g[0])
    with ui.card().classes("w-full kg-card q-pa-md"):
        line_chart(f"Distance between {kg_a} and each release of the other graph",
                   x_labels, series,
                   f"entropy gap: {kg_a} vs DBpedia (bits)",
                   height=480, end_labels=True)
        ui.label(
            f"{kg_a} is fixed, so every movement is the other graph. "
            f"The gap narrowed for {narrowed} of {len(moved)} classes and widened "
            f"for {len(moved) - narrowed}: these two graphs are drifting apart on "
            "most of what they share. A line reaching zero means the two graphs "
            "carry the same information per entity for that class."
        ).classes("text-xs text-gray-600 dark:text-gray-300 q-mt-sm")


def sides(pair: str) -> tuple[str, str]:
    """Snapshot names for a comparison directory. `kg_a`/`kg_b` in the JSON are
    raw endpoint URLs, which are neither readable nor in COLOR, so both series
    ended up the same blue and labelled by IP address. The directory name
    already carries the two snapshot labels."""
    if "-vs-" in pair:
        a, b = pair.split("-vs-", 1)
        return a, b
    return pair, pair


@client_refreshable
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
    kg_a, kg_b = sides(pair)

    # biggest class first: the dumbbell reads top-down
    cats = sorted(cats, key=lambda c: classes[c]["a"]["population"])
    names = [c.title() for c in cats]

    skipped = d.get("skipped") or []
    if skipped:
        ui.label(f"{len(cats) + len(skipped)} classes matched. Left out: "
                 f"{', '.join(s.title() for s in skipped)}. These root classes of "
                 f"{kg_a} are too large for the entropy query on the 12 GB home "
                 "server, which was killed for lack of memory.") \
            .classes("text-sm text-amber-800 bg-amber-50 q-pa-sm rounded w-full")

    with ui.card().classes("w-full kg-card q-pa-md"):
        dumbbell(f"Class population — {kg_a} vs {kg_b}", names,
                 kg_a, [classes[c]["a"]["population"] for c in cats],
                 kg_b, [classes[c]["b"]["population"] for c in cats],
                 "entities (log scale)", axis="log")
        ui.label("Each line spans the two graphs, so its length is the "
                 "disagreement and the dot order shows which graph is larger.") \
            .classes("text-xs text-gray-500 dark:text-gray-400 q-mt-sm")

    with ui.card().classes("w-full kg-card q-pa-md"):
        parity_scatter(f"Class entropy — {kg_a} against {kg_b}",
                       names,
                       [classes[c]["a"]["class_entropy"] for c in cats],
                       [classes[c]["b"]["class_entropy"] for c in cats],
                       kg_a, kg_b, "bits")
        ui.label("The dashed line is equality. A point on it means the two "
                 "graphs carry the same information per entity for that class; "
                 "distance from the line is the disagreement, and the side it "
                 "falls on says which graph is higher. Ringed points sit within "
                 "2% of equality.") \
            .classes("text-xs text-gray-500 dark:text-gray-400 q-mt-sm")

    with ui.expansion("Grouped bars (previous view)").classes("w-full"):
        grouped_bar(f"Class entropy — {kg_a} vs {kg_b}", names,
                    [(kg_a, [classes[c]["a"]["class_entropy"] for c in cats]),
                     (kg_b, [classes[c]["b"]["class_entropy"] for c in cats])],
                    "bits", height=max(320, 34 * len(cats) + 120))

    gap_trajectory(pair, kg_a)

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

traj_state = PerClient({"evolution": EVOLUTIONS[0] if EVOLUTIONS else None,
              "metric": "graph_shape", "topk": 8})


@client_refreshable
def trajectories_view():
    ev, m = traj_state["evolution"], traj_state["metric"]
    if not ev:
        return empty("No trajectory results found — run metric 11 across 3+ snapshots")
    d = read_traj(ev, m)
    if not d:
        return empty(f"trajectories_{m}.json not found for {ev}")
    snaps, series = d["snapshots"], d["series"]
    if not series:
        return empty(
            f"No {m.replace('_', ' ')} series spans every snapshot of {ev}. A trajectory "
            "keeps only classes present in all its snapshots, and YAGO 3 types entities "
            "against WordNet synsets (wordnet_person_100007846) that share no name with "
            "YAGO 4's schema.org classes. Graph shape gives the whole-graph view across "
            "all three versions.")

    xl, xn = snaps, None   # full snapshot names, tilted by line_chart
    if m == "graph_shape":
        def panel(field_title):
            field, title = field_title
            s = series.get(field)
            if not s:
                return
            line_chart(title, xl, [(title, s["values"])], height=280, x_name=xn)
        small_multiples(f"Graph shape trajectory — {ev}", SHAPE_FIELDS, panel,
                         min_w="260px")
        ranked = [(f, series[f]) for f, _ in SHAPE_FIELDS if f in series]
    else:
        ranked = sorted(series.items(),
                        key=lambda kv: abs(kv[1].get("relative_change") or 0),
                        reverse=True)[: traj_state["topk"]]
        with ui.card().classes("w-full kg-card q-pa-md"):
            line_chart(f"{m} trajectory — {len(ranked)} series that changed most — {ev}",
                       xl, [(traj_label(k), s["values"]) for k, s in ranked],
                       height=440, x_name=xn)

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

KATEX_VERSION = "0.16.11"
KATEX_CDN = f"https://cdnjs.cloudflare.com/ajax/libs/KaTeX/{KATEX_VERSION}"

KATEX_HEAD = f"""
<link rel="stylesheet" href="{KATEX_CDN}/katex.min.css">
<script defer src="{KATEX_CDN}/katex.min.js"></script>
<style>
  .formula-box {{
    background: #fff;
    border-radius: 10px;
    padding: 14px 22px;
    margin-top: 0;
    display: block;
    width: fit-content;
    min-width: min(340px, 100%);
    max-width: 100%;
    overflow-x: auto;
    overflow-y: hidden;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 13px;
    color: #334155;
  }}
  .body--dark .formula-box {{ background: #0f172a; color: #cbd5e1; }}
  /* KaTeX display mode adds its own vertical margins; the padding above
     already provides them, and they push the card open otherwise. */
  .formula-box .katex-display {{ margin: 0; }}
  .formula-box .katex {{ font-size: 1.3em; color: #0f172a; }}
  .body--dark .formula-box .katex {{ color: #e2e8f0; }}
</style>
<script>
  // NiceGUI builds the DOM over the websocket, long after DOMContentLoaded, and
  // rebuilds it on every tab switch or @ui.refreshable refresh. So instead of
  // KaTeX's auto-render pass we watch for formula nodes and typeset each one
  // exactly once, reading its LaTeX from data-tex.
  (function () {{
    function typeset(root) {{
      if (typeof katex === "undefined") return;
      var nodes = (root || document).querySelectorAll(".tex-pending");
      nodes.forEach(function (el) {{
        el.classList.remove("tex-pending");
        try {{
          katex.render(el.dataset.tex, el, {{
            displayMode: true, throwOnError: false, output: "html"
          }});
        }} catch (e) {{
          /* leave the plain-text fallback already in the element */
        }}
      }});
    }}
    var queued = false;
    function schedule() {{
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () {{ queued = false; typeset(); }});
    }}
    window.addEventListener("load", schedule);
    document.addEventListener("DOMContentLoaded", schedule);
    new MutationObserver(schedule).observe(document.documentElement,
                                           {{childList: true, subtree: true}});
  }})();
</script>
"""


# ============================================================ overview (front page)

# release positions on the timeline, from the dates the thesis states
RELEASE_YEAR = {"yago-3": 2015.0, "yago-4": 2020.15, "yago-4.5.0.2": 2024.0,
                "dbpedia-2015": 2015.8, "dbpedia-2016": 2016.8,
                "dbpedia-2022-matched": 2022.95, "dbpedia-2025": 2025.95}


def compact(n) -> str:
    n = float(n)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(n) >= div:
            v = n / div
            return (f"{v:.2f}" if v < 10 else f"{v:.1f}" if v < 100 else f"{v:.0f}") + suf
    return f"{n:,.0f}"


def overview_findings() -> list[dict]:
    """Headline results, each computed from its result file so the front page
    can never drift from the data. A finding whose file is missing is skipped."""
    out = []
    v = read_pair("yago-3-vs-yago-4", "vocab_evolution")
    if v:
        c = v["classes"]
        n = lambda x: len(x) if isinstance(x, (list, dict)) else int(x)
        out.append({"big": f"{n(c['kept'])}", "unit": "classes kept",
                    "text": f"YAGO 3 to YAGO 4: all {n(c['removed']):,} classes replaced "
                            f"by {n(c['added']):,} new ones",
                    "go": "vocab"})
    bench = [read_pair(p, "triple_diff") for p in CROSS_DIFF_PAIRS]
    bench = [b["benchmark"] for b in bench if b and "benchmark" in b]
    if bench:
        best = max(b["speedup"] for b in bench)
        mem = max(b["naive_bytes"] / b["encoded_bytes"] for b in bench)
        out.append({"big": f"{best:.1f}×", "unit": "faster, integer diff",
                    "text": f"and up to {mem:.0f}× less memory than string sets, "
                            f"across {len(bench)} version pairs",
                    "go": "diff"})
    x = read_pair("yago-4.5.0.2-vs-dbpedia-2025", "cross_kg")
    if x and "organization" in x.get("classes", {}):
        o = x["classes"]["organization"]
        gap = abs(o["a"]["class_entropy"] - o["b"]["class_entropy"])
        out.append({"big": f"{gap:.4f}", "unit": "bits apart",
                    "text": "organization: the one class where YAGO 4.5 and DBpedia 2025 "
                            "carry the same information per entity",
                    "go": "crosskg"})
    a = read_pair("dbpedia-2015-vs-2022", "class_churn")
    b = read_pair("dbpedia-2022-vs-2025", "class_churn")
    t = "http://www.w3.org/2002/07/owl#Thing"
    if a and b and t in a and t in b:
        out.append({"big": f"{a[t]['churn']:.2f} → {b[t]['churn']:.2f}", "unit": "churn",
                    "text": "DBpedia changed most between 2015 and 2022, then settled",
                    "go": "churn"})
    return out


CROSS_DIFF_PAIRS = ["dbpedia-2015-vs-2016", "dbpedia-2015-vs-2022",
                    "dbpedia-2022-vs-2025", "dbpedia-2015-vs-2025",
                    "yago-4-vs-yago-4.5.0.2"]


def overview_view(go):
    snaps = [l for l in LABELS if (data[l].get("graph_shape"))]
    kgs = sorted({l.split("-", 1)[0] for l in snaps})
    with ui.card().classes("w-full kg-card-head q-pa-md"):
        ui.label("Overview").classes("text-lg font-bold")
        ui.label(f"{len(snaps)} snapshots of {len(kgs)} knowledge graphs, measured by "
                 f"{len(METRICS)} metrics. Every number on this page is read from the "
                 "stored results.").classes("text-sm text-gray-600 dark:text-gray-300")

    # ---- release timeline --------------------------------------------------
    rows = {"yago": "YAGO", "dbpedia": "DBpedia"}
    series = []
    for fam, name in rows.items():
        pts = [l for l in snaps if l.startswith(fam) and l in RELEASE_YEAR]
        pts.sort(key=lambda l: RELEASE_YEAR[l])
        series.append({"type": "line", "data": [[RELEASE_YEAR[l], name] for l in pts],
                       "symbol": "none", "lineStyle": {"color": "#CBD5E1", "width": 2},
                       "silent": True, "z": 1})
        series.append({"type": "scatter", "z": 3, "symbolSize": 16,
                       "data": [{"value": [RELEASE_YEAR[l], name], "name": l,
                                 "itemStyle": {"color": COLOR.get(l, PALETTE[0]),
                                               "borderColor": "#fff", "borderWidth": 2}}
                                for l in pts],
                       "label": {"show": True, "position": "top", "fontSize": 11,
                                 "color": "#374151", ":formatter": "p => p.name"}})
    with ui.card().classes("w-full kg-card q-pa-md"):
        ui.label("Releases measured").classes("text-base font-semibold")
        ui.echart({
            "grid": {"left": 70, "right": 30, "top": 30, "bottom": 30},
            "tooltip": {"trigger": "item", ":formatter": "p => p.name || ''"},
            "xAxis": {"type": "value", "min": 2014, "max": 2027, "interval": 1,
                      "axisLabel": {":formatter": "v => String(v)"},
                      "splitLine": {"lineStyle": {"type": "dashed", "opacity": .35}}},
            "yAxis": {"type": "category", "data": list(rows.values()), "inverse": True,
                      "axisLabel": {"fontSize": 12, "fontWeight": 600}},
            "series": series,
        }).classes("w-full").style("height:190px")

    # ---- one card per snapshot, grouped by knowledge graph -------------------
    for fam, name in rows.items():
        mine = sorted((l for l in snaps if l.startswith(fam)), key=lambda l: RELEASE_YEAR.get(l, 0))
        if not mine:
            continue
        ui.label(name).classes("text-xs font-semibold text-gray-500 q-mt-xs").style(
            "letter-spacing:.08em; text-transform:uppercase")
        with ui.element("div").classes("w-full").style(
                "display:grid; gap:14px; grid-template-columns:repeat(4, minmax(0, 1fr))"):
            for l in mine:
                g = data[l]["graph_shape"]
                with ui.card().classes("kg-card q-pa-md").style(
                        f"border-top:3px solid {COLOR.get(l, PALETTE[0])}"):
                    ui.label(l).classes("text-sm font-semibold")
                    with ui.element("div").style(
                            "display:grid; grid-template-columns:1fr 1fr; gap:6px 14px; margin-top:6px"):
                        for key, lab in (("triples", "triples"), ("typed_entities", "entities"),
                                         ("classes", "classes"), ("predicates", "predicates")):
                            with ui.column().classes("gap-0"):
                                ui.label(compact(g.get(key, 0))).classes(
                                    "text-lg font-bold").style("font-variant-numeric:tabular-nums")
                                ui.label(lab).classes("text-xs text-gray-500")

    # ---- headline findings, each a door into its metric -----------------------
    found = overview_findings()
    if found:
        ui.label("Findings").classes("text-base font-semibold q-mt-sm")
        with ui.element("div").classes("w-full").style(
                "display:grid; gap:14px; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr))"):
            for f in found:
                m = META[f["go"]]
                with ui.card().classes("kg-card q-pa-md cursor-pointer finding-card") \
                        .style("display:flex; flex-direction:column") \
                        .on("click", lambda mid=f["go"]: go(mid)):
                    with ui.row().classes("items-baseline gap-2 no-wrap"):
                        ui.label(f["big"]).classes("text-2xl font-bold").style(
                            "color:#072140; font-variant-numeric:tabular-nums")
                        ui.label(f["unit"]).classes("text-sm text-gray-600")
                    ui.label(f["text"]).classes("text-sm text-gray-700 dark:text-gray-300")
                    ui.label(f"Open metric {m['num']}: {m['name']} →").classes(
                        "text-xs").style("color:#3070B3; margin-top:auto; padding-top:8px")


NAV_CSS = """
<style>
  .nav-item {
    display: flex; align-items: center; gap: 10px;
    padding: 7px 12px; margin: 1px 6px; border-radius: 8px;
    cursor: pointer; font-size: 13.5px; line-height: 1.25;
    color: #334155; transition: background .12s, color .12s;
  }
  .nav-item:hover { background: rgba(48,112,179,.07); }
  .finding-card { transition: border-color .12s, box-shadow .12s; }
  .finding-card:hover { border-color: #3070B3 !important;
                        box-shadow: 0 1px 6px rgba(7,33,64,.10) !important; }
  .nav-item.nav-active { background: #EEF3F9; color: #072140; font-weight: 600;
                         box-shadow: inset 3px 0 0 #3070B3; border-radius: 4px; }
  .nav-item.nav-active .q-icon { color: #3070B3; }
  .nav-num {
    font-variant-numeric: tabular-nums; font-size: 11px; opacity: .65;
    min-width: 15px; text-align: right;
  }
  .nav-phase {
    font-size: 10.5px; letter-spacing: .09em; text-transform: uppercase;
    font-weight: 700; color: #94a3b8; padding: 14px 18px 4px;
  }
  .body--dark .nav-item { color: #cbd5e1; }
  .body--dark .nav-item:hover { background: rgba(96,150,210,.14); }
  .body--dark .nav-phase { color: #64748b; }
</style>
"""

# Sidebar icon per metric; the number, name and phase all come from METRICS.
NAV_ICON = {
    "population": "groups", "entf": "insights", "entetimp": "star_rate",
    "classentropy": "scatter_plot", "inforank": "person_search",
    "diversity": "bubble_chart", "entropy_pagerank": "account_tree",
    "shape": "hub", "churn": "autorenew", "diff": "difference",
    "trajectories": "timeline", "vocab": "menu_book", "crosskg": "compare",
}
PHASE_NAME = {1: "Phase 1 · Class-level",
              2: "Phase 2 · Entity-level",
              3: "Phase 3 · Global"}
ORDER = [m["id"] for m in METRICS]


@ui.page("/")
def index():
    ui.add_head_html(KATEX_HEAD)
    ui.add_head_html(NAV_CSS)
    dark = ui.dark_mode()
    # TUM academic blue. One accent, flat surfaces, hairline borders: the
    # gradient header and filled pills this replaced read as generated UI.
    ui.colors(primary="#3070B3", secondary="#072140", accent="#3070B3")
    ui.add_head_html("""<style>
      body { background: #F7F8FA; }
      .body--dark { background: #0F1620; }
      .tum-header { background: #072140 !important; box-shadow: none !important;
                    border-bottom: 1px solid #0B2E55; }
      .kg-card { border: 1px solid #E3E6EB; border-radius: 6px !important;
                 box-shadow: none !important; }
      .kg-card-head { background: #FFFFFF; border: 1px solid #E3E6EB;
                      border-left: 3px solid #3070B3; border-radius: 6px !important;
                      box-shadow: none !important; }
      .body--dark .kg-card, .body--dark .kg-card-head { border-color: #243244; }
      .body--dark .kg-card-head { background: #15202D; }
      .formula-box { background: #F7F8FA; border: 1px solid #E3E6EB; }
      .body--dark .formula-box { background: #0F1620; border-color: #243244; }
    </style>""")

    with ui.header().classes(
            "items-center q-py-md q-px-lg shadow-lg "
            "tum-header"):
        ui.icon("hub", size="34px").classes("text-white")
        ui.label("Efficient Metrics and Visual Analytics for "
                 "Comparing Evolving Knowledge Graphs").classes(
            "text-xl font-bold text-white leading-tight")
        ui.space()
        # looked like a button and did nothing; it now opens the Overview, whose
        # timeline shows the snapshots, and names them on hover
        ui.chip(f"{len(LABELS)} snapshots", icon="storage",
                on_click=lambda: go("overview")) \
            .classes("bg-white/15 text-white cursor-pointer") \
            .tooltip("Loaded: " + ", ".join(LABELS) + ". Click for the overview.")
        ui.switch(on_change=lambda e: dark.enable() if e.value else dark.disable()) \
            .props('checked-icon="dark_mode" unchecked-icon="light_mode" color="amber"') \
            .tooltip("dark mode")

    if not LABELS:
        with ui.column().classes("w-full q-pa-md"):
            empty(f"No results found under {RESULTS_DIR}")
        return

    # The tab strip still drives the panels, but it is hidden -- the sidebar
    # below sets its value, so all 13 metrics are reachable in one click
    # instead of through a phase tab and then a metric tab.
    with ui.tabs().classes("hidden") as nav:
        ui.tab("overview")
        for mid in ORDER:
            ui.tab(mid)

    current = {"id": "overview"}

    def go(mid: str):
        current["id"] = mid
        nav.set_value(mid)
        sidebar.refresh()

    @client_refreshable
    def sidebar():
        active = " nav-active" if current["id"] == "overview" else ""
        with ui.element("div").classes(f"nav-item{active} q-mt-sm") \
                .on("click", lambda: go("overview")):
            ui.label("").classes("nav-num")
            ui.icon("space_dashboard", size="19px")
            ui.label("Overview").classes("leading-tight")
        for phase in (1, 2, 3):
            ui.label(PHASE_NAME[phase]).classes("nav-phase")
            for m in METRICS:
                if m["phase"] != phase:
                    continue
                mid = m["id"]
                active = " nav-active" if current["id"] == mid else ""
                with ui.element("div").classes(f"nav-item{active}") \
                        .on("click", lambda mid=mid: go(mid)):
                    ui.label(str(m["num"])).classes("nav-num")
                    ui.icon(NAV_ICON[mid], size="19px")
                    ui.label(m["name"]).classes("leading-tight")

    with ui.left_drawer(top_corner=False, bottom_corner=True) \
            .props("width=248 bordered").classes("q-pa-none"):
        sidebar()

    with ui.column().classes("w-full max-w-[2000px] mx-auto q-pa-md gap-4"):
        with ui.tab_panels(nav, value="overview").classes("w-full bg-transparent"):

            with ui.tab_panel("overview").classes("q-pa-none gap-4"):
                overview_view(go)

            # ---------------- phase 1 ----------------
            with ui.tab_panel("population").classes("q-pa-none gap-4"):
                metric_header("population")
                def pop_extra():
                    ui.toggle({"own": "own scale", "shared": "same scale"},
                              value=pop_state["scale"],
                              on_change=lambda e: (pop_state.update(scale=e.value),
                                                   population_view.refresh())) \
                        .props("dense").tooltip(
                            "own scale: each panel fits its largest bar  ·  same scale: "
                            "bar lengths comparable across snapshots")
                    ui.toggle(SCOPE_OPTIONS, value=pop_state["scope"],
                              on_change=lambda e: (
                                  pop_state.update(scope=e.value),
                                  population_view.refresh())) \
                        .props("dense").tooltip(
                            "shared: only classes every selected snapshot "
                            "stores, so every cell is comparable  ·  all: the "
                            "union, where a blank means 'not stored', not zero")
                    ui.number(label="Top N", value=pop_state["topn"],
                              min=3, max=40, format="%d",
                              on_change=lambda e: (
                                  pop_state.update(topn=int(e.value or 10)),
                                  population_view.refresh())) \
                        .classes("w-28").props("outlined dense")

                controls(pop_state, population_view.refresh, passes=False,
                         extra=pop_extra)
                population_view()

            with ui.tab_panel("entf").classes("q-pa-none gap-4"):
                metric_header("entf")
                controls(entf_state, entf_view.refresh,
                         extra=lambda: class_picker(entf_state, "property_entropy",
                                                    entf_view.refresh))
                entf_view()

            with ui.tab_panel("entetimp").classes("q-pa-none gap-4"):
                metric_header("entetimp")
                controls(etimp_state, etimp_view.refresh,
                         extra=lambda: class_picker(etimp_state, "ent_etimp",
                                                    etimp_view.refresh))
                etimp_view()

            with ui.tab_panel("classentropy").classes("q-pa-none gap-4"):
                metric_header("classentropy")
                controls(ent_state, class_entropy_view.refresh,
                         extra=lambda: ui.toggle(
                             ENTROPY_FIELDS, value=ent_state["which"],
                             on_change=lambda e: (ent_state.update(which=e.value),
                                                  class_entropy_view.refresh())
                         ).props("dense"))
                class_entropy_view()

            # ---------------- phase 2 ----------------
            with ui.tab_panel("inforank").classes("q-pa-none gap-4"):
                metric_header("inforank")
                with ui.card().classes("w-full kg-card q-pa-md"):
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

            with ui.tab_panel("diversity").classes("q-pa-none gap-4"):
                metric_header("diversity")
                controls(diversity_state, diversity_view.refresh,
                         extra=lambda: class_picker(diversity_state, "object_diversity",
                                                    diversity_view.refresh))
                diversity_view()

            # ---------------- phase 3 ----------------
            with ui.tab_panel("entropy_pagerank").classes("q-pa-none gap-4"):
                metric_header("entropy_pagerank")
                with ui.card().classes("w-full kg-card q-pa-md"):
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

            with ui.tab_panel("shape").classes("q-pa-none gap-4"):
                metric_header("shape")
                controls(shape_state, shape_view.refresh, passes=False)
                shape_view()

            with ui.tab_panel("churn").classes("q-pa-none gap-4"):
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

            with ui.tab_panel("diff").classes("q-pa-none gap-4"):
                metric_header("diff")
                if not DIFF_PAIRS:
                    empty("No triple-diff results found")
                else:
                    pair_controls(diff_state, diff_view.refresh, DIFF_PAIRS)
                    diff_view()

            with ui.tab_panel("trajectories").classes("q-pa-none gap-4"):
                metric_header("trajectories")
                if not EVOLUTIONS:
                    empty("No trajectory results found")
                else:
                    with ui.card().classes("w-full kg-card q-pa-md"):
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

            with ui.tab_panel("vocab").classes("q-pa-none gap-4"):
                metric_header("vocab")
                if not VOCAB_PAIRS:
                    empty("No vocabulary-evolution results found")
                else:
                    pair_controls(vocab_state, vocab_view.refresh, VOCAB_PAIRS)
                    vocab_view()

            with ui.tab_panel("crosskg").classes("q-pa-none gap-4"):
                metric_header("crosskg")
                if not CROSSKG_PAIRS:
                    empty("No cross-KG results found")
                else:
                    pair_controls(crosskg_state, crosskg_view.refresh, CROSSKG_PAIRS)
                    crosskg_view()


# Health check for hosting platforms. "/" builds all thirteen metric views
# before it answers, which on a free-tier CPU outlasts the probe's timeout.
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# the thesis title as a readable address for the deployed copy
@ui.page("/metrics-visual-analytics-evolving-kgs")
def titled_index():
    index()


if __name__ in {"__main__", "__mp_main__"}:
    import os
    # DASH_HOST=0.0.0.0 DASH_PORT=8090 for a server deployment; defaults stay local
    ui.run(host=os.environ.get("DASH_HOST", "127.0.0.1"),
           port=int(os.environ.get("DASH_PORT", "8080")),
           title="Efficient Metrics and Visual Analytics for "
                 "Comparing Evolving Knowledge Graphs",
           reload=False, show=False)

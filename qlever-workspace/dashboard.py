"""
niceGUI dashboard for the thesis metrics.

Reads the Rust metrics' outputs from rust_metrics/results/ and shows one tab per metric:
  - Entity Type Importance (entity_type_importance.json): per-type bar chart + ranked table.
  - PageRank (page_rank.json): top-N most central classes + searchable full ranking.

Run:   python dashboard.py     then open http://localhost:8080
(Generate/refresh the data first:  cd rust_metrics && cargo run --release 10
                                   cd rust_metrics && cargo run --release pagerank)
"""
import json
from pathlib import Path
from nicegui import ui

RESULTS_DIR = Path(__file__).parent / "rust_metrics" / "results"
ETIMP_RESULTS = RESULTS_DIR / "entity_type_importance.json"
PAGERANK_RESULTS = RESULTS_DIR / "page_rank.json"

BLUE = "#3b82f6"
GREEN = "#10b981"


def short(iri: str) -> str:
    """Trim a long IRI to its readable last segment."""
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


# ---------------- data loading ----------------

def load_etimp():
    """Load results -> {type_name: [(predicate_name, score), ...] sorted desc}."""
    if not ETIMP_RESULTS.exists():
        return {}
    raw = json.loads(ETIMP_RESULTS.read_text())
    out = {}
    for type_iri, preds in raw.items():
        rows = sorted(((short(p), float(s)) for p, s in preds.items()),
                      key=lambda x: x[1], reverse=True)
        out[short(type_iri)] = rows
    return out


def load_pagerank():
    """Load results -> [(class_name, score), ...] sorted desc."""
    if not PAGERANK_RESULTS.exists():
        return []
    raw = json.loads(PAGERANK_RESULTS.read_text())
    return sorted(((short(c), float(s)) for c, s in raw.items()),
                  key=lambda x: x[1], reverse=True)


etimp_data = load_etimp()
type_names = sorted(etimp_data)
etimp_state = {"type": type_names[0] if type_names else None, "topn": 10}

pagerank_data = load_pagerank()
pagerank_state = {"topn": 20, "search": ""}


# ---------------- shared UI helpers ----------------

def stat_card(icon: str, label: str, value: str, color: str):
    """A small statistic card for the header row."""
    with ui.card().classes(
            "items-center q-pa-md rounded-2xl shadow-md min-w-[170px] "
            "hover:shadow-xl transition-shadow"):
        ui.icon(icon, size="28px").style(f"color: {color}")
        ui.label(value).classes("text-2xl font-bold")
        ui.label(label).classes("text-xs text-gray-500 uppercase tracking-wide")


def bar_chart(title: str, labels, values, color: str, unit: str, height: int = 460):
    """A polished horizontal echarts bar chart with a gradient + toolbox."""
    ui.echart({
        "title": {"text": title, "left": "center",
                  "textStyle": {"fontSize": 15, "fontWeight": 600}},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "toolbox": {"feature": {"saveAsImage": {"title": "save"}}, "right": 10},
        "grid": {"left": 190, "right": 70, "top": 46, "bottom": 30,
                 "containLabel": False},
        "xAxis": {"type": "value", "name": unit,
                  "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}},
        "yAxis": {"type": "category", "data": labels,
                  "axisLabel": {"fontSize": 11}},
        "series": [{
            "type": "bar",
            "data": values,
            "barMaxWidth": 20,
            "itemStyle": {
                "borderRadius": [0, 8, 8, 0],
                "color": {
                    "type": "linear", "x": 0, "y": 0, "x2": 1, "y2": 0,
                    "colorStops": [
                        {"offset": 0, "color": color + "66"},
                        {"offset": 1, "color": color},
                    ],
                },
            },
            "label": {"show": True, "position": "right", "formatter": "{c}",
                      "fontSize": 10, "color": "#6b7280"},
            "animationDelay": 60,
        }],
        "animationEasing": "elasticOut",
    }).classes("w-full").style(f"height: {height}px")


# ---------------- ETImp tab content ----------------

@ui.refreshable
def etimp_content():
    if not etimp_data:
        with ui.card().classes("w-full items-center q-pa-xl rounded-2xl"):
            ui.icon("warning", size="42px").classes("text-orange-500")
            ui.label("No results found").classes("text-lg font-medium")
            ui.label("Run:  cd rust_metrics && cargo run --release 10") \
                .classes("text-sm text-gray-500 font-mono")
        return

    rows = etimp_data[etimp_state["type"]]
    top = rows[: etimp_state["topn"]]
    labels = [p for p, _ in reversed(top)]
    values = [round(s, 1) for _, s in reversed(top)]

    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        bar_chart(f"Top {etimp_state['topn']} characteristic predicates — "
                  f"{etimp_state['type']}", labels, values, BLUE, "ETImp score")

    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        ui.label(f"Full ranking for {etimp_state['type']} ({len(rows)} predicates)") \
            .classes("text-base font-semibold q-mb-sm")
        ui.table(
            columns=[
                {"name": "rank", "label": "#", "field": "rank", "align": "left"},
                {"name": "predicate", "label": "Predicate", "field": "predicate",
                 "align": "left"},
                {"name": "score", "label": "ETImp score", "field": "score",
                 "align": "right", "sortable": True},
            ],
            rows=[{"rank": i + 1, "predicate": p, "score": round(s, 2)}
                  for i, (p, s) in enumerate(rows)],
            pagination=10,
        ).classes("w-full").props("flat bordered dense")


# ---------------- PageRank tab content ----------------

@ui.refreshable
def pagerank_content():
    if not pagerank_data:
        with ui.card().classes("w-full items-center q-pa-xl rounded-2xl"):
            ui.icon("warning", size="42px").classes("text-orange-500")
            ui.label("No results found").classes("text-lg font-medium")
            ui.label("Run:  cd rust_metrics && cargo run --release pagerank") \
                .classes("text-sm text-gray-500 font-mono")
        return

    top = pagerank_data[: pagerank_state["topn"]]
    labels = [c for c, _ in reversed(top)]
    values = [round(s, 1) for _, s in reversed(top)]

    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        bar_chart(f"Top {pagerank_state['topn']} most central classes "
                  "(subClassOf taxonomy)", labels, values, GREEN, "PageRank",
                  height=560)

    needle = pagerank_state["search"].lower()
    filtered = ([(c, s) for c, s in pagerank_data if needle in c.lower()]
                if needle else pagerank_data)
    with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
        ui.label(f"Full ranking ({len(filtered):,} of {len(pagerank_data):,} classes)") \
            .classes("text-base font-semibold q-mb-sm")
        ui.table(
            columns=[
                {"name": "rank", "label": "#", "field": "rank", "align": "left"},
                {"name": "class", "label": "Class", "field": "class", "align": "left"},
                {"name": "score", "label": "PageRank", "field": "score",
                 "align": "right", "sortable": True},
            ],
            rows=[{"rank": i + 1, "class": c, "score": round(s, 4)}
                  for i, (c, s) in enumerate(filtered)],
            pagination=15,
        ).classes("w-full").props("flat bordered dense")


# ---------------- page layout ----------------

dark = ui.dark_mode()

# header bar
with ui.header().classes(
        "items-center q-py-md q-px-lg shadow-lg "
        "bg-gradient-to-r from-blue-700 via-indigo-700 to-violet-700"):
    ui.icon("hub", size="34px").classes("text-white")
    with ui.column().classes("gap-0"):
        ui.label("YAGO — KG Metrics Dashboard").classes(
            "text-2xl font-bold text-white leading-tight")
        ui.label("Knowledge-graph metrics computed in Rust + SPARQL, Knowgly-style") \
            .classes("text-xs text-blue-100")
    ui.space()
    ui.chip("YAGO 4.5.0.2 · 1.3 B triples", icon="storage") \
        .classes("bg-white/15 text-white")
    ui.switch(on_change=lambda e: dark.enable() if e.value else dark.disable()) \
        .props('checked-icon="dark_mode" unchecked-icon="light_mode" color="amber"') \
        .tooltip("dark mode")

with ui.column().classes("w-full max-w-6xl mx-auto q-pa-md gap-4"):

    # stat cards
    n_preds = sum(len(v) for v in etimp_data.values())
    with ui.row().classes("w-full justify-center gap-4"):
        stat_card("category", "entity types analysed", f"{len(type_names)}", BLUE)
        stat_card("account_tree", "type–predicate scores", f"{n_preds:,}", BLUE)
        stat_card("workspaces", "classes ranked by PageRank",
                  f"{len(pagerank_data):,}", GREEN)
        stat_card("bolt", "metrics live", "2 of 11", "#8b5cf6")

    # tabs
    with ui.tabs().classes("w-full") as tabs:
        etimp_tab = ui.tab("Entity Type Importance", icon="insights")
        pagerank_tab = ui.tab("PageRank", icon="share")

    with ui.tab_panels(tabs, value=etimp_tab).classes("w-full bg-transparent"):

        with ui.tab_panel(etimp_tab).classes("q-pa-none gap-4"):
            with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
                with ui.row().classes("items-center gap-6 w-full"):
                    ui.icon("tune").classes("text-gray-400")
                    ui.select(type_names, value=etimp_state["type"],
                              label="Entity type",
                              on_change=lambda e: (etimp_state.update(type=e.value),
                                                   etimp_content.refresh())) \
                        .classes("w-72").props("outlined dense options-dense")
                    ui.number(label="Top N", value=etimp_state["topn"], min=3, max=40,
                              format="%d",
                              on_change=lambda e: (
                                  etimp_state.update(topn=int(e.value or 10)),
                                  etimp_content.refresh())) \
                        .classes("w-28").props("outlined dense")
                    ui.space()
                    ui.label("ETImp(p,t) = EF × log₂(|Eₜ| / EF)") \
                        .classes("text-xs text-gray-400 font-mono")
            etimp_content()

        with ui.tab_panel(pagerank_tab).classes("q-pa-none gap-4"):
            with ui.card().classes("w-full rounded-2xl shadow-md q-pa-md"):
                with ui.row().classes("items-center gap-6 w-full"):
                    ui.icon("tune").classes("text-gray-400")
                    ui.number(label="Top N", value=pagerank_state["topn"], min=5,
                              max=50, format="%d",
                              on_change=lambda e: (
                                  pagerank_state.update(topn=int(e.value or 20)),
                                  pagerank_content.refresh())) \
                        .classes("w-28").props("outlined dense")
                    ui.input(label="Search class", placeholder="e.g. Person",
                             on_change=lambda e: (
                                 pagerank_state.update(search=e.value or ""),
                                 pagerank_content.refresh())) \
                        .classes("w-72").props("outlined dense clearable") \
                        .props('prepend-inner-icon="search"' if False else "")
                    ui.space()
                    ui.label("PR(v) = (1−d) + d · Σ PR(u)/outdeg(u)") \
                        .classes("text-xs text-gray-400 font-mono")
            pagerank_content()

    # footer
    ui.label("Bachelor thesis — Efficient Metrics and Visual Analytics for "
             "Comparing Evolving Knowledge Graphs · data source: local QLever "
             "endpoint") \
        .classes("text-xs text-gray-400 self-center q-mt-md")

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(port=8080, title="YAGO Metrics Dashboard", reload=False, show=False)

"""
niceGUI dashboard for the thesis metrics.

Reads the Rust metric's output (rust_metrics/results/entity_type_importance.json)
and shows, per entity type, an interactive bar chart of its most characteristic
predicates plus the full ranked table.

Run:   python dashboard.py     then open http://localhost:8080
(Generate/refresh the data first with:  cd rust_metrics && cargo run --release 10)
"""
import json
from pathlib import Path
from nicegui import ui

RESULTS = Path(__file__).parent / "rust_metrics" / "results" / "entity_type_importance.json"


def short(iri: str) -> str:
    """Trim a long IRI to its readable last segment."""
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def load_data():
    """Load results -> {type_name: [(predicate_name, score), ...] sorted desc}."""
    raw = json.loads(RESULTS.read_text())
    out = {}
    for type_iri, preds in raw.items():
        rows = sorted(((short(p), float(s)) for p, s in preds.items()),
                      key=lambda x: x[1], reverse=True)
        out[short(type_iri)] = rows
    return out


data = load_data()
type_names = sorted(data)
state = {"type": type_names[0] if type_names else None, "topn": 10}


@ui.refreshable
def content():
    if not data:
        ui.label("No results found. Run the Rust metric first: "
                 "cd rust_metrics && cargo run --release 10").classes("text-red-500")
        return

    rows = data[state["type"]]
    top = rows[: state["topn"]]
    # echarts draws horizontal bars bottom->top, so reverse for descending look
    labels = [p for p, _ in reversed(top)]
    values = [round(s, 1) for _, s in reversed(top)]

    ui.echart({
        "title": {"text": f"Top {state['topn']} characteristic predicates — {state['type']}",
                  "left": "center"},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": 180, "right": 50, "top": 50, "bottom": 30},
        "xAxis": {"type": "value", "name": "ETImp score"},
        "yAxis": {"type": "category", "data": labels},
        "series": [{"type": "bar", "data": values,
                    "itemStyle": {"color": "#3b82f6"},
                    "label": {"show": True, "position": "right",
                              "formatter": "{c}"}}],
    }).classes("w-full").style("height: 460px")

    ui.label(f"Full ranking for {state['type']} ({len(rows)} predicates)") \
        .classes("text-lg font-medium mt-4")
    ui.table(
        columns=[
            {"name": "rank", "label": "#", "field": "rank", "align": "left"},
            {"name": "predicate", "label": "Predicate", "field": "predicate", "align": "left"},
            {"name": "score", "label": "ETImp score", "field": "score", "align": "right",
             "sortable": True},
        ],
        rows=[{"rank": i + 1, "predicate": p, "score": round(s, 2)}
              for i, (p, s) in enumerate(rows)],
        pagination=10,
    ).classes("w-full")


# ---------------- page layout ----------------
ui.label("YAGO — Entity Type Importance").classes("text-3xl font-bold")
ui.label("Which predicates best characterize each entity type "
         "(ETImp = EF_p × log2(|E_t| / EF_p), computed in Rust + SPARQL over the local YAGO index)") \
    .classes("text-gray-500 mb-2")
ui.label(f"Loaded {len(type_names)} types from {RESULTS.name}").classes("text-xs text-gray-400 mb-2")

with ui.row().classes("items-center gap-4"):
    ui.select(type_names, value=state["type"], label="Entity type",
              on_change=lambda e: (state.update(type=e.value), content.refresh())) \
        .classes("w-72")
    ui.number(label="Top N", value=state["topn"], min=3, max=40, format="%d",
              on_change=lambda e: (state.update(topn=int(e.value or 10)), content.refresh())) \
        .classes("w-28")

ui.separator()
content()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(port=8080, title="YAGO Metrics Dashboard", reload=False, show=False)

#!/usr/bin/env python3
"""Regenerate writing/data/*.csv from rust_metrics/results/.

Run after any metric re-run; the thesis figures and tables read these files, so
no number in the document is ever typed by hand.
"""
import json, pathlib, sys

R = pathlib.Path(__file__).parent / "rust_metrics" / "results"
D = pathlib.Path.home() / "thesis" / "writing" / "data"
D.mkdir(exist_ok=True)

def load(p):
    f = R / p
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

def num(n):                      # thin space: pgfplotstable splits on commas
    return f"{int(n):,}".replace(",", "\\,")

def write(name, header, rows):
    (D / name).write_text(",".join(header) + "\n" +
                          "\n".join(",".join(str(c) for c in r) for r in rows) + "\n")
    print(f"  {name:<28}{len(rows)} rows")

def cross_kg(pair):
    d = load(f"{pair}/cross_kg.json")
    if not d:
        print(f"  (no cross_kg.json for {pair})"); return None
    return sorted(d["classes"].items(), key=lambda kv: -kv[1]["a"]["population"])

PAIR = sys.argv[1] if len(sys.argv) > 1 else "yago-4.5.0.2-vs-dbpedia-2025"
rows = cross_kg(PAIR)
if rows:
    write("cross_kg_plot.csv",
          ["class","H_yago","H_dbpedia","pop_yago","pop_dbpedia","preds_yago","preds_dbpedia"],
          [[c, f"{v['a']['class_entropy']:.4f}", f"{v['b']['class_entropy']:.4f}",
            int(v['a']['population']), int(v['b']['population']),
            int(v['a']['predicates']), int(v['b']['predicates'])] for c, v in rows])
    write("cross_kg.csv",
          ["class","pop_yago","pop_dbpedia","H_yago","H_dbpedia","delta_H","preds_yago","preds_dbpedia"],
          [[c.capitalize(), num(v['a']['population']), num(v['b']['population']),
            f"{v['a']['class_entropy']:.2f}", f"{v['b']['class_entropy']:.2f}",
            f"{v['delta_class_entropy']:.2f}",
            num(v['a']['predicates']), num(v['b']['predicates'])] for c, v in rows])
    print(f"  pair: {PAIR}  classes: {len(rows)}")

# ---- metric 13 series: one YAGO release against all four DBpedia releases,
# restricted to the classes matched in every pairing
DBP = ["2015", "2016", "2022", "2025"]

def crosskg_series(yago, out):
    runs = {y: load(f"{yago}-vs-dbpedia-{y}/cross_kg.json") for y in DBP}
    if not all(runs.values()):
        print(f"  (series {yago}: missing {[y for y in DBP if not runs[y]]})"); return
    common = set.intersection(*(set(r["classes"]) for r in runs.values()))
    first = runs["2015"]["classes"]
    rows = []
    for c in sorted(common, key=lambda c: -first[c]["a"]["population"]):
        hy = first[c]["a"]["class_entropy"]
        hd = [runs[y]["classes"][c]["b"]["class_entropy"] for y in DBP]
        rows.append([c.capitalize(), f"{hy:.2f}"] + [f"{h:.2f}" for h in hd]
                    + [f"{abs(hy - h):.2f}" for h in hd])
    write(out, ["class", "H_yago"] + [f"H_{y}" for y in DBP] + [f"gap{y}" for y in DBP], rows)

crosskg_series("yago-4.5.0.2", "crosskg_series.csv")
crosskg_series("yago-4", "crosskg_series_yago4.csv")

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

# ---- Experiment 1 / 2 additions: metrics 1, 2, 3, 5, 6, 11 and the class-entropy
# figure, all from the stored results so no chart value is typed by hand.
import re as _re
SNAPS7 = ["yago-3", "yago-4", "yago-4.5.0.2", "dbpedia-2015", "dbpedia-2016",
          "dbpedia-2022-matched", "dbpedia-2025"]
PINNED6 = SNAPS7[1:]
PREFIX = {"http://schema.org/": "schema:", "http://bioschemas.org/": "bio:",
          "http://yago-knowledge.org/resource/": "yago:",
          "http://dbpedia.org/ontology/": "dbo:", "http://dbpedia.org/property/": "dbp:",
          "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
          "http://www.w3.org/2002/07/owl#": "owl:", "http://xmlns.com/foaf/0.1/": "foaf:",
          "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
          "http://www.w3.org/2004/02/skos/core#": "skos:",
          "http://purl.org/dc/terms/": "dct:", "http://www.w3.org/ns/prov#": "prov:",
          "http://www.georss.org/georss/": "georss:",
          "http://www.w3.org/2003/01/geo/wgs84_pos#": "geo:",
          "http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#": "dul:",
          "http://www.wikidata.org/entity/": "wd:",
          "http://yago-knowledge.org/resource/wikicat_": "wikicat:",
          "http://yago-knowledge.org/resource/wordnet_": "wordnet:"}
CANON = {"AdministrativeRegion": "AdministrativeArea", "Species": "Taxon",
         "ChemicalCompound": "Chemical_compound"}

def local(iri):
    return _re.split(r"[/#]", iri)[-1]

def qn(iri):
    for k, v in sorted(PREFIX.items(), key=lambda kv: -len(kv[0])):
        if iri.startswith(k):
            return v + iri[len(k):]
    return local(iri)

def tex(s):                      # safe inside a pgfplotstable string cell
    s = _re.sub(r"_u([0-9A-Fa-f]{4})_", lambda m: chr(int(m.group(1), 16)), s)
    return (s.replace("\\", "").replace("_", "\\_").replace("&", "\\&")
             .replace("%", "\\%").replace("#", "\\#").replace(",", "\\,"))

def pct(x):
    return f"{100 * x:.1f}\\%"

def short30(name):             # YAGO 3 synset names run to 45 characters
    name = _re.sub(r"_1\d{8}$", "", name)       # drop the WordNet synset id
    return name if len(name) <= 32 else name[:30] + "..."

# metric 1: the three largest classes per snapshot and their share of entities
rows = []
for s in SNAPS7:
    d = load(f"{s}/class_population.json")
    top = sorted(d["classes"].items(), key=lambda kv: -kv[1]["population"])[:3]
    rows.append([s.replace("-matched", ""), num(d["total_entities"])] +
                sum([[tex(short30(qn(i))), pct(v["share"])] for i, v in top], []))
write("population_top.csv", ["snapshot", "entities", "c1", "s1", "c2", "s2", "c3", "s3"], rows)

# metrics 2 and 3: Person's top predicates by property entropy and by ETImp
rows = []
for s in ["yago-4", "yago-4.5.0.2", "dbpedia-2015", "dbpedia-2025"]:
    pe, et = load(f"{s}/property_entropy_pinned.json"), load(f"{s}/ent_etimp_pinned.json")
    cls = [k for k in pe if local(k) == "Person"][0]
    a = sorted(pe[cls].items(), key=lambda kv: -kv[1])[:3]
    b = sorted(et[cls].items(), key=lambda kv: -kv[1])[:3]
    for r in range(3):
        rows.append([s if r == 0 else "", r + 1, tex(qn(a[r][0])), f"{a[r][1]:.2f}",
                     tex(qn(b[r][0])), f"{b[r][1]:.1f}"])
write("person_entf_etimp.csv", ["snapshot", "rank", "entf_pred", "entf", "etimp_pred", "etimp"], rows)

# metric 5: the three most informative entities per snapshot
rows = []
for s in SNAPS7:
    d = load(f"{s}/entity_informativeness.json")
    top = sorted(d["entities"].items(), key=lambda kv: -kv[1]["inforank"])[:3]
    for r, (iri, v) in enumerate(top):
        name = local(iri).replace("_", " ")
        name = _re.sub(r" u([0-9A-Fa-f]{4}) ", lambda m: chr(int(m.group(1), 16)), name)
        name = name if len(name) <= 42 else name[:40] + "..."
        rows.append([s.replace("-matched", "") if r == 0 else "", tex(name), num(v["literal_properties"]),
                     f"{v['inforank'] * 1e6:.2f}"])
write("inforank_top.csv", ["snapshot", "entity", "props", "ir_e6"], rows)

# metric 6: most diverse predicate per pinned class, latest release of each graph
def diversity(s):
    d = load(f"{s}/object_diversity_pinned.json")
    return {CANON.get(local(c), local(c)): max(v.items(), key=lambda kv: kv[1])
            for c, v in d.items()}
dy, dd = diversity("yago-4.5.0.2"), diversity("dbpedia-2025")
rows = [[tex(c), tex(qn(dy[c][0])), num(dy[c][1]), tex(qn(dd[c][0])), num(dd[c][1])]
        for c in sorted(dy, key=lambda c: -dy[c][1]) if c in dd]
write("diversity_top.csv", ["class", "y_pred", "y_n", "d_pred", "d_n"], rows)

# metric 4 figure: object entropy of the pinned classes in all six snapshots
H = {}
for s in PINNED6:
    for c, v in load(f"{s}/class_entropy_pinned.json").items():
        H.setdefault(CANON.get(local(c), local(c)), {})[s] = v["object_entropy"]
order = ["Person", "Taxon", "AdministrativeArea", "Star", "Galaxy", "Chemical_compound"]
write("class_entropy_plot.csv", ["class"] + [s.replace(".", "").replace("-", "") for s in PINNED6],
      [[c.replace("_", " ")] + [f"{H[c][s]:.3f}" for s in PINNED6] for c in order])

# metric 11: graph-shape trajectories, each series indexed to its first release
for ev, out in [("yago-evolution", "traj_yago.csv"), ("dbpedia-evolution", "traj_dbpedia.csv")]:
    d = load(f"{ev}/trajectories_graph_shape.json")
    keys = ["triples", "typed_entities", "classes", "predicates"]
    vals = {k: d["series"][k]["values"] for k in keys}
    rows = [[sn.replace("-matched", "")] + [f"{vals[k][i] / vals[k][0]:.4f}" for k in keys]
            + [num(vals[k][i]) for k in keys] for i, sn in enumerate(d["snapshots"])]
    write(out, ["snapshot"] + [k + "_idx" for k in keys] + keys, rows)

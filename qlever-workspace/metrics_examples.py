"""
Example KG metrics computed via SPARQL — the seed of your thesis metrics.

Run:  python metrics_examples.py
Uses whatever endpoint sparql.py points at (public YAGO by default; set
QLEVER_ENDPOINT=http://localhost:9004 to hit your local index later).
"""
from sparql import run_query, scalar, ENDPOINT


def metric_total_triples():
    return scalar("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")


def metric_distinct_predicates():
    return scalar("SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE { ?s ?p ?o }")


def metric_distinct_subjects():
    return scalar("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s ?p ?o }")


def metric_top_predicates(limit=10):
    # How often each predicate is used — a classic schema-usage metric.
    return run_query(f"""
        SELECT ?p (COUNT(*) AS ?uses) WHERE {{ ?s ?p ?o }}
        GROUP BY ?p ORDER BY DESC(?uses) LIMIT {limit}
    """)


def metric_top_classes(limit=10):
    # Most populated classes (how many instances per type).
    return run_query(f"""
        SELECT ?class (COUNT(?s) AS ?instances) WHERE {{
          ?s <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?class
        }} GROUP BY ?class ORDER BY DESC(?instances) LIMIT {limit}
    """)


def shorten(iri: str) -> str:
    # crude prefix-shortener just for readable console output
    for sep in ("#", "/"):
        if sep in iri:
            return iri.rsplit(sep, 1)[-1]
    return iri


if __name__ == "__main__":
    print(f"Endpoint: {ENDPOINT}\n")
    print(f"{'Total triples':28}: {int(metric_total_triples()):,}")
    print(f"{'Distinct predicates':28}: {int(metric_distinct_predicates()):,}")
    print(f"{'Distinct subjects':28}: {int(metric_distinct_subjects()):,}")

    print("\nTop predicates by usage:")
    for r in metric_top_predicates():
        print(f"  {int(r['uses']):>14,}  {shorten(r['p'])}")

    print("\nTop classes by #instances:")
    for r in metric_top_classes():
        print(f"  {int(r['instances']):>14,}  {shorten(r['class'])}")

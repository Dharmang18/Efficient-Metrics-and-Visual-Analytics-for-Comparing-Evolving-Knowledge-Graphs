"""
Tiny reusable SPARQL client for the thesis.

Every metric you build will ultimately be: send a SPARQL query to a QLever
endpoint, get back rows, turn them into numbers/charts. This module is that
one shared building block.

Swap ENDPOINT between:
  - the public YAGO endpoint (works now, no Docker), or
  - your local index once Docker is running:  http://localhost:9004
by setting the QLEVER_ENDPOINT environment variable, or passing endpoint=...
"""
from __future__ import annotations
import os
import requests

# Default endpoint. Override with:  export QLEVER_ENDPOINT=http://localhost:9004
PUBLIC_YAGO = "https://qlever.cs.uni-freiburg.de/api/yago-4"
LOCAL_YAGO = "http://localhost:9004"
ENDPOINT = os.environ.get("QLEVER_ENDPOINT", PUBLIC_YAGO)


def run_query(query: str, endpoint: str | None = None, timeout: int = 120) -> list[dict]:
    """Run a SPARQL SELECT query and return a list of row dicts.

    Each row maps variable name -> its value as a plain Python string.
    (For typed work you can inspect the raw JSON instead; kept simple here.)
    """
    endpoint = endpoint or ENDPOINT
    resp = requests.post(
        endpoint,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    vars_ = data["head"]["vars"]
    rows = []
    for b in data["results"]["bindings"]:
        rows.append({v: b[v]["value"] if v in b else None for v in vars_})
    return rows


def scalar(query: str, endpoint: str | None = None) -> str | None:
    """Convenience: run a query expected to return a single value (e.g. COUNT)."""
    rows = run_query(query, endpoint)
    if not rows:
        return None
    first = rows[0]
    return next(iter(first.values()))


if __name__ == "__main__":
    print("Endpoint:", ENDPOINT)
    print("Total triples:", scalar("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"))

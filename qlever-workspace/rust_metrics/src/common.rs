//! Common reusable SPARQL queries and small maths helpers
//! (mirrors Knowgly's common.rs).

use crate::qlever_client::{endpoint, SparqlEndpoint};
use std::collections::HashMap;

/// Trim a long IRI to its last path/fragment segment, for readable output.
pub fn short(iri: &str) -> &str {
    iri.rsplit(['#', '/']).next().unwrap_or(iri)
}

/// Fetch the most-populated type IRIs (top `limit` by number of entities).
///
/// Knowgly fetches *all* types; on a laptop, running one query per type over
/// 1.3B triples is slow, so we restrict to the busiest types. Same metric,
/// tractable scope. Raise `limit` (or remove it) when running on a server.
pub fn fetch_top_type_iris(limit: usize) -> Vec<String> {
    top_type_iris(endpoint(), limit)
}

/// Same, against an explicit endpoint (used when comparing two graphs).
pub fn top_type_iris(ep: &SparqlEndpoint, limit: usize) -> Vec<String> {
    // COUNT(*) rather than COUNT(DISTINCT ?s): in a set-semantics store the
    // (subject, type) pairs are already unique, so the counts are identical
    // and the DISTINCT only pays for a sort (measured ~1.6x slower on YAGO).
    let q = format!(
        "SELECT ?type (COUNT(*) AS ?n) WHERE {{ ?s a ?type }} \
         GROUP BY ?type ORDER BY DESC(?n) LIMIT {limit}"
    );
    ep.column(&q, "type")
}

/// |E_t| for every type t: number of distinct entities of that type.
/// (Computed in a single GROUP BY query, then looked up per type.)
pub fn entity_count_per_type() -> HashMap<String, u64> {
    entity_count_per_type_of(endpoint())
}

pub fn entity_count_per_type_of(ep: &SparqlEndpoint) -> HashMap<String, u64> {
    let q = "SELECT ?type (COUNT(*) AS ?ef_t) WHERE { ?s a ?type } GROUP BY ?type";
    let mut counts = HashMap::new();
    for r in ep.rows(q) {
        if let (Some(t), Some(n)) = (r.get("type"), r.get("ef_t")) {
            if let Ok(v) = n.parse::<u64>() {
                counts.insert(t.clone(), v);
            }
        }
    }
    counts
}

/// The predicates used most often by entities of one type, with their usage
/// counts. Most per-type metrics only need the busy predicates, and asking for
/// the top K keeps one query per type instead of one per (type, predicate).
pub fn top_predicates_for_type(ep: &SparqlEndpoint, type_iri: &str, limit: usize)
    -> Vec<(String, u64)>
{
    let q = format!(
        "SELECT ?p (COUNT(*) AS ?n) WHERE {{ ?s a <{type_iri}> . ?s ?p ?o }} \
         GROUP BY ?p ORDER BY DESC(?n) LIMIT {limit}"
    );
    ep.rows(&q)
        .into_iter()
        .filter_map(|r| Some((r.get("p")?.clone(), r.get("n")?.parse().ok()?)))
        .collect()
}

/// All class IRIs of a graph (capped, so a runaway query can't blow up memory).
pub fn class_iris(ep: &SparqlEndpoint, limit: usize) -> Vec<String> {
    let q = format!("SELECT DISTINCT ?type WHERE {{ ?s a ?type }} LIMIT {limit}");
    ep.column(&q, "type")
}

/// All predicate IRIs of a graph (capped for the same reason).
pub fn predicate_iris(ep: &SparqlEndpoint, limit: usize) -> Vec<String> {
    let q = format!("SELECT DISTINCT ?p WHERE {{ ?s ?p ?o }} LIMIT {limit}");
    ep.column(&q, "p")
}

// ------------------------------------------------------------------ entropy

/// The *count-of-counts* histogram of the values bound to `?v` by `pattern`:
/// pairs (c, m_c) = "m_c distinct values occur exactly c times".
///
/// This is the trick that makes every entropy metric cheap. Shannon entropy
/// depends only on the multiset of counts, never on the values themselves, so
/// there is no reason to stream millions of object values over HTTP: a nested
/// GROUP BY makes QLever fold them into a histogram of a few hundred rows,
/// and the result is still EXACT, not sampled.
pub fn value_histogram(ep: &SparqlEndpoint, pattern: &str) -> Vec<(f64, f64)> {
    let q = format!(
        "SELECT ?c (COUNT(?v) AS ?m) WHERE {{ \
            {{ SELECT ?v (COUNT(*) AS ?c) WHERE {{ {pattern} }} GROUP BY ?v }} \
         }} GROUP BY ?c"
    );
    ep.rows(&q)
        .into_iter()
        .filter_map(|r| Some((r.get("c")?.parse().ok()?, r.get("m")?.parse().ok()?)))
        .collect()
}

/// Shannon entropy in bits, folded from a count-of-counts histogram:
///     H = -Σ_o P(o) log2 P(o)
///       = log2 N - (1/N) Σ_c m_c · c · log2 c
/// Returns (entropy, N = total occurrences, D = distinct values).
pub fn entropy_from_histogram(hist: &[(f64, f64)]) -> (f64, f64, f64) {
    let n: f64 = hist.iter().map(|(c, m)| c * m).sum();
    let distinct: f64 = hist.iter().map(|(_, m)| *m).sum();
    if n <= 0.0 {
        return (0.0, 0.0, 0.0);
    }
    let weighted: f64 = hist
        .iter()
        .map(|(c, m)| if *c > 0.0 { m * c * c.log2() } else { 0.0 })
        .sum();
    let h = n.log2() - weighted / n;
    // tiny negative values can appear from floating-point noise when every
    // value is identical (H = 0); clamp rather than report -0.0000001 bits
    (if h < 0.0 { 0.0 } else { h }, n, distinct)
}

/// Entropy of the object values of one predicate inside one class — EntF(p, t).
pub fn property_entropy(ep: &SparqlEndpoint, type_iri: &str, predicate_iri: &str)
    -> (f64, f64, f64)
{
    let pattern = format!("?s a <{type_iri}> . ?s <{predicate_iri}> ?v");
    entropy_from_histogram(&value_histogram(ep, &pattern))
}

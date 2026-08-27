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
    selected_type_iris(endpoint(), limit)
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

/// Top types with their entity counts (one GROUP BY, same query as metric 1).
pub fn top_types_with_counts(ep: &SparqlEndpoint, limit: usize) -> Vec<(String, u64)> {
    let q = format!(
        "SELECT ?type (COUNT(*) AS ?n) WHERE {{ ?s a ?type }} \
         GROUP BY ?type ORDER BY DESC(?n) LIMIT {limit}"
    );
    ep.rows(&q)
        .into_iter()
        .filter_map(|r| Some((r.get("type")?.clone(), r.get("n")?.parse().ok()?)))
        .collect()
}

/// The classes a per-class metric should actually measure.
///
/// Two things this solves, both learned the hard way on YAGO:
///
/// 1. **Comparability.** "The top N classes" picks a DIFFERENT set in each
///    snapshot — YAGO 4's top 8 and YAGO 4.5's top 8 share only `Person` — so
///    per-class metrics computed that way cannot be compared across versions,
///    which is the whole point of the thesis. Setting `QLEVER_CLASSES` to a
///    comma-separated list of local names (e.g. `Person,Taxon,Star`) pins the
///    same classes everywhere; each name is resolved to whatever IRI that
///    snapshot actually uses, since the namespace is not stable either
///    (`schema:Taxon` in one version, `yago:Politician` in another).
/// 2. **Tractability.** Unpinned, a class like `schema:Thing` (66.9M entities on
///    YAGO 4) needs more than the server's whole query budget for a single
///    histogram. `QLEVER_MAX_CLASS_SIZE` (default 10M) skips such classes and
///    says so, instead of letting the metric die part-way through.
pub fn selected_type_iris(ep: &SparqlEndpoint, limit: usize) -> Vec<String> {
    match std::env::var("QLEVER_CLASSES").ok().filter(|s| !s.trim().is_empty()) {
        Some(list) => pinned_type_iris(ep, &list),
        None => {
            let max = std::env::var("QLEVER_MAX_CLASS_SIZE")
                .ok()
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(10_000_000);
            let mut kept = Vec::new();
            for (iri, n) in top_types_with_counts(ep, limit * 3) {
                if kept.len() >= limit {
                    break;
                }
                if n > max {
                    println!("  skipping {} ({} entities > QLEVER_MAX_CLASS_SIZE {})",
                             short(&iri), n, max);
                } else {
                    kept.push(iri);
                }
            }
            kept
        }
    }
}

/// Resolve pinned local names to this snapshot's actual class IRIs.
///
/// Aborts if a name cannot be found: a silently missing class would quietly
/// shrink the comparison set and make two snapshots look more alike than they
/// are, which is exactly the kind of wrong number a metric must never produce.
fn pinned_type_iris(ep: &SparqlEndpoint, list: &str) -> Vec<String> {
    let wanted: Vec<&str> = list.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    // One cheap scan of the busiest classes; every pinned class is by definition
    // a populated one, so the top few thousand always contain it.
    let scan = std::env::var("QLEVER_CLASS_SCAN")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(5_000);
    let table = top_types_with_counts(ep, scan);

    let mut out = Vec::new();
    let mut missing = Vec::new();
    for name in &wanted {
        let hits: Vec<&(String, u64)> = table
            .iter()
            .filter(|(iri, _)| short(iri).eq_ignore_ascii_case(name))
            .collect();
        match hits.split_first() {
            Some(((iri, n), rest)) => {
                println!("  pinned {:<22} -> {} ({} entities)", name, iri, n);
                // A local name can be shared by several namespaces -- DBpedia has
                // dbo:Person (1,922,501), schema:Person and foaf:Person (1,860,208
                // each). We take the most populated, which is deterministic, but
                // silently choosing between them would hide a real modelling
                // difference between the graphs, so say so.
                for (other, on) in rest {
                    println!("      NOTE: {} also matches {} ({} entities) -- using the \
                              most populated", name, other, on);
                }
                out.push(iri.clone());
            }
            None => missing.push(*name),
        }
    }
    if !missing.is_empty() {
        eprintln!("\n  ERROR: pinned class(es) not found in the top {scan} classes of {}: {}",
                  ep.url(), missing.join(", "));
        eprintln!("  A missing class would silently shrink the comparison set. Fix the name,");
        eprintln!("  or raise QLEVER_CLASS_SCAN if the class is real but rare.\n");
        std::process::exit(1);
    }
    out
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

/// All class IRIs of a graph, ordered so the cap is deterministic.
pub fn class_iris(ep: &SparqlEndpoint, limit: usize) -> Vec<String> {
    let q = format!("SELECT DISTINCT ?type WHERE {{ ?s a ?type }} ORDER BY ?type LIMIT {limit}");
    truncation_guard(ep.column(&q, "type"), limit, "classes")
}

/// All predicate IRIs of a graph, ordered for the same reason.
pub fn predicate_iris(ep: &SparqlEndpoint, limit: usize) -> Vec<String> {
    let q = format!("SELECT DISTINCT ?p WHERE {{ ?s ?p ?o }} ORDER BY ?p LIMIT {limit}");
    truncation_guard(ep.column(&q, "p"), limit, "predicates")
}

/// A set comparison is only meaningful over COMPLETE sets. If the cap was hit,
/// the two sides were arbitrary samples and every "added"/"removed" term is an
/// artefact of the cap — which looks exactly like a real result unless we say so.
/// (This bit once: YAGO 4 has 10,103 classes, a cap of 300 reported 273 added
/// and 273 removed, both of which are just 300 minus the overlap.)
fn truncation_guard(terms: Vec<String>, limit: usize, what: &str) -> Vec<String> {
    if terms.len() >= limit {
        eprintln!(
            "\n  WARNING: hit the cap of {limit} {what}. The graph has at least that\n\
             \x20 many, so this is a SAMPLE, not the full set, and any added/removed\n\
             \x20 counts derived from it are meaningless. Re-run with a larger cap.\n");
    }
    terms
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

// ------------------------------------------------------------- parallelism

/// A rayon pool for firing SPARQL queries concurrently, sized by
/// `QLEVER_PARALLELISM` (default 4).
///
/// The size matters more than it looks: QLever's `MEMORY_FOR_QUERIES` budget is
/// shared by all queries in flight, so N concurrent `GROUP BY`s over a large
/// class divide that budget N ways. On a 1.3B-triple YAGO with `-m 5G`, four
/// parallel count-of-counts histograms exhausted it and the server answered
/// "Tried to allocate 67.1 MB, but only 65.5 MB were available" — while the very
/// same query on its own finished in 6 seconds. Lower this before lowering the
/// scope of a metric: fewer workers costs wall-clock, a smaller scope costs
/// results.
pub fn query_pool() -> rayon::ThreadPool {
    let n = std::env::var("QLEVER_PARALLELISM")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .filter(|n| *n > 0)
        .unwrap_or(4);
    rayon::ThreadPoolBuilder::new().num_threads(n).build().unwrap()
}

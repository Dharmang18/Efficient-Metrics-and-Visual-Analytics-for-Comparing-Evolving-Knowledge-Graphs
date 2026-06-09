//! Common reusable SPARQL queries (mirrors Knowgly's common.rs).

use crate::qlever_client::endpoint;
use std::collections::HashMap;

/// Fetch the most-populated type IRIs (top `limit` by number of entities).
///
/// Knowgly fetches *all* types; on a laptop, running one query per type over
/// 1.3B triples is slow, so we restrict to the busiest types. Same metric,
/// tractable scope. Raise `limit` (or remove it) when running on a server.
pub fn fetch_top_type_iris(limit: usize) -> Vec<String> {
    let q = format!(
        "SELECT ?type (COUNT(DISTINCT ?s) AS ?n) WHERE {{ ?s a ?type }} \
         GROUP BY ?type ORDER BY DESC(?n) LIMIT {limit}"
    );
    endpoint()
        .query(&q)
        .unwrap_or_default()
        .into_iter()
        .filter_map(|r| r.get("type").cloned())
        .collect()
}

/// |E_t| for every type t: number of distinct entities of that type.
/// (Computed in a single GROUP BY query, then looked up per type.)
pub fn entity_count_per_type() -> HashMap<String, u64> {
    let q = "SELECT ?type (COUNT(DISTINCT ?s) AS ?ef_t) WHERE { ?s a ?type } GROUP BY ?type";
    let mut counts = HashMap::new();
    for r in endpoint().query(q).unwrap_or_default() {
        if let (Some(t), Some(n)) = (r.get("type"), r.get("ef_t")) {
            if let Ok(v) = n.parse::<u64>() {
                counts.insert(t.clone(), v);
            }
        }
    }
    counts
}

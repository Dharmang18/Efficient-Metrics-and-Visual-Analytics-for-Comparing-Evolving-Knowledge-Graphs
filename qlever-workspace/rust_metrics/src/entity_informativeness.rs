//! Metric 5 — Entity informativeness (the InfoRank idea).
//!
//!     IR(v) = dtp(v) / Σ_u dtp(u)
//!
//! dtp(v) = how many DATATYPE (literal) properties entity v has. "Important
//! things have a lot of information recorded about them." One aggregation
//! query, no iteration — and across versions it separates entities that are
//! being actively enriched from ones that were abandoned.
//!
//! Literal objects are what counts: a link to another entity says who v is
//! related to, a literal says something ABOUT v.

use crate::common::short;
use crate::out;
use crate::qlever_client::SparqlEndpoint;
use serde_json::json;

pub struct Entry {
    pub entity: String,
    pub literal_properties: u64,
    pub score: f64,
}

/// `class`: restrict to entities of one class, or None for the whole graph.
pub fn compute(ep: &SparqlEndpoint, class: Option<&str>, limit: usize) -> (Vec<Entry>, f64) {
    let scope = match class {
        Some(c) => format!("?s a <{c}> . ?s ?p ?o"),
        None => "?s ?p ?o".to_string(),
    };

    // Σ_u dtp(u) — the normaliser, over the same scope.
    let total = ep.scalar(
        &format!("SELECT (COUNT(*) AS ?n) WHERE {{ {scope} FILTER(isLiteral(?o)) }}"), "n");

    let q = format!(
        "SELECT ?s (COUNT(*) AS ?dtp) WHERE {{ {scope} FILTER(isLiteral(?o)) }} \
         GROUP BY ?s ORDER BY DESC(?dtp) LIMIT {limit}"
    );
    let entries = ep.rows(&q)
        .into_iter()
        .filter_map(|r| {
            let entity = r.get("s")?.clone();
            let literal_properties: u64 = r.get("dtp")?.parse().ok()?;
            Some(Entry {
                entity,
                literal_properties,
                score: if total > 0.0 { literal_properties as f64 / total } else { 0.0 },
            })
        })
        .collect();
    (entries, total)
}

pub fn run(ep: &SparqlEndpoint, class: Option<&str>, limit: usize) {
    println!("Metric 5: Entity informativeness   IR(v) = dtp(v) / Σ dtp(u)");
    match class {
        Some(c) => println!("Scope:    class <{c}>, top {limit} entities\n"),
        None => println!("Scope:    whole graph, top {limit} entities\n"),
    }

    let (entries, total) = compute(ep, class, limit);
    println!("  Σ dtp(u) = {total:.0} literal properties in scope\n");
    println!("  {:>8}  {:>12}   {}", "literals", "IR(v)", "entity");
    for e in entries.iter().take(20) {
        println!("  {:>8}  {:>12.3e}   {}", e.literal_properties, e.score, short(&e.entity));
    }

    let dict: serde_json::Map<String, serde_json::Value> = entries
        .iter()
        .map(|e| (e.entity.clone(),
                  json!({"literal_properties": e.literal_properties, "inforank": e.score})))
        .collect();

    println!("\nResults saved to:");
    out::write_json("entity_informativeness",
                    &json!({"total_literal_properties": total, "entities": dict}));
    out::write_csv("entity_informativeness", "entity,literal_properties,inforank",
                   &entries.iter()
                           .map(|e| format!("{},{},{:.12}",
                                            out::csv_escape(short(&e.entity)),
                                            e.literal_properties, e.score))
                           .collect::<Vec<_>>());
}

//! Metric 1 — Class population & share.
//!
//!     share(t) = |E_t| / |E|
//!
//! |E_t| = entities of class t, |E| = all typed entities. The first question
//! anyone asks of a snapshot: what is actually in this graph? Across versions
//! the share shows which classes grow, shrink or disappear.

use crate::common::short;
use crate::out;
use crate::qlever_client::SparqlEndpoint;
use serde_json::json;

pub struct ClassPopulation {
    pub class: String,
    pub population: u64,
    pub share: f64,
}

pub fn compute(ep: &SparqlEndpoint, limit: usize) -> (Vec<ClassPopulation>, f64) {
    // |E| — all entities that carry any type at all.
    //
    // Written as COUNT(*) over a DISTINCT subquery rather than the obvious
    // COUNT(DISTINCT ?s). The two are equivalent, but QLever evaluates them very
    // differently: COUNT(DISTINCT ?s) materialises the whole subject column,
    // which on YAGO 4 (2.49B triples, 73M typed subjects) exhausted the entire
    // 5G query budget and then failed on a 24-byte allocation. The subquery form
    // streams the DISTINCT off the already-sorted permutation and answered the
    // same 73,260,634 in 3.5s. Note this is NOT the COUNT(*) shortcut used below
    // for the per-type counts: here the DISTINCT is required, because a subject
    // with several types must be counted once, not once per type.
    let total = ep.scalar(
        "SELECT (COUNT(*) AS ?n) WHERE { { SELECT DISTINCT ?s WHERE { ?s a ?type } } }", "n");

    // COUNT(*) rather than COUNT(DISTINCT ?s): in a set-semantics store the
    // (subject, type) pairs are already unique, so the counts are identical
    // and the DISTINCT only pays for a sort (measured ~1.6x slower on YAGO).
    let q = format!(
        "SELECT ?type (COUNT(*) AS ?n) WHERE {{ ?s a ?type }} \
         GROUP BY ?type ORDER BY DESC(?n) LIMIT {limit}"
    );
    let rows = ep.rows(&q)
        .into_iter()
        .filter_map(|r| {
            let class = r.get("type")?.clone();
            let population: u64 = r.get("n")?.parse().ok()?;
            Some(ClassPopulation {
                class,
                population,
                share: if total > 0.0 { population as f64 / total } else { 0.0 },
            })
        })
        .collect();
    (rows, total)
}

pub fn run(ep: &SparqlEndpoint, limit: usize) {
    println!("Metric 1: Class population & share   share(t) = |E_t| / |E|");
    println!("Scope:    top {limit} classes\n");

    let (rows, total) = compute(ep, limit);
    println!("  |E| = {total:.0} typed entities\n");
    println!("  {:>14}  {:>7}   {}", "population", "share", "class");
    for r in rows.iter().take(15) {
        println!("  {:>14}  {:>6.2} %   {}", r.population, r.share * 100.0, short(&r.class));
    }

    let dict: serde_json::Map<String, serde_json::Value> = rows
        .iter()
        .map(|r| (r.class.clone(), json!({"population": r.population, "share": r.share})))
        .collect();

    println!("\nResults saved to:");
    out::write_json("class_population",
                    &json!({"total_entities": total, "classes": dict}));
    out::write_csv("class_population", "class,population,share",
                   &rows.iter()
                        .map(|r| format!("{},{},{:.8}",
                                         out::csv_escape(short(&r.class)), r.population, r.share))
                        .collect::<Vec<_>>());
}

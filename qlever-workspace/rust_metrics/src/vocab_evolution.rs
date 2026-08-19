//! Metric 12 — Vocabulary / schema evolution.
//!
//!     C_added = C2 - C1      C_removed = C1 - C2      (same for predicates)
//!
//! Which classes and predicates appear, disappear or survive between two
//! versions, and how quickly a newly introduced term is actually USED. A term
//! can enter the schema and stay nearly empty for a version or two, so the
//! adoption count — how many triples the new predicate actually carries — says
//! more than its mere presence.

use crate::common::{class_iris, predicate_iris, short};
use crate::out;
use crate::qlever_client::SparqlEndpoint;
use serde_json::json;
use std::collections::HashSet;

pub struct SetDiff {
    pub added: Vec<String>,
    pub removed: Vec<String>,
    pub kept: usize,
}

fn set_diff(v1: &[String], v2: &[String]) -> SetDiff {
    let s1: HashSet<&String> = v1.iter().collect();
    let s2: HashSet<&String> = v2.iter().collect();
    let mut added: Vec<String> = s2.difference(&s1).map(|s| (*s).clone()).collect();
    let mut removed: Vec<String> = s1.difference(&s2).map(|s| (*s).clone()).collect();
    added.sort();
    removed.sort();
    SetDiff { added, removed, kept: s1.intersection(&s2).count() }
}

/// How many triples a predicate actually carries in the newer version.
fn adoption(ep: &SparqlEndpoint, predicate: &str) -> u64 {
    ep.scalar(&format!("SELECT (COUNT(*) AS ?n) WHERE {{ ?s <{predicate}> ?o }}"), "n") as u64
}

pub fn run(a: &SparqlEndpoint, b: &SparqlEndpoint, cap: usize) {
    println!("Metric 12: Vocabulary / schema evolution");
    println!("  version 1: {}", a.url());
    println!("  version 2: {}", b.url());
    println!("  scope:     up to {cap} distinct terms per side\n");

    let classes = set_diff(&class_iris(a, cap), &class_iris(b, cap));
    let predicates = set_diff(&predicate_iris(a, cap), &predicate_iris(b, cap));

    println!("  classes    kept {:>6}   added {:>6}   removed {:>6}",
             classes.kept, classes.added.len(), classes.removed.len());
    println!("  predicates kept {:>6}   added {:>6}   removed {:>6}\n",
             predicates.kept, predicates.added.len(), predicates.removed.len());

    // Adoption of the new predicates — presence in the schema is not use.
    let mut adopted: Vec<(String, u64)> = predicates.added.iter()
        .take(25)
        .map(|p| (p.clone(), adoption(b, p)))
        .collect();
    adopted.sort_by(|x, y| y.1.cmp(&x.1));

    if !adopted.is_empty() {
        println!("  new predicates, by how much they are actually used in version 2:");
        for (p, n) in adopted.iter().take(12) {
            println!("   {:>14}   {}", n, short(p));
        }
    }
    if !predicates.removed.is_empty() {
        println!("\n  predicates gone in version 2:");
        for p in predicates.removed.iter().take(12) {
            println!("                    {}", short(p));
        }
    }

    println!("\nResults saved to:");
    out::write_json("vocab_evolution", &json!({
        "version_1": a.url(),
        "version_2": b.url(),
        "classes": {
            "kept": classes.kept,
            "added": classes.added,
            "removed": classes.removed,
        },
        "predicates": {
            "kept": predicates.kept,
            "added": predicates.added,
            "removed": predicates.removed,
            "adoption": adopted.iter()
                .map(|(p, n)| (p.clone(), json!(n)))
                .collect::<serde_json::Map<String, serde_json::Value>>(),
        }
    }));

    let mut rows = Vec::new();
    for c in &classes.added { rows.push(format!("class,added,{},", out::csv_escape(short(c)))); }
    for c in &classes.removed { rows.push(format!("class,removed,{},", out::csv_escape(short(c)))); }
    for (p, n) in &adopted { rows.push(format!("predicate,added,{},{}", out::csv_escape(short(p)), n)); }
    for p in &predicates.removed { rows.push(format!("predicate,removed,{},", out::csv_escape(short(p)))); }
    out::write_csv("vocab_evolution", "kind,change,term,triples_in_v2", &rows);
}

//! Metric 6 — Object diversity.
//!
//!     OD(p, t) = |{ o : (e, p, o) ∈ T and e ∈ E_t }|
//!
//! How many DIFFERENT objects a predicate points to inside a class. It
//! separates predicates that fan out over many values from those that reuse a
//! handful, and complements the entropy metrics with a simple exact count:
//! entropy weighs values by how often they occur, this does not weigh at all.
//! The ratio distinct/total is reported too — it says whether the values are
//! mostly unique (near 1) or heavily repeated (near 0).

use crate::common::short;
use crate::out;
use crate::qlever_client::SparqlEndpoint;
use rayon::prelude::*;
use serde_json::json;
use std::collections::HashMap;

pub struct Entry {
    pub class: String,
    pub predicate: String,
    pub distinct_objects: u64,
    pub total_objects: u64,
}

impl Entry {
    /// 1.0 = every value unique, near 0 = the same few values repeated.
    pub fn uniqueness(&self) -> f64 {
        if self.total_objects > 0 {
            self.distinct_objects as f64 / self.total_objects as f64
        } else {
            0.0
        }
    }
}

pub fn compute(ep: &SparqlEndpoint, num_types: usize) -> Vec<Entry> {
    let types = crate::common::selected_type_iris(ep, num_types);
    let pool = crate::common::query_pool();

    // One GROUP BY per class gives every predicate of that class at once.
    pool.install(|| {
        types
            .par_iter()
            .flat_map(|t| {
                let q = format!(
                    "SELECT ?p (COUNT(DISTINCT ?o) AS ?d) (COUNT(*) AS ?n) \
                     WHERE {{ ?s a <{t}> . ?s ?p ?o }} GROUP BY ?p"
                );
                ep.rows(&q)
                    .into_iter()
                    .filter_map(|r| {
                        Some(Entry {
                            class: t.clone(),
                            predicate: r.get("p")?.clone(),
                            distinct_objects: r.get("d")?.parse().ok()?,
                            total_objects: r.get("n")?.parse().ok()?,
                        })
                    })
                    .collect::<Vec<_>>()
            })
            .collect()
    })
}

pub fn run(ep: &SparqlEndpoint, num_types: usize) {
    println!("Metric 6: Object diversity   OD(p,t) = distinct objects of p within class t");
    println!("Scope:    top {num_types} classes\n");

    let mut entries = compute(ep, num_types);
    entries.sort_by(|a, b| b.distinct_objects.cmp(&a.distinct_objects));

    println!("  {:>14}  {:>10}  {:<28} {}", "distinct", "unique", "predicate", "class");
    for e in entries.iter().take(15) {
        println!("  {:>14}  {:>9.2}%  {:<28} {}",
                 e.distinct_objects, e.uniqueness() * 100.0,
                 short(&e.predicate), short(&e.class));
    }

    let mut nested: HashMap<String, HashMap<String, u64>> = HashMap::new();
    for e in &entries {
        nested.entry(e.class.clone()).or_default()
              .insert(e.predicate.clone(), e.distinct_objects);
    }

    println!("\nResults saved to:");
    out::write_json("object_diversity", &json!(nested));
    out::write_csv("object_diversity", "class,predicate,distinct_objects,total_objects,uniqueness",
                   &entries.iter()
                           .map(|e| format!("{},{},{},{},{:.6}",
                                            out::csv_escape(short(&e.class)),
                                            out::csv_escape(short(&e.predicate)),
                                            e.distinct_objects, e.total_objects, e.uniqueness()))
                           .collect::<Vec<_>>());
}

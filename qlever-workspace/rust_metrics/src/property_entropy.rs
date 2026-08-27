//! Metric 2 — Property entropy per type (EntF).
//!
//!     EntF(p, t) = - Σ_o P(o) · log2 P(o)
//!
//! P(o) = share of value o among all values predicate p takes inside class t.
//! birthDate, whose values are spread over many objects, scores high and
//! carries real information; gender, dominated by one value, scores low.
//!
//! Cost note: the naive way is to pull every object value out of the endpoint
//! and count in Rust — millions of rows per (type, predicate). Entropy depends
//! only on the multiset of counts, so `common::value_histogram` has QLever
//! fold them into a count-of-counts of a few hundred rows instead. Exact, not
//! sampled, and small enough that the per-pair queries can run in parallel.

use crate::common::{property_entropy, short, top_predicates_for_type};
use crate::out;
use crate::qlever_client::SparqlEndpoint;
use rayon::prelude::*;
use serde_json::json;
use std::collections::HashMap;

pub struct Entry {
    pub class: String,
    pub predicate: String,
    pub entropy: f64,
    pub values: f64,
    pub distinct: f64,
}

/// EntF for the top `num_preds` predicates of the top `num_types` classes.
pub fn compute(ep: &SparqlEndpoint, num_types: usize, num_preds: usize) -> Vec<Entry> {
    let types = crate::common::selected_type_iris(ep, num_types);

    // (type, predicate) work list — one histogram query each.
    let pairs: Vec<(String, String)> = types
        .iter()
        .flat_map(|t| {
            top_predicates_for_type(ep, t, num_preds)
                .into_iter()
                .map(move |(p, _)| (t.clone(), p))
        })
        .collect();
    println!("  {} classes x top {} predicates = {} histogram queries",
             types.len(), num_preds, pairs.len());

    // Small pool: the point is to keep a 16 GB laptop's QLever responsive.
    let pool = crate::common::query_pool();
    pool.install(|| {
        pairs
            .par_iter()
            .map(|(t, p)| {
                let (entropy, values, distinct) = property_entropy(ep, t, p);
                Entry { class: t.clone(), predicate: p.clone(), entropy, values, distinct }
            })
            .collect()
    })
}

/// Nested dictionary Type -> Predicate -> entropy, the shape the dashboard reads.
pub fn as_nested(entries: &[Entry]) -> HashMap<String, HashMap<String, f64>> {
    let mut nested: HashMap<String, HashMap<String, f64>> = HashMap::new();
    for e in entries {
        nested.entry(e.class.clone()).or_default().insert(e.predicate.clone(), e.entropy);
    }
    nested
}

pub fn run(ep: &SparqlEndpoint, num_types: usize, num_preds: usize) {
    println!("Metric 2: Property entropy per type   EntF(p,t) = -Σ P(o) log2 P(o)");
    println!("Scope:    top {num_types} classes, top {num_preds} predicates each\n");

    let mut entries = compute(ep, num_types, num_preds);
    entries.sort_by(|a, b| b.entropy.partial_cmp(&a.entropy).unwrap());

    println!("\n  most informative (type, predicate) pairs:");
    println!("  {:>9}  {:>12}  {:<28} {}", "bits", "distinct", "predicate", "class");
    for e in entries.iter().take(15) {
        println!("  {:>9.3}  {:>12.0}  {:<28} {}",
                 e.entropy, e.distinct, short(&e.predicate), short(&e.class));
    }

    println!("\nResults saved to:");
    out::write_json("property_entropy", &json!(as_nested(&entries)));
    out::write_csv("property_entropy", "class,predicate,entropy_bits,values,distinct_values",
                   &entries.iter()
                           .map(|e| format!("{},{},{:.6},{:.0},{:.0}",
                                            out::csv_escape(short(&e.class)),
                                            out::csv_escape(short(&e.predicate)),
                                            e.entropy, e.values, e.distinct))
                           .collect::<Vec<_>>());
}

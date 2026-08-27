//! Metric 4 — Class entropy.
//!
//!     H(t) = - Σ_o P(o) · log2 P(o)     over ALL object values of class t
//!
//! One entropy number for a whole class rather than per predicate: how diverse
//! and information-rich the class is as a unit. A class whose entities all look
//! alike scores low; a class of varied, detailed entities scores high. The
//! predicate-side entropy is reported next to it, because a class can be varied
//! in its values while being described by a very narrow set of predicates.

use crate::common::{entropy_from_histogram, short, value_histogram};
use crate::out;
use crate::qlever_client::SparqlEndpoint;
use rayon::prelude::*;
use serde_json::json;

pub struct Entry {
    pub class: String,
    pub object_entropy: f64,
    pub predicate_entropy: f64,
    pub triples: f64,
    pub distinct_objects: f64,
    pub distinct_predicates: f64,
}

pub fn compute(ep: &SparqlEndpoint, num_types: usize) -> Vec<Entry> {
    let types = crate::common::selected_type_iris(ep, num_types);
    let pool = crate::common::query_pool();

    pool.install(|| {
        types
            .par_iter()
            .map(|t| {
                // same histogram trick, once over object values and once over
                // the predicates used by the class
                let (obj_h, n, obj_d) =
                    entropy_from_histogram(&value_histogram(ep, &format!("?s a <{t}> . ?s ?p ?v")));
                let (pred_h, _, pred_d) =
                    entropy_from_histogram(&value_histogram(ep, &format!("?s a <{t}> . ?s ?v ?o")));
                Entry {
                    class: t.clone(),
                    object_entropy: obj_h,
                    predicate_entropy: pred_h,
                    triples: n,
                    distinct_objects: obj_d,
                    distinct_predicates: pred_d,
                }
            })
            .collect()
    })
}

pub fn run(ep: &SparqlEndpoint, num_types: usize) {
    println!("Metric 4: Class entropy   H(t) = -Σ P(o) log2 P(o) over all values of class t");
    println!("Scope:    top {num_types} classes\n");

    let mut entries = compute(ep, num_types);
    entries.sort_by(|a, b| b.object_entropy.partial_cmp(&a.object_entropy).unwrap());

    println!("  {:>10}  {:>10}  {:>14}  {}", "H(objects)", "H(preds)", "triples", "class");
    for e in &entries {
        println!("  {:>10.3}  {:>10.3}  {:>14.0}  {}",
                 e.object_entropy, e.predicate_entropy, e.triples, short(&e.class));
    }

    let dict: serde_json::Map<String, serde_json::Value> = entries
        .iter()
        .map(|e| (e.class.clone(), json!({
            "object_entropy": e.object_entropy,
            "predicate_entropy": e.predicate_entropy,
            "triples": e.triples,
            "distinct_objects": e.distinct_objects,
            "distinct_predicates": e.distinct_predicates,
        })))
        .collect();

    println!("\nResults saved to:");
    out::write_json("class_entropy", &json!(dict));
    out::write_csv("class_entropy",
                   "class,object_entropy_bits,predicate_entropy_bits,triples,distinct_objects,distinct_predicates",
                   &entries.iter()
                           .map(|e| format!("{},{:.6},{:.6},{:.0},{:.0},{:.0}",
                                            out::csv_escape(short(&e.class)),
                                            e.object_entropy, e.predicate_entropy,
                                            e.triples, e.distinct_objects, e.distinct_predicates))
                           .collect::<Vec<_>>());
}

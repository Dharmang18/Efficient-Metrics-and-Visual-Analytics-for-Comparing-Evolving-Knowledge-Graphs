//! Metric 3 — Entropy-weighted type importance (EntETImp).
//!
//!     EntETImp(p, t) = EntF(p, t)^w · ETImp(p, t)^(1-w)      (w = 0.75)
//!
//! A weighted geometric mean of two signals that say different things:
//!   * ETImp (the provided Knowgly baseline) — is p CHARACTERISTIC of class t?
//!   * EntF  (metric 2)                      — are p's values DIVERSE?
//! Either one alone is misleading. A predicate every Person has (rdf:type)
//! scores 0 on ETImp; a predicate with one repeated value (gender) scores ~0 on
//! EntF. Only a predicate that is both typical of the class and informative in
//! its values ranks high here. A geometric mean is used precisely because it
//! collapses to 0 when either factor is 0.

use crate::common::short;
use crate::entity_type_importance::get_entity_type_importances;
use crate::out;
use crate::property_entropy;
use crate::qlever_client::SparqlEndpoint;
use serde_json::json;
use std::collections::HashMap;

/// Weight of the entropy factor in the geometric mean.
pub const W: f64 = 0.75;

pub struct Entry {
    pub class: String,
    pub predicate: String,
    pub entf: f64,
    pub etimp: f64,
    pub score: f64,
}

pub fn compute(ep: &SparqlEndpoint, num_types: usize, num_preds: usize) -> Vec<Entry> {
    // Both factors come from the same classes, so the two dictionaries join.
    println!("  computing EntF (metric 2) ...");
    let entf = property_entropy::as_nested(&property_entropy::compute(ep, num_types, num_preds));

    println!("  computing ETImp (Knowgly baseline) ...");
    let etimp: HashMap<String, HashMap<String, f64>> = get_entity_type_importances(num_types);

    let mut entries = Vec::new();
    for (class, preds) in &entf {
        // ETImp covers every predicate of the class; EntF only the top ones we
        // asked for, so the intersection is what can be scored.
        let Some(etimp_of_class) = etimp.get(class) else { continue };
        for (predicate, &e) in preds {
            let Some(&i) = etimp_of_class.get(predicate) else { continue };
            // 0^0.25 is 0, which is what we want: either factor missing kills it
            let score = e.max(0.0).powf(W) * i.max(0.0).powf(1.0 - W);
            entries.push(Entry {
                class: class.clone(),
                predicate: predicate.clone(),
                entf: e,
                etimp: i,
                score,
            });
        }
    }
    entries
}

pub fn run(ep: &SparqlEndpoint, num_types: usize, num_preds: usize) {
    println!("Metric 3: Entropy-weighted type importance");
    println!("          EntETImp(p,t) = EntF(p,t)^{W} · ETImp(p,t)^{:.2}", 1.0 - W);
    println!("Scope:    top {num_types} classes, top {num_preds} predicates each\n");

    let mut entries = compute(ep, num_types, num_preds);
    entries.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap());

    println!("\n  {:>12}  {:>9}  {:>13}  {:<26} {}",
             "EntETImp", "EntF", "ETImp", "predicate", "class");
    for e in entries.iter().take(15) {
        println!("  {:>12.2}  {:>9.3}  {:>13.0}  {:<26} {}",
                 e.score, e.entf, e.etimp, short(&e.predicate), short(&e.class));
    }

    let mut nested: HashMap<String, HashMap<String, f64>> = HashMap::new();
    for e in &entries {
        nested.entry(e.class.clone()).or_default().insert(e.predicate.clone(), e.score);
    }

    println!("\nResults saved to:");
    out::write_json("ent_etimp", &json!(nested));
    out::write_csv("ent_etimp", "class,predicate,ent_etimp,entf_bits,etimp",
                   &entries.iter()
                           .map(|e| format!("{},{},{:.6},{:.6},{:.4}",
                                            out::csv_escape(short(&e.class)),
                                            out::csv_escape(short(&e.predicate)),
                                            e.score, e.entf, e.etimp))
                           .collect::<Vec<_>>());
}

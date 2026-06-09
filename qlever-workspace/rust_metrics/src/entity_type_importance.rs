//! Entity Type Importance metric (mirrors Knowgly's
//! entity_type_importance_metrics_generator.rs), simplified.
//!
//! For a type t and predicate p:
//!     ETImp(p, t) = EF_p(p, t) * log2( |E_t| / EF_p(p, t) )
//! where
//!     EF_p(p, t) = # distinct entities of type t that use predicate p
//!     |E_t|      = # distinct entities of type t
//!
//! It's a TF-IDF for predicates: a predicate used by *every* entity of a type
//! scores 0 (uninformative); a characteristic predicate scores high.

use crate::common::{entity_count_per_type, fetch_top_type_iris};
use crate::qlever_client::endpoint;
use rayon::prelude::*;
use std::collections::HashMap;

/// EF_p(p, t) for one type: distinct entities of type t using each predicate p.
fn entity_frequency_p_t(type_iri: &str) -> HashMap<String, u64> {
    let q = format!(
        "SELECT ?p (COUNT(DISTINCT ?s) AS ?ef_p_t) WHERE {{ \
            ?s a <{type_iri}> . ?s ?p ?o \
         }} GROUP BY ?p"
    );
    let mut counts = HashMap::new();
    for r in endpoint().query(&q).unwrap_or_default() {
        if let (Some(p), Some(ef)) = (r.get("p"), r.get("ef_p_t")) {
            if let Ok(v) = ef.parse::<u64>() {
                counts.insert(p.clone(), v);
            }
        }
    }
    counts
}

/// Compute ETImp(p, t) for the top `num_types` most-populated types.
/// Returns: Type IRI -> (Predicate IRI -> importance score).
pub fn get_entity_type_importances(num_types: usize) -> HashMap<String, HashMap<String, f64>> {
    let type_iris = fetch_top_type_iris(num_types);
    let e_t = entity_count_per_type();

    // Run the per-type queries in parallel (like Knowgly), but with a small
    // pool so we don't overwhelm a 16 GB laptop running QLever.
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(4)
        .build()
        .unwrap();

    // Type IRI -> Predicate IRI -> EF_p(p, t)
    let ef_p_t: HashMap<String, HashMap<String, u64>> = pool.install(|| {
        type_iris
            .par_iter()
            .map(|t| (t.clone(), entity_frequency_p_t(t)))
            .collect()
    });

    // Apply the formula, storing results in the nested dictionary.
    ef_p_t
        .into_iter()
        .map(|(type_iri, preds)| {
            let total = *e_t.get(&type_iri).unwrap_or(&0) as f64;
            let importances = preds
                .into_iter()
                .map(|(p, ef)| {
                    let ef = ef as f64;
                    let score = if ef > 0.0 && total > 0.0 {
                        ef * (total / ef).log2()
                    } else {
                        0.0
                    };
                    (p, score)
                })
                .collect();
            (type_iri, importances)
        })
        .collect()
}

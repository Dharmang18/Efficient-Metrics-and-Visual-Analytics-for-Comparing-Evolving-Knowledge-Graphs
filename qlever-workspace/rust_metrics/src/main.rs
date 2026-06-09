//! Thesis KG metrics over YAGO — SPARQL + Rust dictionaries (mirrors Knowgly).
//!
//! Usage:
//!     cargo run --release [num_types]
//! Endpoint comes from QLEVER_ENDPOINT (default http://localhost:9004).

mod common;
mod entity_type_importance;
mod qlever_client;

use entity_type_importance::get_entity_type_importances;
use std::fs;
use std::io::Write;

/// Trim a long IRI to its last path/fragment segment, for readable output.
fn short(iri: &str) -> &str {
    iri.rsplit(['#', '/']).next().unwrap_or(iri)
}

fn main() {
    let endpoint =
        std::env::var("QLEVER_ENDPOINT").unwrap_or_else(|_| "http://localhost:9004".to_string());
    let num_types: usize = std::env::args()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(10);

    qlever_client::init(&endpoint);
    println!("Endpoint: {endpoint}");
    println!("Metric:   Entity Type Importance  (ETImp(p,t) = EF_p(p,t) * log2(|E_t| / EF_p(p,t)))");
    println!("Scope:    top {num_types} most-populated types\n");

    let importances = get_entity_type_importances(num_types);

    // --- 1) Print a short preview to the console ---
    let mut types: Vec<&String> = importances.keys().collect();
    types.sort();
    for t in &types {
        let mut preds: Vec<(&String, &f64)> = importances[*t].iter().collect();
        preds.sort_by(|a, b| b.1.partial_cmp(a.1).unwrap());
        println!("== {} ==", short(t));
        for (p, score) in preds.iter().take(6) {
            println!("   {:>16.0}   {}", score, short(p));
        }
        println!();
    }

    // --- 2) Save the FULL results to files you can open ---
    fs::create_dir_all("results").expect("could not create results/ dir");

    // (a) JSON: the canonical nested dictionary  Type -> Predicate -> score
    let json = serde_json::to_string_pretty(&importances).unwrap();
    fs::write("results/entity_type_importance.json", json).unwrap();

    // (b) CSV: one row per (type, predicate, score), sorted — opens in Excel/Numbers
    let mut csv = fs::File::create("results/entity_type_importance.csv").unwrap();
    writeln!(csv, "type,predicate,etimp_score").unwrap();
    for t in &types {
        let mut preds: Vec<(&String, &f64)> = importances[*t].iter().collect();
        preds.sort_by(|a, b| b.1.partial_cmp(a.1).unwrap());
        for (p, score) in preds {
            writeln!(csv, "{},{},{:.2}", short(t), short(p), score).unwrap();
        }
    }

    println!("Results saved to:");
    println!("  results/entity_type_importance.json   (full nested dictionary)");
    println!("  results/entity_type_importance.csv    (one row per type+predicate, sorted)");
}

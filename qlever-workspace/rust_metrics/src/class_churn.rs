//! Metric 9 — Class-level change rate (churn).
//!
//!     churn(t) = ( |A_t| + |D_t| ) / |T_t(v1)|
//!
//! Metric 10 says HOW MUCH changed between two versions; this says WHERE.
//! For every class it takes the added and deleted triples of that class and
//! divides by the class's size in the older version. A big global diff can mean
//! everything drifted slightly, or a few classes were rewritten while the rest
//! stood still — only the per-class rate tells those apart. It reuses the
//! integer-encoded diff engine, one scoped run per class.

use crate::common::{short, top_type_iris};
use crate::out;
use crate::qlever_client::SparqlEndpoint;
use crate::triple_diff::{common_window, diff_encoded, fetch_triples_of, Diff};
use serde_json::json;

pub struct Entry {
    pub class: String,
    pub diff: Diff,
    pub size_v1: usize,
    pub size_v2: usize,
}

impl Entry {
    pub fn churn(&self) -> f64 {
        self.diff.churn(self.size_v1)
    }
}

pub fn compute(a: &SparqlEndpoint, b: &SparqlEndpoint, num_types: usize, cap: usize)
    -> Vec<Entry>
{
    // Classes of the OLDER version: a class that vanished still has churn.
    let classes = top_type_iris(a, num_types);
    let mut entries = Vec::new();

    // Sequential on purpose: each class already issues two ORDER BY queries,
    // and firing them all at once is how you make a QLever server thrash.
    for (i, class) in classes.iter().enumerate() {
        let window = common_window(a, b, Some(class), cap);
        let t1 = fetch_triples_of(a, &window);
        let t2 = fetch_triples_of(b, &window);
        let (diff, _) = diff_encoded(&t1, &t2);
        println!("  [{:>2}/{}] {:<34} churn {:>7.4}   +{} -{}",
                 i + 1, classes.len(), short(class),
                 diff.churn(t1.len()), diff.added, diff.deleted);
        entries.push(Entry { class: class.clone(), diff, size_v1: t1.len(), size_v2: t2.len() });
    }
    entries
}

pub fn run(a: &SparqlEndpoint, b: &SparqlEndpoint, num_types: usize, cap: usize) {
    println!("Metric 9: Class-level change rate (churn)");
    println!("  version 1: {}", a.url());
    println!("  version 2: {}", b.url());
    println!("  scope:     top {num_types} classes, subject window of {cap} per class\n");

    let mut entries = compute(a, b, num_types, cap);
    entries.sort_by(|x, y| y.churn().partial_cmp(&x.churn()).unwrap());

    println!("\n  {:>9}  {:>9}  {:>9}  {:>11}  {}",
             "churn", "added", "deleted", "|T_t(v1)|", "class");
    for e in &entries {
        println!("  {:>9.4}  {:>9}  {:>9}  {:>11}  {}",
                 e.churn(), e.diff.added, e.diff.deleted, e.size_v1, short(&e.class));
    }

    let dict: serde_json::Map<String, serde_json::Value> = entries
        .iter()
        .map(|e| (e.class.clone(), json!({
            "churn": e.churn(),
            "added": e.diff.added,
            "deleted": e.diff.deleted,
            "unchanged": e.diff.unchanged,
            "triples_v1": e.size_v1,
            "triples_v2": e.size_v2,
        })))
        .collect();

    println!("\nResults saved to:");
    out::write_json("class_churn", &json!(dict));
    out::write_csv("class_churn", "class,churn,added,deleted,unchanged,triples_v1,triples_v2",
                   &entries.iter()
                           .map(|e| format!("{},{:.6},{},{},{},{},{}",
                                            out::csv_escape(short(&e.class)), e.churn(),
                                            e.diff.added, e.diff.deleted, e.diff.unchanged,
                                            e.size_v1, e.size_v2))
                           .collect::<Vec<_>>());
}

//! Metric 13 — Cross-KG class comparison.
//!
//!     Δm(t) = m_A(t) - m_B(t)   for every metric m, same class t in KGs A and B
//!
//! Takes a class that exists in two DIFFERENT knowledge graphs — Person in YAGO
//! and in DBpedia — and puts its metric values side by side: population, class
//! entropy, predicate count. Classes are matched at the SCHEMA level, by local
//! name, because overlapping the instances of two KGs through sameAs links is
//! impractical at this scale; so this reports how differently the two graphs
//! model and populate the same concept, and deliberately estimates no union or
//! merge gain.

use crate::common::{entropy_from_histogram, short, top_type_iris, value_histogram};
use crate::out;
use crate::qlever_client::SparqlEndpoint;
use serde_json::json;
use std::collections::HashMap;

pub struct Side {
    pub iri: String,
    pub population: f64,
    pub entropy: f64,
    pub predicates: f64,
}

pub struct Comparison {
    pub name: String,
    pub a: Side,
    pub b: Side,
}

impl Comparison {
    /// Relative difference, so classes of very different size stay comparable.
    pub fn delta_share(&self) -> f64 {
        let (x, y) = (self.a.population, self.b.population);
        if x + y > 0.0 { (x - y) / (x + y) } else { 0.0 }
    }
}

fn measure(ep: &SparqlEndpoint, class: &str) -> Side {
    let population = ep.scalar(
        &format!("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ ?s a <{class}> }}"), "n");
    let predicates = ep.scalar(
        &format!("SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE {{ ?s a <{class}> . ?s ?p ?o }}"), "n");
    let (entropy, _, _) =
        entropy_from_histogram(&value_histogram(ep, &format!("?s a <{class}> . ?s ?p ?v")));
    Side { iri: class.to_string(), population, entropy, predicates }
}

/// Match classes by local name: schema.org/Person and dbpedia.org/ontology/Person
/// both reduce to "Person".
pub fn matched_classes(a: &SparqlEndpoint, b: &SparqlEndpoint, scan: usize)
    -> Vec<(String, String, String)>
{
    let by_name = |ep: &SparqlEndpoint| -> HashMap<String, String> {
        top_type_iris(ep, scan)
            .into_iter()
            .map(|iri| (short(&iri).to_lowercase(), iri))
            .collect()
    };
    let (na, nb) = (by_name(a), by_name(b));

    let mut matches: Vec<(String, String, String)> = na
        .iter()
        .filter_map(|(name, iri_a)| {
            nb.get(name).map(|iri_b| (name.clone(), iri_a.clone(), iri_b.clone()))
        })
        .collect();
    matches.sort();
    matches
}

pub fn run(a: &SparqlEndpoint, b: &SparqlEndpoint, class_name: Option<&str>, scan: usize) {
    println!("Metric 13: Cross-KG class comparison");
    println!("  KG A: {}", a.url());
    println!("  KG B: {}", b.url());

    let mut pairs = matched_classes(a, b, scan);
    if let Some(name) = class_name {
        let wanted = name.to_lowercase();
        pairs.retain(|(n, _, _)| *n == wanted);
        if pairs.is_empty() {
            println!("\n  no class named '{name}' present in the top {scan} classes of both KGs");
            return;
        }
    }
    println!("  matched {} class name(s) present in both graphs\n", pairs.len());

    let comparisons: Vec<Comparison> = pairs
        .iter()
        .map(|(name, iri_a, iri_b)| {
            println!("  measuring {name} ...");
            Comparison { name: name.clone(), a: measure(a, iri_a), b: measure(b, iri_b) }
        })
        .collect();

    println!("\n  {:<22} {:>13} {:>13} {:>9} {:>8} {:>8}",
             "class", "pop A", "pop B", "Δ share", "H_A", "H_B");
    for c in &comparisons {
        println!("  {:<22} {:>13.0} {:>13.0} {:>+9.3} {:>8.3} {:>8.3}",
                 c.name, c.a.population, c.b.population, c.delta_share(),
                 c.a.entropy, c.b.entropy);
    }

    let dict: serde_json::Map<String, serde_json::Value> = comparisons
        .iter()
        .map(|c| (c.name.clone(), json!({
            "a": {"iri": c.a.iri, "population": c.a.population,
                  "class_entropy": c.a.entropy, "predicates": c.a.predicates},
            "b": {"iri": c.b.iri, "population": c.b.population,
                  "class_entropy": c.b.entropy, "predicates": c.b.predicates},
            "delta_population": c.a.population - c.b.population,
            "delta_share": c.delta_share(),
            "delta_class_entropy": c.a.entropy - c.b.entropy,
            "delta_predicates": c.a.predicates - c.b.predicates,
        })))
        .collect();

    println!("\nResults saved to:");
    out::write_json("cross_kg", &json!({"kg_a": a.url(), "kg_b": b.url(), "classes": dict}));
    out::write_csv("cross_kg",
                   "class,population_a,population_b,delta_share,entropy_a,entropy_b,predicates_a,predicates_b",
                   &comparisons.iter()
                               .map(|c| format!("{},{:.0},{:.0},{:.6},{:.6},{:.6},{:.0},{:.0}",
                                                out::csv_escape(&c.name),
                                                c.a.population, c.b.population, c.delta_share(),
                                                c.a.entropy, c.b.entropy,
                                                c.a.predicates, c.b.predicates))
                               .collect::<Vec<_>>());
}

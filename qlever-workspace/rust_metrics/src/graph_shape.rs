//! Metric 8 — Graph size & shape.
//!
//!     density = |T| / |E|        avg. out-degree = |T| / |S|
//!
//! The per-snapshot foundation table: triples, entities, classes, predicates,
//! density and average in-/out-degree. Computed for every version and every KG,
//! its deltas form the growth table that makes all other comparisons
//! interpretable.

use crate::out;
use crate::qlever_client::SparqlEndpoint;
use serde_json::json;

pub struct Shape {
    pub triples: f64,
    pub subjects: f64,
    pub objects: f64,
    pub predicates: f64,
    pub classes: f64,
    pub entities: f64,
}

impl Shape {
    pub fn density(&self) -> f64 {
        if self.entities > 0.0 { self.triples / self.entities } else { 0.0 }
    }
    pub fn avg_out_degree(&self) -> f64 {
        if self.subjects > 0.0 { self.triples / self.subjects } else { 0.0 }
    }
    /// Averaged over the objects that are graph nodes rather than literals.
    pub fn avg_in_degree(&self) -> f64 {
        if self.objects > 0.0 { self.triples / self.objects } else { 0.0 }
    }
}

pub fn compute(ep: &SparqlEndpoint) -> Shape {
    // Six independent aggregations; each is one counting query for QLever.
    Shape {
        triples: ep.scalar("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }", "n"),
        subjects: ep.scalar("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s ?p ?o }", "n"),
        objects: ep.scalar("SELECT (COUNT(DISTINCT ?o) AS ?n) WHERE { ?s ?p ?o }", "n"),
        predicates: ep.scalar("SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE { ?s ?p ?o }", "n"),
        classes: ep.scalar("SELECT (COUNT(DISTINCT ?type) AS ?n) WHERE { ?s a ?type }", "n"),
        entities: ep.scalar("SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?type }", "n"),
    }
}

pub fn as_json(s: &Shape) -> serde_json::Value {
    json!({
        "triples": s.triples,
        "distinct_subjects": s.subjects,
        "distinct_objects": s.objects,
        "predicates": s.predicates,
        "classes": s.classes,
        "typed_entities": s.entities,
        "density_triples_per_entity": s.density(),
        "avg_out_degree": s.avg_out_degree(),
        "avg_in_degree": s.avg_in_degree(),
    })
}

pub fn run(ep: &SparqlEndpoint) {
    println!("Metric 8: Graph size & shape   density = |T| / |E|\n");
    let s = compute(ep);

    println!("  {:>22}  {:>18}", "triples", fmt(s.triples));
    println!("  {:>22}  {:>18}", "distinct subjects", fmt(s.subjects));
    println!("  {:>22}  {:>18}", "distinct objects", fmt(s.objects));
    println!("  {:>22}  {:>18}", "predicates", fmt(s.predicates));
    println!("  {:>22}  {:>18}", "classes", fmt(s.classes));
    println!("  {:>22}  {:>18}", "typed entities", fmt(s.entities));
    println!("  {:>22}  {:>18.2}", "density (|T|/|E|)", s.density());
    println!("  {:>22}  {:>18.2}", "avg out-degree", s.avg_out_degree());
    println!("  {:>22}  {:>18.2}", "avg in-degree", s.avg_in_degree());

    println!("\nResults saved to:");
    out::write_json("graph_shape", &as_json(&s));
    out::write_csv("graph_shape", "measure,value", &vec![
        format!("triples,{:.0}", s.triples),
        format!("distinct_subjects,{:.0}", s.subjects),
        format!("distinct_objects,{:.0}", s.objects),
        format!("predicates,{:.0}", s.predicates),
        format!("classes,{:.0}", s.classes),
        format!("typed_entities,{:.0}", s.entities),
        format!("density,{:.6}", s.density()),
        format!("avg_out_degree,{:.6}", s.avg_out_degree()),
        format!("avg_in_degree,{:.6}", s.avg_in_degree()),
    ]);
}

/// Thousands separators, so a billion is readable at a glance.
fn fmt(v: f64) -> String {
    let s = format!("{:.0}", v);
    let mut out = String::new();
    for (i, ch) in s.chars().enumerate() {
        if i > 0 && (s.len() - i) % 3 == 0 {
            out.push(' ');
        }
        out.push(ch);
    }
    out
}

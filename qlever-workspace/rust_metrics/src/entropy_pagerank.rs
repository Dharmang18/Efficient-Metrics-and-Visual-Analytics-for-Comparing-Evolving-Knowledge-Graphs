//! Metric 7 — Entropy-weighted PageRank (this thesis's own variant).
//!
//!     PR(v) = (1 - d) + d · Σ_{u->v} w(p_uv) · PR(u) / outdeg(u)
//!     w(p)  = EntF(p) / max_q EntF(q)
//!
//! Classic PageRank treats every link alike. Here rank flows preferentially
//! through INFORMATIVE predicates: each edge is scaled by the (normalised)
//! property entropy of its predicate, so an edge like birthDate — diverse,
//! informative values — passes on more rank than a near-constant one like
//! gender. Knowgly weights its links with InfoRank instead; using the property
//! entropy of metric 2 as the edge weight is the simpler variation this thesis
//! proposes, and it wires metric 2 straight into the importance ranking.
//!
//! The classic unweighted PageRank is computed over the SAME edge set and kept
//! beside it as the provided baseline — the interesting output is not either
//! ranking alone but how far a node moves between them.

use crate::common::{entropy_from_histogram, short, value_histogram};
use crate::out;
use crate::page_rank::{DAMPING, MAX_ITERATIONS, START_VALUE, TOLERANCE};
use crate::qlever_client::SparqlEndpoint;
use rayon::prelude::*;
use serde_json::json;
use std::collections::HashMap;

/// Edges carry the weight of their predicate; nodes are interned IRIs.
pub struct WeightedGraph {
    pub nodes: Vec<String>,
    pub edges: Vec<(u32, u32, f64)>,
}

/// Power iteration; `weighted = false` reproduces the classic baseline.
pub fn power_iteration(graph: &WeightedGraph, weighted: bool) -> Vec<f64> {
    let n = graph.nodes.len();
    let mut outdeg = vec![0u32; n];
    for &(s, _, _) in &graph.edges {
        outdeg[s as usize] += 1;
    }

    // incoming adjacency: for each v, the (u, weight) pairs with u -> v
    let mut incoming: Vec<Vec<(u32, f64)>> = vec![Vec::new(); n];
    for &(s, o, w) in &graph.edges {
        incoming[o as usize].push((s, if weighted { w } else { 1.0 }));
    }

    let mut prev = vec![START_VALUE; n];
    let mut next = vec![0.0f64; n];

    for iteration in 1..=MAX_ITERATIONS {
        for v in 0..n {
            let sum: f64 = incoming[v]
                .iter()
                .map(|&(u, w)| w * prev[u as usize] / outdeg[u as usize] as f64)
                .sum(); // outdeg > 0 by construction: u appears as an edge source
            next[v] = (1.0 - DAMPING) + DAMPING * sum;
        }
        let delta: f64 = prev.iter().zip(&next).map(|(a, b)| (a - b).abs()).sum();
        std::mem::swap(&mut prev, &mut next);
        if delta / n as f64 <= TOLERANCE {
            println!("  converged after {iteration} iterations");
            return prev;
        }
    }
    println!("  stopped at the {MAX_ITERATIONS}-iteration cap");
    prev
}

/// EntF(p) for each predicate, computed over the WHOLE graph (not just the
/// sampled edges) — the weight is a property of the predicate, not of the sample.
pub fn predicate_weights(ep: &SparqlEndpoint, predicates: &[String]) -> HashMap<String, f64> {
    let pool = rayon::ThreadPoolBuilder::new().num_threads(4).build().unwrap();
    let entropies: Vec<(String, f64)> = pool.install(|| {
        predicates
            .par_iter()
            .map(|p| {
                let (h, _, _) = entropy_from_histogram(&value_histogram(ep, &format!("?s <{p}> ?v")));
                (p.clone(), h)
            })
            .collect()
    });

    let max = entropies.iter().map(|(_, h)| *h).fold(0.0f64, f64::max);
    entropies
        .into_iter()
        .map(|(p, h)| (p, if max > 0.0 { h / max } else { 0.0 }))
        .collect()
}

/// Build the graph from entity-to-entity edges (literal objects are not links).
pub fn build_graph(ep: &SparqlEndpoint, max_edges: usize)
    -> (WeightedGraph, HashMap<String, f64>)
{
    let q = format!(
        "SELECT ?s ?p ?o WHERE {{ ?s ?p ?o . FILTER(isIRI(?o)) }} LIMIT {max_edges}"
    );
    let triples = ep.triples(&q);
    println!("  fetched {} entity-to-entity edges", triples.len());

    let mut predicates: Vec<String> = triples.iter().map(|(_, p, _)| p.clone()).collect();
    predicates.sort();
    predicates.dedup();
    println!("  {} distinct predicates -> {} entropy queries", predicates.len(), predicates.len());

    let weights = predicate_weights(ep, &predicates);

    let mut ids: HashMap<String, u32> = HashMap::new();
    let mut nodes: Vec<String> = Vec::new();
    let mut edges: Vec<(u32, u32, f64)> = Vec::new();
    for (s, p, o) in triples {
        let w = *weights.get(&p).unwrap_or(&0.0);
        let s_id = *ids.entry(s.clone()).or_insert_with(|| {
            nodes.push(s);
            (nodes.len() - 1) as u32
        });
        let o_id = *ids.entry(o.clone()).or_insert_with(|| {
            nodes.push(o);
            (nodes.len() - 1) as u32
        });
        edges.push((s_id, o_id, w));
    }
    println!("  {} nodes, {} edges", nodes.len(), edges.len());
    (WeightedGraph { nodes, edges }, weights)
}

/// Position of every node in a ranking, best = 1.
fn ranks(scores: &[f64]) -> Vec<usize> {
    let mut order: Vec<usize> = (0..scores.len()).collect();
    order.sort_by(|&a, &b| scores[b].partial_cmp(&scores[a]).unwrap());
    let mut rank = vec![0usize; scores.len()];
    for (position, &node) in order.iter().enumerate() {
        rank[node] = position + 1;
    }
    rank
}

pub fn run(ep: &SparqlEndpoint, max_edges: usize) {
    println!("Metric 7: Entropy-weighted PageRank (own variant)");
    println!("          PR(v) = (1-d) + d · Σ w(p) · PR(u)/outdeg(u),  d = {DAMPING}");
    println!("Scope:    up to {max_edges} entity-to-entity edges\n");

    let (graph, weights) = build_graph(ep, max_edges);
    if graph.nodes.is_empty() {
        println!("  no edges in scope — nothing to rank");
        return;
    }

    println!("\n  entropy-weighted run:");
    let weighted = power_iteration(&graph, true);
    println!("  unweighted baseline run:");
    let baseline = power_iteration(&graph, false);

    let rank_w = ranks(&weighted);
    let rank_b = ranks(&baseline);

    let mut order: Vec<usize> = (0..graph.nodes.len()).collect();
    order.sort_by(|&a, &b| weighted[b].partial_cmp(&weighted[a]).unwrap());

    println!("\n  predicate weights w(p) = EntF(p)/max EntF:");
    let mut by_weight: Vec<(&String, &f64)> = weights.iter().collect();
    by_weight.sort_by(|a, b| b.1.partial_cmp(a.1).unwrap());
    for (p, w) in by_weight.iter().take(8) {
        println!("   {:>6.3}   {}", w, short(p));
    }

    println!("\n  Top 20 by entropy-weighted PageRank (Δrank vs the unweighted baseline):");
    println!("  {:>9}  {:>7}  {:>8}   {}", "score", "rank", "Δrank", "node");
    for &v in order.iter().take(20) {
        let shift = rank_b[v] as i64 - rank_w[v] as i64;
        println!("  {:>9.4}  {:>7}  {:>+8}   {}",
                 weighted[v], rank_w[v], shift, short(&graph.nodes[v]));
    }

    let dict: serde_json::Map<String, serde_json::Value> = order
        .iter()
        .map(|&v| (graph.nodes[v].clone(), json!({
            "entropy_weighted": weighted[v],
            "unweighted": baseline[v],
            "rank_weighted": rank_w[v],
            "rank_unweighted": rank_b[v],
            "rank_shift": rank_b[v] as i64 - rank_w[v] as i64,
        })))
        .collect();

    println!("\nResults saved to:");
    out::write_json("entropy_pagerank", &json!({
        "predicate_weights": weights,
        "nodes": dict,
    }));
    out::write_csv("entropy_pagerank",
                   "node,entropy_weighted,unweighted,rank_weighted,rank_unweighted,rank_shift",
                   &order.iter()
                         .map(|&v| format!("{},{:.8},{:.8},{},{},{}",
                                           out::csv_escape(short(&graph.nodes[v])),
                                           weighted[v], baseline[v], rank_w[v], rank_b[v],
                                           rank_b[v] as i64 - rank_w[v] as i64))
                         .collect::<Vec<_>>());
}

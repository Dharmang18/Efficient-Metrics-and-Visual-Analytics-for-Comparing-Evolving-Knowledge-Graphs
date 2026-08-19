//! PageRank via the power iteration method (exercise).
//!
//! Mirrors the idea of Knowgly's `MetricsGeneration/PageRank` (Java,
//! `WeightedPageRankMetricsGenerator.compute()`), simplified to the classic
//! unweighted, directed PageRank — Knowgly's weighted variant is this with an
//! extra InfoRank factor W(r,p) on each incoming contribution.
//!
//! The thesis pattern still holds: **SPARQL fetches the data (the edge list),
//! Rust dictionaries hold the graph, the formula runs in Rust.**
//!
//! Power iteration, as in Knowgly:
//!   PR_next(v) = (1 - d) + d * Σ_{u -> v} PR_prev(u) / outdeg(u)
//! with two score arrays (prev/next) swapped after every pass — scores are
//! read only from `prev` and written only to `next`, never mixed in one pass.
//! Knowgly runs a fixed 40 iterations (d = 0.85, start value 0.1); we keep
//! those defaults but also stop early once the scores stop changing (L1 delta).

use crate::qlever_client;
use std::collections::HashMap;

pub const DAMPING: f64 = 0.85; // Knowgly's dampingFactor
pub const START_VALUE: f64 = 0.1; // Knowgly's startValue
pub const MAX_ITERATIONS: usize = 40; // Knowgly's numberOfIterations
pub const TOLERANCE: f64 = 1e-9; // early stop: mean |Δscore| per node

/// A directed graph as integer-ID edge lists (Knowgly gets the same thing for
/// free from HDT's dictionary encoding; we intern IRI strings -> u32 ourselves).
pub struct Graph {
    /// IRI of each node, indexed by node id.
    pub nodes: Vec<String>,
    /// Edges as (source, target) node ids.
    pub edges: Vec<(u32, u32)>,
}

impl Graph {
    /// Build a graph from (source IRI, target IRI) pairs, interning the IRIs.
    pub fn from_iri_pairs(pairs: impl IntoIterator<Item = (String, String)>) -> Self {
        let mut ids: HashMap<String, u32> = HashMap::new();
        let mut nodes: Vec<String> = Vec::new();
        let mut edges: Vec<(u32, u32)> = Vec::new();

        let intern = |iri: String, ids: &mut HashMap<String, u32>, nodes: &mut Vec<String>| {
            *ids.entry(iri.clone()).or_insert_with(|| {
                nodes.push(iri);
                (nodes.len() - 1) as u32
            })
        };

        for (s, o) in pairs {
            let s_id = intern(s, &mut ids, &mut nodes);
            let o_id = intern(o, &mut ids, &mut nodes);
            edges.push((s_id, o_id));
        }
        Graph { nodes, edges }
    }
}

/// The power iteration itself. Returns one PageRank score per node.
pub fn power_iteration(graph: &Graph) -> Vec<f64> {
    let n = graph.nodes.len();

    // outdeg(u): how many links leave each node (Knowgly's `numberOutgoing`).
    let mut outdeg = vec![0u32; n];
    for &(s, _) in &graph.edges {
        outdeg[s as usize] += 1;
    }

    // Incoming adjacency: for each v, the list of u with u -> v.
    // (Knowgly asks HDT for `search(0, 0, id)` per node; we pre-bucket instead.)
    let mut incoming: Vec<Vec<u32>> = vec![Vec::new(); n];
    for &(s, o) in &graph.edges {
        incoming[o as usize].push(s);
    }

    // Two score arrays + swap = the signature of power iteration
    // (Knowgly's pageRankScoresPrev / pageRankScoresNext).
    let mut prev = vec![START_VALUE; n];
    let mut next = vec![0.0f64; n];

    for iteration in 1..=MAX_ITERATIONS {
        for v in 0..n {
            // Each in-neighbour u donates its previous score split evenly
            // over its outgoing links; damping keeps a (1-d) floor.
            let sum: f64 = incoming[v]
                .iter()
                .map(|&u| prev[u as usize] / outdeg[u as usize] as f64)
                .sum(); // outdeg > 0 by construction: u appears as an edge source
            next[v] = (1.0 - DAMPING) + DAMPING * sum;
        }

        let delta: f64 = prev.iter().zip(&next).map(|(a, b)| (a - b).abs()).sum();
        std::mem::swap(&mut prev, &mut next); // read-array becomes write-array

        if delta / n as f64 <= TOLERANCE {
            println!("  converged after {iteration} iterations (mean Δ ≤ {TOLERANCE})");
            return prev;
        }
    }
    println!("  stopped at the {MAX_ITERATIONS}-iteration cap (Knowgly's default)");
    prev
}

/// Part 1 of the exercise: a tiny graph you can check by hand.
///
///   D ──> A <──> B <── C ──> A
///
/// B should win (everyone points at it directly or via A), D should lose
/// (nothing points at D, so it keeps the bare (1-d) minimum).
pub fn demo() {
    println!("== Part 1: hand-checkable demo graph ==");
    let pairs = [
        ("A", "B"),
        ("B", "A"),
        ("C", "A"),
        ("C", "B"),
        ("D", "A"),
    ]
    .map(|(s, o)| (s.to_string(), o.to_string()));

    let graph = Graph::from_iri_pairs(pairs);
    let scores = power_iteration(&graph);

    let mut ranked: Vec<(&String, f64)> =
        graph.nodes.iter().zip(scores.iter().copied()).collect();
    ranked.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
    for (node, score) in ranked {
        println!("   {node}: {score:.4}");
    }
    println!("   (expected order: A ≈ B ≫ C = D; C and D sit at the (1-d) floor = 0.15)\n");
}

/// Part 2: PageRank over a real YAGO subgraph — the class taxonomy
/// (`rdfs:subClassOf` edges). SPARQL fetches the edge list; Rust does the rest.
/// The top-ranked nodes should be the most "central" superclasses.
pub fn run_on_taxonomy(limit: usize) -> HashMap<String, f64> {
    println!("== Part 2: YAGO class taxonomy (rdfs:subClassOf) ==");
    let query = format!(
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n\
         SELECT ?s ?o WHERE {{ ?s rdfs:subClassOf ?o }} LIMIT {limit}"
    );
    let rows = qlever_client::endpoint()
        .query(&query)
        .expect("edge-list query failed");
    println!("  fetched {} subClassOf edges", rows.len());

    let graph = Graph::from_iri_pairs(
        rows.into_iter()
            .filter_map(|mut r| Some((r.remove("s")?, r.remove("o")?))),
    );
    println!("  {} nodes, {} edges", graph.nodes.len(), graph.edges.len());

    let scores = power_iteration(&graph);
    graph.nodes.into_iter().zip(scores).collect()
}

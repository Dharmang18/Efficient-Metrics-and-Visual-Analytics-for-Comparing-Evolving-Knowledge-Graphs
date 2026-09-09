//! Metric 7 — Entropy-weighted PageRank (this thesis's own variant).
//!
//!     PR(v) = (1 - d) + d · Σ_{u->v} w(p_uv) · PR(u) / outdeg(u)
//!     w(p)  = EntF(p) / max_q EntF(q)
//!
//! Classic PageRank treats every link alike. Here rank flows preferentially
//! through INFORMATIVE predicates: each edge is scaled by the (normalised)
//! property entropy of its predicate, so an edge like birthPlace — diverse,
//! informative values — passes on more rank than a near-constant one like
//! gender. Knowgly weights its links with InfoRank instead; using the property
//! entropy of metric 2 as the edge weight is the simpler variation this thesis
//! proposes, and it wires metric 2 straight into the importance ranking.
//!
//! The classic unweighted PageRank is computed over the SAME edge set and kept
//! beside it as the provided baseline — the interesting output is not either
//! ranking alone but how far a node moves between them.
//!
//! # Why the edge set is sampled by breadth-first expansion
//!
//! The first implementation took the edges from
//! `SELECT ?s ?p ?o WHERE { ?s ?p ?o . FILTER(isIRI(?o)) } LIMIT n`. That is an
//! unordered LIMIT, so QLever answers it from the front of one permutation and
//! returns a single predicate's block. Measured on YAGO 4.5.0.2, n = 200,000:
//!
//!     rdf:type      199,995
//!     shacl:path          5
//!
//! Every predicate that wins that race is a fan-out-1 attribute (`rdf:type`,
//! `owl:sameAs`, `hasWebsite`), so the "graph" came out as 200,004 nodes over
//! 200,000 edges — a star forest with no paths at all. PageRank on it converged
//! in 3 iterations to something that is just in-degree, i.e. a worse restatement
//! of metric 1, and with only two distinct predicates the entropy weighting was
//! a no-op: every rank_shift against the baseline was 0. No iteration count
//! fixes that; the sample does.
//!
//! So the edge set is now the subgraph INDUCED by breadth-first expansion from
//! a seed set — the top entities of metric 5 (InfoRank), which every snapshot
//! has and which is the same selection rule everywhere, so the sample stays
//! comparable across versions. Structural predicates that describe the schema
//! rather than relating two entities are excluded (see `SKIP_EXACT`).

use crate::common::{entropy_from_histogram, short, value_histogram};
use crate::out;
use crate::page_rank::{DAMPING, START_VALUE, TOLERANCE};

use crate::qlever_client::SparqlEndpoint;
use rayon::prelude::*;
use serde_json::json;
use std::collections::{HashMap, HashSet};

/// Subjects per `VALUES` block. Small enough that one batch is a cheap indexed
/// lookup rather than a scan, large enough that the round trips stay few.
const SEED_BATCH: usize = 64;

/// Iteration cap for THIS metric only.
///
/// `page_rank::MAX_ITERATIONS` is 40 because that is Knowgly's
/// `numberOfIterations`, and the provided baseline keeps it for fidelity. Once
/// the edge set became a real multi-hop subgraph, 40 stopped being enough:
/// on YAGO 3 the weighted run converged at 28 but the unweighted one was still
/// at mean Δ = 2.1e-6 when it hit the cap. Rank contracts by d = 0.85 per
/// iteration, so reaching TOLERANCE = 1e-9 from an O(1) start needs
/// ln(1e-9)/ln(0.85) ≈ 127 in the worst case; 100 covers every graph we
/// actually sample, and both runs here must share one budget or the Δrank
/// against the baseline compares two different amounts of convergence.
const MAX_ITERATIONS: usize = 100;

/// Predicates that do not pass rank from one entity to another.
///
/// `rdf:type` and `rdfs:subClassOf` climb into the schema; `owl:sameAs` leaves
/// the graph for Wikidata/DBpedia IRIs; the rest are ontology axioms or RDF list
/// plumbing. Leaving them in is what produced the degenerate star forest above.
const SKIP_EXACT: &[&str] = &[
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#first",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#rest",
    "http://www.w3.org/2000/01/rdf-schema#subClassOf",
    "http://www.w3.org/2000/01/rdf-schema#subPropertyOf",
    "http://www.w3.org/2000/01/rdf-schema#domain",
    "http://www.w3.org/2000/01/rdf-schema#range",
    "http://www.w3.org/2000/01/rdf-schema#isDefinedBy",
    "http://www.w3.org/2002/07/owl#sameAs",
    "http://www.w3.org/2002/07/owl#equivalentClass",
    "http://www.w3.org/2002/07/owl#equivalentProperty",
    "http://www.w3.org/2002/07/owl#disjointWith",
    "http://www.w3.org/2002/07/owl#inverseOf",
    "http://www.w3.org/2002/07/owl#onProperty",
    "http://www.w3.org/2002/07/owl#someValuesFrom",
    "http://www.w3.org/2002/07/owl#allValuesFrom",
    // IRI-valued attributes: the object is a web page or an image, not an
    // entity of the graph, so it is a sink that would only absorb rank.
    "http://yago-knowledge.org/resource/hasWebsite",
    "http://xmlns.com/foaf/0.1/homepage",
    "http://xmlns.com/foaf/0.1/depiction",
    "http://xmlns.com/foaf/0.1/isPrimaryTopicOf",
    "http://dbpedia.org/ontology/wikiPageExternalLink",
    "http://dbpedia.org/ontology/wikiPageRedirects",
    "http://dbpedia.org/ontology/wikiPageDisambiguates",
    "http://dbpedia.org/ontology/thumbnail",
];

/// Whole vocabularies to skip, by IRI prefix.
const SKIP_PREFIX: &[&str] = &[
    "http://www.w3.org/ns/shacl#",
    "http://www.w3.org/2004/02/skos/core#",
];

/// Edges carry the weight of their predicate; nodes are interned IRIs.
pub struct WeightedGraph {
    pub nodes: Vec<String>,
    pub edges: Vec<(u32, u32, f64)>,
}

/// What one power-iteration run did, so the thesis can state convergence
/// instead of guessing at it.
pub struct Run {
    pub scores: Vec<f64>,
    pub iterations: usize,
    pub mean_delta: f64,
    pub converged: bool,
}

/// Power iteration; `weighted = false` reproduces the classic baseline.
pub fn power_iteration(graph: &WeightedGraph, weighted: bool) -> Run {
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
        let mean_delta = delta / n as f64;
        if mean_delta <= TOLERANCE {
            println!("  converged after {iteration} iterations (mean Δ = {mean_delta:.3e})");
            return Run { scores: prev, iterations: iteration, mean_delta, converged: true };
        }
        if iteration == MAX_ITERATIONS {
            println!("  stopped at the {MAX_ITERATIONS}-iteration cap (mean Δ = {mean_delta:.3e})");
            return Run { scores: prev, iterations: iteration, mean_delta, converged: false };
        }
    }
    unreachable!("MAX_ITERATIONS is at least 1")
}

/// EntF(p) for each predicate, computed over the WHOLE graph (not just the
/// sampled edges) — the weight is a property of the predicate, not of the sample.
pub fn predicate_weights(ep: &SparqlEndpoint, predicates: &[String]) -> HashMap<String, f64> {
    let pool = crate::common::query_pool();
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

/// An IRI that cannot be written between angle brackets would break the query.
/// YAGO 3 in particular has IRIs the 2014 dump left un-encoded.
fn safe_iri(iri: &str) -> bool {
    !iri.is_empty()
        && !iri.chars().any(|c| c.is_whitespace()
            || matches!(c, '<' | '>' | '"' | '{' | '}' | '|' | '\\' | '^' | '`'))
}

/// The `FILTER`s that keep schema and external-link predicates out of the graph.
fn predicate_filter() -> String {
    let list = SKIP_EXACT
        .iter()
        .map(|p| format!("<{p}>"))
        .collect::<Vec<_>>()
        .join(", ");
    let mut filter = format!("FILTER(?p NOT IN ({list}))");
    for prefix in SKIP_PREFIX {
        filter.push_str(&format!(" FILTER(!STRSTARTS(STR(?p), \"{prefix}\"))"));
    }
    filter
}

/// The seed entities the expansion starts from.
///
/// Metric 5 (InfoRank) is the selection rule: the entities with the most literal
/// properties are the ones the graph actually describes, and because every
/// snapshot runs metric 5 with the same `limit`, the seeding is the same rule in
/// every snapshot — which is what makes the sampled subgraphs comparable.
fn seed_entities(ep: &SparqlEndpoint, want: usize) -> Vec<String> {
    if let Some(label) = out::label() {
        if let Some(json) = out::read_json(&label, "entity_informativeness") {
            let mut ranked: Vec<(String, f64)> = json["entities"]
                .as_object()
                .map(|m| {
                    m.iter()
                        .filter_map(|(iri, v)| Some((iri.clone(), v["inforank"].as_f64()?)))
                        .collect()
                })
                .unwrap_or_default();
            ranked.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
            let seeds: Vec<String> = ranked
                .into_iter()
                .map(|(iri, _)| iri)
                .filter(|iri| safe_iri(iri))
                .take(want)
                .collect();
            if !seeds.is_empty() {
                println!("  {} seeds from metric 5 (results/{label}/entity_informativeness.json)",
                         seeds.len());
                return seeds;
            }
        }
    }

    // Fallback: instances of the most populated class. Deterministic and cheap,
    // but it is NOT the same rule across snapshots — say so rather than let a
    // silently different seeding look like a metric change.
    println!("  NOTE: no entity_informativeness.json for this label — seeding from the \
              most populated class instead; this sample is not comparable across snapshots");
    let top = crate::common::top_type_iris(ep, 1);
    match top.first() {
        Some(class) => ep
            .column(&format!("SELECT ?s WHERE {{ ?s a <{class}> }} LIMIT {want}"), "s")
            .into_iter()
            .filter(|iri| safe_iri(iri))
            .collect(),
        None => Vec::new(),
    }
}

/// All out-edges of `frontier`, batched into `VALUES` blocks and run in parallel.
fn expand(ep: &SparqlEndpoint, frontier: &[String], filter: &str)
    -> Vec<(String, String, String)>
{
    let pool = crate::common::query_pool();
    pool.install(|| {
        frontier
            .par_chunks(SEED_BATCH)
            .flat_map(|chunk| {
                let values = chunk
                    .iter()
                    .map(|s| format!("<{s}>"))
                    .collect::<Vec<_>>()
                    .join(" ");
                let q = format!(
                    "SELECT ?s ?p ?o WHERE {{ VALUES ?s {{ {values} }} \
                     ?s ?p ?o . FILTER(isIRI(?o)) {filter} }}"
                );
                ep.triples(&q)
            })
            .collect()
    })
}

/// Build the subgraph induced by breadth-first expansion from the seeds.
///
/// The last hop is a CLOSING pass: only edges pointing back at an already
/// discovered node are kept. Without it the outermost ring would be a fringe of
/// leaves that receive rank and pass none on, which is the same structural
/// defect — on a smaller scale — as the star forest this replaced.
pub fn build_graph(ep: &SparqlEndpoint, seeds: usize, hops: usize, max_edges: usize)
    -> (WeightedGraph, HashMap<String, f64>)
{
    let filter = predicate_filter();
    let frontier_seeds = seed_entities(ep, seeds);
    if frontier_seeds.is_empty() {
        return (WeightedGraph { nodes: Vec::new(), edges: Vec::new() }, HashMap::new());
    }

    let mut visited: HashSet<String> = frontier_seeds.iter().cloned().collect();
    let mut frontier = frontier_seeds;
    let mut triples: Vec<(String, String, String)> = Vec::new();

    for hop in 1..=hops {
        if frontier.is_empty() || triples.len() >= max_edges {
            break;
        }
        let closing = hop == hops;
        let found = expand(ep, &frontier, &filter);

        let mut next_frontier = Vec::new();
        let mut kept = 0usize;
        for (s, p, o) in found {
            if closing && !visited.contains(&o) {
                continue; // closing pass: back-edges only
            }
            if !closing && visited.insert(o.clone()) && safe_iri(&o) {
                next_frontier.push(o.clone());
            }
            triples.push((s, p, o));
            kept += 1;
            if triples.len() >= max_edges {
                break;
            }
        }
        println!("  hop {hop}{}: {} edges kept, frontier {} -> {}",
                 if closing { " (closing)" } else { "" },
                 kept, frontier.len(), next_frontier.len());
        frontier = next_frontier;
    }

    // The same (s,p,o) can be reached from two directions.
    triples.sort();
    triples.dedup();
    println!("  {} distinct entity-to-entity edges", triples.len());

    let mut predicates: Vec<String> = triples.iter().map(|(_, p, _)| p.clone()).collect();
    predicates.sort();
    predicates.dedup();
    println!("  {} distinct predicates -> {} entropy queries",
             predicates.len(), predicates.len());

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
    println!("  {} nodes, {} edges  ({:.2} edges per node)",
             nodes.len(), edges.len(),
             edges.len() as f64 / nodes.len().max(1) as f64);
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

pub fn run(ep: &SparqlEndpoint, seeds: usize, hops: usize, max_edges: usize) {
    println!("Metric 7: Entropy-weighted PageRank (own variant)");
    println!("          PR(v) = (1-d) + d · Σ w(p) · PR(u)/outdeg(u),  d = {DAMPING}");
    println!("Scope:    subgraph induced by {hops}-hop expansion from {seeds} InfoRank \
              seeds, up to {max_edges} edges\n");

    let (graph, weights) = build_graph(ep, seeds, hops, max_edges);
    if graph.edges.is_empty() {
        println!("  no edges in scope — nothing to rank");
        return;
    }

    println!("\n  entropy-weighted run:");
    let weighted = power_iteration(&graph, true);
    println!("  unweighted baseline run:");
    let baseline = power_iteration(&graph, false);

    let rank_w = ranks(&weighted.scores);
    let rank_b = ranks(&baseline.scores);

    let mut order: Vec<usize> = (0..graph.nodes.len()).collect();
    order.sort_by(|&a, &b| weighted.scores[b].partial_cmp(&weighted.scores[a]).unwrap());

    println!("\n  predicate weights w(p) = EntF(p)/max EntF:");
    let mut by_weight: Vec<(&String, &f64)> = weights.iter().collect();
    by_weight.sort_by(|a, b| b.1.partial_cmp(a.1).unwrap());
    for (p, w) in by_weight.iter().take(8) {
        println!("   {:>6.3}   {}", w, short(p));
    }

    let moved = rank_w.iter().zip(&rank_b).filter(|(a, b)| a != b).count();
    println!("\n  {moved} of {} nodes rank differently under the entropy weighting \
              ({:.1}%)", graph.nodes.len(),
             100.0 * moved as f64 / graph.nodes.len() as f64);

    println!("\n  Top 20 by entropy-weighted PageRank (Δrank vs the unweighted baseline):");
    println!("  {:>9}  {:>7}  {:>8}   {}", "score", "rank", "Δrank", "node");
    for &v in order.iter().take(20) {
        let shift = rank_b[v] as i64 - rank_w[v] as i64;
        println!("  {:>9.4}  {:>7}  {:>+8}   {}",
                 weighted.scores[v], rank_w[v], shift, short(&graph.nodes[v]));
    }

    let dict: serde_json::Map<String, serde_json::Value> = order
        .iter()
        .map(|&v| (graph.nodes[v].clone(), json!({
            "entropy_weighted": weighted.scores[v],
            "unweighted": baseline.scores[v],
            "rank_weighted": rank_w[v],
            "rank_unweighted": rank_b[v],
            "rank_shift": rank_b[v] as i64 - rank_w[v] as i64,
        })))
        .collect();

    println!("\nResults saved to:");
    out::write_json("entropy_pagerank", &json!({
        "sampling": {
            "method": "breadth-first expansion from metric-5 InfoRank seeds",
            "seeds": seeds,
            "hops": hops,
            "max_edges": max_edges,
            "nodes": graph.nodes.len(),
            "edges": graph.edges.len(),
            "distinct_predicates": weights.len(),
        },
        "convergence": {
            "damping": DAMPING,
            "tolerance": TOLERANCE,
            "max_iterations": MAX_ITERATIONS,
            "weighted": {"iterations": weighted.iterations,
                         "mean_delta": weighted.mean_delta,
                         "converged": weighted.converged},
            "unweighted": {"iterations": baseline.iterations,
                           "mean_delta": baseline.mean_delta,
                           "converged": baseline.converged},
        },
        "nodes_reranked": moved,
        "predicate_weights": weights,
        "nodes": dict,
    }));
    out::write_csv("entropy_pagerank",
                   "node,entropy_weighted,unweighted,rank_weighted,rank_unweighted,rank_shift",
                   &order.iter()
                         .map(|&v| format!("{},{:.8},{:.8},{},{},{}",
                                           out::csv_escape(short(&graph.nodes[v])),
                                           weighted.scores[v], baseline.scores[v],
                                           rank_w[v], rank_b[v],
                                           rank_b[v] as i64 - rank_w[v] as i64))
                         .collect::<Vec<_>>());
}

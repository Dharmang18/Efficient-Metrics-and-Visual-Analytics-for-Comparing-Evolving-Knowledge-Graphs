//! Metric 10 — Triple-level diff via integer-encoded sets.
//!
//!     Added = T2 - T1      Deleted = T1 - T2      Unchanged = T1 ∩ T2
//!
//! The efficiency contribution. Comparing two versions triple by triple as
//! STRINGS means hashing three IRIs per triple and keeping every byte of them
//! in memory. Instead each distinct term is interned once into a u32, so a
//! triple becomes 12 bytes and the comparison becomes a sort + linear merge
//! over integers. Both paths are implemented here and timed against each other,
//! which is what the thesis benchmarks.
//!
//! Scoping, and why it is done this way. A bare LIMIT returns an ARBITRARY
//! subset and two endpoints need not pick the same one, so diffing those is
//! meaningless. The obvious fix, ORDER BY ?s ?p ?o LIMIT n, is worse: the
//! server must sort the WHOLE graph before it can take n rows — on a 1.5 B
//! triple graph QLever asks for 12.7 GB and gives up.
//!
//! So the diff runs over a SUBJECT WINDOW instead. Take the lexicographically
//! first n subjects of each version (ordering a subject list is cheap — it is
//! an index scan, not a sort of every triple), cut both lists at the smaller
//! upper bound, and fetch all triples of the surviving subjects by name. Inside
//! that window both versions are covered COMPLETELY, so the diff is exact
//! there — including entities that appear or vanish between versions — while
//! nothing anywhere needs a global sort.

use crate::common::short;
use crate::out;
use crate::qlever_client::SparqlEndpoint;
use serde_json::json;
use std::collections::{BTreeSet, HashMap, HashSet};
use std::time::{Duration, Instant};

pub type Triple = (String, String, String);

#[derive(Default, Clone, Copy)]
pub struct Diff {
    pub added: usize,
    pub deleted: usize,
    pub unchanged: usize,
}

impl Diff {
    /// (added + deleted) / |T1| — how much of the old version was touched.
    pub fn churn(&self, old_size: usize) -> f64 {
        if old_size > 0 {
            (self.added + self.deleted) as f64 / old_size as f64
        } else {
            0.0
        }
    }
}

/// How many subjects to name in one VALUES clause. Big enough that the round
/// trips do not dominate, small enough to keep the query text sane.
const BATCH: usize = 1000;

/// The lexicographically first `n` subjects — the deterministic window. This
/// orders a subject LIST, which QLever answers from its index, unlike ordering
/// every triple of the graph.
pub fn window_subjects(ep: &SparqlEndpoint, class: Option<&str>, n: usize) -> Vec<String> {
    let pattern = match class {
        Some(c) => format!("?s a <{c}>"),
        None => "?s ?p ?o".to_string(),
    };
    let q = format!("SELECT DISTINCT ?s WHERE {{ {pattern} }} ORDER BY ?s LIMIT {n}");
    match ep.query(&q) {
        Ok(rows) => rows.into_iter().filter_map(|mut r| r.remove("s")).collect(),
        Err(e) => {
            eprintln!("\ncould not take a subject window from {}\n  {e}", ep.url());
            if class.is_none() {
                eprintln!(
                    "\nA whole-graph window has to order every subject in the graph, which a\n\
                     large graph cannot afford (QLever asks for tens of GB and refuses).\n\
                     Scope the diff to one class instead — that is the intended use anyway:\n\
                     \n  cargo run --release diff 'http://schema.org/Person' {n}\n");
            }
            std::process::exit(1);
        }
    }
}

/// The window both versions cover completely: the union of their two prefixes,
/// cut at whichever prefix ends earlier. Beyond that bound one side would be
/// missing subjects the other has, and a "deletion" there would be an artefact
/// of the cap rather than a real change.
pub fn common_window(a: &SparqlEndpoint, b: &SparqlEndpoint, class: Option<&str>, n: usize)
    -> Vec<String>
{
    let sa = window_subjects(a, class, n);
    let sb = window_subjects(b, class, n);
    let bound = match (sa.last(), sb.last()) {
        (Some(x), Some(y)) => x.min(y).clone(),
        (Some(x), None) => x.clone(),
        (None, Some(y)) => y.clone(),
        (None, None) => return Vec::new(),
    };
    let window: BTreeSet<String> = sa.into_iter().chain(sb).filter(|s| *s <= bound).collect();
    window.into_iter().collect()
}

/// Every triple of the named subjects. No ORDER BY: naming the subjects
/// already pins the result down to one exact set, and the sort happens locally
/// on integers a moment later anyway.
pub fn fetch_triples_of(ep: &SparqlEndpoint, subjects: &[String]) -> Vec<Triple> {
    let mut out = Vec::new();
    for chunk in subjects.chunks(BATCH) {
        let values: String = chunk.iter()
            .map(|s| format!("<{s}>"))
            .collect::<Vec<_>>()
            .join(" ");
        let q = format!("SELECT ?s ?p ?o WHERE {{ VALUES ?s {{ {values} }} ?s ?p ?o }}");
        out.extend(ep.triples(&q));
    }
    out
}

// ---------------------------------------------------------------- fast path

/// Intern every term of both versions into u32 ids, shared across the two
/// sides so equal strings get equal ids and comparison never touches a byte of
/// text again. The dictionary borrows from the input slices, so interning
/// copies no strings.
fn intern<'a>(s: &'a str, ids: &mut HashMap<&'a str, u32>, next_id: &mut u32) -> u32 {
    if let Some(&id) = ids.get(s) {
        return id;
    }
    let id = *next_id;
    *next_id += 1;
    ids.insert(s, id);
    id
}

fn encode<'a>(a: &'a [Triple], b: &'a [Triple]) -> (Vec<[u32; 3]>, Vec<[u32; 3]>) {
    let mut ids: HashMap<&'a str, u32> = HashMap::new();
    let mut next_id: u32 = 0;

    let mut encode_side = |side: &'a [Triple], ids: &mut HashMap<&'a str, u32>| {
        let mut v: Vec<[u32; 3]> = side
            .iter()
            .map(|(s, p, o)| {
                [intern(s, ids, &mut next_id),
                 intern(p, ids, &mut next_id),
                 intern(o, ids, &mut next_id)]
            })
            .collect();
        v.sort_unstable();
        v.dedup();
        v
    };

    let ea = encode_side(a, &mut ids);
    let eb = encode_side(b, &mut ids);
    (ea, eb)
}

/// Linear merge of two sorted integer triple sets.
pub fn diff_encoded(a: &[Triple], b: &[Triple]) -> (Diff, Duration) {
    let start = Instant::now();
    let (ea, eb) = encode(a, b);

    let mut d = Diff::default();
    let (mut i, mut j) = (0usize, 0usize);
    while i < ea.len() && j < eb.len() {
        match ea[i].cmp(&eb[j]) {
            std::cmp::Ordering::Equal => {
                d.unchanged += 1;
                i += 1;
                j += 1;
            }
            std::cmp::Ordering::Less => {
                d.deleted += 1; // in the old version only
                i += 1;
            }
            std::cmp::Ordering::Greater => {
                d.added += 1; // in the new version only
                j += 1;
            }
        }
    }
    d.deleted += ea.len() - i;
    d.added += eb.len() - j;
    (d, start.elapsed())
}

// -------------------------------------------------------------- naive path

/// The baseline the thesis compares against: hash sets of string triples.
pub fn diff_naive(a: &[Triple], b: &[Triple]) -> (Diff, Duration) {
    let start = Instant::now();
    let sa: HashSet<Triple> = a.iter().cloned().collect();
    let sb: HashSet<Triple> = b.iter().cloned().collect();
    let d = Diff {
        added: sb.difference(&sa).count(),
        deleted: sa.difference(&sb).count(),
        unchanged: sa.intersection(&sb).count(),
    };
    (d, start.elapsed())
}

/// Bytes the two representations need for the comparison itself.
fn memory_estimate(a: &[Triple], b: &[Triple]) -> (usize, usize) {
    let strings: usize = a.iter().chain(b.iter())
        .map(|(s, p, o)| s.len() + p.len() + o.len() + 3 * std::mem::size_of::<String>())
        .sum();
    let encoded = (a.len() + b.len()) * 3 * std::mem::size_of::<u32>();
    (strings, encoded)
}

pub fn run(a: &SparqlEndpoint, b: &SparqlEndpoint, class: Option<&str>, cap: usize) {
    println!("Metric 10: Triple-level diff via integer-encoded sets");
    println!("  version 1: {}", a.url());
    println!("  version 2: {}", b.url());
    match class {
        Some(c) => println!("  scope:     class <{c}>, subject window of {cap}\n"),
        None => println!("  scope:     whole graph, subject window of {cap}\n"),
    }

    let window = common_window(a, b, class, cap);
    if window.is_empty() {
        println!("  the scope is empty in at least one version — nothing to diff");
        return;
    }
    let t1 = fetch_triples_of(a, &window);
    let t2 = fetch_triples_of(b, &window);
    println!("  window of {} subjects -> {} + {} triples", window.len(), t1.len(), t2.len());

    // Two versions of one KG share their subject IRIs; two DIFFERENT KGs do
    // not, and then the window lands entirely inside one of them and the diff
    // reports every triple of the other side as "added". That is arithmetically
    // right and completely meaningless, so say so rather than let it pass for
    // a result.
    if t1.is_empty() != t2.is_empty() {
        println!("\n  WARNING: one version contributed no triples at all for this window.");
        println!("  The two endpoints look like different knowledge graphs rather than two");
        println!("  versions of one — their subject IRIs do not overlap, so a triple-level");
        println!("  diff says nothing. Use metric 13 (crosskg) to compare two KGs.\n");
    }

    let (fast, fast_time) = diff_encoded(&t1, &t2);
    let (naive, naive_time) = diff_naive(&t1, &t2);

    // The two paths must agree; if they ever do not, the benchmark is worthless.
    assert_eq!((fast.added, fast.deleted, fast.unchanged),
               (naive.added, naive.deleted, naive.unchanged),
               "integer-encoded and naive diff disagree");

    println!("\n  added     {:>12}", fast.added);
    println!("  deleted   {:>12}", fast.deleted);
    println!("  unchanged {:>12}", fast.unchanged);
    println!("  churn     {:>12.4}   (added+deleted)/|T1|", fast.churn(t1.len()));

    let (mem_naive, mem_encoded) = memory_estimate(&t1, &t2);
    let speedup = naive_time.as_secs_f64() / fast_time.as_secs_f64().max(1e-9);
    println!("\n  benchmark (comparison phase only, the fetch is excluded):");
    println!("  {:<26} {:>10.1} ms   {:>9.1} MB", "integer-encoded sets",
             fast_time.as_secs_f64() * 1e3, mem_encoded as f64 / 1e6);
    println!("  {:<26} {:>10.1} ms   {:>9.1} MB", "naive string hash sets",
             naive_time.as_secs_f64() * 1e3, mem_naive as f64 / 1e6);
    println!("  {:<26} {:>10.1}x   {:>9.1}x", "integer path is",
             speedup, mem_naive as f64 / mem_encoded.max(1) as f64);

    println!("\nResults saved to:");
    out::write_json("triple_diff", &json!({
        "version_1": a.url(),
        "version_2": b.url(),
        "scope": class.map(short).unwrap_or("whole-graph"),
        "subject_window": cap,
        "subjects_compared": window.len(),
        "triples_v1": t1.len(),
        "triples_v2": t2.len(),
        "added": fast.added,
        "deleted": fast.deleted,
        "unchanged": fast.unchanged,
        "churn": fast.churn(t1.len()),
        "benchmark": {
            "encoded_ms": fast_time.as_secs_f64() * 1e3,
            "naive_ms": naive_time.as_secs_f64() * 1e3,
            "speedup": speedup,
            "encoded_bytes": mem_encoded,
            "naive_bytes": mem_naive,
        }
    }));
    out::write_csv("triple_diff", "measure,value", &vec![
        format!("added,{}", fast.added),
        format!("deleted,{}", fast.deleted),
        format!("unchanged,{}", fast.unchanged),
        format!("churn,{:.6}", fast.churn(t1.len())),
        format!("encoded_ms,{:.3}", fast_time.as_secs_f64() * 1e3),
        format!("naive_ms,{:.3}", naive_time.as_secs_f64() * 1e3),
        format!("speedup,{:.3}", speedup),
    ]);
}

//! Thesis KG metrics — SPARQL + Rust dictionaries (mirrors Knowgly).
//!
//! Every metric follows the same pattern: SPARQL does the counting, Rust holds
//! the dictionaries and applies the formula, the result lands in
//! `results/[<label>/]<metric>.{json,csv}` for the niceGUI dashboard.
//!
//! Endpoints come from the environment, so the same binary runs against the
//! laptop, the home server or the university VM without a recompile:
//!   QLEVER_ENDPOINT     the graph to measure     (default http://localhost:9004)
//!   QLEVER_ENDPOINT_B   the second graph         (cross-version / cross-KG only)
//!   QLEVER_LABEL        names this snapshot      -> results/<label>/...
//!
//! Run `cargo run --release help` for the metric list.

mod class_churn;
mod class_entropy;
mod class_population;
mod common;
mod cross_kg;
mod ent_etimp;
mod entity_informativeness;
mod entity_type_importance;
mod entropy_pagerank;
mod graph_shape;
mod object_diversity;
mod out;
mod page_rank;
mod property_entropy;
mod qlever_client;
mod trajectories;
mod triple_diff;
mod vocab_evolution;

use common::short;
use entity_type_importance::get_entity_type_importances;
use qlever_client::{endpoint, SparqlEndpoint};
use std::fs;
use std::io::Write;

const HELP: &str = r#"
Thesis KG metrics — 13 metrics, three analysis levels.

  cargo run --release <metric> [args]

CLASS-LEVEL
  population   [classes=20]                 1  class population & share
  entf         [classes=8] [preds=10]       2  property entropy per type
  entetimp     [classes=8] [preds=10]       3  entropy-weighted type importance
  classentropy [classes=8]                  4  class entropy

ENTITY-LEVEL
  inforank     [top=50] [class-IRI]         5  entity informativeness
  diversity    [classes=8]                  6  object diversity

GLOBAL
  entropy-pagerank [seeds=50] [hops=3] [edges=200000]
                                            7  entropy-weighted PageRank (own variant)
  shape                                     8  graph size & shape
  churn        [classes=8] [cap=50000]      9  class-level change rate      [2 endpoints]
  diff         [class-IRI|-] [cap=200000]  10  triple diff, integer-encoded [2 endpoints]
  trajectories <metric> <label> <label>..  11  metric trajectories          [stored results]
  vocab        [cap=10000]                 12  vocabulary evolution         [2 endpoints]
  crosskg      [class-name|-] [scan=40]    13  cross-KG class comparison    [2 endpoints]

BASELINES (provided, from Knowgly — not thesis contributions)
  etimp        [classes=10]                    entity type importance
  pagerank     [edges=500000]                  classic unweighted PageRank

  all          [classes=8]                     every single-endpoint metric in order

Environment
  QLEVER_ENDPOINT    graph to measure    (default http://localhost:9004)
  QLEVER_ENDPOINT_B  second graph        (needed by churn / diff / vocab / crosskg)
  QLEVER_LABEL       snapshot name       (results/<label>/... — required for trajectories)
  QLEVER_PARALLELISM concurrent queries  (default 4; lower it if the server reports
                                          "Tried to allocate ... but only ... available")
  QLEVER_CLASSES     pinned class list   (comma-separated local names, e.g.
                                          Person,Taxon,Star — same classes in every
                                          snapshot, so per-class metrics compare)
  QLEVER_MAX_CLASS_SIZE  skip classes bigger than this when NOT pinned (default 10M)
  QLEVER_SUFFIX      output suffix       (e.g. _pinned -> results/<label>/entf_pinned.json)
"#;

fn arg(n: usize) -> Option<String> {
    std::env::args().nth(n)
}

fn num_arg(n: usize, default: usize) -> usize {
    arg(n).and_then(|s| s.parse().ok()).unwrap_or(default)
}

/// The second graph. Missing it is the most likely mistake, so say exactly
/// what to set rather than failing somewhere deep in a query.
fn endpoint_b() -> SparqlEndpoint {
    match std::env::var("QLEVER_ENDPOINT_B") {
        Ok(url) if !url.is_empty() => {
            println!("Endpoint B: {url}");
            SparqlEndpoint::new(&url)
        }
        _ => {
            eprintln!("This metric compares two graphs, so it needs a second endpoint:");
            eprintln!("  export QLEVER_ENDPOINT_B=http://localhost:9005");
            std::process::exit(1);
        }
    }
}

/// `-` means "no class filter", so the argument can be skipped positionally.
fn optional_class(n: usize) -> Option<String> {
    arg(n).filter(|s| s != "-" && !s.is_empty())
}

fn main() {
    let endpoint_url =
        std::env::var("QLEVER_ENDPOINT").unwrap_or_else(|_| "http://localhost:9004".to_string());
    qlever_client::init(&endpoint_url);

    let metric = arg(1).unwrap_or_else(|| "etimp".to_string());
    if metric == "help" || metric == "--help" || metric == "-h" {
        println!("{HELP}");
        return;
    }

    println!("Endpoint:  {endpoint_url}");
    if let Some(label) = out::label() {
        println!("Snapshot:  {label}  (results/{label}/)");
    }
    println!();

    let ep = endpoint();
    match metric.as_str() {
        // ---- class level
        "population" => class_population::run(ep, num_arg(2, 20)),
        "entf" => property_entropy::run(ep, num_arg(2, 8), num_arg(3, 10)),
        "entetimp" => ent_etimp::run(ep, num_arg(2, 8), num_arg(3, 10)),
        "classentropy" => class_entropy::run(ep, num_arg(2, 8)),

        // ---- entity level
        "inforank" => entity_informativeness::run(ep, optional_class(3).as_deref(), num_arg(2, 50)),
        "diversity" => object_diversity::run(ep, num_arg(2, 8)),

        // ---- global
        "entropy-pagerank" => entropy_pagerank::run(ep, num_arg(2, 50), num_arg(3, 3),
                                                    num_arg(4, 200_000)),
        "shape" => graph_shape::run(ep),
        "churn" => class_churn::run(ep, &endpoint_b(), num_arg(2, 8), num_arg(3, 50_000)),
        "diff" => triple_diff::run(ep, &endpoint_b(),
                                   optional_class(2).as_deref(), num_arg(3, 200_000)),
        "vocab" => vocab_evolution::run(ep, &endpoint_b(), num_arg(2, 10_000)),
        "crosskg" => cross_kg::run(ep, &endpoint_b(),
                                   optional_class(2).as_deref(), num_arg(3, 40)),
        "trajectories" => {
            let metric_name = arg(2).unwrap_or_else(|| {
                eprintln!("usage: trajectories <metric> <label> <label> [...]");
                std::process::exit(1);
            });
            let labels: Vec<String> = std::env::args().skip(3).collect();
            trajectories::run(&metric_name, &labels);
        }

        // ---- provided baselines
        "pagerank" => run_pagerank(),
        "etimp" => run_etimp(num_arg(2, 10)),
        "all" => run_all(ep, num_arg(2, 8)),

        // a bare number keeps the original `cargo run --release 8` working
        other => match other.parse::<usize>() {
            Ok(n) => run_etimp(n),
            Err(_) => {
                eprintln!("unknown metric '{other}'\n{HELP}");
                std::process::exit(1);
            }
        },
    }
}

/// Every metric that needs only one endpoint, in the order of the metrics list.
fn run_all(ep: &SparqlEndpoint, classes: usize) {
    let rule = "─".repeat(78);
    for (name, run) in [
        ("1  class population", &(|e: &SparqlEndpoint, c: usize| class_population::run(e, c * 3)) as &dyn Fn(&SparqlEndpoint, usize)),
        ("2  property entropy", &|e, c| property_entropy::run(e, c, 10)),
        ("3  entropy-weighted type importance", &|e, c| ent_etimp::run(e, c, 10)),
        ("4  class entropy", &|e, c| class_entropy::run(e, c)),
        ("5  entity informativeness", &|e, _| entity_informativeness::run(e, None, 50)),
        ("6  object diversity", &|e, c| object_diversity::run(e, c)),
        ("7  entropy-weighted PageRank", &|e, _| entropy_pagerank::run(e, 50, 3, 200_000)),
        ("8  graph size & shape", &|e, _| graph_shape::run(e)),
    ] {
        println!("{rule}\n{name}\n{rule}");
        run(ep, classes);
        println!();
    }
    println!("Cross-version metrics (9, 10, 12, 13) need QLEVER_ENDPOINT_B;");
    println!("trajectories (11) needs two labelled runs. See `help`.");
}

fn run_pagerank() {
    let max_edges = num_arg(2, 500_000);
    println!("Baseline: PageRank (power iteration, d = {}, {} iterations max)",
             page_rank::DAMPING, page_rank::MAX_ITERATIONS);
    println!("Scope:    demo graph + YAGO subClassOf taxonomy (≤ {max_edges} edges)\n");

    // Part 1: sanity-check the algorithm on a graph small enough to verify by eye.
    page_rank::demo();

    // Part 2: a real YAGO subgraph.
    let scores = page_rank::run_on_taxonomy(max_edges);

    let mut ranked: Vec<(&String, &f64)> = scores.iter().collect();
    ranked.sort_by(|a, b| b.1.partial_cmp(a.1).unwrap());
    println!("\n  Top 20 classes by PageRank:");
    for (node, score) in ranked.iter().take(20) {
        println!("   {:>10.4}   {}", score, short(node));
    }

    fs::create_dir_all("results").expect("could not create results/ dir");
    let json = serde_json::to_string_pretty(&scores).unwrap();
    fs::write("results/page_rank.json", json).unwrap();

    let mut csv = fs::File::create("results/page_rank.csv").unwrap();
    writeln!(csv, "class,pagerank").unwrap();
    for (node, score) in &ranked {
        writeln!(csv, "{},{:.6}", short(node), score).unwrap();
    }
    println!("\nResults saved to:");
    println!("  results/page_rank.json   (class -> score dictionary)");
    println!("  results/page_rank.csv    (full ranking, sorted)");
}

fn run_etimp(num_types: usize) {
    println!("Baseline: Entity Type Importance  (ETImp(p,t) = EF_p(p,t) * log2(|E_t| / EF_p(p,t)))");
    println!("Scope:    top {num_types} most-populated types\n");

    let importances = get_entity_type_importances(num_types);

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

    fs::create_dir_all("results").expect("could not create results/ dir");
    let json = serde_json::to_string_pretty(&importances).unwrap();
    fs::write("results/entity_type_importance.json", json).unwrap();

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

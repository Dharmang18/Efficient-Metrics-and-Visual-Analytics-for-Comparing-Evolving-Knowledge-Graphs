//! Metric 11 — Metric trajectories.
//!
//!     Δm(v_i) = m(v_{i+1}) - m(v_i)
//!
//! The framework layer, and the reason every other metric writes its result to
//! `results/<label>/<metric>.json`. This reads the same metric back for several
//! labelled snapshots and lines the values up in version order with their
//! deltas — which is what turns a pile of per-snapshot numbers into an
//! evolution metric and feeds the dashboard's trend views.
//!
//! It is deliberately generic over the metric: any numeric leaf of the stored
//! JSON becomes a tracked series, so a metric added later needs no change here.

use crate::out;
use serde_json::{json, Value};
use std::collections::BTreeMap;

/// Walk a stored result and collect every numeric leaf as `path -> value`.
fn flatten(value: &Value, prefix: &str, into: &mut BTreeMap<String, f64>) {
    match value {
        Value::Number(n) => {
            if let Some(v) = n.as_f64() {
                into.insert(prefix.to_string(), v);
            }
        }
        Value::Object(map) => {
            for (k, v) in map {
                let path = if prefix.is_empty() { k.clone() } else { format!("{prefix}/{k}") };
                flatten(v, &path, into);
            }
        }
        Value::Array(items) => {
            for (i, v) in items.iter().enumerate() {
                flatten(v, &format!("{prefix}[{i}]"), into);
            }
        }
        _ => {}
    }
}

pub fn run(metric: &str, labels: &[String]) {
    println!("Metric 11: Metric trajectories   Δm(v_i) = m(v_i+1) - m(v_i)");
    println!("  metric:    {metric}");
    println!("  snapshots: {}\n", labels.join(" -> "));

    // One flattened series per snapshot, in the order the labels were given.
    let mut series: Vec<(String, BTreeMap<String, f64>)> = Vec::new();
    for label in labels {
        match out::read_json(label, metric) {
            Some(v) => {
                let mut flat = BTreeMap::new();
                flatten(&v, "", &mut flat);
                println!("  {label:<24} {} numeric values", flat.len());
                series.push((label.clone(), flat));
            }
            None => {
                eprintln!("\n  missing results/{label}/{metric}.json");
                eprintln!("  run that metric first with QLEVER_LABEL={label}");
                std::process::exit(1);
            }
        }
    }
    if series.len() < 2 {
        eprintln!("\n  a trajectory needs at least two snapshots");
        std::process::exit(1);
    }

    // Keys present in EVERY snapshot are the ones that can be tracked; a key
    // that appears only in some versions is itself a finding, so report both.
    let mut common: Vec<String> = series[0].1.keys().cloned().collect();
    common.retain(|k| series.iter().all(|(_, m)| m.contains_key(k)));
    let partial = series.iter().map(|(_, m)| m.len()).max().unwrap_or(0) - common.len();
    println!("\n  {} values tracked across all snapshots ({partial} appear in only some)\n",
             common.len());

    // Biggest movers first — that is what a reader wants to see.
    let mut rows: Vec<(String, Vec<f64>, f64)> = common
        .iter()
        .map(|k| {
            let values: Vec<f64> = series.iter().map(|(_, m)| m[k]).collect();
            let first = values.first().copied().unwrap_or(0.0);
            let last = values.last().copied().unwrap_or(0.0);
            let relative = if first != 0.0 { (last - first) / first.abs() } else { 0.0 };
            (k.clone(), values, relative)
        })
        .collect();
    rows.sort_by(|a, b| b.2.abs().partial_cmp(&a.2.abs()).unwrap());

    print!("  {:<44}", "value");
    for (label, _) in &series {
        print!(" {:>16}", label.chars().take(16).collect::<String>());
    }
    println!(" {:>12}", "total Δ %");
    for (key, values, relative) in rows.iter().take(25) {
        print!("  {:<44}", key.chars().take(44).collect::<String>());
        for v in values {
            print!(" {:>16.4}", v);
        }
        println!(" {:>+11.2} %", relative * 100.0);
    }

    let dict: serde_json::Map<String, Value> = rows
        .iter()
        .map(|(key, values, relative)| {
            // consecutive deltas, the Δm(v_i) of the formula
            let deltas: Vec<f64> = values.windows(2).map(|w| w[1] - w[0]).collect();
            (key.clone(), json!({
                "values": values,
                "deltas": deltas,
                "relative_change": relative,
            }))
        })
        .collect();

    println!("\nResults saved to:");
    out::write_json("trajectories", &json!({
        "metric": metric,
        "snapshots": labels,
        "series": dict,
    }));

    let mut csv_rows = Vec::new();
    for (key, values, relative) in &rows {
        let cells: Vec<String> = values.iter().map(|v| format!("{v:.6}")).collect();
        csv_rows.push(format!("{},{},{:.6}", out::csv_escape(key), cells.join(","), relative));
    }
    let header = format!("value,{},relative_change", labels.join(","));
    out::write_csv("trajectories", &header, &csv_rows);
}

//! Where metric results go.
//!
//! Every metric writes `<dir>/<metric>.json` (the canonical dictionary the
//! dashboard reads) and `<dir>/<metric>.csv` (sorted, opens in Excel/Numbers).
//! `<dir>` is `results/`, or `results/<label>/` when QLEVER_LABEL names the
//! snapshot being measured — that is what lets the trajectory metric put
//! several versions of the same graph side by side.

use std::fs;
use std::io::Write;
use std::path::PathBuf;

pub fn label() -> Option<String> {
    std::env::var("QLEVER_LABEL").ok().filter(|s| !s.is_empty())
}

pub fn out_dir() -> PathBuf {
    let mut dir = PathBuf::from("results");
    if let Some(l) = label() {
        dir.push(l);
    }
    fs::create_dir_all(&dir).expect("could not create the results directory");
    dir
}

/// Read back a metric result written earlier (used by the trajectory metric).
pub fn read_json(label: &str, metric: &str) -> Option<serde_json::Value> {
    let path = PathBuf::from("results").join(label).join(format!("{metric}.json"));
    let text = fs::read_to_string(&path).ok()?;
    serde_json::from_str(&text).ok()
}

pub fn write_json(metric: &str, value: &serde_json::Value) {
    let path = out_dir().join(format!("{metric}.json"));
    fs::write(&path, serde_json::to_string_pretty(value).unwrap())
        .unwrap_or_else(|e| panic!("could not write {}: {e}", path.display()));
    println!("  {}", path.display());
}

pub fn write_csv(metric: &str, header: &str, rows: &[String]) {
    let path = out_dir().join(format!("{metric}.csv"));
    let mut f = fs::File::create(&path)
        .unwrap_or_else(|e| panic!("could not write {}: {e}", path.display()));
    writeln!(f, "{header}").unwrap();
    for row in rows {
        writeln!(f, "{row}").unwrap();
    }
    println!("  {}", path.display());
}

/// CSV fields may contain commas (IRIs rarely do, labels often do).
pub fn csv_escape(s: &str) -> String {
    if s.contains(',') || s.contains('"') {
        format!("\"{}\"", s.replace('"', "\"\""))
    } else {
        s.to_string()
    }
}

//! Minimal QLever SPARQL client (mirrors Knowgly's qlever_client.rs).
//!
//! One global endpoint, reused everywhere (like Knowgly's `SPARQLEndpoint::access()`).
//! `query()` sends a SPARQL SELECT and returns the result rows as a Vec of
//! `var -> value` maps, so the metric code can do `row["p"]`, `row["ef_p_t"]`, etc.

use std::collections::HashMap;
use std::error::Error;
use std::sync::OnceLock;

pub struct SparqlEndpoint {
    url: String,
}

static ENDPOINT: OnceLock<SparqlEndpoint> = OnceLock::new();

/// Initialise the global endpoint once at program start.
pub fn init(url: &str) {
    let _ = ENDPOINT.set(SparqlEndpoint { url: url.to_string() });
}

/// Access the global endpoint (call `init` first).
pub fn endpoint() -> &'static SparqlEndpoint {
    ENDPOINT.get().expect("qlever_client::init(url) must be called first")
}

impl SparqlEndpoint {
    /// Run a SPARQL SELECT query; return rows as `variable -> value` maps.
    pub fn query(&self, query: &str) -> Result<Vec<HashMap<String, String>>, Box<dyn Error>> {
        // POST the query as a form field, ask for JSON results.
        // Parse from the response READER (not into_string), because some result
        // sets are tens of MB and ureq's into_string() caps at 10 MB.
        let resp = ureq::post(&self.url)
            .set("Accept", "application/sparql-results+json")
            .send_form(&[("query", query)])?;

        let json: serde_json::Value = serde_json::from_reader(resp.into_reader())?;

        // Column names, in order.
        let vars: Vec<String> = json["head"]["vars"]
            .as_array()
            .map(|a| a.iter().filter_map(|v| v.as_str().map(String::from)).collect())
            .unwrap_or_default();

        let mut rows = Vec::new();
        if let Some(bindings) = json["results"]["bindings"].as_array() {
            for b in bindings {
                let mut row = HashMap::new();
                for var in &vars {
                    if let Some(val) = b[var]["value"].as_str() {
                        row.insert(var.clone(), val.to_string());
                    }
                }
                rows.push(row);
            }
        }
        Ok(rows)
    }
}

//! Minimal QLever SPARQL client (mirrors Knowgly's qlever_client.rs).
//!
//! Two ways to reach an endpoint:
//!   * `init(url)` + `endpoint()` — the single global endpoint used by the
//!     per-snapshot metrics (like Knowgly's `SPARQLEndpoint::access()`);
//!   * `SparqlEndpoint::new(url)` — an explicit instance, needed by the
//!     cross-version / cross-KG metrics, which talk to TWO graphs at once.

use std::collections::HashMap;
use std::error::Error;
use std::sync::OnceLock;
use std::time::Duration;

pub struct SparqlEndpoint {
    url: String,
    agent: ureq::Agent,
}

/// Connect and read timeouts for every SPARQL request.
///
/// Without these, ureq waits forever. That is not theoretical: a metric run
/// against the home server over Tailscale sat blocked for **3.5 hours** using
/// 0.03s of CPU, with two sockets still ESTABLISHED to a server that had long
/// since gone idle — the tunnel had dropped the connections without either end
/// noticing, so the reads could never complete. It looked exactly like a slow
/// query, which is the dangerous part.
///
/// READ must exceed the server's own query timeout (`TIMEOUT = 600s` in our
/// Qleverfiles) so that a legitimately long query is never cut short by the
/// client; anything past that is a dead socket, not a slow answer.
const CONNECT_TIMEOUT: Duration = Duration::from_secs(30);
const READ_TIMEOUT: Duration = Duration::from_secs(900);

fn build_agent() -> ureq::Agent {
    ureq::AgentBuilder::new()
        .timeout_connect(CONNECT_TIMEOUT)
        .timeout_read(READ_TIMEOUT)
        .build()
}

static ENDPOINT: OnceLock<SparqlEndpoint> = OnceLock::new();

/// Initialise the global endpoint once at program start.
pub fn init(url: &str) {
    let _ = ENDPOINT.set(SparqlEndpoint { url: url.to_string(), agent: build_agent() });
}

/// Access the global endpoint (call `init` first).
pub fn endpoint() -> &'static SparqlEndpoint {
    ENDPOINT.get().expect("qlever_client::init(url) must be called first")
}

impl SparqlEndpoint {
    /// A second (or third) endpoint, for comparing two graphs.
    pub fn new(url: &str) -> Self {
        SparqlEndpoint { url: url.to_string(), agent: build_agent() }
    }

    pub fn url(&self) -> &str {
        &self.url
    }

    /// Run a SPARQL SELECT query; return rows as `variable -> value` maps.
    pub fn query(&self, query: &str) -> Result<Vec<HashMap<String, String>>, Box<dyn Error>> {
        // POST the query as a form field, ask for JSON results.
        // Parse from the response READER (not into_string), because some result
        // sets are tens of MB and ureq's into_string() caps at 10 MB.
        let resp = match self.agent.post(&self.url)
            .set("Accept", "application/sparql-results+json")
            .send_form(&[("query", query)])
        {
            Ok(resp) => resp,
            // QLever reports WHY a query failed in the body of its error
            // response ("Tried to allocate 2.5 GB, but only 770.8 MB were
            // available"). Losing that behind a bare status code turns a
            // one-line fix into an afternoon, so dig it out.
            Err(ureq::Error::Status(code, resp)) => {
                let body = resp.into_string().unwrap_or_default();
                let detail = serde_json::from_str::<serde_json::Value>(&body)
                    .ok()
                    .and_then(|v| v["exception"].as_str().map(String::from))
                    .unwrap_or_else(|| body.chars().take(300).collect());
                return Err(format!("HTTP {code} from the endpoint: {detail}").into());
            }
            Err(e) => return Err(e.into()),
        };

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

    /// `query`, but a failure aborts loudly instead of silently yielding an
    /// empty result — an empty dictionary looks like a real answer otherwise,
    /// and a metric computed from nothing is worse than no metric at all.
    pub fn rows(&self, query: &str) -> Vec<HashMap<String, String>> {
        match self.query(query) {
            Ok(rows) => rows,
            Err(e) => {
                eprintln!("\nSPARQL query failed against {}\n  error: {e}\n  query: {}\n",
                          self.url, query.trim());
                std::process::exit(1);
            }
        }
    }

    /// A query returning one row with one number, e.g. `SELECT (COUNT(*) AS ?n)`.
    pub fn scalar(&self, query: &str, var: &str) -> f64 {
        self.rows(query)
            .first()
            .and_then(|r| r.get(var))
            .and_then(|v| v.parse::<f64>().ok())
            .unwrap_or(0.0)
    }

    /// A query selecting `?s ?p ?o`, returned as plain triples.
    pub fn triples(&self, query: &str) -> Vec<(String, String, String)> {
        self.rows(query)
            .into_iter()
            .filter_map(|mut r| Some((r.remove("s")?, r.remove("p")?, r.remove("o")?)))
            .collect()
    }

    /// Every value of one variable, as a set-like vector (order preserved).
    pub fn column(&self, query: &str, var: &str) -> Vec<String> {
        self.rows(query)
            .into_iter()
            .filter_map(|mut r| r.remove(var))
            .collect()
    }
}

#!/bin/bash
# Fill in the missing metric-13 pairings.
#
# The home server holds at most two indexes in RAM at once, so each pairing is a
# separate step: start the two endpoints named in the comment, run the block,
# stop them, move to the next. Results land in
# rust_metrics/results/<label>/cross_kg.{json,csv}, which is where the dashboard
# and writing/data/ both read from.
set -uo pipefail
cd "$(dirname "$0")/rust_metrics" || exit 1
source "$HOME/.cargo/env" 2>/dev/null || true

S=100.113.106.12          # home server over Tailscale
CANDIDATES=40             # classes offered to the matcher per side

pair () {                 # pair <label> <endpoint_a> <endpoint_b>
  echo "=== $1 ==="
  QLEVER_ENDPOINT="$2" QLEVER_ENDPOINT_B="$3" QLEVER_LABEL="$1" \
    cargo run --release crosskg - "$CANDIDATES" \
    && echo "    -> results/$1/cross_kg.json" \
    || echo "    FAILED: $1"
}

# --- YAGO 4.5.0.2 (:9006) against each DBpedia -----------------------------
pair yago-4.5.0.2-vs-dbpedia-2015 http://$S:9006 http://$S:9008
pair yago-4.5.0.2-vs-dbpedia-2016 http://$S:9006 http://$S:9009
# pair yago-4.5.0.2-vs-dbpedia-2025 already done

# --- YAGO 4 (:9005) against each DBpedia -----------------------------------
# Thing (66.9M) and CreativeWork (35.9M) push QLever past the laptop's 12 GB and
# the kernel OOM-kills it, so they are skipped and recorded as "skipped" in the
# JSON. Keep only yago-4 and one DBpedia server running while these go.
export QLEVER_CROSSKG_SKIP=thing,creativework
pair yago-4-vs-dbpedia-2015 http://$S:9005 http://$S:9008
pair yago-4-vs-dbpedia-2016 http://$S:9005 http://$S:9009
pair yago-4-vs-dbpedia-2025 http://$S:9005 http://$S:9010
pair yago-4-vs-dbpedia-2022 http://$S:9005 http://131.159.130.53:7014
unset QLEVER_CROSSKG_SKIP

# DBpedia 2022-matched lives on the TUM VM (:7014) and needs the CIT VPN:
#   pair yago-4.5.0.2-vs-dbpedia-2022 http://$S:9006 http://131.159.130.53:7014
#
# YAGO 3 is intentionally absent: it types against WordNet synsets, so local-name
# matching finds nothing and the run would return an empty class set.

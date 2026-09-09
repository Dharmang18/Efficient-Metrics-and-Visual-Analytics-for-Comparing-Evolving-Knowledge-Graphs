#!/bin/bash
# Run one phase of the metric suite against one dataset.
#
#   ./run_phase.sh <phase 1|2|3> <label> <endpoint> [endpoint_b]
#
# The three phases are the three analysis levels the metrics are already grouped
# into (`cargo run --release help`):
#   phase 1  CLASS-LEVEL   population, entf, entetimp, classentropy      (1 endpoint)
#
# Per-class metrics run TWICE per snapshot:
#   descriptive  each snapshot's own top-N classes  -> results/<label>/<metric>.json
#   comparative  the pinned PHASE_CLASSES list      -> results/<label>/<metric>_pinned.json
# The pinned pass exists because "top N by population" selects almost disjoint
# classes in different versions (YAGO 4 and YAGO 4.5 share only Person in their
# top 8), so the descriptive numbers cannot be compared across snapshots.
#   phase 2  ENTITY-LEVEL  inforank, diversity, entropy-pagerank         (1 endpoint)
#   phase 3  GLOBAL        shape, churn, diff,
#                          vocab, crosskg, trajectories                  (2 endpoints)
#
# Results land in rust_metrics/results/<label>/<metric>.{json,csv}, which is the
# layout metric 11 (trajectories) reads back.

set -uo pipefail
PHASE="${1:?phase (1|2|3)}"
LABEL="${2:?label, e.g. yago-4.5.0.2}"
export QLEVER_ENDPOINT="${3:?endpoint URL}"
export QLEVER_LABEL="$LABEL"
[ $# -ge 4 ] && export QLEVER_ENDPOINT_B="$4"

cd "$(dirname "$0")/rust_metrics" || exit 1
BIN=./target/release/rust_metrics
LOG_DIR="results/$LABEL"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/phase$PHASE.log"

# Each entry is "<parallelism> <metric> [args]". QLever's MEMORY_FOR_QUERIES is a
# budget SHARED by all queries in flight, so the right number of workers depends on
# how much memory one query of that metric needs, not on how many cores we have.
# Measured on YAGO 4.5.0.2 (1.3B triples, -m 5G):
#   entf/entetimp  group one predicate's values -> 2 workers fits, 4 does not.
#   classentropy   groups EVERY value of a class (?s a T . ?s ?p ?v) -> needs the
#                  whole budget alone; at 2 workers it died asking for 1.5 GB with
#                  996 MB left, at 1 it completed in under two minutes.
# PAR_DEFAULT (QLEVER_PARALLELISM, default 2 here) applies to everything else.
PAR_DEFAULT="${QLEVER_PARALLELISM:-2}"

# Classes present and tractable in every snapshot being compared. Override with
# PHASE_CLASSES=... to change the comparison set.
PHASE_CLASSES="${PHASE_CLASSES:-Person,Taxon,Star,Galaxy,AdministrativeArea,Chemical_compound}"
case "$PHASE" in
  1) METRICS=("$PAR_DEFAULT population 20" "$PAR_DEFAULT entf 8 10" \
              "$PAR_DEFAULT entetimp 8 10" "1 classentropy 8") ;;
  2) METRICS=("$PAR_DEFAULT inforank 50" "$PAR_DEFAULT diversity 8" \
              "1 entropy-pagerank 50 3 200000") ;;
  3) METRICS=("$PAR_DEFAULT shape" "$PAR_DEFAULT churn 8 50000" \
              "$PAR_DEFAULT vocab 200000") ;;
  *) echo "unknown phase $PHASE"; exit 1 ;;
esac

{
  echo "=========================================================="
  echo "phase $PHASE   label=$LABEL   endpoint=$QLEVER_ENDPOINT"
  [ -n "${QLEVER_ENDPOINT_B:-}" ] && echo "                endpoint_b=$QLEVER_ENDPOINT_B"
  echo "started $(date '+%F %T')"
  echo "=========================================================="
} | tee "$LOG"

run_metrics() {
  local pass="$1"
  echo "" | tee -a "$LOG"
  echo "########## $pass pass ##########" | tee -a "$LOG"
  for m in "${METRICS[@]}"; do
    # shellcheck disable=SC2086
    set -- $m
    par="$1"; shift
    # metric 1 describes the whole snapshot; pinning classes would be meaningless
    # population + the whole-graph metrics ignore the pinned class list, so a
    # pinned pass would just duplicate the descriptive result — skip them.
    case "$pass:$1" in pinned:population|pinned:inforank|pinned:entropy-pagerank) continue ;; esac
    echo "" | tee -a "$LOG"
    echo "---- $1 ($pass, parallelism $par) ---- $(date '+%T')" | tee -a "$LOG"
    t0=$(date +%s)
    if QLEVER_PARALLELISM="$par" $BIN "$@" 2>&1 | tee -a "$LOG"; then
      echo "   ok in $(( $(date +%s) - t0 ))s" | tee -a "$LOG"
    else
      echo "   FAILED after $(( $(date +%s) - t0 ))s" | tee -a "$LOG"
      fail=$((fail+1))
    fi
  done
}

fail=0

# pass 1: each snapshot's own top-N classes (with the oversize skip)
unset QLEVER_CLASSES QLEVER_SUFFIX
run_metrics descriptive

# pass 2: the pinned, cross-snapshot comparable class list
export QLEVER_CLASSES="$PHASE_CLASSES"
export QLEVER_SUFFIX="_pinned"
run_metrics pinned
unset QLEVER_CLASSES QLEVER_SUFFIX

echo "" | tee -a "$LOG"
echo "phase $PHASE done $(date '+%F %T') — $fail failure(s)" | tee -a "$LOG"
exit $fail

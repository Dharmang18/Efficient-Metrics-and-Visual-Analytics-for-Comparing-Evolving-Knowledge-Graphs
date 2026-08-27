#!/bin/sh
# Download DBpedia latest-core (157 files, ~4.2 GB) with curl.
# The Qleverfile recipe uses wget, which this Mac does not have; curl -C - resumes,
# so this script is safe to re-run until every file is complete.
cd "$(dirname "$0")" || exit 1
mkdir -p rdf-input
xargs -P 6 -I{} sh -c '
  f="rdf-input/$(basename "$1")"
  # --fail is not optional: without it curl writes the 404 body to the file and
  # exits 0, so a "successful" download leaves a 162-byte HTML page named .ttl.bzip2
  # and the index build silently ingests nothing from it.
  if curl -fsSL -C - -o "$f" "$1"; then echo "ok   $(basename "$1")"; else
    rm -f "$f"; echo "FAIL $(basename "$1")"; fi
' _ {} < rdf-input.urls

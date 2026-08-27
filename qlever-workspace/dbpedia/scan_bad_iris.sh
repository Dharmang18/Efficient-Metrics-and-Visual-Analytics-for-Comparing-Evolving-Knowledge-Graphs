#!/bin/bash
# Report, per input file, how many lines contain an unterminated IRI reference —
# the class of line that aborted the first real index build:
#   Parse error: Unterminated IRI reference (found '<' but no '>' before one of
#   the following characters: <, ", newline)
#
# Run INSIDE the qlever image (it has lbzcat and perl):
#   docker run --rm -v "$PWD":/index -w /index --entrypoint bash \
#     docker.io/adfreiburg/qlever:latest -c ./scan_bad_iris.sh
#
# Writes bad_iri_report.txt (counts per file) and bad_iri_examples.txt (samples).
cd /index || exit 1
REPORT=bad_iri_report.txt
EXAMPLES=bad_iri_examples.txt
: > "$REPORT"; : > "$EXAMPLES"

total=0
for f in rdf-input/*.nt rdf-input/*.bz2; do
  [ -e "$f" ] || continue
  case "$f" in *.bz2) reader="lbzcat -n2";; *) reader="cat";; esac
  b=$(basename "$f")
  $reader "$f" 2>/dev/null | perl -ne 'print if /<[^>\s]*(?:[<"]|$)/' > /tmp/bad.$$ 2>/dev/null
  n=$(wc -l < /tmp/bad.$$)
  if [ "$n" -gt 0 ]; then
    printf "%10d  %s\n" "$n" "$b" | tee -a "$REPORT"
    { echo "### $b ($n lines)"; head -5 /tmp/bad.$$; echo; } >> "$EXAMPLES"
    total=$((total + n))
  fi
  rm -f /tmp/bad.$$
done
printf "%10d  TOTAL\n" "$total" | tee -a "$REPORT"
echo "SCAN DONE"

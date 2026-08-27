#!/bin/sh
# Build the thesis. TinyTeX lives in the home directory — no sudo, no PATH setup
# needed beyond this line.
export PATH="$PATH:$HOME/Library/TinyTeX/bin/universal-darwin"
pdflatex -interaction=nonstopmode thesis.tex >/dev/null
bibtex   thesis                              >/dev/null 2>&1 || true
pdflatex -interaction=nonstopmode thesis.tex >/dev/null
pdflatex -interaction=nonstopmode thesis.tex >/dev/null
echo "thesis.pdf  ($(wc -c < thesis.pdf | tr -d ' ') bytes)"
if grep -qE "^! " thesis.log; then echo "ERRORS:"; grep -E "^! " thesis.log | sort -u; else echo "no errors"; fi

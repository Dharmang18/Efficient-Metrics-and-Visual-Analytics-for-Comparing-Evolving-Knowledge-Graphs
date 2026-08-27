# Thesis document

LaTeX source of the thesis, using the standard TUM `tumthesis` class.

```
thesis.tex          main file: metadata, packages, chapter order
include/*.tex       one file per chapter — the outline lives here
bib/literature.bib  bibliography (seeded from the papers already read)
figures/            put generated plots here
*.cls, *.sty        the TUM template (do not edit)
```

## Building

```sh
./build.sh          # pdflatex -> bibtex -> pdflatex x2, then reports errors
open thesis.pdf
```

LaTeX is installed as **TinyTeX** in `~/Library/TinyTeX` — a user-space TeX Live,
chosen because this Mac has no passwordless sudo and `brew install --cask
basictex` would stall on a password prompt. `build.sh` puts it on PATH itself;
for interactive use, `~/.zshrc` already exports:

```sh
export PATH="$PATH:$HOME/Library/TinyTeX/bin/universal-darwin"
```

Missing a package later? `tlmgr install <name>` — no sudo required.

Two fixes were needed to make this 2016-era template build on TeX Live 2026:

- `packages.sty` loaded `etex`, which no longer ships (its extensions are part of
  the LaTeX kernel since 2019). The line is commented out with a note.
- `thesis.tex` must not use `\backmatter` (the class is based on `report`) or
  `\bstctlcite` (needs an IEEEtran control entry we do not have).

## Notes

- The class is based on `report`, so `\backmatter` does **not** exist here.
- Chapter files are outlines: section structure plus comments describing what
  belongs in each, including which numbers are already measured and where they
  came from. No placeholder prose — nothing in here is text to be "kept".
- Target scale, calibrated against a 2026 thesis from the same chair:
  ~16,000 words over ~57 pages, with the Experiments chapter more than half of it.

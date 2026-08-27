# DBpedia snapshot used in this thesis

Collection: `https://databus.dbpedia.org/dbpedia/collections/latest-core`
Resolved on 2026-08-20. The collection lists **157 files**; **86 are actually
retrievable (4.22 GB compressed)** and those are what the index is built from.
DBpedia's own parts are the **2022.12.01** release.

## What the index contains

| MB (compressed) | part | why it matters |
|---|---|---|
| 46 + 151 | `instance-types` specific + transitive | the `?s a ?type` assertions — every class-level metric depends on these |
| 169 | `labels_lang=en` | `rdfs:label` |
| 192 + 153 | `mappingbased-objects` / `-literals` | the clean, ontology-mapped facts |
| 922 | `infobox-properties` | raw infobox predicates |
| 5 | `ontology--DEV` (plain `.nt`) | the DBpedia ontology itself |
| — | categories, redirects, page ids/length, revisions, sdtypes, geo-coordinates, external/wikipedia/freebase/YAGO links | context and cross-KG links |

## 71 files are missing, and none of them are recoverable

**69 files** — every one published by `vehnem` (`replaced-iris`, `text`, `yago`) —
redirect to `vmdbpedia.informatik.uni-leipzig.de`, which is up but returns **404**
for all of them:

- `long-abstracts` / `short-abstracts` `lang=en` — **the English abstracts**
- `labels` / `long-abstracts` / `short-abstracts` for 22 other languages with English
  URIs (the "replaced-iris" variants)
- a 2016 YAGO alignment: `instance-types`, `taxonomy`, `sameAs`

**2 more files** — `linked-hypernyms` `core` and `extension` (`propan/lhd`, 2016) —
redirect to `boa.lmcloud.vse.cz`, which no longer resolves at all (`NXDOMAIN` from
both the local resolver and 1.1.1.1).

None of these are DBpedia's own current extraction output, and the databus lists no
mirrors. The practical consequences for the thesis:

1. **No `dbo:abstract` triples.** Abstracts are long free-text literals, so their
   absence mostly removes a predicate that would have dominated object-entropy
   rankings. Worth stating explicitly wherever DBpedia entropy is compared to YAGO.
2. **English-only labels.** Fine for a comparison against YAGO, which is queried in
   English here too.

Any DBpedia figure in the thesis should be read as
**"latest-core, restricted to the 86 files still served"**.

## Two traps this dataset set, both now fixed

1. **`curl` without `--fail` writes the 404 body to the file and exits 0.** The first
   download reported "155 ok / 2 failed" while 69 of those "ok" files were 162-byte
   HTML error pages named `*.ttl.bzip2`. `download.sh` now uses `curl -fsSL` and
   deletes the file on failure. Verify a fresh download by magic bytes, not by exit
   codes: real parts start with `BZh`.
2. **QLever logs "Index build completed" even when it ingested almost nothing.** The
   first build consumed only the four plain `.nt` ontology files — 69,322 triples —
   because `lbzcat` rejected the HTML files, and still finished "successfully" with
   all six permutations present. **Check the triple count in
   `dbpedia.index-log.txt`, never the completion line.** (This is the same lesson as
   the YAGO-4 build: `meta-data.json` is not a done-flag either.)

## Notes on the Qleverfile

Adapted from `qlever-control/Qleverfiles/Qleverfile.dbpedia`:

- `GET_DATA_CMD` -> `./download.sh` (upstream uses `wget`; this Mac has only `curl`).
- `CAT_INPUT_FILES` drops the `rdf-input/*.bzip2` branch — after the cleanup every
  remaining input is `.bz2` or plain `.nt`, and leaving the glob in would have made
  the build fail on an unmatched pattern.
- `PORT` 7012 -> 9007, to sit beside YAGO 4.5.0.2 on 9004.
- `MEMORY_FOR_QUERIES` 10G -> 4G, `CACHE_MAX_SIZE` 5G -> 2G: the Colima VM has 10 GB
  and may be serving YAGO at the same time.
- `TIMEOUT = 600s`; the qlever CLI default of 30s is far too short for a cold aggregate.

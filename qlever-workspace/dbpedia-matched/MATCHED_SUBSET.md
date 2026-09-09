# DBpedia across three versions — the matched subset

The thesis compares five snapshots: YAGO 4 (2020), YAGO 4.5.0.2 (2024), and DBpedia
**2015-10**, **2022.12.01**, **2025-12-01**. Two of those are within-KG evolution for
YAGO; the three DBpedia releases are within-KG evolution over a decade.

## Why a subset at all

Every DBpedia release ships a *different set of files*, from a different extraction
pipeline:

- **2015-10** — the classic `core-i18n/en/` dump on `downloads.dbpedia.org`,
  files named `instance_types_en.ttl.bz2` etc.
- **2022.12.01** — the Databus `latest-core` collection, files named as artifacts
  (`instance-types_inference=specific_lang=en.ttl.bz2` …). This is the **last**
  classic-extraction release; the Databus has nothing newer for these artifacts.
- **2025-12-01** — the new `dbpedia-wikipedia-kg-dump`, partitioned by graph and
  predicate family (`partition=rdf-type`, `partition=dbo`, `partition=dbp` …).

If we simply indexed "whatever each release ships", metric 12 (vocabulary evolution)
and metric 10 (triple diff) would report our *download choices* as change — a release
that happened to include categories or page metadata would look like it grew. So all
three are built from the **same five roles**, and nothing else:

| role | what it carries | 2015-10 | 2022.12.01 | 2025-12-01 |
|---|---|---|---|---|
| direct + transitive types | `?s a ?type` for every class level | `instance_types_en` + `instance_types_transitive_en` | `instance-types_inference=specific` + `=transitive` | `partition=rdf-type` (already the full closure) |
| ontology-mapped objects | clean `dbo:` object properties | `mappingbased_objects_en` | `mappingbased-objects_lang=en` | `dbpedia-ontology-properties partition=dbo` |
| ontology-mapped literals | clean `dbo:` literal properties | `mappingbased_literals_en` | `mappingbased-literals_lang=en` | *(folded into the dbo partition)* |
| raw infobox properties | the messy `dbp:` predicates | `infobox_properties_en` | `infobox-properties_lang=en` | `raw-source-properties partition=dbp` |
| labels | `rdfs:label` | `labels_en` | `labels_lang=en` | `partition=rdfs-label` |
| redirects | `dbo:wikiPageRedirects` | `redirects_en` | `redirects_lang=en` | `partition=dbo-wikiPageRedirects` |

Deliberately **excluded** everywhere: categories/SKOS, abstracts, page ids/length,
revisions, interlanguage/external/Wikipedia/Freebase links, sdtypes, the disjoint
domain/range variants, and the stale 2016–2019 link dumps that `latest-core` drags in.

## Types are TRANSITIVE, and this matters

DBpedia publishes two type files. `instance_types` (a.k.a. `inference=specific`)
gives each entity only its **single most specific** class; `instance_types_transitive`
adds **all superclasses**. A footballer is `dbo:SoccerPlayer` in the specific file and
also `dbo:Athlete`, `dbo:Person`, `dbo:Agent` in the transitive one.

We include **both**, because the class-level metrics scope entities by class, and YAGO
asserts `schema:Person` *directly* on every person. If DBpedia counted only most-specific
types, `dbo:Person` would be a tiny residual and would not be comparable to YAGO's
`schema:Person`, nor stable across DBpedia versions (as taxonomies deepen, more entities
move to more specific leaves).

Measured on the 2022 index, specific-only vs specific+transitive:

| class | specific only | + transitive (used) |
|---|---:|---:|
| Person | 298,492 | 1,922,501 |
| Species | 360 | 1,975,461 |
| Star / Galaxy / ChemicalCompound | unchanged (leaf classes) | unchanged |

2025's single `rdf-type` partition already contains the full closure (verified by
sampling: `dbr:Jack_Bauer` carries `FictionalCharacter`, `Agent`, `owl:Thing`, …), so
it needs no second file.

### Validation: matched vs full 2022 (2026-08-27)

The matched index (`:7014`, 237,155,678 triples) reproduces the full 86-file index
(`:7013`, 526 M triples) on class populations, confirming the subset loses no typed
entities — only the extra descriptive triples we meant to drop:

| class | full (:7013) | matched (:7014) | |
|---|---:|---:|---|
| Person | 1,922,501 | 1,860,208 | 97% — gap = excluded `sdtypes` + schema.org/foaf type files |
| Species | 1,975,461 | 1,975,461 | exact |
| Star / Galaxy / ChemicalCompound | — | — | exact |
| AdministrativeArea | 0 | 0 | 0 in BOTH — see note below |

Distinct classes 977 → 772 (the 205 missing are the excluded-file classes); distinct
typed subjects is identical to the specific-only build (7,564,288), as it must be —
transitive types add types to the same subjects, not new subjects.

**`AdministrativeArea` note:** `dbo:AdministrativeArea` has zero instances in DBpedia
2022 (full index too), so the pinned class needs a DBpedia synonym — likely
`dbo:AdministrativeRegion` or `schema:AdministrativeArea`. Add it to `canon()`/the pinned
list before running per-class metrics on DBpedia, the same way `Species` and
`ChemicalCompound` are already handled.

## Class names differ by namespace

The pinned comparison classes are matched by **local name**, not IRI (see
`../CLASS_MAPPING.md`). Across the DBpedia releases they live under
`http://dbpedia.org/ontology/`, and `Taxon` is `Species` there — the dashboard's
`canon()` folds `species → taxon`.

## Where each snapshot is served

| snapshot | machine | port |
|---|---|---|
| YAGO 4 (2020) | Windows server | 9005 |
| YAGO 4.5.0.2 | Windows server (+ local backup on the Mac) | 9006 |
| DBpedia 2022 — **full** `latest-core`, 86 files | TUM VM | 7013 |
| DBpedia 2022 — **matched** 6-file subset | TUM VM | 7014 |
| DBpedia 2015-10 — matched | Windows server (planned) | 9008 |
| DBpedia 2025-12-01 — matched | Windows server (planned) | 9010 |

The full 2022 index (`:7013`) is kept as an independent cross-check of the matched
build; it is not one of the five compared snapshots.

## Reproduce

Per release: `urls.txt` here lists the exact files (all HEAD-verified 200). Fetch with
a resume-safe loop, then build with a Qleverfile whose `CAT_INPUT_FILES` pipes
everything through `iri_filter.pl` (drops malformed IRIs QLever would reject) — the same
filter used for the full 2022 build. Raise the fd limit first (`ulimit -n 65536`): the
default 1024 is what failed the first Mac build ("Too many open files").

# The pinned class set

Per-class metrics (2, 3, 4, 6) are run twice per snapshot:

- **descriptive** — that snapshot's own top-N classes → `results/<label>/<metric>.json`
- **comparative** — the pinned classes below → `results/<label>/<metric>_pinned.json`

The pinned pass exists because *"the top N classes"* selects a **different set in every
snapshot**. YAGO 4 and YAGO 4.5 share only `Person` in their top 8:

| | top 8 by population |
|---|---|
| YAGO 4 | Thing, CreativeWork, Article, ScholarlyArticle, Place, Person, Human, GeoCoordinates |
| YAGO 4.5 | Taxon, Star, Person, Galaxy, Review_article, Researcher, Chemical_compound, Politician |

Per-class numbers taken from those two lists cannot be compared, which is the whole
point of an evolution thesis. The pinned list fixes the classes so metric 11
(trajectories) and metric 13 (cross-KG) line up class-for-class.

## The classes

| pinned name | YAGO 4 | YAGO 4.5 | DBpedia |
|---|---:|---:|---:|
| Person | 6,433,965 | 2,982,308 | 1,922,501 |
| Taxon → Species | 2,726,502 | 3,506,350 | 1,975,461 |
| AdministrativeArea | 1,942,524 | 518,290 | 54,915 |
| Chemical_compound → ChemicalCompound | 1,015,809 | 1,114,868 | 12,767 |
| Star | 1,707,848 | 3,278,545 | 5,019 |
| Galaxy | 1,336,587 | 2,094,595 | 1,984 |

    YAGO      QLEVER_CLASSES=Person,Taxon,Star,Galaxy,AdministrativeArea,Chemical_compound
    DBpedia   QLEVER_CLASSES=Person,Species,Star,Galaxy,AdministrativeArea,ChemicalCompound

## Two things to state in the thesis

**1. Class IRIs are not stable, so classes are matched by local name.**
The same class sits in different namespaces in different snapshots:

| class | YAGO 4 | YAGO 4.5 |
|---|---|---|
| Taxon | `http://bioschemas.org/Taxon` | `http://schema.org/Taxon` |
| Person | `http://schema.org/Person` | `http://schema.org/Person` |
| Star, Galaxy, Chemical_compound | `http://yago-knowledge.org/resource/...` | same |

Matching on the IRI would have silently dropped `Taxon` from the comparison. This is
the confirmed instance of the namespace migration previously only suspected for
`parentTaxon`.

**2. A local name can be ambiguous, and the resolver says so.**
DBpedia carries three classes named `Person`:

    http://dbpedia.org/ontology/Person   1,922,501
    http://schema.org/Person             1,860,208
    http://xmlns.com/foaf/0.1/Person     1,860,208

`common::pinned_type_iris` takes the most populated (deterministic) and prints a NOTE
naming the alternatives, because silently choosing between them would hide a genuine
modelling difference between the graphs.

## The size gap is a result, not a defect

DBpedia's astronomy and chemistry coverage is orders of magnitude smaller than YAGO's
— `Galaxy` 1,984 vs 2,094,595 (≈1,000×), `Star` 5,019 vs 3,278,545 (≈650×),
`ChemicalCompound` 12,767 vs 1,114,868 (≈87×). YAGO 4.x imports Wikidata's structured
data, while DBpedia extracts Wikipedia infoboxes, and the domains where Wikidata is
systematically populated are exactly where the gap opens. Entropy over a
1,984-entity class is not statistically comparable to entropy over 2.09M entities, so
report the populations alongside every cross-KG entropy figure rather than the
entropies alone.

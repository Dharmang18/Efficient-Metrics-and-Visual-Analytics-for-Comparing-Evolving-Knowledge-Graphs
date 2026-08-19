# Final Metrics List

## Class-Level Analysis

### 1. Class population & share
Number of entities per class and its fraction of all entities. Across versions it
shows which classes grow or shrink over time.

### 2. Property entropy per type
Shannon entropy of a property's object-value distribution within a class: how varied
the values of a predicate are for entities of one type. High entropy means informative,
diverse values (name, birthDate); low entropy means near-constant values.

### 3. Entropy-weighted type importance
Combination of property entropy and type importance (weighted geometric mean).
Ranks the predicates that are both characteristic of a class and carry diverse
information.

### 4. Class entropy
Entropy of object values and predicates across all entities of a class — measures how
diverse and information-rich a class is as a whole.

---

## Entity-Level Analysis

### 5. Entity informativeness
Normalized count of an entity's datatype (literal) properties: "important things have
lots of information about them." A single aggregation, no iteration needed. Across
versions it shows entities gaining or losing informativeness.

### 6. Object diversity
Distinct-object counts per predicate within a class, and per entity. Captures how
varied the values connected to a class or entity are.

---

## Global Graph Analysis

### 7. Graph size & shape
Per snapshot: number of triples, entities, classes and predicates; graph density
(triples per entity); average in- and out-degree. Computed for every version and KG,
it becomes the growth table that makes all later comparisons interpretable.

### 8. Triple-level diff via integer-encoded sets
Added, deleted and changed triples between two versions of a KG, computed over
dictionary-encoded integer triples instead of string comparison. The efficient
comparison engine of the thesis, benchmarked on runtime and memory against a naive
baseline.

### 9. Metric trajectories
Every metric above computed per version and per KG, with deltas and trend views in
the dashboard. Turns each per-snapshot metric into an evolution metric and forms the
visual-analytics backbone of the thesis.

### 10. Vocabulary / schema evolution
Classes and predicates added, removed or deprecated per version, and how quickly new
terms are adopted. Derived from the triple-diff engine.

### 11. Class overlap & potential gain
Overlap of a class between two different KGs via sameAs/label linkage, and the
potential gain from merging them. Quantifies how complementary two KGs are per domain.

---

Metrics 10 and 11 are stretch goals, implemented if the timeline allows.

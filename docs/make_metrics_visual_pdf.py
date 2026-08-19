"""
Final metrics list -> illustrated PDF (reportlab only, no matplotlib).

Each metric gets: title, detailed explanation, and a small schematic diagram
drawn with reportlab canvas primitives.

Run:  python make_metrics_visual_pdf.py     -> writes metrics_final.pdf
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Flowable, KeepTogether, HRFlowable,
)

BLUE = colors.HexColor("#3b82f6")
GREEN = colors.HexColor("#10b981")
AMBER = colors.HexColor("#f59e0b")
RED = colors.HexColor("#ef4444")
GRAY = colors.HexColor("#6b7280")
LGRAY = colors.HexColor("#e5e7eb")
DARK = colors.HexColor("#111827")
PURPLE = colors.HexColor("#8b5cf6")


# ---------------------------------------------------------------- helpers
class Diagram(Flowable):
    """A fixed-size schematic; `key` picks the drawing routine."""

    def __init__(self, key, width=450, height=120):
        super().__init__()
        self.key = key
        self.width = width
        self.height = height

    # --- tiny drawing helpers -------------------------------------------
    def _t(self, x, y, s, size=7.5, color=DARK, center=False, bold=False):
        c = self.canv
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        (c.drawCentredString if center else c.drawString)(x, y, s)

    def _bar(self, x, y, w, h, color=BLUE):
        c = self.canv
        c.setFillColor(color)
        c.setStrokeColor(color)
        c.rect(x, y, w, h, stroke=0, fill=1)

    def _arrow(self, x1, y1, x2, y2, color=GRAY, w=1.2):
        c = self.canv
        c.setStrokeColor(color)
        c.setLineWidth(w)
        c.line(x1, y1, x2, y2)
        # arrow head: two short legs sweeping BACK from the tip
        import math
        ang = math.atan2(y2 - y1, x2 - x1)
        for da in (0.45, -0.45):
            c.line(x2, y2,
                   x2 - 7 * math.cos(ang + da), y2 - 7 * math.sin(ang + da))

    def _dot(self, x, y, r=3.2, color=BLUE):
        c = self.canv
        c.setFillColor(color)
        c.circle(x, y, r, stroke=0, fill=1)

    def _box(self, x, y, w, h, label_lines, fill=colors.HexColor("#eff6ff"),
             stroke=BLUE, size=7.5):
        c = self.canv
        c.setFillColor(fill)
        c.setStrokeColor(stroke)
        c.setLineWidth(1)
        c.roundRect(x, y, w, h, 4, stroke=1, fill=1)
        ty = y + h - 11
        for line in label_lines:
            self._t(x + w / 2, ty, line, center=True)
            ty -= 10

    def draw(self):
        getattr(self, "d_" + self.key)()

    # --- 1. class population --------------------------------------------
    def d_population(self):
        data = [("Person", 42, BLUE), ("CreativeWork", 27, GREEN),
                ("Place", 18, AMBER), ("all other classes", 13, GRAY)]
        y = self.height - 26
        self._t(0, self.height - 8, "Share of all entities per class (one snapshot):",
                size=8, bold=True)
        for name, pct, col in data:
            self._bar(95, y - 3, pct * 6.2, 9, col)
            self._t(0, y - 1, name, size=8)
            self._t(100 + pct * 6.2, y - 1, f"{pct} %", size=8, color=col)
            y -= 17
        self._t(0, y - 2, "Across versions: watch each class's share rise or fall.",
                size=7.5, color=GRAY)

    # --- 2. property entropy --------------------------------------------
    def d_entf(self):
        # left: high entropy, values evenly spread
        self._t(60, self.height - 8, "birthDate — values evenly spread", size=8,
                center=True, bold=True)
        for i, h in enumerate([22, 25, 21, 24, 23]):
            self._bar(20 + i * 18, 30, 12, h, BLUE)
        self._t(60, 16, "HIGH entropy = informative", size=8, center=True, color=BLUE)

        # right: low entropy, one dominant value
        self._t(300, self.height - 8, "gender — one dominant value", size=8,
                center=True, bold=True)
        for i, h in enumerate([64, 6, 4]):
            self._bar(270 + i * 18, 30, 12, h, AMBER)
        self._t(300, 16, "LOW entropy = near-constant", size=8, center=True, color=AMBER)

        self._t(430, 52, "same 5 values, very different", size=7.5, center=True, color=GRAY)
        self._t(430, 42, "information content", size=7.5, center=True, color=GRAY)

    # --- 3. entetimp ------------------------------------------------------
    def d_entetimp(self):
        self._box(5, 45, 130, 40, ["ETImp(p,t)", "is p characteristic", "of the class?"])
        self._box(160, 45, 130, 40, ["EntF(p,t)", "are p's values", "diverse?"],
                  fill=colors.HexColor("#fffbeb"), stroke=AMBER)
        self._t(147, 62, "×", size=14, center=True, bold=True)
        self._arrow(292, 65, 320, 65)
        self._box(322, 38, 128, 54, ["EntETImp ranking", "1. birthDate", "2. spouse",
                                     "3. birthPlace"], fill=colors.HexColor("#ecfdf5"),
                  stroke=GREEN)
        self._t(225, 20, "typical AND informative predicates rise to the top",
                size=8, center=True, color=GRAY)

    # --- 4. class entropy -------------------------------------------------
    def d_class_entropy(self):
        c = self.canv
        # left class: diverse dots
        c.setStrokeColor(BLUE); c.setLineWidth(1.2); c.setFillColor(colors.white)
        c.ellipse(20, 25, 180, 95, stroke=1, fill=0)
        import random
        random.seed(7)
        palette = [BLUE, GREEN, AMBER, RED, PURPLE]
        for i in range(14):
            self._dot(38 + random.random() * 125, 38 + random.random() * 44,
                      color=palette[i % 5])
        self._t(100, 10, "class A: varied predicates/objects — HIGH entropy",
                size=7.5, center=True, color=BLUE)

        # right class: uniform dots
        c.setStrokeColor(AMBER); c.setFillColor(colors.white)
        c.ellipse(260, 25, 420, 95, stroke=1, fill=0)
        for i in range(14):
            self._dot(276 + random.random() * 125, 38 + random.random() * 44,
                      color=AMBER)
        self._t(340, 10, "class B: everything looks the same — LOW entropy",
                size=7.5, center=True, color=AMBER)

    # --- 5. entity informativeness ---------------------------------------
    def d_inforank(self):
        # rich entity
        cx, cy = 90, 62
        for i, lab in enumerate(["name", "birthDate", "height", "spouse",
                                 "awards", "nationality"]):
            import math
            ang = i * math.pi / 3
            x2, y2 = cx + 62 * math.cos(ang), cy + 38 * math.sin(ang)
            self._arrow(cx, cy, x2, y2, color=LGRAY, w=1)
            self._t(x2, y2 + 3 if y2 > cy else y2 - 9, lab, size=6.5,
                    center=True, color=GRAY)
        self._dot(cx, cy, 11, BLUE)
        self._t(cx, cy - 3, "E1", size=8, center=True, color=colors.white, bold=True)
        self._t(cx, 3, "6 literal properties -> HIGH informativeness", size=7.5,
                center=True, color=BLUE)

        # sparse entity
        cx2 = 330
        for i, lab in enumerate(["name", "type"]):
            import math
            ang = i * math.pi - 0.6
            x2, y2 = cx2 + 62 * math.cos(ang), cy + 38 * math.sin(ang)
            self._arrow(cx2, cy, x2, y2, color=LGRAY, w=1)
            self._t(x2, y2 + 3 if y2 > cy else y2 - 9, lab, size=6.5,
                    center=True, color=GRAY)
        self._dot(cx2, cy, 11, AMBER)
        self._t(cx2, cy - 3, "E2", size=8, center=True, color=colors.white, bold=True)
        self._t(cx2, 3, "2 literal properties -> LOW informativeness", size=7.5,
                center=True, color=AMBER)

    # --- 6. object diversity ----------------------------------------------
    def d_objdiv(self):
        y = 65
        self._t(10, y + 25, "nationality", size=8.5, bold=True)
        self._arrow(70, y + 28, 120, y + 28)
        for i in range(9):
            self._dot(130 + i * 13, y + 28, 3, GREEN)
        self._t(255, y + 25, "… 195 distinct objects  -> DIVERSE", size=8, color=GREEN)

        self._t(10, y - 15, "gender", size=8.5, bold=True)
        self._arrow(70, y - 12, 120, y - 12)
        for i in range(3):
            self._dot(130 + i * 13, y - 12, 3, AMBER)
        self._t(180, y - 15, "3 distinct objects  -> NARROW", size=8, color=AMBER)

        self._t(10, 12, "count(DISTINCT object) per predicate, within a class or per entity",
                size=7.5, color=GRAY)

    # --- 7. pagerank ---------------------------------------------------------
    def d_pagerank(self):
        A, B, V = (80, 88), (80, 36), (250, 62)
        # thick edge: informative predicate transfers a lot of rank
        self._arrow(A[0] + 14, A[1] - 3, V[0] - 20, V[1] + 8, color=BLUE, w=3.2)
        self._t(160, 97, "birthDate", size=8, center=True, color=BLUE, bold=True)
        self._t(160, 87, "high entropy -> w ≈ 1.0", size=7, center=True, color=BLUE)
        # thin edge: uninformative predicate transfers little
        self._arrow(B[0] + 14, B[1] + 3, V[0] - 20, V[1] - 8, color=AMBER, w=0.7)
        self._t(160, 30, "gender", size=8, center=True, color=AMBER, bold=True)
        self._t(160, 20, "low entropy -> w ≈ 0.1", size=7, center=True, color=AMBER)
        for (x, y), r, col in [(A, 10, BLUE), (B, 10, AMBER), (V, 14, GREEN)]:
            self._dot(x, y, r, col)
        self._t(V[0], V[1] + 22, "receives rank mostly via", size=7, center=True,
                color=GRAY)
        self._t(V[0], 30, "informative links", size=7, center=True, color=GRAY)
        self._t(390, 68, "same power iteration,", size=7.5, center=True, color=GRAY)
        self._t(390, 56, "one extra weight w(p)", size=7.5, center=True, color=GRAY)
        self._t(390, 44, "per edge — from metric 2", size=7.5, center=True, color=GRAY)

    # --- 7. graph size ------------------------------------------------------
    def d_size(self):
        self._box(10, 30, 150, 70, ["YAGO 4 (2020)", "~2.0 B triples", "~64 M entities",
                                    "density 31.2"], )
        self._box(290, 30, 150, 70, ["YAGO 4.5 (2024)", "~2.5 B triples", "~50 M entities",
                                     "density 50.1"], fill=colors.HexColor("#ecfdf5"),
                  stroke=GREEN)
        self._arrow(165, 65, 285, 65, color=GRAY, w=1.5)
        self._t(225, 72, "Δ growth table", size=8, center=True, bold=True)
        self._t(225, 50, "+25 % triples, −22 % entities:", size=7.5, center=True, color=GRAY)
        self._t(225, 40, "fewer but denser entities", size=7.5, center=True, color=GRAY)
        self._t(225, 12, "(numbers illustrative)", size=6.5, center=True, color=LGRAY)

    # --- 8. triple diff -----------------------------------------------------
    def d_diff(self):
        c = self.canv
        c.setFillAlpha(0.45)
        c.setFillColor(BLUE); c.setStrokeColor(BLUE)
        c.roundRect(60, 35, 190, 70, 8, stroke=1, fill=1)
        c.setFillColor(GREEN); c.setStrokeColor(GREEN)
        c.roundRect(200, 35, 190, 70, 8, stroke=1, fill=1)
        c.setFillAlpha(1)
        self._t(105, 110, "version 1", size=8.5, center=True, bold=True, color=BLUE)
        self._t(345, 110, "version 2", size=8.5, center=True, bold=True, color=GREEN)
        self._t(125, 68, "DELETED", size=8, center=True, color=colors.white, bold=True)
        self._t(225, 68, "UNCHANGED", size=8, center=True, color=colors.white, bold=True)
        self._t(330, 68, "ADDED", size=8, center=True, color=colors.white, bold=True)
        self._t(225, 18, "each triple (s,p,o) becomes one integer ID -> the diff is a fast set",
                size=7.5, center=True, color=GRAY)
        self._t(225, 8, "operation over sorted integers, not slow string comparison",
                size=7.5, center=True, color=GRAY)

    # --- 9. trajectories ----------------------------------------------------
    def d_traj(self):
        ox, oy, w, h = 55, 30, 330, 75
        c = self.canv
        c.setStrokeColor(LGRAY); c.setLineWidth(1)
        c.line(ox, oy, ox + w, oy)          # x axis
        c.line(ox, oy, ox, oy + h)          # y axis
        for i, v in enumerate(["v2018", "v2020", "v2024"]):
            self._t(ox + 40 + i * 120, oy - 12, v, size=8, center=True)
        pts1 = [(ox + 40, oy + 18), (ox + 160, oy + 34), (ox + 280, oy + 62)]
        pts2 = [(ox + 40, oy + 46), (ox + 160, oy + 40), (ox + 280, oy + 30)]
        for pts, col in [(pts1, BLUE), (pts2, AMBER)]:
            c.setStrokeColor(col); c.setLineWidth(1.6)
            c.lines([(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
                     for i in range(len(pts) - 1)])
            for x, y in pts:
                self._dot(x, y, 3, col)
        self._t(ox + w + 8, oy + 58, "class entropy", size=7.5, color=BLUE)
        self._t(ox + w + 8, oy + 27, "graph density", size=7.5, color=AMBER)
        self._t(0, 5, "any per-snapshot metric, plotted over versions -> an evolution metric for free",
                size=7.5, color=GRAY)

    # --- 10. vocab evolution -------------------------------------------------
    def d_vocab(self):
        y = 45
        self._arrow(20, y, 440, y, color=GRAY, w=1.5)
        for x, v in [(60, "v1"), (230, "v2"), (400, "v3")]:
            self._dot(x, y, 4, DARK)
            self._t(x, y - 16, v, size=8.5, center=True, bold=True)
        self._t(145, y + 26, "+12 classes", size=8, center=True, color=GREEN)
        self._t(145, y + 14, "+3 predicates", size=8, center=True, color=GREEN)
        self._t(315, y + 26, "−2 classes deprecated", size=8, center=True, color=RED)
        self._t(315, y + 14, "+1 predicate", size=8, center=True, color=GREEN)

    # --- 9. churn --------------------------------------------------------------
    def d_churn(self):
        self._t(0, self.height - 10, "Where did the change happen? churn per class "
                "(v1 -> v2)", size=8, bold=True)
        rows = [("Taxon", 85, RED), ("Person", 22, BLUE), ("Country", 3, GREEN)]
        y = self.height - 32
        for name, pct, col in rows:
            self._t(0, y - 1, name, size=8)
            self._bar(60, y - 3, pct * 3.4, 9, col)
            self._t(66 + pct * 3.4, y - 1, f"{pct} %", size=8, color=col)
            y -= 19
        self._t(0, y + 2, "same global diff, very unevenly distributed — a few "
                "classes rewritten, the rest stable", size=7.5, color=GRAY)

    # --- 11. overlap -----------------------------------------------------------
    def d_overlap(self):
        self._t(0, self.height - 10, "Same class, two KGs: Person in YAGO vs DBpedia",
                size=8, bold=True)
        self._bar(300, self.height - 12, 10, 7, BLUE)
        self._t(314, self.height - 11, "YAGO", size=7.5)
        self._bar(355, self.height - 12, 10, 7, AMBER)
        self._t(369, self.height - 11, "DBpedia", size=7.5)
        rows = [("population", 150, 110, "+36 %"),
                ("class entropy", 120, 135, "−11 %"),
                ("PageRank", 95, 80, "+19 %")]
        y = self.height - 34
        for name, wa, wb, delta in rows:
            self._t(0, y - 1, name, size=8)
            self._bar(85, y + 1, wa, 7, BLUE)
            self._bar(85, y - 8, wb, 7, AMBER)
            self._t(95 + max(wa, wb), y - 4, "Δ " + delta, size=8, color=GRAY)
            y -= 26
        self._t(0, y + 4, "classes matched by name/label at the schema level — "
                "no instance-level sameAs linkage", size=7.5, color=GRAY)


# ---------------------------------------------------------------- content
METRICS = [
    ("Class-Level Analysis", None, None, None, None),
    ("1. Class population & share",
     "Counts the entities of every class and the fraction of the whole KG they "
     "represent. It answers the first question anyone asks of a snapshot — what is "
     "actually in this graph? — and, compared across versions, shows which classes "
     "grow, shrink or disappear over time.",
     "population", 110,
     "share(t) = |E<sub>t</sub>| / |E|<br/><font size='8.5' color='#6b7280'>|E<sub>t</sub>| = number of entities of class t, |E| = all entities</font>"),
    ("2. Property entropy per type",
     "For one class and one predicate, the Shannon entropy of the predicate's "
     "object-value distribution. If the values are spread evenly over many objects "
     "(birthDate: nearly every person has a different one) the entropy is high and "
     "the predicate carries real information. If one value dominates (gender) the "
     "entropy is low. Tracked across versions, it shows predicates becoming more or "
     "less informative as the KG fills up.",
     "entf", 108,
     "EntF(p, t) = − Σ<sub>o</sub> P(o) · log<sub>2</sub> P(o)<br/><font size='8.5' color='#6b7280'>P(o) = count of value o among all values of predicate p inside class t</font>"),
    ("3. Entropy-weighted type importance",
     "Multiplies two signals: how characteristic a predicate is for a class "
     "(the provided ETImp baseline) and how diverse its values are (metric 2), "
     "combined as a weighted geometric mean. The result ranks, per class, the "
     "predicates that are both typical and informative.",
     "entetimp", 98,
     "EntETImp(p, t) = EntF(p, t)<super>w</super> · ETImp(p, t)<super>1−w</super><br/><font size='8.5' color='#6b7280'>weighted geometric mean, w ≈ 0.75</font>"),
    ("4. Class entropy",
     "One entropy number for a whole class, over the object values and predicates of "
     "all its entities. It measures how diverse and information-rich the class is as "
     "a unit: a class whose entities all look alike scores low, a class with varied, "
     "detailed entities scores high. Its trajectory shows classes becoming richer or "
     "flatter between versions.",
     "class_entropy", 100,
     "H(t) = − Σ<sub>o</sub> P(o) · log<sub>2</sub> P(o)<br/><font size='8.5' color='#6b7280'>over all object values o of all entities of class t</font>"),
    ("Entity-Level Analysis", None, None, None, None),
    ("5. Entity informativeness",
     "The normalized count of an entity's datatype (literal) properties — the "
     "InfoRank idea that important things have lots of information recorded about "
     "them. It needs a single aggregation query, no iteration, and across versions "
     "it identifies entities that are being actively enriched versus abandoned.",
     "inforank", 112,
     "IR(v) = dtp(v) / Σ<sub>u</sub> dtp(u)<br/><font size='8.5' color='#6b7280'>dtp(v) = number of literal (datatype) properties of entity v</font>"),
    ("6. Object diversity",
     "The number of distinct objects each predicate points to, within a class or for "
     "a single entity. It separates predicates that fan out to many different values "
     "from predicates that reuse a handful, and complements the entropy metrics with "
     "a simple, exact count.",
     "objdiv", 98,
     "OD(p, t) = |{ o : (e, p, o) ∈ T and e ∈ E<sub>t</sub> }|<br/><font size='8.5' color='#6b7280'>number of distinct objects of predicate p within class t</font>"),
    ("7. Entropy-weighted PageRank — own variant",
     "PageRank with one change: rank flows preferentially through INFORMATIVE "
     "predicates. Every link is weighted by the property entropy of its predicate "
     "(metric 2), so an edge like birthDate — diverse, informative values — passes "
     "on more rank than a near-constant edge like gender. Knowgly's version weights "
     "links with InfoRank instead; using the per-type property entropy as the edge "
     "weight is this thesis's own, simpler variation, and it connects metric 2 "
     "directly into the importance ranking. Computed per version and per KG, the "
     "score of the same class or entity is then compared across snapshots — e.g. "
     "Person in YAGO 4 vs YAGO 4.5 vs DBpedia — revealing importance shifts over "
     "time and between graphs (classes matched across KGs by name/label, as in "
     "metric 13). Classic unweighted PageRank stays as the provided baseline.",
     "pagerank", 104,
     "PR(v) = (1 − d) + d · Σ<sub>u→v</sub> w(p<sub>uv</sub>) · PR(u) / outdeg(u)<br/><font size='8.5' color='#6b7280'>w(p) = EntF(p) / max<sub>q</sub> EntF(q) — the (normalized) property entropy of the predicate on the edge; d = 0.85</font>"),
    ("Global Graph Analysis", None, None, None, None),
    ("8. Graph size & shape",
     "The per-snapshot foundation table: triples, entities, classes, predicates, "
     "density (triples per entity) and average in-/out-degree. Computed for every "
     "version and every KG, its deltas form the growth table that makes all other "
     "comparisons interpretable.",
     "size", 106,
     "density = |T| / |E| ,&nbsp;&nbsp;&nbsp; avg. out-degree = |T| / |S|<br/><font size='8.5' color='#6b7280'>T = triples, E = entities, S = distinct subjects</font>"),
    ("9. Class-level change rate (churn)",
     "Localizes the change between two versions: for every class, the fraction of "
     "its triples that were added or deleted. It answers WHERE the KG evolved — "
     "whether a big diff means everything drifting slightly, or a few classes being "
     "rewritten while the rest stay stable. Computed by grouping the added and "
     "deleted triple sets of the triple-level diff (metric 10) by the subject's "
     "class, so it reuses the integer-encoded diff engine at almost no extra cost.",
     "churn", 92,
     "churn(t) = ( |A<sub>t</sub>| + |D<sub>t</sub>| ) / |T<sub>t</sub>(v<sub>1</sub>)|<br/><font size='8.5' color='#6b7280'>A<sub>t</sub>, D<sub>t</sub> = added / deleted triples of class t between v<sub>1</sub> and v<sub>2</sub>; T<sub>t</sub>(v<sub>1</sub>) = its triples in the older version</font>"),
    ("10. Triple-level diff via integer-encoded sets",
     "Computes the exact sets of added, deleted and unchanged triples between two "
     "versions. Every triple is first dictionary-encoded into integer IDs, so the "
     "comparison becomes a set operation over sorted integers instead of comparing "
     "strings — the efficiency contribution of the thesis, benchmarked on runtime "
     "and memory against a naive baseline.",
     "diff", 122,
     "Added = T<sub>2</sub> − T<sub>1</sub> ,&nbsp;&nbsp;&nbsp; Deleted = T<sub>1</sub> − T<sub>2</sub> ,&nbsp;&nbsp;&nbsp; Unchanged = T<sub>1</sub> ∩ T<sub>2</sub><br/><font size='8.5' color='#6b7280'>T<sub>1</sub>, T<sub>2</sub> = integer-encoded triple sets of the two versions</font>"),
    ("11. Metric trajectories",
     "The framework layer: every metric above is computed per version and per KG, "
     "and the dashboard plots the values as trajectories with deltas. This turns "
     "each per-snapshot metric into an evolution metric and is the visual-analytics "
     "backbone of the thesis.",
     "traj", 110,
     "Δm(v<sub>i</sub>) = m(v<sub>i+1</sub>) − m(v<sub>i</sub>)<br/><font size='8.5' color='#6b7280'>for every metric m and each pair of consecutive versions v<sub>i</sub>, v<sub>i+1</sub></font>"),
    ("12. Vocabulary / schema evolution  (additional)",
     "Which classes and predicates are added, removed or deprecated in each version, "
     "and how quickly new terms are actually adopted in the data. Derived almost for "
     "free from the triple-diff engine of metric 10.",
     "vocab", 82,
     "C<sub>added</sub> = C<sub>2</sub> − C<sub>1</sub> ,&nbsp;&nbsp;&nbsp; C<sub>removed</sub> = C<sub>1</sub> − C<sub>2</sub><br/><font size='8.5' color='#6b7280'>classes C of each version; the same for the predicate sets</font>"),
    ("13. Cross-KG class comparison  (additional)",
     "Takes one class that exists in two different KGs — Person in YAGO and in "
     "DBpedia — and puts its metric values side by side: population, property "
     "entropy, class entropy, PageRank. The classes are matched at the schema level "
     "(by name/label); overlapping the instances of two different KGs via sameAs "
     "links is impractical, so no union or merge-gain is estimated. The comparison "
     "shows how differently the two graphs model and populate the same concept.",
     "overlap", 114,
     "Δm(t) = m<sub>A</sub>(t) − m<sub>B</sub>(t) for every metric m<br/><font size='8.5' color='#6b7280'>same class t in the two KGs A, B — e.g. Person in YAGO vs DBpedia</font>"),
]


def build():
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=17, spaceAfter=10,
                        textColor=colors.HexColor("#1d4ed8"))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13, spaceBefore=14,
                        spaceAfter=4, textColor=DARK)
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10.5, spaceBefore=10,
                        spaceAfter=2, textColor=colors.HexColor("#374151"))
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9, leading=12.5,
                          spaceAfter=4)
    fstyle = ParagraphStyle("formula", parent=ss["BodyText"], fontSize=11,
                            leading=15, alignment=1, spaceBefore=3, spaceAfter=7,
                            backColor=colors.HexColor("#f3f4f6"),
                            borderPadding=(5, 7, 5, 7))

    story = [Paragraph("Final Metrics List", h1)]
    pending = []  # section heading is glued to its first metric (never stranded)
    for title, text, key, height, formula in METRICS:
        if text is None:  # section heading
            pending = [HRFlowable(width="100%", color=LGRAY, spaceBefore=10,
                                  spaceAfter=2),
                       Paragraph(title, h2)]
            continue
        block = pending + [Paragraph(title, h3), Paragraph(text, body),
                           Paragraph(formula, fstyle),
                           Diagram(key, height=height), Spacer(1, 6)]
        pending = []
        story.append(KeepTogether(block))

    doc = SimpleDocTemplate("metrics_final.pdf", pagesize=A4,
                            leftMargin=50, rightMargin=50,
                            topMargin=46, bottomMargin=46,
                            title="Final Metrics List")
    doc.build(story)
    print("wrote metrics_final.pdf")


if __name__ == "__main__":
    build()

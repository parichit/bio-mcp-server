"""
test_parser.py  —  Unit test for the PubMed XML parser, Day 2 (TEACHING EDITION)
================================================================================

The shortest file in the project, but it teaches the habit that scales into
next week's evaluation harness: KNOWN INPUT -> function -> ASSERT on output.

WHY THIS FILE EXISTS — separation of concerns:
  search_pubmed has two kinds of code that fail for different reasons.
    * Network code  — flaky, nondeterministic, needs NCBI to be reachable.
    * Parsing code  — deterministic, fragile, breaks on edge cases in the XML.
  You test them separately. The network you exercise live; the parser you test
  with a FIXTURE (a saved input string) so the test is fast, offline, and lets
  you manufacture edge cases on demand. You can't make NCBI return a malformed
  abstract when you want one — but you can type one into a fixture.

WHY THE PARSER IS A SEPARATE FUNCTION (file 1, Stage 6):
  So it can be imported and tested WITHOUT touching the network code. If parsing
  lived inside search_pubmed, you couldn't test it without a live API call.

HOW TO CHOOSE FIXTURE CASES — cover each branch of the parser:
  Read _parse_pubmed_xml and list what varies, then make one article per case.
    case 1: structured abstract (multiple <AbstractText Label=...>) + inline <i>
            markup in the title   -> tests the label-join AND .itertext() flattening
    case 2: a single UNLABELED abstract           -> tests the `else text` branch
    case 3: no <Abstract> element at all          -> tests the fallback string
  A fixture is not "some example data" — it is data chosen on purpose to hit
  every code path. That intentionality is what makes it a test, not a demo.
"""

# ── STAGE 1: import the unit under test (just the parser, not the whole tool) ──
from server import _parse_pubmed_xml


# ── STAGE 2: the fixture — one article per parser branch ──────────────────────
# This mirrors the real shape of an NCBI efetch (rettype=abstract, retmode=xml)
# response, trimmed to the elements the parser reads.
SAMPLE = """<?xml version="1.0"?>
<PubmedArticleSet>

  <!-- case 1: structured abstract (two labeled sections) + <i> inside the title -->
  <PubmedArticle><MedlineCitation><PMID>29144463</PMID><Article>
    <ArticleTitle>Variants in <i>BRCA1</i> and risk.</ArticleTitle>
    <Abstract>
      <AbstractText Label="BACKGROUND">Beta cells are heterogeneous.</AbstractText>
      <AbstractText Label="RESULTS">We identified four subpopulations.</AbstractText>
    </Abstract>
  </Article></MedlineCitation></PubmedArticle>

  <!-- case 2: a single abstract with NO Label attribute -->
  <PubmedArticle><MedlineCitation><PMID>30000002</PMID><Article>
    <ArticleTitle>A plain unstructured abstract.</ArticleTitle>
    <Abstract><AbstractText>One block of text, no labels.</AbstractText></Abstract>
  </Article></MedlineCitation></PubmedArticle>

  <!-- case 3: no Abstract element at all -->
  <PubmedArticle><MedlineCitation><PMID>30000003</PMID><Article>
    <ArticleTitle>A paper with no abstract.</ArticleTitle>
  </Article></MedlineCitation></PubmedArticle>

</PubmedArticleSet>"""


# ── STAGE 3: run the parser on the fixture ────────────────────────────────────
arts = _parse_pubmed_xml(SAMPLE)


# ── STAGE 4: assert per case — each assert pins ONE behavior ──────────────────
# When one fails, the failure points straight at the branch that broke, so the
# message of a good test is "exactly what went wrong", not "something went wrong".
assert len(arts) == 3, f"expected 3 articles, got {len(arts)}"

# case 1 — structured abstract: labels kept and sections joined in order
assert arts[0].pmid == "29144463"
assert arts[0].abstract.startswith("BACKGROUND:")
assert "RESULTS:" in arts[0].abstract
# case 1 — title: .itertext() flattened the inline <i> tag into plain text
assert arts[0].title == "Variants in BRCA1 and risk.", arts[0].title
# case 1 — url built from the pmid
assert arts[0].url == "https://pubmed.ncbi.nlm.nih.gov/29144463/"

# case 2 — unlabeled abstract: no "Label:" prefix, just the raw text
assert arts[1].abstract == "One block of text, no labels."

# case 3 — missing abstract: the graceful fallback string, not a crash
assert arts[2].abstract == "(no abstract available)"


# ── STAGE 5: a clear pass signal ──────────────────────────────────────────────
print("✅ All parser branches covered:")
print("   - structured (labeled) abstract joined")
print("   - inline markup flattened in title")
print("   - unlabeled abstract passed through")
print("   - missing abstract -> fallback string")
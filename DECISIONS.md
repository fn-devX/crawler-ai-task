# Judgment calls & assumptions

The brief is intentionally open in places. These are the decisions I made where it
was ambiguous, and why.

- **People-only graph.** "People" is taken literally: companies and products
  (OpenAI, ChatGPT, Grok) are *not* nodes, even though they appear in explanations
  and tags. Edges connect two people only. This keeps the graph coherent; an
  `entity_type` column could relax it later.

- **Authors are people and get edges.** Article authors become nodes with role
  `author` and a `reports_on` edge to the people they write about, matching the
  brief's `Author —reports critically on→ Musk` example.

- **Open relationship vocabulary.** The LLM picks short snake_case verb phrases
  (`criticizes`, `partners_with`, …) instead of a fixed enum — real coverage beats
  a rigid taxonomy. Labels are normalized (`"partners with"` → `partners_with`) so
  they merge cleanly. The eval's *untyped* metric exists precisely because this
  vocabulary is open.

- **Provenance = verbatim sentence + article URL/title.** Stored per evidence row,
  so one edge can accumulate support from several articles instead of duplicating.

- **Entity resolution kept simple (as asked).** Normalize a name (lowercase, strip
  honorifics/possessives/punctuation), then match by full name, alias, or an
  *unambiguous* last name — so "Sam Altman" / "Altman" / "OpenAI's CEO" collapse to
  one node, while an ambiguous bare surname (two different "Page"s) is not merged.
  No embeddings or coreference; that would be over-engineering for two pages.

- **Idempotent merges over a rebuild.** `/rescan` reconciles into the existing graph
  (no duplicate people/edges) rather than rebuilding, so it's safe to run repeatedly.

- **SQLite over a graph DB.** Zero-setup and inspectable; the node/edge/evidence
  shape models the graph fine at this scale. The store sits behind an interface, so
  swapping in a real graph DB only touches one module.

- **Resilient crawling.** A configurable per-request delay and a descriptive
  User-Agent; one failing article is recorded in the response `errors` and does not
  abort a rescan. The LLM occasionally returns a field as a JSON string instead of a
  list — that's coerced before validation rather than dropping the article.


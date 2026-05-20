# Check 05 — Wikidata entity graph and Person sameAs reciprocity

## Why this matters

Wikidata is the canonical entity hub feeding Google Knowledge Graph,
Apple Spotlight, Bing/Copilot, and (increasingly) Claude/ChatGPT/Perplexity
entity disambiguation. An author with a Wikidata Q-ID can appear in
Google Knowledge Panels *without* a Wikipedia article in 2026, gated on:

- The Wikidata entry has key structured-data properties populated
- The Person.sameAs in the site's JSON-LD references the Q-ID
- Reciprocal claim: Wikidata's P856 (official website) points back at
  the apex domain
- Bonus: LinkedIn/GitHub/Crunchbase "Website" fields also point at apex
  (operator-side; not enforced here)

The reciprocity edge is what triangulates entity-graph claims. Wikidata
P856 → apex is the single highest-leverage move because it's the canonical
structured claim Google + Bing + LLM systems trust as authoritative.

**Why entity-hub presence matters disproportionately (cross-reference).**
Nature Communications 2025 found that fewer than 10 distinct URLs appear
in 80% of LLM responses to a given query — citation concentration is
narrow. Entity-hub presence (Wikipedia, Wikidata, top-tier hubs in check
5.5) and authoritative backlinks (check 10) matter disproportionately
because once a site enters the top-cited set for a query, it locks in.
Conversely, sites absent from the top hubs almost never break into the
cited set, regardless of content quality. This shapes the strategic
calculus: hub presence is a discrete eligibility threshold, not a
continuous quality dial.

**Cited sources:** Wikidata:Schema.org (https://www.wikidata.org/wiki/Wikidata:Schema.org);
"How to Get a Knowledge Panel" 2026; momenticmarketing — @id in Schema.org for SEO/LLMs.

## What's checked

### 5.1 — Person.sameAs in JSON-LD

| Assertion | Pass | Fail |
|---|---|---|
| Person.sameAs contains Wikidata URL | yes | no |
| Wikidata URL format: `https://www.wikidata.org/wiki/Q<NNNN>` | yes | bare Q-ID or wrong format |
| Other sameAs entries (LinkedIn/GitHub/Crunchbase/X) | optional | — |

### 5.2 — Wikidata Q-ID validity

Requires `wikidata_qid` set in `<repo>/.launch-readiness.yml`.

| Assertion | Pass | Fail |
|---|---|---|
| Q-ID exists and is accessible | yes | 404 |
| Q-ID is `instance of: human` (P31 → Q5) | yes | wrong type |
| Q-ID has `given name` (P735) | yes | no |
| Q-ID has `family name` (P734) | yes | no |
| Q-ID has `occupation` (P106) | yes | no |
| Q-ID has `field of work` (P101) | yes | no |
| Q-ID has `country of citizenship` (P27) | yes | no |
| Q-ID has `sex or gender` (P21) | yes | no |
| Q-ID has `position held` (P39) | yes | no |

### 5.3 — Wikidata P856 reciprocity

The load-bearing edge.

| Assertion | Pass | Fail |
|---|---|---|
| Wikidata Q-ID has P856 (official website) | yes | no |
| P856 value matches `canonical_origin` in config | yes | mismatch / missing |

### 5.4 — JSON-LD Person.@id format

| Assertion | Pass | Fail |
|---|---|---|
| Person.@id is absolute URL (e.g., `https://example.com/#person`) | yes | fragment-only |
| Same @id used consistently across all pages | yes | drift |

## How to fix

### Fix 5.1 — Add Wikidata URL to sameAs

In Person entity JSON-LD:

```json
{
  "@type": "Person",
  "@id": "https://example.com/#person",
  "sameAs": [
    "https://www.wikidata.org/wiki/Q139721032",
    "https://www.linkedin.com/in/author",
    "https://github.com/author",
    ...
  ]
}
```

Use the FULL Wikidata URL, not the bare Q-ID. Google's entity resolver
prefers URL form.

**Auto-fix safety: safe** if `wikidata_qid` is in config; **manual**
otherwise.

### Fix 5.2 — Populate Wikidata properties

This is an operator-side action; cannot be auto-fixed. The operator logs
into Wikidata and edits the Q-ID entry.

Required properties for entity recognition:
- P31 = Q5 (instance of: human) — required for Person
- P735 (given name) — link to Wikidata item for given name
- P734 (family name) — link to Wikidata item for family name
- P106 (occupation) — at least one occupation item (Q937857 = entrepreneur, Q15978655 = software developer, etc.)
- P101 (field of work) — link to fields (Q11660 = AI, Q11190 = healthcare, Q170790 = tourism)
- P27 (country of citizenship)
- P21 (sex or gender)
- P39 (position held) — current and past roles

Optional but high-signal:
- P69 (educated at) — university links
- P166 (award received)
- P800 (notable work) — link to notable pieces or companies

**Auto-fix safety: manual** (operator action on wikidata.org).

### Fix 5.3 — Set P856 (the load-bearing fix)

On the Wikidata Q-ID page, add property:
- P856 (official website) → value: `https://thomasjankowski.com`
  (or the project's apex)

This is the single highest-leverage step. After this is set, Knowledge
Panel eligibility opens, and Google + Bing + LLM entity resolvers can
verify the site-Person binding via the reciprocal claim.

**Auto-fix safety: manual** (operator action; not API-driven).

### Fix 5.4 — Absolute Person.@id

Convert any `@id: "#person"` to `@id: "https://example.com/#person"` in
the schema emitter. Affects every page's JSON-LD. Covered by check 02
fix 2.3.

**Auto-fix safety: safe** (mechanical replacement).

## Failure ratings

- **FAIL:** Wikidata URL missing from sameAs, Q-ID 404, P856 not set, @id fragment-only.
- **WARN:** Q-ID has <5 of the 8 properties in 5.2.
- **PASS:** all assertions hold.

## Cited research

- [Wikidata for SEO (2026)](https://www.reputationx.com/blog/wikidata)
- [How to Get a Knowledge Panel (2026)](https://www.panstag.com/2026/04/how-to-get-knowledge-panel-google.html)
- [Wikipedia & Wikidata for Knowledge Graph (2026)](https://www.stackmatix.com/blog/wikipedia-wikidata-knowledge-graph)
- [Wikidata P856 property talk](https://www.wikidata.org/wiki/Property_talk:P856)
- [Using @id in Schema.org for SEO / LLMs / Knowledge Graphs](https://momenticmarketing.com/blog/id-schema-for-seo-llms-knowledge-graphs)

## Implementation notes

The script `scripts/check-wikidata.py`:
1. Reads `wikidata_qid` and `canonical_origin` from `.launch-readiness.yml`
2. Fetches the Q-ID via the Wikidata API (`https://www.wikidata.org/wiki/Special:EntityData/Q<N>.json`)
3. Inventories present properties
4. Reports the gap list

The fix for P856 is operator-side; the script generates a step-by-step
"go to Wikidata, edit this property" instruction with the canonical URL
pre-filled.

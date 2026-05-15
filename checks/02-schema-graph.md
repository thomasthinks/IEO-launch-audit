# Check 02 — Schema.org graph completeness and validity

## Why this matters

JSON-LD structured data is the single highest-leverage IEO surface in 2026.
Google publicly confirmed (April 2025, AI Overviews documentation) that
Schema.org markup informs entity disambiguation and AI-answer attribution.
Bing's Fabrice Canel (SMX Munich, March 2025) confirmed similar for Bing
Chat / Copilot. Anthropic's crawler documentation references structured
data as a citation-class signal.

The peer-reviewed evidence is softer: a December 2024 study found no
statistically significant correlation between schema *coverage* and LLM
citation *frequency*. But the consensus across vendor confirmations is
that schema increases citation *accuracy* (when cited, cited correctly),
which is what an editorial site wants — Person-entity disambiguation,
correct topic attribution, accurate cross-reference threading.

The failure mode: a partial or fragmented graph where Person fragments
don't unify across pages, Article entities aren't linked to a WebSite
root, or @ids use fragment-only references that crawlers can't resolve
into a unified entity model.

**Cited sources:** Schema.org Validator (validator.schema.org); Google
Rich Results Test (search.google.com/test/rich-results); momenticmarketing
"Using @id in Schema.org Markup for SEO, LLMs, & Knowledge Graphs";
schema.org/SpeakableSpecification; W3C JSON-LD Best Practices.

## What's checked

For each page emitting JSON-LD:

### 2.1 — Validation

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| JSON-LD parses as valid JSON | — | — | parse error |
| Validates against Schema.org Validator (no errors) | clean | warnings | errors |
| Validates against Google Rich Results Test | eligible | partial eligibility | ineligible |

### 2.2 — Graph topology

| Assertion | Pass | Fail |
|---|---|---|
| WebSite root entity exists at `{origin}/#website` | exists | missing |
| Every Article has `isPartOf` chain resolving to WebSite | yes | breaks |
| Every Person `@id` is absolute URL (not fragment-only) | absolute | fragment |
| Every CollectionPage `@id` is absolute URL | absolute | fragment |
| Per-page WebPage node exists wrapping the Article | yes | missing |

### 2.3 — Person entity completeness

Person should have: `@id` (absolute), `@type`, `name`, `url`, `description`,
`jobTitle`, `hasOccupation` (Occupation object), `knowsAbout`, `sameAs`
(array), `mainEntityOfPage` (refs ProfilePage), `image` (refs ImageObject).

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| Person has all 11 properties | yes | 9-10 present | <9 present |
| `sameAs` includes Wikidata URL (not just LinkedIn/GitHub/etc.) | yes | — | no |
| `mainEntityOfPage` references a ProfilePage @id | yes | — | no |

### 2.4 — Article entity completeness

Article should have: `@type` (any of 15 subtypes covered by offline
rules as of v1.1: `Article`, `NewsArticle`, `BlogPosting`,
`ScholarlyArticle`, `TechArticle`, `Report`,
`AdvertiserContentArticle`, `OpinionNewsArticle`, `SatiricalArticle`,
`BackgroundNewsArticle`, `AnalysisNewsArticle`,
`AskPublicNewsArticle`, `ReportageNewsArticle`, `ReviewNewsArticle`,
`SocialMediaPosting`, `DiscussionForumPosting` — all inherit Article's
required-property set per Schema.org's hierarchy), `@id`
(absolute), `url`, `headline`, `description`, `datePublished`,
`dateModified`, `author` (refs Person @id), `inLanguage`, `wordCount`,
`articleSection` (string pillar), `keywords`, `mentions` (array of @id
refs), `isPartOf` (refs CollectionPage @id + WebSite @id),
`about` (refs DefinedTerm), `publisher` (refs Person @id),
`copyrightHolder` (refs Person @id), `copyrightYear`, `speakable`
(SpeakableSpecification with `cssSelector` array), `image` (refs
ImageObject).

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| Article has all required properties | yes | 1-2 missing | 3+ missing |
| `about` references DefinedTerm with sameAs to Wikipedia/Wikidata | yes | DefinedTerm without sameAs | no `about` |
| `mentions[]` entries are @id refs (not inline objects) | refs | inline | empty |
| Speakable `cssSelector` is array of multiple selectors | array | single | missing |
| `image` refs an ImageObject (not just a URL string) | object | URL string | missing |
| **CiTO typed-citation coverage** (≥80% of `citation[]` entries carry a `[groundedBy]` / `[extendedBy]` / `[substantiatedBy]` / `[contradictedBy]` / `[discussedIn]` marker in description) — *v1.1, gated by `cito_enabled: true` (default); opt out for vanilla schema.org* | ≥80% | <80% | — |
| **Speakable passage word-count band** (resolved selector text lands in 100-300 words, matching modal AI Overview output) — *v1.1, INFO severity; single-source empirical (xSeek 1M-query AIO dataset 2024)* | inside band | outside band → INFO | — |

### 2.5 — ImageObject for hero images

Each piece's hero image should be an ImageObject with `@id`, `url`,
`contentUrl` (CDN URL distinct from canonical), `width`, `height`,
`caption`, `creditText`, `creator` (refs Person @id), `copyrightNotice`.

| Assertion | Pass | Fail |
|---|---|---|
| ImageObject emitted for each piece's hero | yes | no |
| Has width + height | yes | no |
| Has creditText + creator + copyrightNotice | yes | partial/no |

### 2.6 — CollectionPage → ItemList

CollectionPage for each pillar should nest `mainEntity` → `ItemList` with
`numberOfItems` + `itemListElement` of `ListItem` (position, url, name).

| Assertion | Pass | Fail |
|---|---|---|
| CollectionPage emitted per pillar | yes | no |
| Each CollectionPage has `mainEntity` → ItemList | yes | no |
| ItemList has `numberOfItems` + `itemListElement[]` | yes | no |

### 2.7 — ProfilePage completeness

ProfilePage at `/about#profilepage` should have `mainEntity` → Person,
`isPartOf` → WebSite, `breadcrumb`, `dateCreated`, `dateModified`,
`lastReviewed`, `hasPart` (array of Article @id refs to every piece by
this Person).

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| ProfilePage entity exists | yes | — | no |
| Has all 7 properties | yes | 5-6 | <5 |
| `hasPart` references all author's pieces | all | partial | missing |

## How to fix

### Fix 2.1 — Validation errors

Run the page's JSON-LD through:
- https://validator.schema.org/
- https://search.google.com/test/rich-results

Address each error specifically. Common issues: malformed dates (use
ISO 8601), `image` as plain URL when ImageObject expected, `author` as
string when Person object expected.

**Auto-fix safety: manual** (each error is case-specific).

### Fix 2.2 — Add WebSite root entity

In your schema emitter, prepend the WebSite entity to every page's graph:

```javascript
{
  "@type": "WebSite",
  "@id": "https://example.com/#website",
  "url": "https://example.com",
  "name": "Site Name",
  "inLanguage": "en",
  "publisher": {"@id": "https://example.com/#person"},
  "copyrightHolder": {"@id": "https://example.com/#person"},
  "copyrightYear": 2026
}
```

Then every WebPage / Article / CollectionPage's `isPartOf` references
this `@id`.

**Auto-fix safety: manual** (touches the schema emitter; semantic
change).

### Fix 2.3 — Convert @ids from fragment to absolute

Change every:
```json
"@id": "#person"
```
to:
```json
"@id": "https://example.com/#person"
```

Across Person, WebSite, Article, ProfilePage, CollectionPage,
BreadcrumbList, ImageObject. Fragment-only @ids resolve to the
current page; absolute URLs let crawlers unify the entity across all
pages.

**Auto-fix safety: safe** (mechanical string replacement on @id values
emitted by the schema emitter).

### Fix 2.4 — Add Person properties

Add to the Person entity:

```json
{
  "hasOccupation": {
    "@type": "Occupation",
    "name": "Chief Executive Officer",
    "skills": ["applied AI", "healthcare technology", "travel technology"]
  },
  "mainEntityOfPage": {"@id": "https://example.com/about#profilepage"},
  "image": {"@id": "https://example.com/about#image"}
}
```

`hasOccupation` should reflect actual role, not a brag. Skills should
match the `knowsAbout` array.

**Auto-fix safety: manual** (semantic content, operator must verify
values).

### Fix 2.5 — Add `about` as DefinedTerm with sameAs

In each Article, add:

```json
"about": [
  {
    "@type": "DefinedTerm",
    "name": "Artificial intelligence",
    "sameAs": [
      "https://en.wikipedia.org/wiki/Artificial_intelligence",
      "https://www.wikidata.org/wiki/Q11660"
    ]
  }
]
```

Map pillar concepts to their Wikipedia + Wikidata equivalents. Highest
single LLM-citation upgrade after Person sameAs.

**Auto-fix safety: manual** (concept-mapping requires operator
judgment; not all pillar concepts have clean Wikipedia equivalents).

### Fix 2.6 — Add ImageObject for hero images

For each piece's hero, emit:

```json
{
  "@type": "ImageObject",
  "@id": "https://example.com/writing/slug#hero-image",
  "url": "https://example.com/assets/slug-hero.avif",
  "contentUrl": "https://cdn.example.com/.../slug-hero.avif",
  "width": 1920,
  "height": 1080,
  "caption": "Hero descriptor",
  "creditText": "Thomas Jankowski, aided by AI",
  "creator": {"@id": "https://example.com/#person"},
  "copyrightNotice": "© 2026 Thomas Jankowski"
}
```

Article's `image` references this `@id`.

**Auto-fix safety: safe** (can derive from existing hero_image
frontmatter + ImageObject template).

### Fix 2.7 — Nest CollectionPage with ItemList

For each pillar CollectionPage:

```json
{
  "@type": "CollectionPage",
  "@id": "https://example.com/writing/pillar/ai#collection",
  "url": "https://example.com/writing/pillar/ai",
  "name": "AI pillar",
  "isPartOf": {"@id": "https://example.com/#website"},
  "mainEntity": {
    "@type": "ItemList",
    "numberOfItems": 104,
    "itemListElement": [
      {"@type": "ListItem", "position": 1, "url": "...", "name": "Title 1"},
      {"@type": "ListItem", "position": 2, "url": "...", "name": "Title 2"}
    ]
  }
}
```

**Auto-fix safety: safe** (mechanical — list comes from existing piece
data filtered by pillar).

### Fix 2.8 — Expand ProfilePage

```json
{
  "@type": "ProfilePage",
  "@id": "https://example.com/about#profilepage",
  "url": "https://example.com/about",
  "mainEntity": {"@id": "https://example.com/#person"},
  "isPartOf": {"@id": "https://example.com/#website"},
  "breadcrumb": {"@id": "https://example.com/about#breadcrumb"},
  "dateCreated": "2024-01-08",
  "dateModified": "2026-05-14",
  "lastReviewed": "2026-05-14",
  "hasPart": [
    {"@id": "https://example.com/writing/piece-1#article"},
    {"@id": "https://example.com/writing/piece-2#article"}
  ]
}
```

`hasPart` should reference every Article authored by the Person. Closes
the bidirectional Person ↔ Article loop.

**Auto-fix safety: safe** (mechanical from existing piece data).

### Fix 2.9 — Speakable as selector array

Change:
```json
"speakable": {
  "@type": "SpeakableSpecification",
  "cssSelector": ["[data-thesis-block]"]
}
```
to:
```json
"speakable": {
  "@type": "SpeakableSpecification",
  "cssSelector": ["[data-thesis-block]", "h1", "[data-pull-quote]"]
}
```

Multiple shallow selectors are more resilient than one deep XPath for LLM
extraction.

**Auto-fix safety: safe** (template change in schema emitter).

## Failure ratings

- **FAIL (must fix before flip):** validation errors, missing WebSite
  root, fragment-only @ids, missing Speakable.
- **WARN (should fix before flip):** missing ImageObject, missing
  CollectionPage→ItemList, Person properties <9, Article missing 1-2
  properties.
- **PASS:** all assertions hold.

## Cited research

- [Schema Markup After March 2026: Structured Data Update](https://www.digitalapplied.com/blog/schema-markup-after-march-2026-structured-data-strategies)
- [Schema Markup in 2026: Why It's Now Critical for SERP Visibility](https://almcorp.com/blog/schema-markup-detailed-guide-2026-serp-visibility/)
- [Schema.org markup for AI citations: what matters in 2026](https://www.soar.sh/blog/schema-markup-ai-citations-2026)
- [Using @id in Schema.org Markup for SEO, LLMs, & Knowledge Graphs](https://momenticmarketing.com/blog/id-schema-for-seo-llms-knowledge-graphs)
- [JSON-LD Best Practices (W3C)](https://w3c.github.io/json-ld-bp/)
- [Google Speakable Schema Markup docs](https://developers.google.com/search/docs/appearance/structured-data/speakable)
- [schema.org SpeakableSpecification](https://schema.org/SpeakableSpecification)
- [Google ProfilePage Schema Markup docs](https://developers.google.com/search/docs/appearance/structured-data/profile-page)
- [Google Updates Image Structured Data (creditText, creator, copyrightNotice)](https://www.searchenginejournal.com/google-updates-image-structured-data/467786/)
- [schema.org hasOccupation](https://schema.org/hasOccupation)
- [Wikidata:Schema.org](https://www.wikidata.org/wiki/Wikidata:Schema.org)

## Implementation notes

The script `scripts/check-schema.py` performs the structural validation
(2.2-2.8). The semantic validation (2.1) requires either an internet call
to validator.schema.org or a local schema-validator dependency
(`@schema-org-validator/cli` if available); the script attempts both.

Auto-fixable items (safe-fix tagged) are stored in `templates/`. The
auto-fix loop reads the current schema emitter, identifies the gap, and
applies the template. Schema-emitter source is detected via grep
patterns in `scripts/check-schema.py`.

### 2.9 — Offline curated-rules coverage

Check 2.9 (driven by `references/schema-org-rules.json`) validates
required-property + property-value-type + deprecated-property rules
against the following types. Anything outside this set falls through
to the optional web-validator fallback (2.10).

| Type | Required props (offline rule) |
|---|---|
| `Article` (+ `NewsArticle`, `BlogPosting`, `ScholarlyArticle`, `TechArticle`, `Report`) | `@type`, `@id`, `headline`, `datePublished`, `author` |
| `Person` | `@type`, `@id`, `name` |
| `Organization` | `@type`, `@id`, `name`, `url` |
| `WebSite` | `@type`, `@id`, `url` |
| `WebPage` | `@type`, `@id`, `name`, `url` |
| `BreadcrumbList` | `@type`, `itemListElement` |
| `CollectionPage` | `@type`, `@id`, `name`, `url`, `mainEntity` |
| `ProfilePage` | `@type`, `@id`, `name`, `url`, `mainEntity` |
| `ImageObject` | `@type`, `url` |
| `ItemList` | `@type`, `itemListElement` |
| `ListItem` | `@type`, `position`, `name`, `item` |
| `DefinedTerm` | `@type`, `name`, `sameAs` |
| `SpeakableSpecification` | `@type` |
| `Occupation` | `@type`, `name` |

A node's `@type` may be a string OR an array of strings (Schema.org
multi-typing); the check matches against every value. A node with
`@type: ["X", "Y"]` is validated against both X's rules and Y's rules
if both are in the table.

The `_web_validator.should_be_covered_offline` field in the rules
JSON tracks the next types worth promoting from the fallback (network)
to the offline catalog.

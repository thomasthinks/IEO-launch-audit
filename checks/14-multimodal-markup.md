# Check 14 — Multimodal markup (figcaption + alt-text + HTML tables)

## Why this matters

LLM citation engines parse rendered HTML, not hidden metadata.

- **SearchVIU 2025** built test pages with prices in JSON-LD, Microdata,
  RDFa, and visible HTML separately. Across 5 systems (ChatGPT, Claude,
  Gemini, Perplexity, Google AI Mode), only visible HTML was extracted
  at retrieval time. Hidden surfaces were ignored.
- **Williams-Cook "Duck Test" (Feb 2026)** built a "Ducky T-shirts" page
  with a fabricated address in JSON-LD only — no visible text. Both
  ChatGPT and Perplexity returned the fake address verbatim. Evidence
  that LLMs scrape the raw JSON-LD as text, not as structured data;
  visible HTML wins as load-bearing context.
- **Aleyda Solís AI-search checklist (2026)** specifies multimodal
  markup — `<figcaption>` on content images + HTML tables for tabular
  data — as a practitioner-tier GEO recommendation.

The implication: image semantics belong in `<figcaption>` and `alt=`,
not in JSON-LD `ImageObject.description`. Tabular data belongs in
`<table>`, not in screenshots. Both are LLM-extractable surfaces; the
JSON-LD / screenshot equivalents are not.

**Cited sources:**
- [SearchVIU schema-vs-visible-text experiment 2025](https://www.searchviu.com/en/schema-markup-and-ai-in-2025-what-chatgpt-claude-perplexity-gemini-really-see/)
- [Williams-Cook Duck Test (Feb 2026, YouTube)](https://www.youtube.com/watch?v=-nTqaG3GKLk)
- [Aleyda Solís AI-search optimization checklist](https://www.aleydasolis.com/en/ai-search/ai-search-optimization-checklist/)

**Source tier:** practitioner-consensus + indirect-methodology alignment.
The two methodology-disclosed studies (SearchVIU + Williams-Cook) measure
the upstream principle ("visible HTML wins") but do not measure
figcaption / table deltas directly. Findings default to **INFO / PASS**;
**WARN** fires only when density is unambiguously sparse on a page with
≥3 content images. See `docs/decisions/0001-claim-verification.md` for
why this check intentionally avoids precise lift claims.

## What's checked

This check is **opt-in** via `.launch-readiness.yml`:

```yaml
multimodal_markup_check: true   # opt-in
```

When unset, the check emits one INFO finding (`14.skipped`) and returns.
No false alarms on sites that haven't opted in.

When opted-in, the check:

1. Walks build-output HTML root (`dist/public` / `out` / `_site` /
   `public` / `build`).
2. Samples up to 10 pages: home + `/about` + piece pages from common
   roots (`writing/`, `blog/`, `posts/`, `articles/`).
3. For each page:
   - Restricts content scope to `<main>` or `<article>` when present.
     Falls back to whole-document scan + flags the caveat.
   - Counts `<img>` tags in content scope.
   - Counts `<img>` tags with non-empty `alt=` (empty `alt=""` counts as
     present — that's decorative-image semantics, not a missing attribute).
   - Counts `<figure>` blocks containing `<figcaption>`.
   - Counts `<table>` tags (excluding nav/header/footer regions).

### Findings

| Finding | Severity | Trigger |
|---|---|---|
| `14.skipped` | INFO | `multimodal_markup_check` not set |
| `14.figcaption_dense` | PASS | ≥70% of content imgs in `<figure>`/`<figcaption>` |
| `14.figcaption_partial` | INFO | 30-70% figcaption density |
| `14.figcaption_sparse` | WARN | <30% figcaption density AND ≥3 content imgs |
| `14.alt_text_dense` | PASS | ≥90% of content imgs carry `alt=` |
| `14.alt_text_partial` | INFO | 70-90% alt-text coverage |
| `14.alt_text_sparse` | WARN | <70% alt-text AND ≥3 content imgs |
| `14.tables_present` | INFO | ≥1 `<table>` detected (informational) |
| `14.no_tables_image_heavy` | INFO | 0 tables but ≥5 content images (possible screenshots-of-data) |
| `14.no_content_images` | INFO | 0 `<img>` in content scope |
| `14.no_content_scope` | INFO | no `<main>`/`<article>` on any sampled page |
| `14.no_build` / `14.no_pages` / `14.no_readable_pages` | MANUAL_VERIFY | sampling preconditions failed |

## How to fix

### Fix 14.figcaption_sparse — wrap content images

Replace:

```html
<img src="/img/hero.jpg" alt="System diagram of the agent stack">
```

With:

```html
<figure>
  <img src="/img/hero.jpg" alt="System diagram of the agent stack">
  <figcaption>
    The agent stack as of May 2026: planner, executor, and memory
    layers with their respective API surfaces.
  </figcaption>
</figure>
```

The figcaption binds visual context to the image as visible DOM text —
the load-bearing surface for LLM extraction. Avoid empty captions or
captions that just duplicate the `alt=` value.

### Fix 14.alt_text_sparse — add alt= to every content image

```html
<img src="/img/photo.jpg" alt="Author Thomas Jankowski at the May 2026 build review, holding a printout of the v1.3 release notes">
```

Use descriptive `alt=` for informational images; `alt=""` for
decorative ones (`alt=""` counts as present in this check — that's the
semantic convention, not a miss). Existing a11y tools (Lighthouse,
axe-core) flag this from a screen-reader angle; this check audits the
same DOM surface from the IEO/GEO angle.

### Fix 14.no_tables_image_heavy — convert screenshots-of-data to HTML tables

If your site renders comparison tables, pricing tables, or data tables
as images (screenshots, infographics, exported PNG charts), LLMs
**cannot extract them as data**. Convert to native HTML:

```html
<table>
  <thead>
    <tr><th>Tier</th><th>Price</th><th>Limit</th></tr>
  </thead>
  <tbody>
    <tr><td>Free</td><td>$0</td><td>100/day</td></tr>
    <tr><td>Pro</td><td>$20/mo</td><td>10k/day</td></tr>
  </tbody>
</table>
```

For complex visualizations that genuinely need raster output, pair the
image with a `<figure>` + `<figcaption>` describing the data, AND emit
the underlying numbers as a `<table>` (or `<dl>`) elsewhere on the
page. LLMs extract from the latter.

### Fix 14.no_content_scope — wrap content in `<main>` or `<article>`

The check fell back to whole-document image counting because neither
`<main>` nor `<article>` was found. Counts may include chrome (logos,
icons, social buttons). Wrap primary content:

```html
<body>
  <header>...</header>
  <main>
    <article>
      <h1>...</h1>
      ...content...
    </article>
  </main>
  <footer>...</footer>
</body>
```

This benefits other audits too (semantic-region isolation reduces
false-positive noise across multiple checks).

**Auto-fix safety: manual** (content-shape decisions; no safe
auto-rewriting).

## Failure ratings

This check is **advisory-tier** by default. WARN findings escalate
overall check status to WARN; INFO findings do not. The check never
emits FAIL — practitioner-tier evidence doesn't justify FAIL severity
without a confirmed indexing-side consequence (cf. check 13, where
`merchant_feed: true` escalates to FAIL because Google Merchant Center
demotes non-compliant listings).

## Tunables (`.launch-readiness.yml`)

```yaml
multimodal_markup_check: true        # gate (required)
multimodal_figcaption_pass: 0.7      # PASS threshold (default 0.7)
multimodal_figcaption_warn: 0.3      # WARN threshold (default 0.3)
multimodal_alt_text_pass: 0.9        # PASS threshold (default 0.9)
multimodal_alt_text_warn: 0.7        # WARN threshold (default 0.7)
multimodal_sample_size: 10           # pages to sample (default 10)
```

## Implementation notes

`scripts/check-multimodal-markup.py`:

1. Gate on `multimodal_markup_check: true`; emit `14.skipped` INFO + return
   if unset.
2. Locate build-output HTML root.
3. Sample candidate pages (home + /about + up to N piece pages from
   common article roots).
4. Per page: restrict to `<main>` / `<article>` scope when present;
   count `<img>`, `<img alt=...>`, `<figure>...<figcaption>`, `<table>`
   (with nav/header/footer regions stripped for table counting).
5. Aggregate ratios across the sample; emit graded findings.

Stdlib `re` only. No PIL / BeautifulSoup / lxml. ~280 lines.
Audit-budget impact: ~10-30s for the default 10-page sample.

## Out of scope

- Image OCR. Detecting "this image contains tabular data" requires OCR
  and lives outside the skill's stdlib-only stance. The
  `14.no_tables_image_heavy` heuristic is a soft prompt, not a detection.
- Per-image semantic quality grading (is the alt= description actually
  *good*?). Out of scope for a structural audit.
- Background-image CSS audit. Sites that render content imagery via
  `background-image:` won't have `<img>` tags; this check undercounts
  on those sites and emits `14.no_content_images` INFO. Recommend the
  consumer convert to `<img>` for LLM-extractable image context.

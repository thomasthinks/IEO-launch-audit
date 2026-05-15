# Check 08 — Internal-link quality

## Why this matters

2025-2026 SEO and GEO best practice converged: mechanical TFIDF or
keyword-distinctive-phrase auto-injection of internal links is now
considered obsolete. The current floor is LLM-curated or hand-curated
inline links with stable named-concept anchors. The reason: phrase
distinctiveness ≠ topical relevance, and topically-mismatched links
actively degrade the cluster signals Google + LLM systems use.

Common failure mode (the "TFIDF trap"): a single generic word (e.g.,
"latency") matches in two topically-unrelated pieces; auto-injection
wraps the word with `<a href>` to the other piece; reader hits the link
and lands on a completely different topic. Multiply across 248 pieces
and the catalog reads as a random hyperlink mess.

This check identifies the TFIDF trap and recommends mitigation.

**Cited sources:** Yoast 2020 (canonical); SEJ 2025; Search Engine Land
internal-linking guide (2025); Ahrefs internal linking guide (2025);
SearchAtlas 2025 "9 Automated Internal Linking Tools" (which documents
the TFIDF→LLM-curated shift); Cognitive load in hypertext reading
(DeStefano & LeFevre).

## What's checked

### 8.1 — Inline-link anchor-text quality

For each `<a href="/writing/...">phrase</a>` in piece bodies:

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| Anchor text is ≥3 words OR is a stable named concept | yes | 2 words | single-word generic |
| Anchor text appears in target piece's title or first paragraph | yes | — | target body only |
| Source piece's pillar overlaps target piece's pillar (or named intersection) | yes | adjacent pillar | random cross-pillar |

### 8.2 — Inline-link density

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| Inline-link density ≤ 1 per 500w (Stratechery / PG model) | yes | 1-2 per 500w | >2 per 500w |
| No piece has more than 7 inline links | yes | 8-12 | >12 |

### 8.3 — Recirculation module presence

| Assertion | Pass | Warn |
|---|---|---|
| End-of-piece "Read next" or "Related" block exists | yes | no |
| Backlinks block (pieces citing this one) exists (optional) | yes | no |
| Pillar membership badge per piece (optional) | yes | no |

### 8.4 — JSON-LD mentions[] quality (graph-side)

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| mentions[] derived from multi-word phrases (not single tokens) | yes | mixed | single-word matches |
| mentions[] targets share pillar or named intersection with source | yes | adjacent | random |
| mentions[] phrase appears in target's title or first paragraph | yes | body only | no overlap |

## How to fix

### Fix 8.1 — Strip mechanical TFIDF links

If the inline-link injection was mechanical, strip all auto-injected
links:

```python
# Mechanical revert: remove <a href="/writing/..."> wrappers that were
# auto-injected. Tag injected links with a marker comment for safe
# rollback.
```

Then either:
- Add hand-curated inline links during editorial passes (Stratechery
  model)
- Use an LLM-curated injection (subagent per piece, ~5 high-quality
  link proposals per piece, operator-ratified before apply)

**Auto-fix safety: safe** (revert auto-injection); the curation pass is
**manual** or **LLM-driven** (separate operation).

### Fix 8.2 — Tighten link-graph criteria

If the link-graph data drives JSON-LD `mentions[]` AND inline links,
tighten the criteria at the graph-emission level:

- Multi-word phrases only (≥3 words; drops generic single nouns)
- Phrase must appear in target's title OR first paragraph (not just
  anywhere in body)
- Same pillar OR named intersection (drops random cross-pillar matches)

In Python:

```python
def is_quality_callback(phrase: str, source: dict, target: dict) -> bool:
    if len(phrase.split()) < 3:
        return False
    if phrase.lower() not in (target['title'].lower() + ' ' + target['first_para'].lower()):
        return False
    source_pillars = set(source.get('pillars', []))
    target_pillars = set(target.get('pillars', []))
    if not (source_pillars & target_pillars) and not has_named_intersection(source, target):
        return False
    return True
```

**Auto-fix safety: safe** (tightens existing emitter; reduces edge count
but improves quality).

### Fix 8.3 — Add Read-next footer

Add a footer section to each piece page:

```tsx
<section className="related-pieces">
  <h2 className="type-label">Read next</h2>
  <ul>
    {topThreeFromMentions.map(piece => (
      <li><Link href={`/writing/${piece.slug}`}>
        <span className="pillar">{piece.pillar}</span>
        <h3>{piece.title}</h3>
        <p>{piece.dek}</p>
      </Link></li>
    ))}
  </ul>
</section>
```

Pulls top-3 from the (tightened) mentions[] graph, ranked by target's
in-degree (most central hubs surface first).

**Auto-fix safety: manual** (renderer change).

## Failure ratings

- **FAIL:** majority of inline links are single-word generic anchors,
  mentions[] full of single-word matches, link-density >2/500w.
- **WARN:** no Read-next footer, no inline links at all (defensible but
  loses reader-side recirculation), single-word anchors present but
  minority.
- **PASS:** inline anchors are multi-word + named-concept, mentions[] is
  topically coherent, Read-next footer or equivalent recirculation
  exists.

## Cited research

- [Yoast — Related posts in WordPress (Aug 2020)](https://yoast.com/wordpress-related-posts-relevant-links/)
- [Search Engine Land — Internal linking for SEO](https://searchengineland.com/guide/internal-linking)
- [Ahrefs — Internal Links for SEO Guide](https://ahrefs.com/blog/internal-links-for-seo/)
- [Ahrefs — Topic Clusters in 10 Minutes](https://ahrefs.com/blog/topic-clusters/)
- [SearchAtlas — 9 Automated Internal Linking Tools (2025)](https://searchatlas.com/blog/automated-internal-linking/)
- [Techoclock — Best AI Internal Linking Tools (2026)](https://techoclock.com/best-ai-internal-linking-tools/)
- [Cognitive load in hypertext reading (DeStefano & LeFevre)](https://www.sciencedirect.com/science/article/abs/pii/S0747563205000658)
- [Design Of This Website — gwern.net](https://gwern.net/design)

## Implementation notes

`scripts/check-link-quality.py`:
1. Parse rendered TSX (or HTML) for each piece's inline `<a href>` tags
2. For each link: count anchor-text words, check if anchor appears in
   target's title/first-para, check pillar overlap
3. Tabulate per-piece link density
4. Parse JSON-LD mentions[] for graph-side same checks
5. Report findings + recommend Phase A / Phase B fixes

# Check 07 — Sitemap accuracy

## Why this matters

Google publicly confirmed (2023) that `<lastmod>` in sitemap.xml is
trusted only when it correlates with actual content changes. Sitemaps
where every URL has the same lastmod (build timestamp) are flagged as
"lying about freshness" and the entire sitemap is discounted.

In 2026, auditors (Screaming Frog, Sitebulb, Ahrefs) compare sitemap
`lastmod` to:
- The page's `Last-Modified` HTTP response header
- A content-hash check (does the page body match what `lastmod` claims)

Sitemap should be the structural index of the site; getting it wrong
discounts every downstream signal that depends on it.

**Cited sources:** [Google Search Central — Sitemap protocol](https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview); 
sitemap.xml protocol spec (sitemaps.org); Screaming Frog sitemap audit
documentation.

## What's checked

### 7.1 — Sitemap presence

| Assertion | Pass | Fail |
|---|---|---|
| `sitemap.xml` exists at site root | yes | no |
| `sitemap.xml` referenced from `robots.txt` `Sitemap:` directive | yes | no |
| Valid XML against sitemap protocol schema | yes | malformed |

### 7.2 — Sitemap completeness

| Assertion | Pass | Fail |
|---|---|---|
| Every list-visible piece URL is in sitemap | yes | gaps |
| No 404 URLs in sitemap (would soft-404 on crawl) | yes | dead URLs |
| Static pages (home, /writing, /about, /contact) included | yes | gaps |

### 7.3 — lastmod accuracy

| Assertion | Pass | Warn | Fail |
|---|---|---|---|
| Each `<url>`'s `<lastmod>` ≤ source file mtime + 1 day | yes | within 7 days | older or future |
| Spread of `<lastmod>` values matches edit pattern (not all identical to build time) | varied | mostly identical | all identical |
| `<lastmod>` in ISO 8601 (`YYYY-MM-DD` or full datetime) | yes | — | other format |

### 7.4 — Image sitemap (optional)

| Assertion | Pass | Warn |
|---|---|---|
| `image-sitemap.xml` exists if site has hero images | yes | no |
| Each piece-with-hero appears in image sitemap | yes | partial |
| Image URLs are absolute | yes | relative |

### 7.5 — RSS feed (optional)

| Assertion | Pass | Warn |
|---|---|---|
| `rss.xml` exists | yes | no |
| RSS items are reverse-chronological | yes | unsorted |
| RSS items include full body OR substantive description | yes | title-only |
| RSS referenced from `<link rel="alternate" type="application/rss+xml">` in HTML head | yes | no |

## How to fix

### Fix 7.1 — Generate sitemap

Each emitter handles sitemap generation differently. Common gotcha:
including pieces that haven't been rendered (lead to soft-404s) or
omitting pieces that have (lose indexing).

The emitter should filter to "pieces that have a rendered .tsx and are
list-visible (not prototype, not future-dated past today)."

**Auto-fix safety: manual** (emitter logic).

### Fix 7.2 — Fix lastmod accuracy

The sitemap emitter should derive `<lastmod>` from a per-piece source of
truth, NOT from build time. Two valid sources:

1. **Source file mtime** — correct when the build pipeline preserves
   authoring mtimes:

   ```python
   from pathlib import Path
   from datetime import datetime

   def lastmod_iso(src_path: Path) -> str:
       return datetime.fromtimestamp(src_path.stat().st_mtime).strftime("%Y-%m-%d")
   ```

2. **Editorial frontmatter `dateModified`** — correct when source files
   are generated/touched by a build step that loses the authoring mtime
   (e.g. backdated catalogues, content migrations, multi-stage emitters).
   The audit's `sitemap_lastmod_mode: editorial` config option compares
   against `dateModified` / `originalPublicationDate` / `publishedDate`
   in priority order (configurable via `slug_to_frontmatter_map.date_keys`).

Configure which mode the audit uses to verify the emitter via
`sitemap_lastmod_mode` in `.launch-readiness.yml`. Default is
`file_mtime`. Switch to `editorial` for backdated catalogues.

If using build-time as lastmod everywhere, that's the bug — Google will
flag.

**Auto-fix safety: manual** (touches emitter logic).

### Fix 7.3 — Submit to GSC + Bing Webmaster

After sitemap is correct:
1. Verify domain in GSC via DNS TXT record
2. Verify domain in Bing Webmaster Tools via DNS TXT record
3. Submit `sitemap.xml` URL in each console
4. Monitor coverage in each over the next 7 days

DNS TXT verification (vs HTML-tag verification) is preferred — it
survives platform migrations and rebuilds.

**Auto-fix safety: manual** (operator action on GSC + BWT consoles).

## Failure ratings

- **FAIL:** sitemap missing, malformed XML, all lastmod identical to
  build time, dead URLs in sitemap.
- **WARN:** image-sitemap missing, RSS missing/title-only, lastmod within
  7 days of edits (acceptable but should be tighter).
- **PASS:** all assertions hold.

## Cited research

- [Google Search Central — Sitemaps](https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview)
- [sitemap.xml protocol (sitemaps.org)](https://www.sitemaps.org/protocol.html)
- [Google: lastmod trust requires correlation with content changes (2023)](https://www.seroundtable.com/google-on-sitemap-lastmod-35920.html)

## Implementation notes

`scripts/check-sitemap.py`:
1. Reads sitemap.xml + parses XML
2. For each `<url>`, identifies the source file by URL → slug → file mapping
3. Compares `<lastmod>` to either source mtime (mode=`file_mtime`, default)
   or editorial date keys from frontmatter (mode=`editorial` —
   `dateModified` → `originalPublicationDate` → `publishedDate`, first
   present wins)
4. Reports gaps. URLs whose slug doesn't resolve to a source file, or
   (in editorial mode) whose frontmatter has none of the configured
   date keys, count as `unverifiable` rather than mismatched.

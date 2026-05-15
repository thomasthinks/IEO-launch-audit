# Check 01 — Technical SEO baseline

## Why this matters

External auditors (Screaming Frog, Sitebulb, Ahrefs Site Audit, Lighthouse,
Google Search Console) flag a consistent set of pre-launch failures.
Common deal-breakers in 2026: `noindex` accidentally left from staging,
missing security headers (HSTS, CSP, Permissions-Policy), hero-image LCP
failures, soft-404s (404 page returning HTTP 200), sitemap `lastmod`
claims that don't match real file mtimes (Google now verifies this rather
than blindly trusting).

The mobile-first indexing threshold has shifted: viewport meta is
mandatory; tap-target minimum relaxed from 48×48 to 24×24 (WCAG 2.2). The
INP metric replaced FID in March 2024 and is weighted heavily in 2026
PageSpeed Insights. The `rel=prev/next` pagination signal was deprecated
by Google in 2019; Bing still respects it. `X-Frame-Options` was
superseded by CSP `frame-ancestors`; `X-XSS-Protection` is now
deprecated.

**Cited sources:** Screaming Frog issue catalogue; Sitebulb critical-issues
docs; web.dev Core Web Vitals (2026); Google Search Central blog;
Mozilla MDN HTTP security headers.

## What's checked

### 1.1 — HTTP response headers

Run `curl -I` against the apex + 5 sample piece URLs.

| Header | Required value pattern | Severity if missing |
|---|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` | FAIL |
| `X-Content-Type-Options` | `nosniff` | FAIL |
| `Content-Security-Policy` | non-empty (even permissive) | WARN |
| `Referrer-Policy` | `strict-origin-when-cross-origin` (or stricter) | WARN |
| `Permissions-Policy` | non-empty | WARN |
| `Cache-Control` (hashed assets) | `public, max-age=31536000, immutable` | WARN |

Drop-warning if these are still present (deprecated):
- `X-XSS-Protection` — deprecated, can hurt
- `X-Frame-Options` — superseded by CSP `frame-ancestors`

### 1.2 — Indexability

| Assertion | Pass | Fail |
|---|---|---|
| robots.txt does NOT contain `Disallow: /` for User-agent: * | yes | leftover staging block |
| `<meta name="robots" content="noindex">` NOT present in HTML head | yes | leftover staging tag |
| `X-Robots-Tag` HTTP header NOT set to `noindex` | yes | leftover staging header |
| Each page emits a self-referencing absolute canonical | yes | missing/relative |

### 1.3 — 404 status correctness

Common SSG bug: not-found pages return HTTP 200 with "Coming Soon"
content, which Google flags as soft-404.

| Assertion | Pass | Fail |
|---|---|---|
| `curl -I https://example.com/this-does-not-exist` returns HTTP 404 | yes | 200 (soft-404) |

### 1.4 — Hero-image LCP attributes

For each piece's hero `<img>`:

| Assertion | Pass | Fail |
|---|---|---|
| Has `fetchpriority="high"` | yes | no |
| Has explicit `width` + `height` attributes | yes | no (causes CLS) |
| Has `loading="eager"` (NOT `loading="lazy"`) | yes | lazy (defeats LCP) |
| Image format AVIF or WebP (negotiated by Accept header or `<picture>` source) | yes | only JPG/PNG |

### 1.5 — Mobile-first baseline

| Assertion | Pass | Fail |
|---|---|---|
| `<meta name="viewport" content="width=device-width, initial-scale=1">` | yes | missing/malformed |
| Tap targets ≥24×24 CSS pixels (WCAG 2.2 AA) | yes | smaller |
| Base font ≥16px | yes | smaller |

### 1.6 — Sitemap lastmod accuracy

Google publicly confirmed in 2023 that `lastmod` in sitemap is only
trusted when it correlates with actual content changes. Auditors compare
sitemap `lastmod` to `Last-Modified` HTTP response header AND to the
content hash.

| Assertion | Pass | Fail |
|---|---|---|
| Each `<url><lastmod>` in sitemap.xml ≤ corresponding file mtime + 1 day | yes | mismatch |
| Sitemap `lastmod` not equal to build-time across all entries (suggests fake) | varied | all identical |

## How to fix

### Fix 1.1 — Add security headers

For **Vercel** (`vercel.json`):

```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        {"key": "Strict-Transport-Security", "value": "max-age=31536000; includeSubDomains; preload"},
        {"key": "X-Content-Type-Options", "value": "nosniff"},
        {"key": "Referrer-Policy", "value": "strict-origin-when-cross-origin"},
        {"key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()"},
        {"key": "Content-Security-Policy", "value": "default-src 'self'; img-src 'self' data: https:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self'; frame-ancestors 'none'"}
      ]
    }
  ]
}
```

For **Netlify** (`_headers`):

```
/*
  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Content-Security-Policy: default-src 'self'; img-src 'self' data: https:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self'; frame-ancestors 'none'
```

For **Cloudflare Pages / Workers**: similar via Workers function or
`_headers` file.

Template at `templates/vercel-headers.json.example`.

**Auto-fix safety: safe** (additive; doesn't override existing headers).

### Fix 1.2 — Verify indexability

```bash
# robots.txt should NOT block
curl https://example.com/robots.txt | grep -E "Disallow:\s*/$" && echo "FAIL"

# Pages should NOT have noindex
curl https://example.com/ | grep -i "noindex" && echo "FAIL"

# No X-Robots-Tag noindex
curl -I https://example.com/ | grep -i "x-robots-tag.*noindex" && echo "FAIL"
```

If any flagged: edit robots.txt / HTML head / server config.

**Auto-fix safety: manual** (requires editing the source; identifying
where the staging block came from).

### Fix 1.3 — 404 returns 404

SSG-specific. The build pipeline needs to emit a `404.html` that the host
serves with HTTP 404 status (not 200). 

For Vercel: `vercel.json`:
```json
{"trailingSlash": false, "cleanUrls": true, "headers": [...]}
```
Combined with a `404.html` in `dist/public/`, Vercel automatically returns
404 status for non-matching paths.

For Netlify: `_redirects`:
```
/*    /404.html   404
```

For static-only hosts: depends on host. GitHub Pages serves 404.html with
404 status automatically.

**Auto-fix safety: manual** (host-specific config).

### Fix 1.4 — Hero image attrs

In every piece's TSX hero block:

```tsx
<img
  src={heroImage}
  alt={altText}
  width={1920}
  height={1080}
  fetchpriority="high"
  loading="eager"
  decoding="async"
/>
```

For mechanical patching: a script can identify hero `<img>` tags (inside
`<figure className="prose-essay-hero">`) and add missing attributes.

**Auto-fix safety: safe** (mechanical attribute addition).

### Fix 1.5 — Viewport meta

In `client/index.html` (or equivalent):

```html
<meta name="viewport" content="width=device-width, initial-scale=1">
```

Tap targets + font size require CSS audit; less mechanically fixable.

**Auto-fix safety: safe** (viewport meta tag); **manual** (tap targets +
font sizes).

### Fix 1.6 — Sitemap lastmod accuracy

Sitemap emitter should set `<lastmod>` from the source file's `mtime` (or
from frontmatter `dateModified`), NOT from build time. Common bug: every
URL gets the same `lastmod` (build timestamp), which Google detects and
discounts the entire sitemap.

```python
# Python emitter example
from pathlib import Path
mtime_iso = datetime.fromtimestamp(Path(src_file).stat().st_mtime).strftime("%Y-%m-%d")
```

**Auto-fix safety: manual** (touches the sitemap emitter logic).

## Failure ratings

- **FAIL (must fix before flip):** missing HSTS, missing nosniff, leftover
  noindex/Disallow, soft-404, hero `loading="lazy"`, no viewport meta.
- **WARN (should fix before flip):** missing CSP/Referrer-Policy/
  Permissions-Policy, hero missing `fetchpriority`, sitemap `lastmod` all
  identical to build time, tap targets <24px.
- **PASS:** all assertions hold.

## Cited research

- web.dev Core Web Vitals 2026 documentation
- Google Search Central — Mobile-first indexing
- MDN — HTTP security headers
- Screaming Frog — Common SEO issues catalog
- Sitebulb — Critical-issues documentation
- Lighthouse audits

## Implementation notes

`scripts/check-headers.py` performs the curl-based header audit (1.1).
`scripts/check-sitemap.py` validates lastmod accuracy (1.6). Hero
attribute check is a grep across rendered TSX (1.4). 404-status check
requires a deployed origin (1.3); reported as MANUAL VERIFY if no origin
is available.

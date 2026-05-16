# Check 13 — Imagery provenance (C2PA / IPTC `digitalSourceType`)

## Why this matters

Google's Merchant Center (Feb 2024+) mandates that AI-generated product
images carry IPTC PhotoMetadata `digitalSourceType` marking them as
`trainedAlgorithmicMedia` or `compositeSynthetic`. Non-compliant
listings get **demoted or removed** from Merchant Center search
results. That's an indexing-side enforcement consequence, not a
regulatory-compliance audit.

This check is the SEO/IEO analogue of an asset-side provenance audit.
It does NOT cover EU AI Act Article 50 compliance (declined in
ROADMAP § Out-of-scope as different audit class). It DOES cover the
practical case where missing image provenance metadata costs
distribution on Google's surfaces.

C2PA Content Credentials provide cryptographically-signed provenance
(stronger than IPTC alone) and are aligned with the Content
Authenticity Initiative (CAI). Adobe Firefly, DALL-E 3, Google Imagen,
and Sora emit C2PA + IPTC by default. Midjourney, screenshot
pipelines, and most image-resizing build steps **strip** the metadata.

**Cited sources:** [Google Merchant Center AI-image metadata
requirements](https://support.google.com/merchants/answer/14743464);
[IPTC NewsCodes `digitalSourceType`
vocabulary](https://cv.iptc.org/newscodes/digitalsourcetype/);
[C2PA Specification 2.4](https://spec.c2pa.org/specifications/specifications/2.4/explainer/Explainer.html);
[How Google + C2PA are increasing transparency for gen-AI
content](https://blog.google/technology/ai/google-gen-ai-content-transparency-c2pa/).

## What's checked

This check is **opt-in** via `.launch-readiness.yml`:

```yaml
ai_generated_imagery: true   # site uses generative AI for hero/inline images
merchant_feed: true          # site syndicates to Google Merchant (raises severity)
```

When `ai_generated_imagery` is unset or false, the check emits one INFO
finding and skips. No false alarms on sites without AI imagery.

When opted in, the check:

1. Walks sampled rendered HTML pages (home, /about, up to 8 piece pages).
2. Extracts `og:image` / `twitter:image` content URLs.
3. Resolves to local filesystem path under `dist/public` / `public` / `out`
   / `_site` / `build`. Falls back to remote fetch (256KB Range request)
   when the image isn't locally findable.
4. Scans up to 256KB of image bytes for an XMP packet (between
   `<?xpacket begin ...?>` and `<?xpacket end ...?>` markers).
5. Inspects the XMP packet for IPTC `digitalSourceType` values or C2PA
   manifest markers.

### Findings

| Finding | Severity | Trigger |
|---|---|---|
| `13.skipped` | INFO | `ai_generated_imagery` not set |
| `13.ai_provenance_marked` | PASS | image XMP carries `trainedAlgorithmicMedia` / `compositeSynthetic` |
| `13.ai_provenance_missing` | WARN (FAIL when `merchant_feed: true`) | AI imagery declared but XMP lacks any `digitalSourceType` |
| `13.c2pa_present` | PASS | C2PA manifest markers detected in image |
| `13.non_ai_explicit` | INFO | image XMP carries non-AI `digitalSourceType` (`digitalCapture` / `digitizedFromOriginal` / etc) |
| `13.unreadable` | MANUAL_VERIFY | sampled og:image was unresolvable locally + remote fetch failed |
| `13.no_og_images` | MANUAL_VERIFY | sampled HTML pages don't emit og:image |

## How to fix

### Fix 13.ai_provenance_missing

Embed IPTC `digitalSourceType` in image XMP during the asset-build
pipeline. Three approaches in order of cost:

**1. Build-tool embedding (cheapest).** ExifTool can write the IPTC
value during a post-encode step:

```bash
exiftool -Iptc4xmpExt:DigitalSourceType=\
"https://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia" \
  path/to/hero.jpg
```

For composites (multiple AI generations merged or AI + photography):

```bash
exiftool -Iptc4xmpExt:DigitalSourceType=\
"https://cv.iptc.org/newscodes/digitalsourcetype/compositeSynthetic" \
  path/to/composite.jpg
```

**2. C2PA SDK (stronger).** Use the `c2pa-rs` or `c2pa-python` SDK to
emit a signed C2PA manifest with provenance assertions. Cryptographic
binding to the asset; survives lossless re-encoding.

**3. Image-generation pipeline (cleanest).** Adobe Firefly, DALL-E 3,
Google Imagen, and Sora emit IPTC + C2PA by default. If your generation
provider does, preserve metadata through your post-processing steps
(don't strip during resize / convert). ImageMagick's `-define
preserve-timestamp=true` plus explicit `-set` for IPTC fields are the
preservation hooks.

**Auto-fix safety: manual** (asset-side; touches binary metadata).

### Fix 13.unreadable

The audit couldn't read the image. Common causes:

- Relative `og:image` URL doesn't resolve under known build-output roots.
  Fix: emit absolute URLs, OR confirm build copies hero images into one
  of `dist/public` / `public` / `out` / `_site` / `build`.
- Remote fetch blocked (HTTP 403 / 404 / 429 / TLS). Fix: verify the CDN
  serves the image to a generic Python user-agent; confirm Range requests
  are honored.

## Failure ratings

Default severity is WARN for missing provenance when `ai_generated_imagery: true`.

When `merchant_feed: true` is ALSO set, severity escalates to FAIL —
Google Merchant Center actively demotes / removes AI product images
lacking IPTC `digitalSourceType`, so this is real distribution cost,
not just transparency.

## Cited research

- [Google Merchant Center — AI-generated content metadata](https://support.google.com/merchants/answer/14743464)
- [IPTC digital source type NewsCodes](https://cv.iptc.org/newscodes/digitalsourcetype/)
- [How Google and C2PA are increasing transparency for gen AI](https://blog.google/technology/ai/google-gen-ai-content-transparency-c2pa/)
- [C2PA Content Credentials Explainer 2.4](https://spec.c2pa.org/specifications/specifications/2.4/explainer/Explainer.html)
- [Shutterstock AI Content Policies 2026](https://aimetadatacleaner.com/blog/shutterstock-ai-content-policies-2026-guide)
- [Content Authenticity Initiative — State of Content Authenticity 2026](https://contentauthenticity.org/blog/the-state-of-content-authenticity-in-2026)

## Implementation notes

`scripts/check-imagery-provenance.py`:

1. Gate on `ai_generated_imagery: true`; emit `13.skipped` INFO + return
   if unset.
2. Locate `dist/public` (or alternates) + collect sample candidate HTML
   pages (home + /about + up to 8 /writing pieces).
3. Per page: extract og:image URL; resolve to local file OR Range-fetch
   first 256KB.
4. Find XMP packet via `<?xpacket begin ...?>` / `<?xpacket end ...?>`
   marker scan. Stdlib `re` only — no PIL / ExifRead / Pillow.
5. Detect IPTC `digitalSourceType` values + C2PA / ContentCredentials
   markers via substring presence.
6. Aggregate + emit PASS / WARN / INFO / MANUAL_VERIFY findings.

Stdlib only. ~250 lines. Read-only against image bytes; no network
calls when og:image resolves locally. Remote fetch (when needed) uses
Range header to bound bytes-per-image.

Scope distinction from declined EU AI Act check: this audits Google
Merchant Center indexing-side enforcement, not regulatory compliance.
The check stays narrow + opt-in to honor the standing
"no-false-alarms-on-human-edited-sites" stance.

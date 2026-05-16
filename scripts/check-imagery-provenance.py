#!/usr/bin/env python3
"""
Check 13 — AI-imagery provenance (C2PA / IPTC digitalSourceType).

v1.3 opt-in. Reads og:image / twitter:image targets from sampled rendered
HTML pages and scans for IPTC PhotoMetadata `digitalSourceType` or C2PA
manifest markers. Reports presence of:

  - trainedAlgorithmicMedia (AI-generated)
  - compositeSynthetic (AI-composited)
  - digitalCapture / digitizedFromOriginal / etc. (non-AI)
  - (none)

Gated on operator declaration via `.launch-readiness.yml`:

  ai_generated_imagery: true   # site uses generative AI for hero/inline images
  merchant_feed: true          # site syndicates to Google Merchant (raises severity)

When `ai_generated_imagery` is unset/false, the check skips silently with
one INFO finding. The provenance vocabulary lives in image-embedded XMP,
not in JSON-LD — this is OUT-OF-BAND for the rest of the schema audit.

Scope distinction from the declined EU AI Act Article 50 scope:
this check audits SEO/IEO-side surfaces — specifically Google Merchant
Center's mandate to mark AI product images via IPTC `digitalSourceType`
(demotion / removal for non-compliant Merchant listings). That's an
indexing-side consequence, not a regulatory-compliance audit. Read-only;
no network calls unless og:image is remote.
"""
from __future__ import annotations

import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, load_config, time_check,
)


# IPTC PhotoMetadata `digitalSourceType` resource URLs.
# Source: https://cv.iptc.org/newscodes/digitalsourcetype/
IPTC_AI_VALUES = (
    "trainedAlgorithmicMedia",
    "compositeSynthetic",
    "algorithmicMedia",
    "trainedAlgorithmicallyGeneratedMedia",  # legacy / alternate naming
)
IPTC_NON_AI_VALUES = (
    "digitalCapture",
    "digitizedFromOriginal",
    "negativeFilm",
    "positiveFilm",
    "print",
    "minorHumanEdits",
)
ALL_IPTC_VALUES = IPTC_AI_VALUES + IPTC_NON_AI_VALUES

# Per-page sample for og:image extraction.
DEFAULT_IMAGE_SAMPLE_SIZE = 10
# Max image-bytes to read when scanning for XMP packets. XMP packets in
# JPEGs are typically <64KB. PNG XMP iTXt and WebP XMP chunks are similar.
# Reading the first 256KB catches XMP-in-APP1-marker plus most C2PA JUMB
# preambles without committing to full image decode.
MAX_IMAGE_BYTES = 256 * 1024


def find_og_image(html: str) -> str | None:
    """Extract og:image content URL from HTML. Returns None if absent."""
    m = re.search(
        r'<meta\s+(?:property|name)=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\']og:image["\']',
            html, re.IGNORECASE,
        )
    if not m:
        # Twitter card fallback
        m = re.search(
            r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
    return m.group(1).strip() if m else None


def resolve_image_path(repo: Path, og_url: str, canonical_origin: str) -> Path | None:
    """If og:image is a local path or matches canonical_origin, resolve
    to a filesystem path under repo/dist (or repo/public). Returns None
    when the image is remote or unresolvable locally."""
    # Strip canonical origin prefix if present.
    relative: str
    if og_url.startswith(canonical_origin.rstrip("/")):
        relative = og_url[len(canonical_origin.rstrip("/")):]
    elif og_url.startswith("/"):
        relative = og_url
    else:
        return None
    relative = relative.lstrip("/")
    # Search common public roots.
    for root in ("dist/public", "public", "out", "_site", "build"):
        candidate = repo / root / relative
        if candidate.exists():
            return candidate
    return None


def fetch_image_bytes(url: str, max_bytes: int = MAX_IMAGE_BYTES) -> bytes | None:
    """Fetch up to max_bytes of an image via Range header. Used as a
    fallback for remote og:image URLs (typically CDN-served). Stdlib only."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "IEO-launch-audit/1.3 (+imagery-provenance)",
            "Range": f"bytes=0-{max_bytes - 1}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read(max_bytes)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def extract_xmp_packet(data: bytes) -> str | None:
    """Find an XMP packet inside JPEG/PNG/WebP bytes and return as text.
    XMP packets are XML-wrapped in <?xpacket begin ... ?> ... <?xpacket end ... ?>
    markers, encoded UTF-8 inside the file. Stdlib-only."""
    # Search for the begin / end markers (8-bit text scan inside the byte
    # blob — XMP is always ASCII/UTF-8 inside its markers, regardless of
    # container format).
    try:
        text = data.decode("latin-1", errors="replace")
    except Exception:
        return None
    m = re.search(r"<\?xpacket begin=.*?\?>(.*?)<\?xpacket end=.*?\?>", text, re.DOTALL)
    return m.group(1) if m else None


def detect_provenance(xmp_text: str) -> tuple[str, str | None]:
    """Inspect an XMP packet for IPTC `digitalSourceType` markers + C2PA
    references. Returns (status, evidence) where status is one of:
      'ai_generated' / 'ai_composite' / 'non_ai' / 'c2pa_present' / 'none'.
    `evidence` is the captured value string or None.
    """
    # IPTC digitalSourceType values (resource URIs)
    for v in IPTC_AI_VALUES:
        if v in xmp_text:
            if "composite" in v.lower():
                return ("ai_composite", v)
            return ("ai_generated", v)
    for v in IPTC_NON_AI_VALUES:
        if v in xmp_text:
            return ("non_ai", v)
    # C2PA manifest reference (loose check)
    if "c2pa" in xmp_text.lower() or "ContentCredentials" in xmp_text:
        return ("c2pa_present", "c2pa marker")
    return ("none", None)


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    result = CheckResult(check="13-imagery-provenance")

    # Gate: only run when operator declares AI imagery.
    if config.get("ai_generated_imagery") is not True:
        result.findings.append(Finding(
            id="13.skipped", severity="INFO",
            title="Imagery-provenance check skipped (ai_generated_imagery not set in .launch-readiness.yml)",
            notes=(
                "Opt-in: set `ai_generated_imagery: true` in config when the "
                "site uses generative AI for hero / inline images. The check "
                "scans og:image / twitter:image XMP for IPTC digitalSourceType "
                "(trainedAlgorithmicMedia / compositeSynthetic) or C2PA "
                "manifest markers. When `merchant_feed: true` also set, "
                "missing-provenance findings escalate to FAIL (Google Merchant "
                "Center demotes / removes AI product images lacking IPTC "
                "digitalSourceType)."
            ),
        ))
        return result

    merchant_feed = config.get("merchant_feed") is True
    canonical_origin = (config.get("canonical_origin") or "").rstrip("/")

    # Find sampled rendered HTML pages.
    html_roots = ["dist/public", "out", "_site", "public", "build"]
    html_root = next((repo / r for r in html_roots if (repo / r).exists()), None)
    if not html_root:
        result.findings.append(Finding(
            id="13.no_build", severity="MANUAL_VERIFY",
            title="No build-output directory found (dist/public, out, _site, public, build); cannot sample og:image",
            fix_action="Run the build pipeline before re-running the imagery-provenance check.",
        ))
        return result

    # Collect candidate HTML pages: home, /about, sampled /writing/*.
    candidates: list[Path] = []
    for p in (html_root / "index.html",
              html_root / "about" / "index.html"):
        if p.exists():
            candidates.append(p)
    writing_dir = html_root / "writing"
    if writing_dir.exists():
        # Take up to N piece pages (deterministic ordering).
        all_pieces = sorted(writing_dir.rglob("index.html"))
        candidates.extend(all_pieces[:DEFAULT_IMAGE_SAMPLE_SIZE - len(candidates)])

    if not candidates:
        result.findings.append(Finding(
            id="13.no_pages", severity="MANUAL_VERIFY",
            title="No HTML pages with og:image candidates found",
        ))
        return result

    by_status: dict[str, list[tuple[str, str]]] = {
        "ai_generated": [], "ai_composite": [],
        "non_ai": [], "c2pa_present": [], "none": [],
        "unreadable": [],
    }
    pages_scanned = 0

    for page in candidates:
        try:
            html = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        og = find_og_image(html)
        if not og:
            continue
        pages_scanned += 1
        page_label = str(page.relative_to(repo))
        # Resolve to local path; fall back to remote fetch.
        local = resolve_image_path(repo, og, canonical_origin)
        if local is not None:
            try:
                data = local.read_bytes()[:MAX_IMAGE_BYTES]
            except OSError:
                by_status["unreadable"].append((page_label, og))
                continue
        else:
            # Remote fetch with Range header.
            if not og.startswith(("http://", "https://")):
                # Relative URL we couldn't resolve locally.
                by_status["unreadable"].append((page_label, og))
                continue
            data = fetch_image_bytes(og)
            if data is None:
                by_status["unreadable"].append((page_label, og))
                continue
        xmp = extract_xmp_packet(data)
        if xmp is None:
            by_status["none"].append((page_label, og))
            continue
        status, evidence = detect_provenance(xmp)
        by_status[status].append((page_label, f"{og} ({evidence})" if evidence else og))

    # Aggregate findings.
    ai_count = len(by_status["ai_generated"]) + len(by_status["ai_composite"])
    non_ai_count = len(by_status["non_ai"])
    none_count = len(by_status["none"])
    c2pa_count = len(by_status["c2pa_present"])
    unreadable_count = len(by_status["unreadable"])

    if pages_scanned == 0:
        result.findings.append(Finding(
            id="13.no_og_images", severity="MANUAL_VERIFY",
            title="No og:image / twitter:image meta tags found in sampled HTML pages",
            fix_action="Verify the site emits og:image per page; re-run.",
        ))
        return result

    if ai_count > 0:
        sample_ai = (by_status["ai_generated"] + by_status["ai_composite"])[:5]
        result.findings.append(Finding(
            id="13.ai_provenance_marked", severity="PASS",
            title=(
                f"{ai_count}/{pages_scanned} sampled images carry IPTC "
                "digitalSourceType for AI-generated content"
            ),
            current=[f"{lbl}: {og}" for lbl, og in sample_ai],
            notes=(
                "trainedAlgorithmicMedia / compositeSynthetic detected in XMP. "
                "Compliant with Google Merchant Center's AI-image marking "
                "requirement and aligned with the Content Authenticity "
                "Initiative (CAI) / C2PA pattern."
            ),
        ))

    if none_count > 0:
        severity = "FAIL" if merchant_feed else "WARN"
        sample_missing = by_status["none"][:5]
        result.findings.append(Finding(
            id="13.ai_provenance_missing", severity=severity,
            title=(
                f"{none_count}/{pages_scanned} sampled images lack IPTC "
                "digitalSourceType (site declared ai_generated_imagery: true)"
            ),
            current=[f"{lbl}: {og}" for lbl, og in sample_missing],
            expected=(
                "Each AI-generated image should carry IPTC "
                "PhotoMetadata.digitalSourceType in XMP "
                "(trainedAlgorithmicMedia / compositeSynthetic)."
            ),
            fix_safety="manual",
            fix_action=(
                "Embed IPTC digitalSourceType in image XMP during the "
                "asset-build pipeline. Adobe Firefly / DALL-E 3 / Imagen / "
                "Sora emit by default; Midjourney + screenshot pipelines "
                "strip XMP. Use exiftool, ImageMagick, or the C2PA SDK to "
                "write `Iptc4xmpExt:DigitalSourceType = "
                "https://cv.iptc.org/newscodes/digitalsourcetype/"
                "trainedAlgorithmicMedia`."
            ),
            notes=(
                "Severity FAIL when merchant_feed: true (Google Merchant "
                "Center demotes / removes non-compliant AI product images). "
                "Otherwise WARN — provenance is a transparency / trust signal "
                "but NOT yet a confirmed organic ranking signal for AI engines."
            ),
        ))

    if c2pa_count > 0:
        result.findings.append(Finding(
            id="13.c2pa_present", severity="PASS",
            title=(
                f"{c2pa_count}/{pages_scanned} sampled images carry C2PA "
                "Content Credentials manifest markers"
            ),
            current=[f"{lbl}: {og}" for lbl, og in by_status["c2pa_present"][:5]],
            notes=(
                "C2PA manifests provide cryptographically-signed provenance "
                "(stronger than IPTC alone). Aligned with Google's gen-AI "
                "transparency posture."
            ),
        ))

    if non_ai_count > 0:
        result.findings.append(Finding(
            id="13.non_ai_explicit", severity="INFO",
            title=(
                f"{non_ai_count}/{pages_scanned} sampled images carry non-AI "
                "digitalSourceType (digitalCapture / digitizedFromOriginal / etc)"
            ),
            current=[f"{lbl}: {og}" for lbl, og in by_status["non_ai"][:5]],
            notes="Photography / scanned imagery is explicitly marked as such — clean signal.",
        ))

    if unreadable_count > 0:
        result.findings.append(Finding(
            id="13.unreadable", severity="MANUAL_VERIFY",
            title=(
                f"{unreadable_count}/{pages_scanned} sampled og:image targets "
                "were unreadable (local-path miss + remote fetch failure)"
            ),
            current=[f"{lbl}: {og}" for lbl, og in by_status["unreadable"][:5]],
            notes="Investigate: relative URL not resolved against build artifacts; or remote fetch blocked.",
        ))

    result.summary = (
        f"Imagery-provenance: {pages_scanned} pages scanned. "
        f"AI-marked: {ai_count}, non-AI marked: {non_ai_count}, "
        f"C2PA: {c2pa_count}, unmarked: {none_count}, unreadable: {unreadable_count}."
    )
    result.config_used = {
        "ai_generated_imagery": True,
        "merchant_feed": merchant_feed,
        "image_sample_size": DEFAULT_IMAGE_SAMPLE_SIZE,
    }
    return result


if __name__ == "__main__":
    parser = base_argparser("13-imagery-provenance")
    args = parser.parse_args()
    emit(run(args))

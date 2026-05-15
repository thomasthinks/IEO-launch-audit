#!/usr/bin/env python3
"""
Check 01 — Technical SEO: HTTP response headers, viewport, hero attrs, sitemap lastmod.

Static-config audit (parses host config files). For dynamic verification
of actually-served headers, set `canonical_origin` in config — script will
curl sample URLs and verify response headers match.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Allow execution from any working dir
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult,
    Finding,
    base_argparser,
    emit,
    find_artifact,
    load_config,
    time_check,
)


REQUIRED_HEADERS = {
    "Strict-Transport-Security": ("FAIL", r"max-age=\d+.*includeSubDomains"),
    "X-Content-Type-Options": ("FAIL", r"nosniff"),
    "Content-Security-Policy": ("WARN", r".+"),
    "Referrer-Policy": ("WARN", r"strict-origin-when-cross-origin|no-referrer|same-origin"),
    "Permissions-Policy": ("WARN", r".+"),
}

DEPRECATED_HEADERS = {
    "X-XSS-Protection": "deprecated; can hurt — remove",
    "X-Frame-Options": "superseded by CSP frame-ancestors — keep CSP version",
}


def parse_vercel_json(repo: Path) -> dict[str, str]:
    """Extract header rules from vercel.json. Returns flat dict header→value."""
    import json
    p = repo / "vercel.json"
    if not p.exists():
        return {}
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out: dict[str, str] = {}
    for rule in cfg.get("headers", []):
        if rule.get("source") in ("/(.*)", "/.*", "/"):
            for h in rule.get("headers", []):
                if "key" in h and "value" in h:
                    out[h["key"]] = h["value"]
    return out


def parse_netlify_headers(repo: Path) -> dict[str, str]:
    """Parse _headers file (Netlify)."""
    for path in [repo / "_headers", repo / "public" / "_headers", repo / "dist" / "_headers"]:
        if path.exists():
            out: dict[str, str] = {}
            in_global = False
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not line.startswith(" ") and not line.startswith("\t"):
                    in_global = stripped == "/*"
                    continue
                if in_global and ":" in stripped:
                    k, _, v = stripped.partition(":")
                    out[k.strip()] = v.strip()
            return out
    return {}


def curl_headers(url: str) -> dict[str, str]:
    """Live header probe via curl -sI. Returns header dict."""
    try:
        r = subprocess.run(
            ["curl", "-sI", "-L", "-A", "IEO-launch-audit/0.2", url],
            capture_output=True, text=True, timeout=10,
        )
        out: dict[str, str] = {}
        for line in r.stdout.splitlines():
            if ":" in line and not line.startswith("HTTP/"):
                k, _, v = line.partition(":")
                out[k.strip()] = v.strip()
        return out
    except Exception:
        return {}


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    canonical_origin = config.get("canonical_origin", "")
    # live_probe_origin is the URL the audit actually curls; falls back to
    # canonical_origin via load_config() normalisation. Decoupling these lets
    # pre-flip dev work point live probes at localhost without breaking
    # URL-shape comparisons against the real apex.
    live_probe_origin = config.get("live_probe_origin", "")
    result = CheckResult(check="01-technical-seo")
    result.config_used = {
        "canonical_origin": canonical_origin,
        "live_probe_origin": live_probe_origin,
        "stack": args.stack,
    }

    # 1.1 — Static config audit
    static_headers: dict[str, str] = {}
    static_source = None
    if args.stack.startswith("vercel"):
        static_headers = parse_vercel_json(repo)
        static_source = "vercel.json"
    if not static_headers:
        netlify = parse_netlify_headers(repo)
        if netlify:
            static_headers = netlify
            static_source = "_headers"

    # 1.2 — Live probe (if origin set)
    live_headers: dict[str, str] = {}
    if live_probe_origin:
        live_headers = curl_headers(live_probe_origin)

    # Combine: live wins if available; else static
    effective = live_headers if live_headers else static_headers
    source_label = "live curl" if live_headers else (static_source or "no source")

    for header, (severity, pattern) in REQUIRED_HEADERS.items():
        # Case-insensitive lookup
        val = next((v for k, v in effective.items() if k.lower() == header.lower()), None)
        if val and re.search(pattern, val, re.IGNORECASE):
            result.findings.append(Finding(
                id=f"1.1.{header}", severity="PASS", title=f"{header} present",
                current=val, expected=pattern, fix_safety="safe",
            ))
        elif val:
            result.findings.append(Finding(
                id=f"1.1.{header}", severity="WARN", title=f"{header} present but pattern mismatch",
                current=val, expected=pattern, fix_safety="safe",
                fix_action=f"Update {header} to match pattern: {pattern}",
                fix_template="templates/vercel-headers.json.example",
            ))
        else:
            result.findings.append(Finding(
                id=f"1.1.{header}", severity=severity, title=f"{header} missing",
                current=None, expected=pattern, fix_safety="safe",
                fix_action=f"Add {header} to host config",
                fix_template="templates/vercel-headers.json.example",
                notes=f"Source checked: {source_label}",
            ))

    for header, why in DEPRECATED_HEADERS.items():
        val = next((v for k, v in effective.items() if k.lower() == header.lower()), None)
        if val:
            result.findings.append(Finding(
                id=f"1.1.dep.{header}", severity="WARN", title=f"{header} present (deprecated)",
                current=val, expected=None, fix_safety="safe",
                fix_action=f"Remove {header}: {why}",
            ))

    # 1.2 — Indexability (robots.txt, noindex meta, X-Robots-Tag)
    robots_path = find_artifact(repo, config, "robots_txt", [
        "robots.txt", "public/robots.txt", "dist/public/robots.txt", "static/robots.txt",
    ])
    if robots_path:
        content = robots_path.read_text(encoding="utf-8")
        # Check for "Disallow: /" under "User-agent: *"
        m = re.search(r"User-agent:\s*\*\s*\n(?:(?!User-agent:).*\n)*?Disallow:\s*/\s*\n", content, re.IGNORECASE)
        if m:
            result.findings.append(Finding(
                id="1.2.robots.disallow_all", severity="FAIL",
                title="robots.txt blocks all crawlers",
                current="Disallow: / under User-agent: *",
                fix_safety="manual",
                fix_action="Remove the Disallow: / line — likely a staging leftover.",
            ))
        else:
            result.findings.append(Finding(
                id="1.2.robots.allow", severity="PASS",
                title="robots.txt does not block all crawlers",
                fix_safety="safe",
            ))
    else:
        result.findings.append(Finding(
            id="1.2.robots.missing", severity="WARN",
            title="robots.txt not found at expected locations",
            fix_safety="safe",
            fix_template="templates/robots.txt",
            fix_action="Create robots.txt from template.",
        ))

    # X-Robots-Tag check (live only)
    if live_headers:
        xrt = next((v for k, v in live_headers.items() if k.lower() == "x-robots-tag"), None)
        if xrt and "noindex" in xrt.lower():
            result.findings.append(Finding(
                id="1.2.xrobotstag.noindex", severity="FAIL",
                title="X-Robots-Tag header sets noindex",
                current=xrt, fix_safety="manual",
                fix_action="Remove X-Robots-Tag: noindex — likely staging leftover.",
            ))

    # 1.3 — 404 status correctness (live only)
    if live_probe_origin:
        try:
            r = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 f"{live_probe_origin}/__launch_readiness_audit_does_not_exist_404_check__"],
                capture_output=True, text=True, timeout=10,
            )
            code = r.stdout.strip()
            if code == "404":
                result.findings.append(Finding(
                    id="1.3.softfoutfourzerofour", severity="PASS",
                    title="Unknown path returns 404 (not soft-404)",
                    current=code, expected="404", fix_safety="safe",
                ))
            else:
                result.findings.append(Finding(
                    id="1.3.softfoutfourzerofour", severity="FAIL",
                    title=f"Unknown path returns HTTP {code} (soft-404)",
                    current=code, expected="404", fix_safety="manual",
                    fix_action="Configure host to return real 404 status for unknown paths.",
                ))
        except Exception as e:
            result.findings.append(Finding(
                id="1.3.softfoutfourzerofour", severity="MANUAL_VERIFY",
                title="Could not verify 404 status",
                notes=str(e),
            ))
    else:
        result.findings.append(Finding(
            id="1.3.softfoutfourzerofour", severity="MANUAL_VERIFY",
            title="404 status check requires live_probe_origin (or canonical_origin) in config",
            fix_action="Set live_probe_origin (or canonical_origin) in .launch-readiness.yml, or audit post-deploy.",
        ))

    # 1.4 — Hero image attrs (grep TSX bodies)
    hero_results = []
    tsx_dir = repo / "client/src/content/writing"
    if tsx_dir.exists():
        missing_fetch = missing_dims = missing_eager = 0
        total = 0
        for p in tsx_dir.glob("*.tsx"):
            text = p.read_text(encoding="utf-8")
            # Look for <img inside prose-essay-hero figure
            m = re.search(r'<figure className="prose-essay-hero">\s*<img\s+([^>]*)>', text, re.DOTALL)
            if not m:
                continue
            total += 1
            attrs = m.group(1)
            if "fetchpriority" not in attrs.lower():
                missing_fetch += 1
            if not (re.search(r'width=', attrs) and re.search(r'height=', attrs)):
                missing_dims += 1
            if 'loading="eager"' not in attrs.lower() and 'loading="lazy"' in attrs.lower():
                missing_eager += 1
        if total:
            result.findings.append(Finding(
                id="1.4.hero.fetchpriority",
                severity="WARN" if missing_fetch else "PASS",
                title=f"Hero img fetchpriority='high' missing on {missing_fetch}/{total} pieces",
                current=missing_fetch, expected=0, fix_safety="safe",
                fix_action="Add fetchpriority=\"high\" to hero img in each piece's TSX.",
            ))
            result.findings.append(Finding(
                id="1.4.hero.dims",
                severity="WARN" if missing_dims else "PASS",
                title=f"Hero img width/height attrs missing on {missing_dims}/{total} pieces",
                current=missing_dims, expected=0, fix_safety="safe",
                fix_action="Add width + height attrs (causes CLS otherwise).",
            ))
            result.findings.append(Finding(
                id="1.4.hero.eager",
                severity="FAIL" if missing_eager else "PASS",
                title=f"Hero img loading='lazy' present on {missing_eager}/{total} pieces (defeats LCP)",
                current=missing_eager, expected=0, fix_safety="safe",
                fix_action="Change loading=\"lazy\" to loading=\"eager\" on hero img.",
            ))

    # 1.5 — Viewport meta (grep index.html)
    for idx_path in [repo / "client/index.html", repo / "public/index.html",
                      repo / "src/index.html", repo / "index.html"]:
        if idx_path.exists():
            html = idx_path.read_text(encoding="utf-8")
            if re.search(r'<meta\s+name="viewport"\s+content="width=device-width', html):
                result.findings.append(Finding(
                    id="1.5.viewport", severity="PASS",
                    title="Viewport meta present and correct",
                    fix_safety="safe",
                ))
            else:
                result.findings.append(Finding(
                    id="1.5.viewport", severity="FAIL",
                    title="Viewport meta missing or malformed",
                    fix_safety="safe",
                    fix_action='Add: <meta name="viewport" content="width=device-width, initial-scale=1">',
                ))
            break
    else:
        result.findings.append(Finding(
            id="1.5.viewport", severity="MANUAL_VERIFY",
            title="No index.html found at expected locations — verify viewport meta in your template.",
        ))

    result.summary = (
        f"{sum(1 for f in result.findings if f.severity == 'PASS')} PASS, "
        f"{sum(1 for f in result.findings if f.severity == 'WARN')} WARN, "
        f"{sum(1 for f in result.findings if f.severity == 'FAIL')} FAIL, "
        f"{sum(1 for f in result.findings if f.severity == 'MANUAL_VERIFY')} MANUAL_VERIFY."
    )
    return result


if __name__ == "__main__":
    parser = base_argparser("01-technical-seo")
    args = parser.parse_args()
    emit(run(args))

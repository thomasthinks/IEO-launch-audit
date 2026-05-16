#!/usr/bin/env python3
"""
Check 02 — Schema.org graph completeness and validity.

Reads the emitted JSON-LD (schema-graph.json) + samples per-page HTML
for embedded <script type="application/ld+json"> blocks. Validates
structural completeness per checks/02-schema-graph.md.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
import json as _json  # alias for clarity in per-page parser

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, find_artifact, load_config, time_check,
)


REQUIRED_PERSON_PROPS = [
    "@id", "@type", "name", "url", "description", "jobTitle",
    "hasOccupation", "knowsAbout", "sameAs", "mainEntityOfPage", "image",
]
REQUIRED_ARTICLE_PROPS = [
    "@type", "@id", "url", "headline", "description", "datePublished",
    "dateModified", "author", "inLanguage", "wordCount", "articleSection",
    "keywords", "isPartOf", "speakable", "image",
]
HIGH_LEVERAGE_ARTICLE_PROPS = [
    "about", "publisher", "copyrightHolder", "copyrightYear", "mentions",
]

# Article + its valid Schema.org subtypes. Per schema.org, all of these
# inherit Article's required properties; check 2.4 should accept any of
# them as a valid article node. Keep the order stable; the first match
# wins when picking a representative subtype label for findings.
ARTICLE_SUBTYPES = [
    "Article",
    "NewsArticle",
    "BlogPosting",
    "ScholarlyArticle",
    "TechArticle",
    "Report",
    "AdvertiserContentArticle",
    "OpinionNewsArticle",
    "SatiricalArticle",
    "BackgroundNewsArticle",
    "AnalysisNewsArticle",
    "AskPublicNewsArticle",
    "ReportageNewsArticle",
    "ReviewNewsArticle",
    "SocialMediaPosting",
    "DiscussionForumPosting",
]

# v0.7 CiTO typed-citation relation markers. Emitter convention: the
# typed-relation prefix appears in the `description` field of each
# citation[] entry, e.g. "[groundedBy] Smith 2024 — proof of foo".
# When `cito_enabled: true` (default), check 2.4d audits coverage.
CITO_RELATION_MARKERS = (
    "[groundedBy]",
    "[extendedBy]",
    "[substantiatedBy]",
    "[contradictedBy]",
    "[discussedIn]",
)

# v0.5 — curated Schema.org rules for offline type validation.
RULES_PATH = Path(__file__).resolve().parent.parent / "references" / "schema-org-rules.json"


def load_schema_rules() -> dict:
    """Load the curated Schema.org rules JSON shipped with the skill.
    Returns {} if missing (validation block becomes a no-op)."""
    try:
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# v0.5 — configurable per-page JSON-LD sample size (check 2.8).
_DEFAULT_JSONLD_SAMPLE_SIZE = 10


def _resolve_jsonld_sample(pages: list, config_value) -> list:
    """Slice the rendered-HTML page list per the jsonld_sample_size config.

    Accepts:
      - integer N (N > 0): first N pages
      - string "all" (case-insensitive): every page
      - None / missing: default of 10
      - any other value (negative, zero, malformed): fall back to default 10
    """
    if config_value is None:
        n = _DEFAULT_JSONLD_SAMPLE_SIZE
    elif isinstance(config_value, str) and config_value.strip().lower() == "all":
        return list(pages)
    elif isinstance(config_value, bool):
        # bool is a subclass of int in Python; treat as malformed.
        n = _DEFAULT_JSONLD_SAMPLE_SIZE
    elif isinstance(config_value, int) and config_value > 0:
        n = config_value
    else:
        n = _DEFAULT_JSONLD_SAMPLE_SIZE
    return list(pages)[:n]


_ISO_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$"
)

# v0.6 — web-validator fallback endpoint (validator.schema.org).
# Unofficial / undocumented / rate-limited. Disabled by default; opt-in via
# config knob `web_validator_fallback: true`. See SKILL.md § Web-validator
# fallback for caveats.
_WEB_VALIDATOR_URL = "https://validator.schema.org/validate"
_WEB_VALIDATOR_TIMEOUT_S = 15
# Google's anti-JSON-hijack prefix — strip before parsing.
_XSSI_PREFIX = b")]}'"


def _post_to_web_validator(jsonld_snippet: str) -> dict | None:
    """POST a JSON-LD snippet (wrapped in a script tag) to validator.schema.org.

    Returns the parsed JSON response on success.
    Returns None if the endpoint is unreachable, times out, returns non-JSON,
    or is otherwise unusable — callers must handle the None case.
    """
    html_body = (
        '<script type="application/ld+json">'
        + jsonld_snippet
        + "</script>"
    )
    data = urllib.parse.urlencode({"html": html_body}).encode("utf-8")
    req = urllib.request.Request(
        _WEB_VALIDATOR_URL,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "IEO-launch-audit/0.6 (+schema-validator-fallback)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_WEB_VALIDATOR_TIMEOUT_S) as resp:
            raw = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    # Strip Google XSSI prefix if present.
    if raw.startswith(_XSSI_PREFIX):
        raw = raw[len(_XSSI_PREFIX):]
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _extract_validator_errors(response: dict) -> list[dict]:
    """Walk a validator.schema.org response and pull each error into a flat list.

    Each item: {type: <@type>, prop: <property|''>, errorType: <code>,
                args: [...], isSevere: bool}.
    Defensive: validator schema may change; missing keys degrade to empty.
    """
    out: list[dict] = []
    if not isinstance(response, dict):
        return out
    for tg in response.get("tripleGroups") or []:
        if not isinstance(tg, dict):
            continue
        type_name = tg.get("type") or tg.get("typeGroup") or "?"
        for node in tg.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            # Node-level errors
            for err in node.get("errors") or []:
                if isinstance(err, dict):
                    out.append({
                        "type": type_name,
                        "prop": "",
                        "errorType": err.get("errorType", "?"),
                        "args": err.get("args", []),
                        "isSevere": bool(err.get("isSevere")),
                    })
            # Property-level errors
            for prop in node.get("properties") or []:
                if not isinstance(prop, dict):
                    continue
                pname = prop.get("pred", "")
                for err in prop.get("errors") or []:
                    if isinstance(err, dict):
                        out.append({
                            "type": type_name,
                            "prop": pname,
                            "errorType": err.get("errorType", "?"),
                            "args": err.get("args", []),
                            "isSevere": bool(err.get("isSevere")),
                        })
    return out


# v1.1 — Speakable passage-length sanity bands.
# Empirical basis: xSeek 1M-query AI Overviews dataset (Zyppy / Rampton
# 2024): 62% of AIO outputs land in 100-300 words; modal band 150-200
# words at 20.3% concentration. Speakable selectors resolving to passages
# outside the 100-300 band aren't matching the structural primitive AI
# engines emit. Frame as INFO (single-source empirical), not WARN/FAIL.
SPEAKABLE_PASSAGE_MIN, SPEAKABLE_PASSAGE_MAX = 100, 300

# v1.2 — wordCount drift tolerance for check 2.4.word_count_drift.
# Source-of-truth is the rendered <article> / <main> / fallback body
# word count; declared wordCount in JSON-LD should track within this
# fraction. Outside the band → WARN — drift this large signals the
# emitter is computing word count from a different source than the
# rendered piece (e.g., raw markdown vs. compiled JSX output, or a
# stale frontmatter snapshot vs. live body).
WORD_COUNT_DRIFT_TOLERANCE = 0.10  # 10%
WORD_COUNT_MIN_BODY = 100  # noise floor — pages with <100 rendered words are skipped


def _resolve_simple_selector_text(html: str, selector: str) -> str | None:
    """Resolve a simple cssSelector against rendered HTML and return the
    inner text content. Stdlib-only; supports a small grammar that covers
    the Speakable patterns this skill recommends:

      - `[attr-name]`          — element with that attribute
      - `[attr="value"]`       — element with attr exactly "value"
      - `#some-id`             — element with id="some-id"
      - `.some-class`          — element whose class list contains some-class
      - `tagname`              — first element of that type

    Returns None when the grammar isn't supported or no element matches.
    Callers must handle the None case; v1.1's word-count audit treats
    unresolvable selectors as MV.
    """
    sel = selector.strip()
    patterns = []
    # [attr] / [attr="value"]
    m = re.match(r'^\[([a-zA-Z][\w-]*)(?:=["\']?([^"\']+)["\']?)?\]$', sel)
    if m:
        attr, val = m.group(1), m.group(2)
        attr_pat = (rf'\s{re.escape(attr)}="{re.escape(val)}"'
                    if val else rf'\s{re.escape(attr)}\b')
        patterns.append(
            rf'<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*{attr_pat}[^>]*>(.*?)</\1>'
        )
    # #id
    m = re.match(r'^#([\w-]+)$', sel)
    if m:
        idv = re.escape(m.group(1))
        patterns.append(
            rf'<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\sid="{idv}"[^>]*>(.*?)</\1>'
        )
    # .class
    m = re.match(r'^\.([\w-]+)$', sel)
    if m:
        cls = re.escape(m.group(1))
        patterns.append(
            rf'<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\sclass="[^"]*\b{cls}\b[^"]*"[^>]*>(.*?)</\1>'
        )
    # tagname
    m = re.match(r'^([a-zA-Z][a-zA-Z0-9]*)$', sel)
    if m:
        tag = re.escape(m.group(1))
        patterns.append(rf'<{tag}\b[^>]*>(.*?)</{tag}>')

    for pat_src in patterns:
        match = re.search(pat_src, html, re.DOTALL | re.IGNORECASE)
        if match:
            # Last capture group is always the inner HTML.
            inner = match.group(match.lastindex)
            return re.sub(r'<[^>]+>', ' ', inner)
    return None


def _count_words(text: str) -> int:
    """Whitespace-split word count after HTML strip."""
    return len([w for w in text.split() if w.strip()])


def _extract_body_words(html: str) -> int | None:
    """Count rendered body words for a piece's HTML. Tries <article>,
    then <main>, then all <p> tags as fallback. Returns None if no
    structural body could be located.

    Conservative: strips `<script>`, `<style>`, `<nav>`, `<aside>`,
    `<header>`, `<footer>`, and `<figure>` blocks before counting so
    page chrome doesn't inflate the count vs the editorial body.
    """
    # Strip non-body sections that don't represent editorial content.
    cleaned = html
    for tag in ("script", "style", "nav", "aside", "header", "footer", "figure"):
        cleaned = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>", " ", cleaned, flags=re.DOTALL | re.IGNORECASE
        )
    # Prefer <article>; fall back to <main>; fall back to concatenated <p>.
    for tag in ("article", "main"):
        m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", cleaned, re.DOTALL | re.IGNORECASE)
        if m:
            inner = re.sub(r"<[^>]+>", " ", m.group(1))
            return _count_words(inner)
    paragraphs = re.findall(r"<p\b[^>]*>(.*?)</p>", cleaned, re.DOTALL | re.IGNORECASE)
    if paragraphs:
        combined = " ".join(re.sub(r"<[^>]+>", " ", p) for p in paragraphs)
        return _count_words(combined)
    return None


def _find_article_with_wordcount(parsed_jsonld) -> dict | None:
    """Walk a parsed JSON-LD object for the first Article-subtype node
    with a `wordCount` property. Searches @graph nesting + root-level.
    Returns None if no such node found."""
    candidates: list = []
    if isinstance(parsed_jsonld, list):
        for item in parsed_jsonld:
            candidates.extend(_walk_for_articles(item))
    else:
        candidates.extend(_walk_for_articles(parsed_jsonld))
    for n in candidates:
        if isinstance(n.get("wordCount"), int):
            return n
    return None


def _walk_for_articles(node) -> list[dict]:
    """Yield Article-subtype dicts from a JSON-LD node (root or nested
    inside @graph). Type check uses ARTICLE_SUBTYPES."""
    out: list[dict] = []
    if not isinstance(node, dict):
        return out
    t = node.get("@type")
    if isinstance(t, str) and t in ARTICLE_SUBTYPES:
        out.append(node)
    elif isinstance(t, list) and any(tt in ARTICLE_SUBTYPES for tt in t if isinstance(tt, str)):
        out.append(node)
    if isinstance(node.get("@graph"), list):
        for child in node["@graph"]:
            out.extend(_walk_for_articles(child))
    return out


def _walk_speakable_nodes(parsed_jsonld) -> list:
    """Yield each Speakable-shape dict found inside a parsed JSON-LD object.
    Handles both Article.speakable inline values and standalone
    SpeakableSpecification nodes nested in @graph."""
    out = []
    if isinstance(parsed_jsonld, list):
        for item in parsed_jsonld:
            out.extend(_walk_speakable_nodes(item))
        return out
    if not isinstance(parsed_jsonld, dict):
        return out
    # @graph
    if isinstance(parsed_jsonld.get("@graph"), list):
        for node in parsed_jsonld["@graph"]:
            out.extend(_walk_speakable_nodes(node))
    # Article-style: speakable property pointing at an object or array
    sp = parsed_jsonld.get("speakable")
    if isinstance(sp, dict):
        out.append(sp)
    elif isinstance(sp, list):
        for s in sp:
            if isinstance(s, dict):
                out.append(s)
    # Standalone SpeakableSpecification
    t = parsed_jsonld.get("@type")
    if t == "SpeakableSpecification" or (isinstance(t, list) and "SpeakableSpecification" in t):
        out.append(parsed_jsonld)
    return out


# v1.3 helpers — used by check 2.4.graph_consolidation + 2.4.schema_text_parity.

# Fields the schema↔text parity check walks. Strings with <3 words are
# skipped (not enough signal); longer fields are checked first-5-words
# against the rendered DOM.
_PARITY_STRING_FIELDS = {
    "name", "headline", "description", "alternativeHeadline",
    "abstract", "articleBody", "creditText", "caption",
}


def _count_cross_id_refs(parsed_blocks: list, page_ids: set) -> int:
    """Count {@id: <some_id>} reference patterns where the id is in
    page_ids. The argument is a list of parsed JSON-LD blocks (each a
    dict or list). Used by check 2.4.graph_consolidation."""
    def walk(obj) -> int:
        if isinstance(obj, dict):
            if len(obj) == 1 and "@id" in obj and obj["@id"] in page_ids:
                return 1
            return sum(walk(v) for v in obj.values())
        if isinstance(obj, list):
            return sum(walk(item) for item in obj)
        return 0
    return sum(walk(b) for b in parsed_blocks)


def _strip_html_to_text(html: str) -> str:
    """Strip <script>, <style>, then all tags. Lowercase + collapse
    whitespace. Used as the parity-check DOM-side reference text."""
    s = re.sub(r"<script\b.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<style\b.*?</style>", " ", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def _walk_string_fields_for_parity(parsed_blocks: list):
    """Yield (path, value) for every JSON-LD string field worth parity-
    checking against the rendered DOM. Skips strings with <3 words
    (not enough signal). Used by check 2.4.schema_text_parity.

    Important: must enter `@graph` and similar JSON-LD container keys to
    reach the actual nodes. Filter is on the LEAF key name (must be in
    _PARITY_STRING_FIELDS), not on whether the path passes through `@`-
    prefixed containers."""
    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                # Don't yield from @-prefixed keys (they're JSON-LD
                # control metadata: @id, @type, @context). But DO recurse
                # into containers like @graph that hold nodes.
                new_path = f"{path}.{k}" if path else k
                if (
                    not k.startswith("@")
                    and k in _PARITY_STRING_FIELDS
                    and isinstance(v, str)
                    and len(v.split()) >= 3
                ):
                    yield (new_path, v)
                if isinstance(v, (dict, list)):
                    yield from walk(v, new_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                yield from walk(item, f"{path}[{i}]")
    for i, b in enumerate(parsed_blocks):
        yield from walk(b, f"block[{i}]")


def _value_matches_type(value, expected_type: str) -> bool:
    """Check a JSON-LD property value against a curated type spec.
    Lenient: an object containing only {@id: URL} satisfies any URL-typed slot."""
    if value is None:
        return False
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "string-or-array":
        if isinstance(value, str):
            return True
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if expected_type == "string-or-array-or-object":
        if isinstance(value, (str, dict)):
            return True
        return isinstance(value, list)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "ISO-date":
        return isinstance(value, str) and bool(_ISO_DATE_RE.match(value))
    if expected_type == "URL":
        if isinstance(value, str):
            return value.startswith(("http://", "https://"))
        if isinstance(value, dict):
            aid = value.get("@id") or value.get("url")
            return isinstance(aid, str) and aid.startswith(("http://", "https://"))
        return False
    if expected_type == "URL-or-array-of-URLs":
        if isinstance(value, str):
            return value.startswith(("http://", "https://"))
        if isinstance(value, list):
            return all(_value_matches_type(v, "URL") for v in value)
        return False
    if expected_type == "URL-or-object":
        return _value_matches_type(value, "URL") or isinstance(value, dict)
    if expected_type == "URL-or-object-or-array":
        if isinstance(value, list):
            return True
        return _value_matches_type(value, "URL") or isinstance(value, dict)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "object-or-array":
        return isinstance(value, (dict, list))
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string-or-array":
        if isinstance(value, str):
            return True
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    # Unknown expected type — be lenient, treat as pass so we don't false-positive.
    return True


def is_absolute_id(at_id: str) -> bool:
    return bool(at_id and at_id.startswith(("http://", "https://")))


def find_graph_artifact(repo: Path, config: dict) -> Path | None:
    return find_artifact(repo, config, "schema_graph_json", [
        "dist/public/schema-graph.json",
        "public/schema-graph.json",
        "out/schema-graph.json",
        "build/schema-graph.json",
        "_site/schema-graph.json",
    ])


def get_nodes_by_type(graph: dict, type_name: str) -> list[dict]:
    """Return all nodes in @graph matching the type."""
    nodes = graph.get("@graph", []) if "@graph" in graph else [graph]
    return [n for n in nodes if n.get("@type") == type_name or (
        isinstance(n.get("@type"), list) and type_name in n["@type"])]


def get_article_nodes(graph: dict) -> list[tuple[dict, str]]:
    """Return (node, subtype_label) for every Article-or-subtype node.

    A node qualifies if any of its @type values (string or list) is in
    ARTICLE_SUBTYPES. The returned subtype_label is the first matching
    subtype in ARTICLE_SUBTYPES priority order — used in finding output
    so audit consumers can see which subtype was emitted.
    """
    nodes = graph.get("@graph", []) if "@graph" in graph else [graph]
    out: list[tuple[dict, str]] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        n_type = n.get("@type")
        if isinstance(n_type, list):
            types = [t for t in n_type if isinstance(t, str)]
        elif isinstance(n_type, str):
            types = [n_type]
        else:
            continue
        # First match in ARTICLE_SUBTYPES order; preserves stable label.
        for sub in ARTICLE_SUBTYPES:
            if sub in types:
                out.append((n, sub))
                break
    return out


def get_first_person(graph: dict) -> dict | None:
    nodes = get_nodes_by_type(graph, "Person")
    return nodes[0] if nodes else None


def get_first_website(graph: dict) -> dict | None:
    nodes = get_nodes_by_type(graph, "WebSite")
    return nodes[0] if nodes else None


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    result = CheckResult(check="02-schema-graph")

    graph_path = find_graph_artifact(repo, config)
    if not graph_path:
        result.findings.append(Finding(
            id="2.0.missing", severity="FAIL",
            title="schema-graph.json artifact not found",
            fix_safety="manual",
            fix_action="Build the site (npm run build / yarn build) to emit schema artifacts, "
                       "or set artifacts.schema_graph_json in .launch-readiness.yml.",
        ))
        return result

    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        result.findings.append(Finding(
            id="2.1.parse", severity="FAIL",
            title="schema-graph.json malformed",
            current=str(e), fix_safety="manual",
        ))
        return result

    result.findings.append(Finding(
        id="2.1.parse", severity="PASS", title="schema-graph.json parses cleanly",
        fix_safety="safe",
    ))

    # 2.2 — WebSite root
    website = get_first_website(graph)
    if website:
        result.findings.append(Finding(
            id="2.2.website", severity="PASS",
            title="WebSite root entity present",
            current=website.get("@id"),
        ))
    else:
        result.findings.append(Finding(
            id="2.2.website", severity="FAIL",
            title="WebSite root entity missing",
            expected="@type: WebSite at /#website with publisher → Person @id",
            fix_safety="manual",
            fix_action="Add a WebSite node to the schema emitter (see checks/02 § Fix 2.2).",
        ))

    # 2.2b — @id absolute URLs
    nodes = graph.get("@graph", [])
    fragment_ids = [n.get("@id") for n in nodes if n.get("@id", "").startswith("#")]
    if fragment_ids:
        result.findings.append(Finding(
            id="2.2.absolute_ids", severity="FAIL",
            title=f"{len(fragment_ids)} entities use fragment-only @ids (silently fragments graph)",
            current=fragment_ids[:5],
            expected="https://example.com/#name format",
            fix_safety="safe",
            fix_action="Prepend canonical_origin to each @id (see checks/02 § Fix 2.3).",
        ))
    else:
        result.findings.append(Finding(
            id="2.2.absolute_ids", severity="PASS",
            title="All @ids are absolute URLs",
        ))

    # 2.3 — Person completeness
    person = get_first_person(graph)
    if person:
        missing = [p for p in REQUIRED_PERSON_PROPS if p not in person]
        if not missing:
            result.findings.append(Finding(
                id="2.3.person.complete", severity="PASS",
                title="Person entity has all required properties",
            ))
        elif len(missing) <= 2:
            result.findings.append(Finding(
                id="2.3.person.partial", severity="WARN",
                title=f"Person entity missing {len(missing)}: {missing}",
                current=list(person.keys()), expected=REQUIRED_PERSON_PROPS,
                fix_safety="manual",
                fix_action="Add missing properties to Person (see checks/02 § Fix 2.4).",
            ))
        else:
            result.findings.append(Finding(
                id="2.3.person.incomplete", severity="FAIL",
                title=f"Person entity missing {len(missing)} required properties: {missing}",
                current=list(person.keys()),
                fix_safety="manual",
                fix_action="Add hasOccupation, mainEntityOfPage, image refs to Person.",
            ))

        # sameAs includes Wikidata?
        same_as = person.get("sameAs") or []
        if any("wikidata.org" in str(s).lower() for s in same_as):
            result.findings.append(Finding(
                id="2.3.person.wikidata", severity="PASS",
                title="Person.sameAs includes Wikidata URL",
            ))
        else:
            result.findings.append(Finding(
                id="2.3.person.wikidata", severity="WARN",
                title="Person.sameAs missing Wikidata URL",
                current=same_as,
                fix_safety="manual",
                fix_action="Add https://www.wikidata.org/wiki/Q<NNNN> to sameAs (see check 05).",
            ))
    else:
        result.findings.append(Finding(
            id="2.3.person.missing", severity="FAIL",
            title="No Person entity found in schema-graph.json",
            fix_safety="manual",
        ))

    # 2.4 — Article completeness (sample first 10 articles)
    # Accept any node whose @type is in ARTICLE_SUBTYPES per Schema.org's
    # Article hierarchy (Article, NewsArticle, BlogPosting,
    # ScholarlyArticle, TechArticle, Report, etc.).
    article_pairs = get_article_nodes(graph)
    articles = [a for a, _ in article_pairs]
    subtype_counts: dict[str, int] = {}
    for _, sub in article_pairs:
        subtype_counts[sub] = subtype_counts.get(sub, 0) + 1
    subtype_summary = ", ".join(f"{k}={v}" for k, v in sorted(subtype_counts.items(), key=lambda x: -x[1]))
    if not articles:
        result.findings.append(Finding(
            id="2.4.article.none", severity="FAIL",
            title="No Article-subtype nodes in schema-graph.json",
            expected=f"At least one node with @type in {ARTICLE_SUBTYPES[:6]}…",
            fix_safety="manual",
        ))
    else:
        sample_pairs = article_pairs[:10]
        sample = [a for a, _ in sample_pairs]
        agg_missing_required = 0
        agg_missing_high = 0
        for a in sample:
            agg_missing_required += sum(1 for p in REQUIRED_ARTICLE_PROPS if p not in a)
            agg_missing_high += sum(1 for p in HIGH_LEVERAGE_ARTICLE_PROPS if p not in a)
        avg_missing_required = agg_missing_required / len(sample)
        avg_missing_high = agg_missing_high / len(sample)
        result.findings.append(Finding(
            id="2.4.article.required",
            severity="FAIL" if avg_missing_required >= 3 else ("WARN" if avg_missing_required >= 1 else "PASS"),
            title=f"Article required-property completeness: avg {avg_missing_required:.1f}/{len(REQUIRED_ARTICLE_PROPS)} missing per article (sample of {len(sample)} of {len(articles)})",
            current=subtype_summary,
            fix_safety="manual",
            fix_action="Expand schema emitter Article output (see checks/02 § Fix 2.4).",
        ))
        result.findings.append(Finding(
            id="2.4.article.high_leverage",
            severity="WARN" if avg_missing_high >= 3 else ("INFO" if avg_missing_high >= 1 else "PASS"),
            title=f"Article high-leverage-property completeness: avg {avg_missing_high:.1f}/{len(HIGH_LEVERAGE_ARTICLE_PROPS)} missing (sample of {len(sample)})",
            current=subtype_summary,
            fix_safety="manual",
            fix_action="Add about (DefinedTerm), publisher, copyrightHolder, copyrightYear, mentions.",
        ))

        # 2.4b — Speakable selector array.
        #
        # v1.2.1 severity gate: Speakable is officially **beta** at Google
        # and only consumed by Google Assistant for US-English news.
        # Confirmed in 2026: NOT used by AI Overviews / AI Mode for
        # summarization. For consumers outside US-news-English context,
        # the array-vs-single-selector finding demotes from WARN to INFO
        # (Speakable still helps a niche surface, but isn't load-bearing).
        # When the consumer explicitly declares `news_publisher_us_english:
        # true` in .launch-readiness.yml, prior WARN behaviour is preserved.
        is_us_news = bool(config.get("news_publisher_us_english", False))
        speakable_warn_sev = "WARN" if is_us_news else "INFO"
        with_speakable = [a for a in sample if "speakable" in a]
        if with_speakable:
            arr_count = sum(1 for a in with_speakable
                            if isinstance(a["speakable"].get("cssSelector"), list)
                            and len(a["speakable"]["cssSelector"]) > 1)
            if arr_count == len(with_speakable):
                result.findings.append(Finding(
                    id="2.4.speakable", severity="PASS",
                    title="Speakable cssSelector is array of multiple selectors",
                ))
            else:
                result.findings.append(Finding(
                    id="2.4.speakable", severity=speakable_warn_sev,
                    title=f"Speakable cssSelector is single selector on {len(with_speakable) - arr_count}/{len(with_speakable)} sampled articles",
                    expected="Array of 2+ shallow selectors for resilient extraction",
                    fix_safety="safe",
                    fix_action="Set cssSelector to ['[data-thesis-block]', 'h1', '[data-pull-quote]'].",
                    notes=(
                        "Speakable is beta + Google-Assistant-only (US English news). "
                        "Not used by AI Overviews / AI Mode for summarization. "
                        "Severity defaults to INFO outside US-news-English context; "
                        "set `news_publisher_us_english: true` in .launch-readiness.yml "
                        "to restore WARN."
                    ),
                ))

        # 2.4c — mentions[] as @id refs (not inline objects)
        with_mentions = [a for a in sample if a.get("mentions")]
        if with_mentions:
            uses_refs = sum(
                1 for a in with_mentions
                if all(isinstance(m, dict) and len(m) == 1 and "@id" in m for m in a["mentions"])
            )
            if uses_refs == len(with_mentions):
                result.findings.append(Finding(
                    id="2.4.mentions.refs", severity="PASS",
                    title="mentions[] uses @id refs",
                ))
            else:
                result.findings.append(Finding(
                    id="2.4.mentions.refs", severity="WARN",
                    title=f"{len(with_mentions) - uses_refs}/{len(with_mentions)} articles use inline mentions[] objects",
                    fix_safety="safe",
                    fix_action="Emit mentions[] entries as @id refs to other Article @ids.",
                ))

        # 2.4d — CiTO typed-citation relation coverage (v1.1).
        # When cito_enabled=true (default), audit how many citation[] entries
        # carry a typed-relation marker in their description field. Skipped
        # when the consumer has opted out via `cito_enabled: false` (for
        # tooling that chokes on multi-@context JSON-LD or for sites that
        # prefer vanilla schema.org citation arrays).
        if config.get("cito_enabled", True) is False:
            result.findings.append(Finding(
                id="2.4.cito_coverage", severity="INFO",
                title="CiTO typed-citation coverage check suppressed (cito_enabled: false in config)",
                notes="Vanilla schema.org citation[] arrays accepted without typed-relation richness.",
            ))
        else:
            with_citation = [a for a in sample if a.get("citation")]
            if with_citation:
                total_cites = 0
                typed_cites = 0
                for a in with_citation:
                    for c in a.get("citation", []) or []:
                        if not isinstance(c, dict):
                            continue
                        total_cites += 1
                        desc = c.get("description", "") or ""
                        if any(m in desc for m in CITO_RELATION_MARKERS):
                            typed_cites += 1
                if total_cites > 0:
                    pct = typed_cites * 100 / total_cites
                    severity = "PASS" if pct >= 80 else "WARN"
                    result.findings.append(Finding(
                        id="2.4.cito_coverage", severity=severity,
                        title=(
                            f"{typed_cites}/{total_cites} ({pct:.0f}%) citation[] entries "
                            f"carry a CiTO typed-relation marker"
                        ),
                        expected="≥80% with [groundedBy] / [extendedBy] / [substantiatedBy] / [contradictedBy] / [discussedIn]",
                        fix_safety="manual",
                        fix_action=(
                            "Expand the schema emitter to tag each citation[] entry's "
                            "description with a CiTO relation prefix. Drop the check via "
                            "`cito_enabled: false` if the consumer prefers vanilla schema.org."
                        ),
                        notes=(
                            "CiTO relations are scoped to the description field so the "
                            "JSON-LD remains schema.org-valid without requiring a cito: "
                            "@context prefix."
                        ),
                    ))

        # 2.4.about_mentions_usage — `about` vs `mentions` usage (v1.3).
        # Schema.org defines `about` = 1-3 primary entities the page IS
        # about; `mentions` = secondary references. NO Google primary doc
        # differentiates ranking weight (Mueller on record: Google
        # "rarely learns anything unique from structured data"). Advisory
        # only; INFO-tier. Surfaces three signals:
        #   - articles with `mentions` but no `about` (likely-misused);
        #   - articles with `about` array length > 3 (over-broad);
        #   - articles with no `about` at all (typical for thin-emitter
        #     consumers; expected on most sites that haven't adopted the
        #     entity-linking pattern).
        sample_n = len(sample)
        with_about = [a for a in sample if a.get("about")]
        with_mentions_only = [
            a for a in sample
            if a.get("mentions") and not a.get("about")
        ]
        about_over_broad = [
            a for a in sample
            if isinstance(a.get("about"), list) and len(a["about"]) > 3
        ]
        if not with_about and sample_n > 0:
            result.findings.append(Finding(
                id="2.4.about_mentions_usage", severity="INFO",
                title=(
                    f"0/{sample_n} sampled articles emit `about` "
                    "(entity-linking signal missing)"
                ),
                fix_safety="manual",
                fix_action=(
                    "Add `about` to Article schema referencing the 1-3 "
                    "primary DefinedTerm / Person / Place / Organization "
                    "entities the piece IS about. Distinct from `mentions` "
                    "(secondary references). Advisory: no Google primary "
                    "doc confirms `about` ranking weight, but the semantic "
                    "distinction is the entity-linking best practice."
                ),
                notes="Practitioner consensus + schema.org definition; not Google-confirmed weighting.",
            ))
        elif with_mentions_only:
            result.findings.append(Finding(
                id="2.4.about_mentions_usage", severity="INFO",
                title=(
                    f"{len(with_mentions_only)}/{sample_n} sampled articles use "
                    "`mentions` but no `about` (entity-linking inverted)"
                ),
                current=[a.get("@id", "?") for a in with_mentions_only[:5]],
                fix_safety="manual",
                fix_action=(
                    "Consider lifting 1-3 primary entities from mentions[] "
                    "into about[]. about = what the piece IS about; "
                    "mentions = secondary references."
                ),
            ))
        elif about_over_broad:
            result.findings.append(Finding(
                id="2.4.about_mentions_usage", severity="INFO",
                title=(
                    f"{len(about_over_broad)}/{sample_n} sampled articles have "
                    "`about` array > 3 entries (over-broad)"
                ),
                current=[
                    f"{a.get('@id', '?')} (about×{len(a['about'])})"
                    for a in about_over_broad[:5]
                ],
                fix_safety="manual",
                fix_action=(
                    "Narrow `about` to 1-3 primary entities. Move secondary "
                    "entities to `mentions`. The about/mentions split is the "
                    "entity-linking discipline."
                ),
            ))
        elif with_about:
            result.findings.append(Finding(
                id="2.4.about_mentions_usage", severity="PASS",
                title=(
                    f"{len(with_about)}/{sample_n} sampled articles emit `about` "
                    "with disciplined entity counts (1-3 primary entities)"
                ),
            ))

    # 2.5 — CollectionPage → ItemList
    collections = get_nodes_by_type(graph, "CollectionPage")
    if collections:
        with_itemlist = sum(1 for c in collections
                            if isinstance(c.get("mainEntity"), dict)
                            and c["mainEntity"].get("@type") == "ItemList")
        if with_itemlist == len(collections):
            result.findings.append(Finding(
                id="2.5.collection.itemlist", severity="PASS",
                title=f"All {len(collections)} CollectionPages nest ItemList in mainEntity",
            ))
        else:
            result.findings.append(Finding(
                id="2.5.collection.itemlist", severity="WARN",
                title=f"{len(collections) - with_itemlist}/{len(collections)} CollectionPages missing ItemList",
                fix_safety="safe",
                fix_action="Add mainEntity → ItemList with numberOfItems + itemListElement[].",
            ))

    # 2.6 — ProfilePage hasPart
    profiles = get_nodes_by_type(graph, "ProfilePage")
    if profiles:
        with_haspart = sum(1 for p in profiles if p.get("hasPart"))
        if with_haspart:
            result.findings.append(Finding(
                id="2.6.profile.haspart", severity="PASS",
                title="ProfilePage has hasPart (Article @id refs)",
            ))
        else:
            result.findings.append(Finding(
                id="2.6.profile.haspart", severity="WARN",
                title="ProfilePage missing hasPart linkage to authored Articles",
                fix_safety="safe",
                fix_action="Add hasPart: [{@id: article_1_id}, ...] referencing every authored piece.",
            ))

    # 2.7 — ImageObject for hero
    images = get_nodes_by_type(graph, "ImageObject")
    if articles and len(images) < len(articles) * 0.5:
        result.findings.append(Finding(
            id="2.7.imageobject", severity="WARN",
            title=f"Only {len(images)} ImageObject nodes for {len(articles)} articles (expect 1 per hero)",
            fix_safety="safe",
            fix_action="Emit ImageObject per piece's hero with @id, width, height, creditText.",
        ))
    elif images:
        result.findings.append(Finding(
            id="2.7.imageobject", severity="PASS",
            title=f"{len(images)} ImageObject nodes (likely heroes wired)",
        ))

    # 2.9 — Schema.org type-vocabulary validation (v0.5, offline).
    # Walks @graph and checks each node against the curated rules JSON:
    #   - required properties per @type
    #   - property values match the curated type spec
    #   - deprecated / mis-spelled properties
    rules = load_schema_rules()
    if rules:
        type_required = rules.get("type_required_props", {})
        value_types = rules.get("property_value_types", {})
        deprecated = rules.get("deprecated_properties", {})

        all_nodes = graph.get("@graph", []) if "@graph" in graph else [graph]

        type_required_misses: list[tuple[str, str, list[str]]] = []  # (node_id, type, missing)
        value_type_misses: list[tuple[str, str, str, str]] = []     # (node_id, type, prop, expected)
        deprecated_hits: list[tuple[str, str, str]] = []            # (node_id, type, prop)

        for node in all_nodes:
            if not isinstance(node, dict):
                continue
            n_type = node.get("@type")
            if isinstance(n_type, list):
                types = [t for t in n_type if isinstance(t, str)]
            elif isinstance(n_type, str):
                types = [n_type]
            else:
                continue
            n_id = str(node.get("@id") or node.get("url") or "<no-id>")

            # Required-properties check (per matching curated type)
            for t in types:
                req = type_required.get(t)
                if not req:
                    continue
                missing = [p for p in req if p not in node]
                if missing:
                    type_required_misses.append((n_id, t, missing))

            # Value-type check for known properties
            for prop, val in node.items():
                if prop.startswith("@") and prop != "@id":
                    continue
                expected = value_types.get(prop)
                if not expected:
                    continue
                if not _value_matches_type(val, expected):
                    value_type_misses.append((n_id, types[0] if types else "?", prop, expected))

            # Deprecated-properties check
            for prop in node.keys():
                if prop in deprecated:
                    deprecated_hits.append((n_id, types[0] if types else "?", prop))

        # Emit findings
        if type_required_misses:
            sample = [
                f"{t}@{nid}: missing {miss}"
                for nid, t, miss in type_required_misses[:5]
            ]
            result.findings.append(Finding(
                id="2.9.types_required",
                severity="FAIL" if len(type_required_misses) >= 3 else "WARN",
                title=f"{len(type_required_misses)} nodes missing Schema.org-required properties for their @type",
                current=sample,
                expected="Each @type must include the curated required-props set (see references/schema-org-rules.json).",
                fix_safety="manual",
                fix_action="Expand schema emitter to populate every required property for the affected @types.",
            ))
        else:
            result.findings.append(Finding(
                id="2.9.types_required", severity="PASS",
                title="All graph nodes include required properties for their @type (per curated rules)",
            ))

        if value_type_misses:
            sample = [
                f"{t}@{nid}.{prop}: not {exp}"
                for nid, t, prop, exp in value_type_misses[:5]
            ]
            result.findings.append(Finding(
                id="2.9.value_types",
                severity="FAIL" if len(value_type_misses) >= 5 else "WARN",
                title=f"{len(value_type_misses)} property values don't match expected Schema.org type",
                current=sample,
                expected="Property values must match the curated type spec (see references/schema-org-rules.json).",
                fix_safety="manual",
                fix_action="Coerce ISO-dates / integers / URLs in the schema emitter to the correct JSON type.",
            ))
        else:
            result.findings.append(Finding(
                id="2.9.value_types", severity="PASS",
                title="All checked property values match Schema.org curated type spec",
            ))

        if deprecated_hits:
            sample = [
                f"{t}@{nid}.{prop}: {deprecated.get(prop, '')}"
                for nid, t, prop in deprecated_hits[:5]
            ]
            result.findings.append(Finding(
                id="2.9.deprecated",
                severity="WARN",
                title=f"{len(deprecated_hits)} uses of deprecated / misspelled Schema.org properties",
                current=sample,
                fix_safety="manual",
                fix_action="Remove or rename deprecated property names in the schema emitter.",
            ))
        else:
            result.findings.append(Finding(
                id="2.9.deprecated", severity="PASS",
                title="No deprecated Schema.org properties used",
            ))

    # 2.10 — web-validator fallback for @types not covered by curated rules.
    # v0.6 opt-in: posts uncovered-type nodes to validator.schema.org and
    # surfaces each validator-flagged error as a finding. Off by default;
    # enable with `web_validator_fallback: true`. Network-bound + unofficial
    # endpoint — degrades to a MANUAL_VERIFY finding on any failure mode.
    if config.get("web_validator_fallback") is True:
        rules_for_fallback = load_schema_rules()
        covered_types = set((rules_for_fallback.get("type_required_props") or {}).keys())
        all_nodes = graph.get("@graph", []) if "@graph" in graph else [graph]

        uncovered: list[dict] = []
        uncovered_types: set[str] = set()
        for node in all_nodes:
            if not isinstance(node, dict):
                continue
            n_type = node.get("@type")
            if isinstance(n_type, list):
                node_types = [t for t in n_type if isinstance(t, str)]
            elif isinstance(n_type, str):
                node_types = [n_type]
            else:
                continue
            # A node is uncovered iff NONE of its @types appear in curated rules.
            if node_types and not any(t in covered_types for t in node_types):
                uncovered.append(node)
                for t in node_types:
                    uncovered_types.add(t)

        if not uncovered:
            result.findings.append(Finding(
                id="2.10.web_validator", severity="PASS",
                title="No uncovered @types found; web-validator fallback not needed",
                notes="All graph nodes match curated offline rules in references/schema-org-rules.json.",
            ))
        else:
            # Cap at 25 uncovered nodes per run to bound network calls + reduce
            # rate-limit risk against an unofficial endpoint.
            sample_uncovered = uncovered[:25]
            # POST the uncovered subset as a fresh @graph so the validator only
            # sees out-of-scope types.
            payload = json.dumps({
                "@context": "https://schema.org",
                "@graph": sample_uncovered,
            }, default=str)
            response = _post_to_web_validator(payload)

            if response is None:
                result.findings.append(Finding(
                    id="2.10.web_validator", severity="MANUAL_VERIFY",
                    title=(
                        f"web-validator fallback config'd ON but endpoint unreachable / "
                        f"undocumented; {len(uncovered)} uncovered-type node(s) need manual review"
                    ),
                    current=sorted(uncovered_types),
                    expected="HTTP 200 + JSON response from validator.schema.org/validate",
                    fix_safety="manual",
                    fix_action=(
                        "Run validator.schema.org/validate manually against schema-graph.json "
                        "or expand references/schema-org-rules.json to cover these @types offline."
                    ),
                    notes=(
                        "validator.schema.org is hosted by Google as an unofficial service "
                        "with rate limits (429 after ~50 reqs/hr) and no API contract. "
                        "Repeat failures are expected; fall back to offline curated rules."
                    ),
                ))
            else:
                errors = _extract_validator_errors(response)
                num_objects = response.get("numObjects", 0)
                total_errors = response.get("totalNumErrors", 0)
                total_warnings = response.get("totalNumWarnings", 0)

                if not errors and total_errors == 0:
                    result.findings.append(Finding(
                        id="2.10.web_validator", severity="PASS",
                        title=(
                            f"validator.schema.org accepted {num_objects} uncovered-type node(s) "
                            f"({sorted(uncovered_types)}) with 0 errors / {total_warnings} warnings"
                        ),
                        notes="Endpoint is unofficial; treat as advisory rather than authoritative.",
                    ))
                else:
                    sample_err_lines = [
                        f"{e['type']}.{e['prop'] or '<node>'}: {e['errorType']} {e['args']}"
                        for e in errors[:5]
                    ]
                    severity = "WARN"
                    # If every reported error is marked severe, escalate to FAIL.
                    if errors and all(e["isSevere"] for e in errors):
                        severity = "FAIL"
                    result.findings.append(Finding(
                        id="2.10.web_validator",
                        severity=severity,
                        title=(
                            f"validator.schema.org flagged {len(errors)} issue(s) across "
                            f"{num_objects} uncovered-type node(s) ({sorted(uncovered_types)})"
                        ),
                        current=sample_err_lines,
                        expected="0 errors from validator.schema.org for these @types",
                        fix_safety="manual",
                        fix_action=(
                            "Inspect the flagged properties on the listed @types in the schema "
                            "emitter; the validator is unofficial so cross-check against the "
                            "Schema.org type page before treating as authoritative."
                        ),
                        notes=(
                            f"Validator response: numObjects={num_objects}, "
                            f"totalNumErrors={total_errors}, totalNumWarnings={total_warnings}. "
                            "Endpoint has no API contract; output shape may change without notice."
                        ),
                    ))

    # v0.4 — per-piece JSON-LD validation sampling
    # Look for rendered HTML in dist/ or out/ and extract inline JSON-LD
    # from each. Verify it's structurally consistent with the consolidated graph.
    html_roots = ["dist/public/writing", "out/writing", "_site/writing", "public/writing"]
    html_root = None
    for r in html_roots:
        d = repo / r
        if d.exists():
            html_root = d
            break

    if html_root:
        all_html_pages = list(html_root.rglob("index.html"))
        sample_html = _resolve_jsonld_sample(all_html_pages, config.get("jsonld_sample_size"))
        missing_jsonld = 0
        malformed_jsonld = 0
        valid_jsonld = 0
        # 2.4.speakable_passage_length tracking (v1.1) — collect word
        # counts for every resolvable Speakable cssSelector across the
        # sampled pages. Outside-band counts are emitted as INFO, not
        # WARN: empirical basis is single-source (xSeek AIO dataset).
        speakable_word_counts: list[tuple[str, int]] = []  # (page_path, words)
        speakable_unresolved: list[tuple[str, str]] = []  # (page_path, selector)
        # 2.4.word_count_drift tracking (v1.2) — per-page (declared, actual)
        # wordCount comparison. Each entry is (page_path, declared, actual).
        word_count_drift: list[tuple[str, int, int]] = []
        word_count_ok: int = 0
        # 2.4.graph_consolidation tracking (v1.3) — NLWeb readiness signal.
        # Per-page: total inline JSON-LD blocks; presence of @graph wrapper;
        # cross-@id reference count. Fragmented = >1 block or no @graph wrapper.
        graph_block_counts: list[int] = []     # one entry per parsed page
        graph_uses_at_graph: list[bool] = []   # whether the page's blocks
                                               #   include an @graph wrapper
        graph_cross_refs_total: int = 0
        # 2.4.schema_text_parity tracking (v1.3) — JSON-LD string fields not
        # present in the rendered DOM. LLM fetchers tokenize JSON-LD as raw
        # text, but Google policy + SearchVIU/DuckTest evidence converge on
        # "schema not mirrored in visible HTML is functionally invisible."
        parity_checked: int = 0
        parity_missing: list[tuple[str, str, str]] = []   # (page, path, value)
        for h in sample_html:
            html_text = h.read_text(encoding="utf-8")
            # Find ALL JSON-LD blocks on the page (was: first only). Per-page
            # missing/malformed counts now respect any-block-malformed semantics.
            blocks = re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                html_text, re.DOTALL,
            )
            if not blocks:
                missing_jsonld += 1
                continue
            parsed_blocks: list = []
            any_malformed = False
            for b in blocks:
                try:
                    parsed_blocks.append(json.loads(b))
                except json.JSONDecodeError:
                    any_malformed = True
            if any_malformed:
                malformed_jsonld += 1
                continue
            valid_jsonld += 1
            graph_block_counts.append(len(blocks))
            # 2.4.graph_consolidation — does ANY of this page's blocks carry
            # an @graph wrapper? And how many cross-@id refs are visible
            # within the parsed graph?
            has_graph_wrapper = False
            page_ids: set = set()
            for pb in parsed_blocks:
                if isinstance(pb, dict) and isinstance(pb.get("@graph"), list):
                    has_graph_wrapper = True
                    for node in pb["@graph"]:
                        if isinstance(node, dict) and node.get("@id"):
                            page_ids.add(node["@id"])
            graph_uses_at_graph.append(has_graph_wrapper)
            # Count cross-@id refs ({@id: ...} that points at a page-local @id).
            graph_cross_refs_total += _count_cross_id_refs(parsed_blocks, page_ids)
            # For wordCount + Speakable + parity, treat the union of all
            # parsed blocks as the page's effective JSON-LD payload.
            for parsed in parsed_blocks:
                # 2.4.word_count_drift — declared wordCount vs rendered body.
                # Skip pages with very short rendered bodies (noise floor) and
                # pages whose Article emitter doesn't declare wordCount.
                wc_node = _find_article_with_wordcount(parsed)
                if wc_node is not None:
                    declared_wc = wc_node.get("wordCount")
                    actual_wc = _extract_body_words(html_text)
                    if (
                        isinstance(declared_wc, int)
                        and actual_wc is not None
                        and actual_wc >= WORD_COUNT_MIN_BODY
                    ):
                        drift = abs(declared_wc - actual_wc) / actual_wc
                        if drift > WORD_COUNT_DRIFT_TOLERANCE:
                            word_count_drift.append((str(h), declared_wc, actual_wc))
                        else:
                            word_count_ok += 1
                # Walk Speakable nodes and resolve their cssSelectors against
                # this page's HTML.
                for sp_node in _walk_speakable_nodes(parsed):
                    sel = sp_node.get("cssSelector")
                    if isinstance(sel, str):
                        selectors = [sel]
                    elif isinstance(sel, list):
                        selectors = [s for s in sel if isinstance(s, str)]
                    else:
                        selectors = []
                    for s in selectors:
                        text = _resolve_simple_selector_text(html_text, s)
                        if text is None:
                            speakable_unresolved.append((str(h), s))
                            continue
                        words = _count_words(text)
                        if words > 0:
                            speakable_word_counts.append((str(h), words))
            # 2.4.schema_text_parity — strip rendered HTML, walk JSON-LD
            # string fields, check first-5-words signal is present in DOM.
            stripped = _strip_html_to_text(html_text)
            for spath, sval in _walk_string_fields_for_parity(parsed_blocks):
                parity_checked += 1
                sig = " ".join(sval.split()[:5]).lower()
                if sig and sig not in stripped:
                    parity_missing.append((str(h), spath, sval[:80]))
        if sample_html:
            sample_n = len(sample_html)
            if missing_jsonld > 0:
                result.findings.append(Finding(
                    id="2.8.perpage.missing", severity="FAIL",
                    title=f"{missing_jsonld}/{sample_n} sampled rendered HTML pages have NO inline JSON-LD",
                    fix_safety="manual",
                    fix_action="Verify the prerender / SSG pipeline injects per-page <script type='application/ld+json'>.",
                ))
            if malformed_jsonld > 0:
                result.findings.append(Finding(
                    id="2.8.perpage.malformed", severity="FAIL",
                    title=f"{malformed_jsonld}/{sample_n} sampled pages have malformed inline JSON-LD",
                    fix_safety="manual",
                    fix_action="Run validator.schema.org on the affected pages.",
                ))
            if valid_jsonld == sample_n:
                result.findings.append(Finding(
                    id="2.8.perpage.valid", severity="PASS",
                    title=f"All {sample_n} sampled rendered pages have valid inline JSON-LD",
                ))

            # 2.4.speakable_passage_length — passage-length distribution
            # across resolved Speakable selectors. Empirical band 100-300
            # words from xSeek 1M-query AI Overviews dataset (2024). Frame
            # findings as INFO (advisory) — single-source empirical, not
            # gating.
            if speakable_word_counts:
                outside = [
                    (p, w) for (p, w) in speakable_word_counts
                    if w < SPEAKABLE_PASSAGE_MIN or w > SPEAKABLE_PASSAGE_MAX
                ]
                inside_n = len(speakable_word_counts) - len(outside)
                if outside:
                    sample_outside = [
                        f"{Path(p).parent.name}/{Path(p).name} ({w}w)"
                        for p, w in outside[:5]
                    ]
                    result.findings.append(Finding(
                        id="2.4.speakable_passage_length", severity="INFO",
                        title=(
                            f"{len(outside)}/{len(speakable_word_counts)} Speakable "
                            f"selectors resolve to passages outside {SPEAKABLE_PASSAGE_MIN}-"
                            f"{SPEAKABLE_PASSAGE_MAX} words (advisory)"
                        ),
                        current=sample_outside,
                        expected=(
                            f"{SPEAKABLE_PASSAGE_MIN}-{SPEAKABLE_PASSAGE_MAX} words "
                            "(matches modal AI Overview output length, xSeek 1M-query dataset 2024)"
                        ),
                        fix_safety="manual",
                        fix_action=(
                            "Reshape the targeted passage to land near 150-200 words. "
                            "Too-short passages provide thin extraction; too-long passages "
                            "exceed the modal AIO output band and reduce reliable extraction."
                        ),
                        notes=(
                            "Single-source empirical (xSeek/Zyppy 1M-query AI Overviews "
                            "analysis). Frame as observability, not a hard rule."
                        ),
                    ))
                else:
                    result.findings.append(Finding(
                        id="2.4.speakable_passage_length", severity="PASS",
                        title=(
                            f"All {inside_n} resolved Speakable passages within "
                            f"{SPEAKABLE_PASSAGE_MIN}-{SPEAKABLE_PASSAGE_MAX} word band"
                        ),
                    ))
            elif speakable_unresolved:
                # Some selectors found but none resolvable by the simple grammar.
                result.findings.append(Finding(
                    id="2.4.speakable_passage_length", severity="MANUAL_VERIFY",
                    title=(
                        f"{len(speakable_unresolved)} Speakable cssSelector(s) used "
                        "compound/non-trivial grammar; passage-length audit skipped"
                    ),
                    current=[s for _p, s in speakable_unresolved[:5]],
                    notes=(
                        "Stdlib selector grammar supports [attr], [attr=value], "
                        "#id, .class, tagname. Compound selectors (descendant, "
                        "child, multiple-class) are out of scope."
                    ),
                ))

            # 2.4.word_count_drift — declared wordCount vs rendered body
            # word count, per sampled page (v1.2). External auditors can't
            # see this drift because they only have the rendered HTML —
            # internally consistent against itself but silently divergent
            # from the schema-graph claim.
            total_wc_checked = word_count_ok + len(word_count_drift)
            if total_wc_checked == 0:
                # No Article-with-wordCount sampled; nothing to compare.
                # Quiet — Article completeness is already audited in 2.4.
                pass
            elif word_count_drift:
                sample_drift = [
                    f"{Path(p).parent.name}/{Path(p).name} (declared {d}, actual {a}, {(abs(d - a) / a) * 100:.0f}% drift)"
                    for p, d, a in word_count_drift[:5]
                ]
                result.findings.append(Finding(
                    id="2.4.word_count_drift", severity="WARN",
                    title=(
                        f"{len(word_count_drift)}/{total_wc_checked} sampled article(s) "
                        f"have declared wordCount drifting >{int(WORD_COUNT_DRIFT_TOLERANCE * 100)}% "
                        "from rendered body"
                    ),
                    current=sample_drift,
                    expected=(
                        f"Declared wordCount within ±{int(WORD_COUNT_DRIFT_TOLERANCE * 100)}% "
                        "of rendered <article>/<main> body word count"
                    ),
                    fix_safety="manual",
                    fix_action=(
                        "Verify the schema emitter computes wordCount from the same "
                        "source as the rendered body (post-MDX compile, not pre-MDX "
                        "source). Stale frontmatter snapshots that survive content "
                        "edits are the most common drift cause."
                    ),
                    notes=(
                        "Body extraction strips <script>/<style>/<nav>/<aside>/"
                        "<header>/<footer>/<figure> before counting. Pages with "
                        f"<{WORD_COUNT_MIN_BODY} rendered words are skipped (noise floor)."
                    ),
                ))
            else:
                result.findings.append(Finding(
                    id="2.4.word_count_drift", severity="PASS",
                    title=(
                        f"All {total_wc_checked} sampled article(s) have declared "
                        f"wordCount within ±{int(WORD_COUNT_DRIFT_TOLERANCE * 100)}% of rendered body"
                    ),
                ))

            # 2.4.graph_consolidation — NLWeb readiness (v1.3).
            # Pages with >1 inline JSON-LD block are fragmented; pages
            # without @graph wrappers don't expose entity relationships
            # cleanly. Both reduce agentic-web/NLWeb readiness. INFO-tier:
            # advisory, not measured-penalty (no controlled-test comparing
            # fragmented vs consolidated citation rates as of 2026-05).
            if graph_block_counts:
                pages_n = len(graph_block_counts)
                fragmented = sum(1 for n in graph_block_counts if n > 1)
                no_wrapper = sum(1 for w in graph_uses_at_graph if not w)
                avg_blocks = sum(graph_block_counts) / pages_n
                avg_refs = graph_cross_refs_total / pages_n
                if fragmented == 0 and no_wrapper == 0 and avg_refs >= 1:
                    result.findings.append(Finding(
                        id="2.4.graph_consolidation", severity="PASS",
                        title=(
                            f"Schema graph consolidated across {pages_n} sampled pages "
                            f"(1 block / @graph wrapper / avg {avg_refs:.1f} cross-@id refs)"
                        ),
                    ))
                else:
                    parts = []
                    if fragmented > 0:
                        parts.append(f"{fragmented}/{pages_n} pages have >1 inline JSON-LD block")
                    if no_wrapper > 0:
                        parts.append(f"{no_wrapper}/{pages_n} pages lack @graph wrapper")
                    if avg_refs < 1:
                        parts.append(f"avg {avg_refs:.1f} cross-@id refs/page (entities not connected)")
                    result.findings.append(Finding(
                        id="2.4.graph_consolidation", severity="INFO",
                        title="Schema graph fragmented: " + "; ".join(parts),
                        current={
                            "avg_blocks_per_page": round(avg_blocks, 2),
                            "avg_cross_refs_per_page": round(avg_refs, 2),
                            "fragmented_pages": fragmented,
                            "pages_missing_graph_wrapper": no_wrapper,
                        },
                        fix_safety="manual",
                        fix_action=(
                            "Consolidate per-page emitter to one @graph block "
                            "with @id cross-references between entities. The "
                            "Yoast 27.1 Schema Aggregator (Mar 2026) + Microsoft "
                            "NLWeb (MS Build 2025) pattern queries one consolidated "
                            "endpoint per site; fragmented per-page JSON-LD is "
                            "harder for agentic-web tooling to consume. "
                            "Advisory only — no measured citation penalty as of 2026-05."
                        ),
                        notes=(
                            "INFO-tier: NLWeb adoption is early (Yoast 27.1 + "
                            "Cloudflare AI Search integrations exist; no controlled "
                            "fragmented-vs-consolidated citation-rate study yet). "
                            "Surface so consumers prep for the agentic-web pattern."
                        ),
                    ))

            # 2.4.schema_text_parity — JSON-LD strings not mirrored in
            # the rendered DOM (v1.3). LLM fetchers tokenize JSON-LD as
            # raw text per SearchVIU 2025 + Williams-Cook "Duck Test"
            # early 2026. Google's General Structured Data Guidelines
            # state: "Don't mark up content that is not visible to readers
            # of the page." Schema-only strings are functionally invisible
            # to AI engines AND a policy violation per Google.
            if parity_checked > 0:
                missing_n = len(parity_missing)
                if missing_n == 0:
                    result.findings.append(Finding(
                        id="2.4.schema_text_parity", severity="PASS",
                        title=(
                            f"All {parity_checked} JSON-LD string fields mirrored "
                            "in rendered DOM"
                        ),
                    ))
                else:
                    # Dedupe by (path, value) so the same Person.description
                    # appearing on N pages collapses to one entry in the
                    # sample.
                    unique = []
                    seen: set = set()
                    for p, path, val in parity_missing:
                        key = (path, val)
                        if key in seen:
                            continue
                        seen.add(key)
                        unique.append((p, path, val))
                    sample_missing = [
                        f"[{path}] '{val}'  (in {Path(p).parent.name}/{Path(p).name})"
                        for p, path, val in unique[:5]
                    ]
                    pct = missing_n * 100 / parity_checked
                    severity = "WARN" if pct >= 50 else "INFO"
                    result.findings.append(Finding(
                        id="2.4.schema_text_parity", severity=severity,
                        title=(
                            f"{missing_n}/{parity_checked} ({pct:.0f}%) JSON-LD "
                            "string fields not found in rendered DOM "
                            f"({len(unique)} unique)"
                        ),
                        current=sample_missing,
                        expected="JSON-LD string fields should mirror visible HTML content",
                        fix_safety="manual",
                        fix_action=(
                            "Ensure each JSON-LD string field (name, headline, "
                            "description, articleBody, about.name) is also present "
                            "in the rendered HTML body. LLM fetchers tokenize "
                            "JSON-LD as raw text — schema-only content is "
                            "functionally invisible to ChatGPT / Claude / Perplexity / "
                            "Gemini per controlled tests (SearchVIU 2025, "
                            "Williams-Cook Duck Test 2026). Also a Google policy "
                            "violation: 'Don't mark up content that is not visible "
                            "to readers of the page.'"
                        ),
                    ))

    result.summary = (
        f"{sum(1 for f in result.findings if f.severity == 'PASS')} PASS, "
        f"{sum(1 for f in result.findings if f.severity == 'WARN')} WARN, "
        f"{sum(1 for f in result.findings if f.severity == 'FAIL')} FAIL"
    )
    return result


if __name__ == "__main__":
    parser = base_argparser("02-schema-graph")
    args = parser.parse_args()
    emit(run(args))

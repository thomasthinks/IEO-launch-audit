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
]

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

        # 2.4b — Speakable selector array
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
                    id="2.4.speakable", severity="WARN",
                    title=f"Speakable cssSelector is single selector on {len(with_speakable) - arr_count}/{len(with_speakable)} sampled articles",
                    expected="Array of 2+ shallow selectors for resilient extraction",
                    fix_safety="safe",
                    fix_action="Set cssSelector to ['[data-thesis-block]', 'h1', '[data-pull-quote]'].",
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
        for h in sample_html:
            html_text = h.read_text(encoding="utf-8")
            m = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html_text, re.DOTALL)
            if not m:
                missing_jsonld += 1
                continue
            try:
                json.loads(m.group(1))
                valid_jsonld += 1
            except json.JSONDecodeError:
                malformed_jsonld += 1
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

#!/usr/bin/env python3
"""
Check 05 — Wikidata entity graph.

Fetches the configured Q-ID via the Wikidata API, inventories present
properties, surfaces gaps + the load-bearing P856 reciprocity edge.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    CheckResult, Finding, base_argparser, emit, find_artifact, load_config, time_check,
)


REQUIRED_PROPS = {
    "P31": "instance of (expect: Q5 human)",
    "P735": "given name",
    "P734": "family name",
    "P106": "occupation",
    "P101": "field of work",
    "P27": "country of citizenship",
    "P21": "sex or gender",
    "P39": "position held",
}
CRITICAL_PROPS = {
    "P856": "official website (reciprocity edge to apex domain)",
}


def fetch_wikidata(qid: str) -> dict | None:
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "IEO-launch-audit/0.2"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def claims_for_prop(entity: dict, qid: str, prop: str) -> list[str]:
    claims = entity.get("entities", {}).get(qid, {}).get("claims", {}).get(prop, [])
    out = []
    for c in claims:
        mainsnak = c.get("mainsnak", {})
        if mainsnak.get("snaktype") != "value":
            continue
        dv = mainsnak.get("datavalue", {}).get("value")
        if isinstance(dv, dict):
            out.append(dv.get("id") or dv.get("text") or dv.get("amount") or str(dv))
        else:
            out.append(str(dv))
    return out


@time_check
def run(args) -> CheckResult:
    repo = Path(args.repo)
    config = load_config(args.config)
    qid = config.get("wikidata_qid", "")
    canonical_origin = config.get("canonical_origin", "")
    result = CheckResult(check="05-wikidata-entity")

    if not qid:
        result.findings.append(Finding(
            id="5.0.config", severity="MANUAL_VERIFY",
            title="wikidata_qid not set in .launch-readiness.yml",
            fix_safety="manual",
            fix_action="Set wikidata_qid: Q<NNNN> in .launch-readiness.yml. "
                       "If author has no Wikidata entry, create one at wikidata.org.",
        ))
        return result

    if not canonical_origin:
        result.findings.append(Finding(
            id="5.0.origin", severity="MANUAL_VERIFY",
            title="canonical_origin not set — cannot verify P856 reciprocity",
            fix_safety="manual",
            fix_action="Set canonical_origin: https://example.com in .launch-readiness.yml.",
        ))

    # Also check that the schema-graph.json's Person.sameAs includes the Q-ID
    graph_path = find_artifact(repo, config, "schema_graph_json", [
        "dist/public/schema-graph.json", "public/schema-graph.json",
    ])
    if graph_path:
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            person = next((n for n in graph.get("@graph", []) if n.get("@type") == "Person"), None)
            if person:
                same_as = person.get("sameAs", [])
                wikidata_url = f"https://www.wikidata.org/wiki/{qid}"
                if wikidata_url in same_as:
                    result.findings.append(Finding(
                        id="5.1.sameas.wikidata", severity="PASS",
                        title="Person.sameAs includes Wikidata Q-ID URL",
                    ))
                else:
                    result.findings.append(Finding(
                        id="5.1.sameas.wikidata", severity="FAIL",
                        title="Person.sameAs does not include Wikidata Q-ID URL",
                        current=same_as, expected=wikidata_url,
                        fix_safety="safe",
                        fix_action=f"Add '{wikidata_url}' to Person.sameAs in schema emitter.",
                    ))
        except Exception:
            pass

    # Fetch Q-ID
    entity = fetch_wikidata(qid)
    if not entity:
        result.findings.append(Finding(
            id="5.2.qid.fetch_failed", severity="MANUAL_VERIFY",
            title=f"Could not fetch Wikidata entity {qid}",
            fix_safety="manual",
            fix_action=f"Verify https://www.wikidata.org/wiki/{qid} loads in browser.",
        ))
        return result

    # 5.2 — P856 reciprocity (highest leverage)
    p856_vals = claims_for_prop(entity, qid, "P856")
    if not p856_vals:
        result.findings.append(Finding(
            id="5.2.p856.missing", severity="FAIL",
            title="P856 (official website) not set on Wikidata",
            fix_safety="manual",
            fix_action=f"Go to https://www.wikidata.org/wiki/{qid} and add P856 → "
                       f"{canonical_origin or '<apex domain>'}. "
                       "This is the highest-leverage entity-graph edge.",
        ))
    else:
        match = canonical_origin and any(canonical_origin.rstrip("/") in v.rstrip("/") for v in p856_vals)
        if match:
            result.findings.append(Finding(
                id="5.2.p856.match", severity="PASS",
                title=f"P856 set and matches canonical_origin: {p856_vals[0]}",
            ))
        else:
            result.findings.append(Finding(
                id="5.2.p856.mismatch", severity="WARN",
                title=f"P856 set but doesn't match canonical_origin",
                current=p856_vals, expected=canonical_origin,
                fix_safety="manual",
                fix_action=f"Update P856 on Wikidata to {canonical_origin}.",
            ))

    # 5.3 — Other required properties
    missing_required = []
    for prop, desc in REQUIRED_PROPS.items():
        vals = claims_for_prop(entity, qid, prop)
        if not vals:
            missing_required.append((prop, desc))

    if missing_required:
        # Short human-readable label = description with any "(...)"" hint stripped.
        # e.g. "instance of (expect: Q5 human)" -> "instance of"
        missing_enum = [f"{p} ({d.split(' (')[0]})" for p, d in missing_required]
        result.findings.append(Finding(
            id="5.3.props.missing",
            severity="WARN" if len(missing_required) <= 4 else "FAIL",
            title=f"Wikidata {qid} missing {len(missing_required)} of {len(REQUIRED_PROPS)} properties: {missing_enum}",
            current=missing_enum,
            fix_safety="manual",
            fix_action=f"Visit https://www.wikidata.org/wiki/{qid} and add: " +
                       ", ".join(f"{p} ({d})" for p, d in missing_required),
        ))
    else:
        result.findings.append(Finding(
            id="5.3.props.complete", severity="PASS",
            title=f"Wikidata {qid} has all {len(REQUIRED_PROPS)} expected properties",
        ))

    # 5.4 — Verify P31 = Q5
    p31_vals = claims_for_prop(entity, qid, "P31")
    if "Q5" in p31_vals:
        result.findings.append(Finding(
            id="5.4.is_human", severity="PASS",
            title=f"{qid} P31 = Q5 (instance of: human)",
        ))
    elif p31_vals:
        result.findings.append(Finding(
            id="5.4.is_human", severity="WARN",
            title=f"{qid} P31 is {p31_vals}, not Q5",
            fix_safety="manual",
        ))

    result.summary = f"Wikidata {qid}: {'P856 OK' if p856_vals else 'P856 MISSING (load-bearing)'}, " \
                     f"{len(REQUIRED_PROPS) - len(missing_required)}/{len(REQUIRED_PROPS)} required props present."
    return result


if __name__ == "__main__":
    parser = base_argparser("05-wikidata-entity")
    args = parser.parse_args()
    emit(run(args))

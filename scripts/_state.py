"""
State-file substrate for IEO-launch-audit Phase A (v1.5, ADR 0002).

Per ADR 0002 Decision 1: audit-diff persistence is the primary measurement
signal across passes. Per Decision 2: state lives in consumer repo as
`.ieo-audit-state.yml`, committed by the operator. Per Decision 3: skill
emits state but never auto-mutates; consumer commits or not.

Reads/writes a versioned YAML state file at repo root. Stdlib-only: uses
PyYAML when available, falls back to a state-file-shape-specific parser
+ emitter when PyYAML is absent. The fallback only handles the schema
actually used here (top-level scalars + a `findings` list of flat dicts)
— it is NOT a general YAML implementation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_FILE_NAME = ".ieo-audit-state.yml"
STATE_VERSION = 1


@dataclass
class StateFinding:
    """Per-finding state tracked across audit passes."""
    id: str
    severity: str           # PASS / WARN / FAIL / INFO / MANUAL_VERIFY / NOT_APPLICABLE
    title: str
    first_seen: str         # ISO timestamp (UTC, Z-suffixed)
    last_seen: str          # ISO timestamp (UTC, Z-suffixed)
    pass_count: int = 1     # consecutive passes finding has been present


@dataclass
class State:
    state_version: int = STATE_VERSION
    skill_version: str = ""
    last_pass_date: str = ""
    findings: list[StateFinding] = field(default_factory=list)

    def find(self, finding_id: str) -> StateFinding | None:
        return next((f for f in self.findings if f.id == finding_id), None)


def state_path(repo: Path) -> Path:
    return repo / STATE_FILE_NAME


def load_state(repo: Path) -> State | None:
    """Load `.ieo-audit-state.yml` from repo root. Returns None if absent
    or unreadable. Degrades gracefully on state-version mismatch (newer
    state-file from a future skill version is treated as absent rather
    than corrupted)."""
    p = state_path(repo)
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        import yaml
        data = yaml.safe_load(text) or {}
    except ImportError:
        data = _yaml_fallback_parse(text)
    except Exception:
        # Malformed YAML — treat as absent (graceful degrade per CLAUDE.md).
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("state_version", 1)
    try:
        version = int(version)
    except (TypeError, ValueError):
        return None
    if version > STATE_VERSION:
        # State file written by a newer skill version. Don't corrupt by
        # overwriting; treat as absent for this pass and let the operator
        # resolve via skill upgrade.
        return None
    findings_raw = data.get("findings", []) or []
    findings: list[StateFinding] = []
    if isinstance(findings_raw, list):
        for f in findings_raw:
            if not isinstance(f, dict):
                continue
            try:
                findings.append(StateFinding(
                    id=str(f.get("id", "")),
                    severity=str(f.get("severity", "")),
                    title=str(f.get("title", "")),
                    first_seen=str(f.get("first_seen", "")),
                    last_seen=str(f.get("last_seen", "")),
                    pass_count=int(f.get("pass_count", 1)),
                ))
            except (TypeError, ValueError):
                continue
    return State(
        state_version=version,
        skill_version=str(data.get("skill_version", "")),
        last_pass_date=str(data.get("last_pass_date", "")),
        findings=findings,
    )


def write_state(repo: Path, state: State) -> Path:
    """Write state to repo root atomically (tmp file + rename). Returns the
    path written."""
    p = state_path(repo)
    out = {
        "state_version": state.state_version,
        "skill_version": state.skill_version,
        "last_pass_date": state.last_pass_date,
        "findings": [asdict(f) for f in state.findings],
    }
    text = _yaml_emit(out)
    tmp = p.with_suffix(".yml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)
    return p


def build_state_from_results(
    skill_version: str,
    results: list[dict],
    prior: State | None,
) -> State:
    """Construct the new state from current-pass audit results, merging
    with prior state to preserve `first_seen` + increment `pass_count`
    where a finding persists.

    `results` is a list of CheckResult-as-dict (from the audit JSON report).
    `prior` is the previously-loaded state (or None for first pass).
    """
    now = _utc_now_iso()
    new_findings: list[StateFinding] = []
    seen_ids: set[str] = set()
    for check_result in results:
        if not isinstance(check_result, dict):
            continue
        for f in check_result.get("findings", []) or []:
            if not isinstance(f, dict):
                continue
            fid = f.get("id")
            if not fid or fid in seen_ids:
                continue
            seen_ids.add(fid)
            sev = f.get("severity", "")
            title = f.get("title", "")
            prior_finding = prior.find(fid) if prior else None
            first_seen = prior_finding.first_seen if prior_finding else now
            pass_count = (prior_finding.pass_count + 1) if prior_finding else 1
            new_findings.append(StateFinding(
                id=str(fid),
                severity=str(sev or ""),
                title=str(title or ""),
                first_seen=first_seen,
                last_seen=now,
                pass_count=pass_count,
            ))
    return State(
        state_version=STATE_VERSION,
        skill_version=skill_version,
        last_pass_date=now,
        findings=new_findings,
    )


def _utc_now_iso() -> str:
    """ISO 8601 UTC timestamp with trailing Z (not +00:00)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --- YAML fallback helpers ----------------------------------------------------
# Used when PyYAML is not importable. Only supports the state-file shape.

def _yaml_emit(data: dict) -> str:
    try:
        import yaml
        return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)
    except ImportError:
        return _yaml_emit_fallback(data)


def _yaml_emit_fallback(data: dict) -> str:
    """Stdlib emitter for the state-file shape only. Schema:
        state_version: <int>
        skill_version: <str>
        last_pass_date: <str>
        findings:
          - id: <str>
            severity: <str>
            title: <str>
            first_seen: <str>
            last_seen: <str>
            pass_count: <int>
    """
    lines: list[str] = []
    for k, v in data.items():
        if k == "findings":
            lines.append(f"{k}:")
            if not v:
                continue
            for finding in v:
                lines.append("- " + _yaml_inline_item_key(finding, first=True))
                for fk, fv in list(finding.items())[1:]:
                    lines.append(f"  {fk}: {_yaml_scalar(fv)}")
        else:
            lines.append(f"{k}: {_yaml_scalar(v)}")
    return "\n".join(lines) + "\n"


def _yaml_inline_item_key(finding: dict, first: bool = False) -> str:
    """Emit the first key:value of a list-item on the same line as the dash."""
    items = list(finding.items())
    if not items:
        return ""
    k, v = items[0]
    return f"{k}: {_yaml_scalar(v)}"


def _yaml_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    needs_quote = (
        s == ""
        or any(c in s for c in (":", "#", "\n", '"', "'", "{", "}", "[", "]"))
        or s.startswith(("-", "?", "!", "&", "*", "|", ">", "%", "@", "`"))
        or s.lower() in ("null", "true", "false", "yes", "no", "on", "off")
    )
    if needs_quote:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def _yaml_fallback_parse(text: str) -> dict:
    """Stdlib parser for the state-file shape. Inverse of _yaml_emit_fallback.
    Tolerant: silently skips lines that don't match the expected shape."""
    out: dict[str, Any] = {}
    current_list: list | None = None
    current_item: dict | None = None
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        if indent == 0:
            current_list = None
            current_item = None
            if ":" in stripped:
                k, _, v = stripped.partition(":")
                k = k.strip()
                v = v.strip()
                if v:
                    out[k] = _parse_scalar(v)
                else:
                    out[k] = []
                    current_list = out[k]
        elif indent == 2 and current_list is not None:
            # Either "- key: value" (start of new list item) or
            # "  key: value" (continuation of current item, won't hit this branch).
            if stripped.startswith("- "):
                rest = stripped[2:].strip()
                current_item = {}
                current_list.append(current_item)
                if ":" in rest:
                    k, _, v = rest.partition(":")
                    current_item[k.strip()] = _parse_scalar(v.strip())
        elif indent == 4 and current_item is not None and ":" in stripped:
            # Continuation key:value of current list item.
            k, _, v = stripped.partition(":")
            current_item[k.strip()] = _parse_scalar(v.strip())
    return out


def _parse_scalar(s: str) -> Any:
    if s == "" or s == "null":
        return None if s == "null" else ""
    if s == "true":
        return True
    if s == "false":
        return False
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s

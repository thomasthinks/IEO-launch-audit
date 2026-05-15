"""
Shared helpers for IEO-launch-audit check scripts.

Each check script is self-contained but imports from this module for
common patterns: arg parsing, config loading, JSON-result emission,
artifact-path resolution. Importable via the repo's PYTHONPATH or
via relative import when called from scripts/audit.sh.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


SEVERITIES = ("PASS", "WARN", "FAIL", "INFO", "MANUAL_VERIFY", "NOT_APPLICABLE")


@dataclass
class Finding:
    id: str  # e.g. "1.1.HSTS"
    severity: str  # PASS / WARN / FAIL / INFO / MANUAL_VERIFY / NOT_APPLICABLE
    title: str
    current: Any = None
    expected: Any = None
    fix_safety: str = "manual"  # safe | manual
    fix_template: str | None = None
    fix_action: str | None = None
    notes: str | None = None


@dataclass
class CheckResult:
    check: str  # e.g. "01-technical-seo"
    status: str = "PASS"  # PASS / WARN / FAIL — overwritten by compute_status() after findings populated
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""
    duration_ms: float = 0
    config_used: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        out = asdict(self)
        out["findings"] = [asdict(f) for f in self.findings]
        return json.dumps(out, indent=2, default=str)


def base_argparser(check_name: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"IEO-launch-audit: {check_name}")
    p.add_argument("--repo", required=True, help="Repo root path")
    p.add_argument("--config", required=True, help="Config YAML path (may not exist)")
    p.add_argument("--stack", default="unknown", help="Detected tech stack")
    return p


def load_config(path: str) -> dict[str, Any]:
    """Load .launch-readiness.yml; tolerate missing file (return {}).

    Post-load normalisation:
    - `live_probe_origin` defaults to `canonical_origin` when unset. This
      preserves backwards-compat with v0.4 configs that only set
      `canonical_origin`. The two are semantically distinct:
        * `canonical_origin` — apex domain used for URL-shape comparisons
          (sitemap <loc> prefix match, Wikidata P856 reconciliation,
          JSON-LD @id checks).
        * `live_probe_origin` — origin the audit can actually curl right
          now (e.g. http://localhost:5000 during pre-flip dev). Used for
          live HTTP header probes, 404-status checks, Lighthouse runs.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except ImportError:
        # Fallback: very loose key:value parser for the common cases.
        cfg = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, _, v = line.partition(":")
            cfg[k.strip()] = v.strip()
    if "live_probe_origin" not in cfg or not cfg.get("live_probe_origin"):
        cfg["live_probe_origin"] = cfg.get("canonical_origin", "")
    return cfg


def find_artifact(repo: Path, config: dict, key: str, default_globs: list[str]) -> Path | None:
    """Look up an artifact path. Config can override; otherwise glob the
    default locations relative to the repo root."""
    artifacts = config.get("artifacts", {})
    if key in artifacts:
        p = repo / artifacts[key]
        return p if p.exists() else None
    for glob in default_globs:
        matches = list(repo.glob(glob))
        if matches:
            return matches[0]
    return None


def severity_rank(s: str) -> int:
    """For computing overall check status from findings."""
    return {"FAIL": 3, "WARN": 2, "MANUAL_VERIFY": 1, "INFO": 0, "PASS": 0, "NOT_APPLICABLE": 0}.get(s, 0)


def compute_status(findings: list[Finding]) -> str:
    """Overall check status = worst finding severity."""
    if not findings:
        return "PASS"
    max_rank = max(severity_rank(f.severity) for f in findings)
    if max_rank >= 3:
        return "FAIL"
    if max_rank >= 2:
        return "WARN"
    if max_rank >= 1:
        return "MANUAL_VERIFY"
    return "PASS"


def emit(result: CheckResult) -> None:
    """Write JSON to stdout. The orchestrator captures this."""
    sys.stdout.write(result.to_json())
    sys.stdout.write("\n")
    sys.stdout.flush()


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def _yaml_fallback_parse(block: str) -> dict[str, Any]:
    """Very loose YAML scalar parser for the frontmatter fallback path.

    Handles only top-level `key: "value"` / `key: value` lines. Drops
    nested structures, lists, multiline blocks. Sufficient for reading
    a handful of date string keys when PyYAML is not installed.
    """
    out: dict[str, Any] = {}
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+?)\s*$", line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        # Strip a single layer of surrounding quotes
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
            raw = raw[1:-1]
        out[key] = raw
    return out


def load_frontmatter(path: Path) -> dict[str, Any] | None:
    """Read a YAML frontmatter block (`---\\n...\\n---`) from the head of
    a file and return it as a dict. Returns None if the file has no
    leading frontmatter block. Uses `yaml` when available; falls back to
    a scalar-only parser otherwise (sufficient for reading date strings).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    block = m.group(1)
    try:
        import yaml
        parsed = yaml.safe_load(block)
        return parsed if isinstance(parsed, dict) else None
    except ImportError:
        return _yaml_fallback_parse(block)
    except Exception:
        # Malformed YAML — degrade rather than crash the check.
        return _yaml_fallback_parse(block)


def find_frontmatter_for_slug(
    repo: Path,
    slug: str,
    patterns: list[str],
) -> Path | None:
    """Locate a frontmatter source file for a slug via configured glob
    patterns. Each pattern may contain `{slug}` as a placeholder.

    Returns the first match across the patterns (in declaration order),
    or None if nothing matched.
    """
    for raw in patterns:
        if not raw:
            continue
        glob = raw.replace("{slug}", slug)
        matches = list(repo.glob(glob))
        if matches:
            return matches[0]
    return None


def time_check(fn):
    """Decorator: measure execution time + emit on completion."""
    def wrapper(*args, **kwargs):
        t0 = time.monotonic()
        result = fn(*args, **kwargs)
        result.duration_ms = (time.monotonic() - t0) * 1000
        result.status = compute_status(result.findings)
        return result
    return wrapper

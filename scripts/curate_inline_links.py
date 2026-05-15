#!/usr/bin/env python3
"""
curate_inline_links.py — driver for the LLM-curated inline-link scaffold.

This script does NOT call any LLM API. It prepares per-batch markdown task
files that a Claude Code subagent (or any LLM operator) can consume.

Why this exists: the prior mechanical pass (TFIDF-distinctive noun-chunk
extraction) injected 385 inline links that had to be reverted on
2026-05-14. The replacement direction is LLM-curated. v0.5 of the
IEO-launch-audit skill ships this scaffold; full curation runs
post-flip.

Pipeline:

  corpus TSX dir  ->  parse (slug, title, body)
                  ->  batch into N chunks
                  ->  for each batch:
                        emit  .curation/batch-NN.md
                              { prompt template
                              ; this batch's pieces (slug + title + body)
                              ; FULL corpus link table }
                  ->  emit .curation/manifest.json (dispatch index)

The operator then runs a subagent against each batch file. The subagent
reads the embedded prompt template and the embedded pieces, and emits
JSON link suggestions. v0.5 stops at scaffold; v0.6+ wires the JSON
back into the site.

Config (read from .launch-readiness.yml at the repo root):

  curation:
    corpus_tsx_dir: client/src/content/writing
    corpus_link_table: null       # optional explicit override; default = derive
    batch_size: 25
    output_dir: .curation
    body_excerpt_words: 0         # 0 = full body; N > 0 = first-N-word excerpt
    canonical_origin: https://thomasjankowski.com   # for the link table URLs

All keys are optional; defaults shown above. The driver runs against any
repo whose TSX bodies follow the
`export const X: Piece = { slug: "...", title: "...", ..., Body, };`
pattern.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from _lib import load_config  # noqa: E402

SKILL_ROOT = SCRIPT_DIR.parent
PROMPT_TEMPLATE_PATH = SKILL_ROOT / "templates" / "curate-inline-links-prompt.md"


# Match `slug: "..."` and `title: "..."` inside a Piece export.
SLUG_RE = re.compile(r'^\s*slug:\s*"([^"]+)"\s*,?\s*$', re.MULTILINE)
TITLE_RE = re.compile(r'^\s*title:\s*"([^"]+)"\s*,?\s*$', re.MULTILINE)

# Match the Body() function. We grab the JSX inside `return (...)` and
# strip tags down to text. This is intentionally loose — we want the
# reading prose, not a perfect AST.
BODY_FUNC_RE = re.compile(r"function\s+Body\s*\(\s*\)\s*\{(.*?)^\}", re.DOTALL | re.MULTILINE)


@dataclass
class Piece:
    slug: str
    title: str
    body_text: str   # stripped-down prose (tags removed)
    word_count: int
    source_path: str

    def excerpt(self, max_words: int) -> str:
        if max_words <= 0 or self.word_count <= max_words:
            return self.body_text
        words = self.body_text.split()
        return " ".join(words[:max_words]) + " [...]"


def strip_jsx_to_text(jsx: str) -> str:
    """Very loose JSX -> prose extractor.

    - Drops everything before the first `<p` (skips hero figure etc).
    - Removes JSX tags entirely.
    - Decodes a small set of HTML entities common in this corpus.
    - Collapses whitespace.

    This is "good enough for an LLM to read." Perfect parsing isn't
    required — the LLM tolerates noise in the input as long as the
    prose is intact.
    """
    # Trim leading hero/figure boilerplate by anchoring at first <p>.
    first_p = jsx.find("<p")
    if first_p > 0:
        jsx = jsx[first_p:]

    # Drop {/* ... */} JSX comments.
    jsx = re.sub(r"\{/\*.*?\*/\}", " ", jsx, flags=re.DOTALL)
    # Drop {expression} JSX braces (usually short — anchors, variables).
    # Keep the inner text best-effort by stripping just the braces when
    # the content is a quoted string; otherwise drop the whole expr.
    jsx = re.sub(r"\{\s*\"([^\"]*)\"\s*\}", r"\1", jsx)
    jsx = re.sub(r"\{\s*'([^']*)'\s*\}", r"\1", jsx)
    jsx = re.sub(r"\{[^{}]*\}", " ", jsx)
    # Strip all remaining tags.
    text = re.sub(r"<[^>]+>", " ", jsx)
    # Decode a handful of common entities.
    text = (text
            .replace("&mdash;", ", ")
            .replace("&ndash;", "-")
            .replace("&amp;", "&")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&apos;", "'")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&nbsp;", " "))
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_piece(path: Path) -> Piece | None:
    """Extract slug, title, and body prose from a single TSX file."""
    try:
        src = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    slug_m = SLUG_RE.search(src)
    title_m = TITLE_RE.search(src)
    body_m = BODY_FUNC_RE.search(src)
    if not (slug_m and title_m and body_m):
        return None

    body_text = strip_jsx_to_text(body_m.group(1))
    if not body_text:
        return None

    return Piece(
        slug=slug_m.group(1),
        title=title_m.group(1),
        body_text=body_text,
        word_count=len(body_text.split()),
        source_path=str(path),
    )


def gather_pieces(corpus_dir: Path) -> list[Piece]:
    pieces: list[Piece] = []
    for tsx in sorted(corpus_dir.glob("*.tsx")):
        p = parse_piece(tsx)
        if p:
            pieces.append(p)
    return pieces


def build_link_table(pieces: list[Piece], canonical_origin: str) -> list[dict[str, str]]:
    """Slug -> title -> URL table for inclusion in every batch file."""
    origin = (canonical_origin or "").rstrip("/")
    rows = []
    for p in pieces:
        url = f"{origin}/writing/{p.slug}" if origin else f"/writing/{p.slug}"
        rows.append({"slug": p.slug, "title": p.title, "url": url})
    return rows


def batch_pieces(pieces: list[Piece], batch_size: int) -> list[list[Piece]]:
    if batch_size <= 0:
        batch_size = 25
    return [pieces[i:i + batch_size] for i in range(0, len(pieces), batch_size)]


def format_link_table_md(table: list[dict[str, str]]) -> str:
    lines = ["| slug | title | url |", "|------|-------|-----|"]
    for row in table:
        # Pipe-escape titles defensively.
        title = row["title"].replace("|", "\\|")
        lines.append(f"| `{row['slug']}` | {title} | {row['url']} |")
    return "\n".join(lines)


def format_batch_md(
    batch_num: int,
    batch_total: int,
    batch: list[Piece],
    link_table: list[dict[str, str]],
    prompt_template: str,
    body_excerpt_words: int,
) -> str:
    """Self-contained batch file for one subagent."""
    parts: list[str] = []
    parts.append(f"# Curation batch {batch_num:02d} of {batch_total:02d}")
    parts.append("")
    parts.append(
        f"This batch contains **{len(batch)} pieces** to curate inline "
        f"links for, plus the full corpus link table. Follow the prompt "
        f"below exactly. Emit one JSON array covering all pieces in "
        f"this batch."
    )
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## Prompt")
    parts.append("")
    parts.append(prompt_template.strip())
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## Full corpus link table")
    parts.append("")
    parts.append(
        "Every link target you suggest MUST appear in this table. The "
        "table is the universe of valid `target_slug` values."
    )
    parts.append("")
    parts.append(format_link_table_md(link_table))
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## Pieces in this batch")
    parts.append("")
    for piece in batch:
        body = piece.excerpt(body_excerpt_words)
        parts.append(f"### `{piece.slug}`")
        parts.append("")
        parts.append(f"**Title:** {piece.title}")
        parts.append("")
        parts.append(f"**Body** ({piece.word_count} words):")
        parts.append("")
        parts.append("> " + body.replace("\n", "\n> "))
        parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(
        "## Output\n\nEmit the JSON array per the prompt. Nothing else."
    )
    parts.append("")
    return "\n".join(parts)


def build_manifest(
    batch_files: list[Path],
    repo: Path,
    corpus_dir: Path,
    batch_size: int,
    body_excerpt_words: int,
    total_pieces: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "skill": "IEO-launch-audit",
        "step": "curate_inline_links",
        "repo": str(repo),
        "corpus_tsx_dir": str(corpus_dir.relative_to(repo)) if corpus_dir.is_relative_to(repo) else str(corpus_dir),
        "total_pieces": total_pieces,
        "batch_size": batch_size,
        "body_excerpt_words": body_excerpt_words,
        "batch_count": len(batch_files),
        "batches": [
            {
                "index": i + 1,
                "path": str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p),
            }
            for i, p in enumerate(batch_files)
        ],
        "invocation_patterns": {
            "parallel_one_shot": (
                "In Claude Code, dispatch one general-purpose subagent per "
                "batch in parallel. Each subagent reads its batch file, "
                "follows the embedded prompt, and emits a JSON array."
            ),
            "recurring": (
                "/loop 1d /curate-links — re-runs the driver weekly/monthly "
                "and dispatches subagents. Slash command is repo-local."
            ),
            "scheduled": (
                "/schedule routine — same flow as /loop, bounded to a "
                "specific cron expression / timestamp."
            ),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prep per-batch curation task files for LLM inline-link curation."
    )
    ap.add_argument("--repo", required=True, help="Repo root path")
    ap.add_argument(
        "--config",
        default=None,
        help="Path to .launch-readiness.yml (default: <repo>/.launch-readiness.yml)",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Override config: number of pieces per batch (default: 25)",
    )
    ap.add_argument(
        "--output-dir",
        default=None,
        help="Override config: where to write batch files (default: <repo>/.curation)",
    )
    ap.add_argument(
        "--body-excerpt-words",
        type=int,
        default=None,
        help="Override config: truncate body to first N words (0 = full body)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write files; report what would be emitted.",
    )
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists():
        print(f"ERROR: repo not found: {repo}", file=sys.stderr)
        return 2

    config_path = Path(args.config) if args.config else repo / ".launch-readiness.yml"
    config = load_config(str(config_path))
    curation_cfg = (config.get("curation") or {}) if isinstance(config, dict) else {}

    corpus_tsx_dir = repo / (curation_cfg.get("corpus_tsx_dir") or "client/src/content/writing")
    batch_size = args.batch_size or int(curation_cfg.get("batch_size") or 25)
    output_dir = Path(args.output_dir) if args.output_dir else repo / (curation_cfg.get("output_dir") or ".curation")
    body_excerpt_words = (
        args.body_excerpt_words
        if args.body_excerpt_words is not None
        else int(curation_cfg.get("body_excerpt_words") or 0)
    )
    canonical_origin = (
        curation_cfg.get("canonical_origin")
        or config.get("canonical_origin")
        or ""
    )

    if not corpus_tsx_dir.exists():
        print(f"ERROR: corpus dir not found: {corpus_tsx_dir}", file=sys.stderr)
        return 2

    if not PROMPT_TEMPLATE_PATH.exists():
        print(f"ERROR: prompt template missing: {PROMPT_TEMPLATE_PATH}", file=sys.stderr)
        return 2

    prompt_template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    pieces = gather_pieces(corpus_tsx_dir)
    if not pieces:
        print(f"ERROR: no parseable pieces found in {corpus_tsx_dir}", file=sys.stderr)
        return 2

    link_table = build_link_table(pieces, canonical_origin)
    batches = batch_pieces(pieces, batch_size)

    # Dry-run report
    if args.dry_run:
        report = {
            "dry_run": True,
            "repo": str(repo),
            "corpus_tsx_dir": str(corpus_tsx_dir),
            "output_dir": str(output_dir),
            "pieces_parsed": len(pieces),
            "batch_size": batch_size,
            "batch_count": len(batches),
            "body_excerpt_words": body_excerpt_words,
            "canonical_origin": canonical_origin or "(unset — relative URLs)",
            "would_write": [
                f"{output_dir}/batch-{i + 1:02d}.md ({len(b)} pieces)"
                for i, b in enumerate(batches)
            ] + [f"{output_dir}/manifest.json"],
            "first_batch_pieces": [
                {"slug": p.slug, "title": p.title, "words": p.word_count}
                for p in batches[0][:5]
            ] if batches else [],
        }
        print(json.dumps(report, indent=2))
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    batch_files: list[Path] = []
    for i, batch in enumerate(batches):
        batch_md = format_batch_md(
            batch_num=i + 1,
            batch_total=len(batches),
            batch=batch,
            link_table=link_table,
            prompt_template=prompt_template,
            body_excerpt_words=body_excerpt_words,
        )
        out_path = output_dir / f"batch-{i + 1:02d}.md"
        out_path.write_text(batch_md, encoding="utf-8")
        batch_files.append(out_path)

    manifest = build_manifest(
        batch_files=batch_files,
        repo=repo,
        corpus_dir=corpus_tsx_dir,
        batch_size=batch_size,
        body_excerpt_words=body_excerpt_words,
        total_pieces=len(pieces),
    )
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "pieces_parsed": len(pieces),
        "batches_emitted": len(batch_files),
        "output_dir": str(output_dir),
        "manifest": str(manifest_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

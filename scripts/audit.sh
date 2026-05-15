#!/usr/bin/env bash
# IEO-launch-audit — top-level orchestrator
#
# Runs 10 audit checks. Reports findings to .launch-readiness-report.md
# and .launch-readiness-report.json at repo root.
#
# Usage:
#   bash .claude/skills/IEO-launch-audit/scripts/audit.sh [options]
#
# Options:
#   --repo PATH           Audit this repo (default: $PWD)
#   --report-only         Don't apply any fixes; just report (default)
#   --apply-safe-fixes    Apply fixes tagged `safe` in checks/NN-*.md
#   --checks NN,NN,...    Run only specified checks (default: all 10)
#   --config PATH         Override config path (default: <repo>/.launch-readiness.yml)
#   --output-dir PATH     Where to emit reports (default: <repo>/)
#   --diff                After the run, diff current report vs prior snapshot
#                         (.launch-readiness-report.prev.json) and emit
#                         .launch-readiness-diff.md + stdout
#   --diff-path PATH      Override prior-report location for --diff comparison
#                         (e.g., compare against a saved snapshot)
#   -h, --help            Show this help
set -euo pipefail

REPO="${REPO:-$(pwd)}"
APPLY_FIXES=0
CHECKS=""
CONFIG=""
OUTPUT_DIR=""
DIFF=0
DIFF_PATH=""
NO_ROTATE=0
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  sed -n '2,/^set -euo/p' "$0" | sed 's/^# \?//;/^set/d'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --report-only) APPLY_FIXES=0; shift ;;
    --apply-safe-fixes) APPLY_FIXES=1; shift ;;
    --checks) CHECKS="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --diff) DIFF=1; shift ;;
    --diff-path) DIFF_PATH="$2"; DIFF=1; shift 2 ;;
    --no-rotate) NO_ROTATE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

REPO="$(cd "$REPO" && pwd)"
CONFIG="${CONFIG:-$REPO/.launch-readiness.yml}"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO}"

# Default check set. Check 11 (live-apex) only runs when explicitly requested
# OR when a live origin is configured (canonical_origin / live_probe_origin).
# It hits the network and adds ~60-90s; not in the 1-10 default block.
[[ -z "$CHECKS" ]] && CHECKS="1,2,3,4,5,6,7,8,9,10"

echo "IEO-launch-audit  v0.4.0"
echo "Repo:         $REPO"
echo "Skill dir:    $SKILL_DIR"
echo "Config:       $CONFIG"
echo "Output:       $OUTPUT_DIR"
echo "Checks:       $CHECKS"
echo "Apply fixes:  $([[ $APPLY_FIXES -eq 1 ]] && echo yes || echo no)"
echo

REPORT_MD="$OUTPUT_DIR/.launch-readiness-report.md"
REPORT_JSON="$OUTPUT_DIR/.launch-readiness-report.json"
REPORT_JSON_PREV="$OUTPUT_DIR/.launch-readiness-report.prev.json"
DIFF_MD="$OUTPUT_DIR/.launch-readiness-diff.md"

# Auto-rotate: snapshot the previous report before this run overwrites it.
# The recursive --apply-safe-fixes re-invocation passes --no-rotate so it
# doesn't clobber the original prior with the just-now-overwritten report.
if [[ $NO_ROTATE -eq 0 ]] && [[ -f "$REPORT_JSON" ]]; then
  cp "$REPORT_JSON" "$REPORT_JSON_PREV"
fi

# Detect tech stack
detect_stack() {
  if [[ -f "$REPO/vercel.json" ]] || [[ -f "$REPO/next.config.js" ]] || [[ -f "$REPO/next.config.mjs" ]]; then
    echo "vercel-nextjs"
  elif [[ -f "$REPO/astro.config.mjs" ]] || [[ -f "$REPO/astro.config.ts" ]]; then
    echo "astro"
  elif [[ -f "$REPO/hugo.toml" ]] || [[ -f "$REPO/config.toml" ]]; then
    echo "hugo"
  elif [[ -f "$REPO/_config.yml" ]]; then
    echo "jekyll"
  elif [[ -f "$REPO/package.json" ]]; then
    echo "node-static"
  else
    echo "plain-static"
  fi
}

STACK="$(detect_stack)"
echo "Detected stack: $STACK"
echo

# Per-check runner. Each check is a Python script invoked via python3.
# Script names follow check-<topic>.py convention (mapped below).
run_check() {
  local script_name="$1"
  local py_script="$SKILL_DIR/scripts/check-${script_name}.py"
  local sh_script="$SKILL_DIR/scripts/check-${script_name}.sh"
  if [[ -f "$py_script" ]]; then
    python3 "$py_script" --repo "$REPO" --config "$CONFIG" --stack "$STACK"
  elif [[ -f "$sh_script" ]]; then
    bash "$sh_script" --repo "$REPO" --config "$CONFIG" --stack "$STACK"
  else
    echo "{\"check\": \"$script_name\", \"status\": \"NOT_IMPLEMENTED\", \"note\": \"Script not yet built\"}"
  fi
}

# Check IDs and friendly names
declare -A CHECK_NAMES=(
  [1]="Technical SEO"
  [2]="Schema.org graph"
  [3]="AI-bot directives"
  [4]="Core Web Vitals"
  [5]="Wikidata entity graph"
  [6]="IndexNow setup"
  [7]="Sitemap accuracy"
  [8]="Internal-link quality"
  [9]="Content tactics"
  [10]="External backlinks"
  [11]="Live-apex audit"
)

# Map check number to script name
declare -A CHECK_SCRIPTS=(
  [1]="headers"
  [2]="schema"
  [3]="ai-bots"
  [4]="performance"
  [5]="wikidata"
  [6]="indexnow"
  [7]="sitemap"
  [8]="link-quality"
  [9]="content-tactics"
  [10]="backlinks"
  [11]="live-apex"
)

# Emit report header
{
  echo "# Launch-readiness audit report"
  echo ""
  echo "**Repo:** $REPO  "
  echo "**Stack:** $STACK  "
  echo "**Date:** $(date -u +%Y-%m-%dT%H:%M:%SZ)  "
  # Skill version, sourced from SKILL.md frontmatter so bumps stay in one place.
  echo "**Skill version:** $(grep '^  version:' "$SKILL_DIR/SKILL.md" | head -1 | awk -F': ' '{print $2}')"
  echo ""
} > "$REPORT_MD"

echo "[" > "$REPORT_JSON"
FIRST=1

# Run each check. Supports comma-separated lists ("1,2,7") OR ranges ("1-11")
# OR a mix ("1,3-5,11"). Range expansion runs before the per-check loop.
expand_checks() {
  local in="$1"
  local out=""
  IFS=',' read -ra TOKS <<< "$in"
  for t in "${TOKS[@]}"; do
    t="${t// /}"
    if [[ "$t" =~ ^[0-9]+-[0-9]+$ ]]; then
      local lo="${t%-*}"
      local hi="${t#*-}"
      for ((i=lo; i<=hi; i++)); do
        out="${out}${i},"
      done
    elif [[ -n "$t" ]]; then
      out="${out}${t},"
    fi
  done
  echo "${out%,}"
}
CHECKS="$(expand_checks "$CHECKS")"
IFS=',' read -ra CHECK_LIST <<< "$CHECKS"
for n in "${CHECK_LIST[@]}"; do
  n="${n// /}"  # trim spaces
  script_name="${CHECK_SCRIPTS[$n]:-unknown}"
  echo "Running check $n: ${CHECK_NAMES[$n]} (script: check-${script_name}.py)..."
  result="$(run_check "$script_name" 2>&1 || echo "{\"check\":\"$n\",\"status\":\"ERROR\",\"stderr\":\"see log\"}")"

  # Append to JSON
  if [[ $FIRST -eq 0 ]]; then
    echo "," >> "$REPORT_JSON"
  fi
  FIRST=0
  echo "$result" >> "$REPORT_JSON"

  # Append to MD
  {
    echo ""
    echo "## Check $n — ${CHECK_NAMES[$n]}"
    echo ""
    echo '```json'
    echo "$result"
    echo '```'
  } >> "$REPORT_MD"
done

echo "]" >> "$REPORT_JSON"

echo ""
echo "Report:       $REPORT_MD"
echo "JSON:         $REPORT_JSON"

# Incremental diff against prior snapshot (auto-rotated above) or an
# operator-supplied snapshot path.
if [[ $DIFF -eq 1 ]]; then
  PRIOR="${DIFF_PATH:-$REPORT_JSON_PREV}"
  echo ""
  echo "Diff:         $DIFF_MD"
  if [[ -f "$PRIOR" ]]; then
    python3 "$SKILL_DIR/scripts/audit_diff.py" \
      --current "$REPORT_JSON" \
      --prior "$PRIOR" \
      --out "$DIFF_MD"
  else
    python3 "$SKILL_DIR/scripts/audit_diff.py" \
      --current "$REPORT_JSON" \
      --out "$DIFF_MD"
  fi
fi

if [[ $APPLY_FIXES -eq 1 ]]; then
  echo ""
  echo "Apply-safe-fixes pass running..."
  python3 "$SKILL_DIR/scripts/apply_fixes.py" --repo "$REPO" --config "$CONFIG"
  echo ""
  echo "Re-running audit to verify fixes landed..."
  bash "$0" --repo "$REPO" --config "$CONFIG" --report-only --checks "$CHECKS" --output-dir "$OUTPUT_DIR" --no-rotate
fi

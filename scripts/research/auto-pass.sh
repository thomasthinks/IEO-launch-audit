#!/usr/bin/env bash
# auto-pass.sh — Phase C auto-research ship script (v1.6.0)
#
# Operates the git + gh sequence for the monthly auto-research routine.
# Called from a Claude Code session invoked via /schedule after the
# session has completed the discovery + steelman + verification waves
# per scripts/research/PROTOCOL.md.
#
# Usage:
#   bash scripts/research/auto-pass.sh init [YYYY-MM]
#     - Set up a research branch for the pass. Default: current month.
#   bash scripts/research/auto-pass.sh ship YYYY-MM
#     - Commit research artifacts + push branch + open PR.
#
# Never merges. ADR 0002 Decision 3 + 4: maintainer reviews + decides.

set -euo pipefail

SUBCOMMAND="${1:-}"
PASS_YEAR_MONTH="${2:-$(date -u +%Y-%m)}"
BRANCH="auto-research/${PASS_YEAR_MONTH}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$SKILL_DIR"

usage() {
  cat <<EOF
Usage: $0 init [YYYY-MM]
       $0 ship YYYY-MM

Phase C auto-research ship script. See scripts/research/PROTOCOL.md.
EOF
  exit 2
}

abort() {
  echo "auto-pass.sh: $*" >&2
  exit 1
}

cmd_init() {
  # Verify no prior pass for this month is still open.
  if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    abort "Branch '$BRANCH' already exists on origin. Resolve the prior pass before starting another."
  fi
  # Verify no error marker from a prior failed pass.
  if [[ -f scripts/research/.last-pass-error.md ]]; then
    abort "scripts/research/.last-pass-error.md exists from a prior failed pass. Clear it before starting another."
  fi
  # Set up the branch.
  git fetch origin main >/dev/null 2>&1 || abort "git fetch failed; check remote."
  git checkout -B "$BRANCH" origin/main
  echo "Branch $BRANCH ready."
  echo "Next: follow PROTOCOL.md steps 2-6 to populate research artifacts, then run:"
  echo "    bash $0 ship $PASS_YEAR_MONTH"
}

cmd_ship() {
  [[ -z "$PASS_YEAR_MONTH" ]] && abort "ship requires YYYY-MM argument."

  CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
  if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
    abort "Currently on '$CURRENT_BRANCH', expected '$BRANCH'. Run 'init' first or checkout the right branch."
  fi

  RESEARCH_FILE="references/research-${PASS_YEAR_MONTH}.md"
  if [[ ! -f "$RESEARCH_FILE" ]]; then
    abort "$RESEARCH_FILE not found. Did you complete step 6 of PROTOCOL.md?"
  fi

  # Stage all research artifacts produced by the pass.
  git add "references/research-${PASS_YEAR_MONTH}.md" || true
  git add "scripts/research/${PASS_YEAR_MONTH}-discovery-slate.md" 2>/dev/null || true
  git add "scripts/research/${PASS_YEAR_MONTH}-steelman.md" 2>/dev/null || true
  git add "scripts/research/${PASS_YEAR_MONTH}-verification.md" 2>/dev/null || true
  # Error marker, if present, goes too — surfaces in PR description.
  if [[ -f scripts/research/.last-pass-error.md ]]; then
    git add scripts/research/.last-pass-error.md
    TITLE_PREFIX="[FAILED] "
  else
    TITLE_PREFIX=""
  fi

  if git diff --cached --quiet; then
    abort "No staged changes. Did the research pass produce any artifacts?"
  fi

  git commit -m "research(auto): ${PASS_YEAR_MONTH} monthly research pass

Auto-research pass per scripts/research/PROTOCOL.md.
Maintainer review required before merge (ADR 0002 Decision 3+4).
"

  git push -u origin "$BRANCH"

  # Try gh; degrade gracefully if absent.
  if ! command -v gh >/dev/null 2>&1; then
    cat > scripts/research/.last-pass-error.md <<EOF
# Auto-pass ship: gh CLI unavailable

Branch '$BRANCH' pushed to origin. PR not opened automatically because
\`gh\` is not installed in the current environment.

**Manual PR creation:**

\`\`\`
gh pr create --base main --head $BRANCH \\
  --title "${TITLE_PREFIX}research(auto): ${PASS_YEAR_MONTH} monthly pass" \\
  --body-file references/research-${PASS_YEAR_MONTH}.md
\`\`\`

Or open https://github.com/thomasthinks/IEO-launch-audit/pull/new/$BRANCH
in a browser.

Clear this marker file after the PR is opened.
EOF
    abort "gh CLI not available — branch pushed; PR creation deferred. See scripts/research/.last-pass-error.md."
  fi

  # Compose PR body from the final consolidation file.
  PR_BODY_FILE=$(mktemp)
  {
    echo "## Auto-research pass: ${PASS_YEAR_MONTH}"
    echo ""
    echo "Produced by \`scripts/research/auto-pass.sh\` per \`scripts/research/PROTOCOL.md\`."
    echo "Maintainer review required before merge (ADR 0002 Decision 3+4)."
    echo ""
    echo "### Findings summary"
    echo ""
    echo "See \`${RESEARCH_FILE}\` for the survivor candidate slate. Wave outputs (discovery / steelman / verification) committed alongside for traceability."
    echo ""
    if [[ -f scripts/research/.last-pass-error.md ]]; then
      echo "### ⚠️ Pass produced errors"
      echo ""
      cat scripts/research/.last-pass-error.md
      echo ""
    fi
    echo "### Next steps for the maintainer"
    echo ""
    echo "1. Read \`${RESEARCH_FILE}\` end-to-end."
    echo "2. For each PROMOTE-tier candidate: decide whether to ship in the next release."
    echo "3. For each DEMOTE / KILL: confirm reasoning + log in ADR 0001 if a new folklore pattern surfaced."
    echo "4. Update memory if the pass shifted the v1.x project state."
    echo "5. Either close this PR (declining all candidates), merge a subset, or open follow-up implementation PRs."
  } > "$PR_BODY_FILE"

  gh pr create \
    --base main \
    --head "$BRANCH" \
    --title "${TITLE_PREFIX}research(auto): ${PASS_YEAR_MONTH} monthly research pass" \
    --body-file "$PR_BODY_FILE"
  rm -f "$PR_BODY_FILE"

  echo "PR opened. Maintainer review required."
}

case "$SUBCOMMAND" in
  init)
    cmd_init
    ;;
  ship)
    cmd_ship
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    abort "Unknown subcommand: $SUBCOMMAND"
    ;;
esac

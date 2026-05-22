# Check 15 — Accessibility (axe-core via Lighthouse)

## Why this matters

WCAG accessibility compliance is a legal requirement in many jurisdictions (ADA in the US, EAA in EU starting 2025, AODA in Ontario) and a brand-quality signal in every other consumer-site context. But the **load-bearing reason for an IEO audit** is different:

LLM citation engines parse rendered HTML for entity extraction. Semantic HTML — proper heading order, descriptive link names, labeled buttons, alt text on images, valid lang attributes, ARIA where needed — directly improves the surface AI engines pull citations from. The 2025-26 follow-on work to Princeton/Georgia Tech KDD 2024 (referenced in check 09) measured a correlation between axe-core failure density and LLM-summary quality regressions: pages with missing alt text get described less accurately; pages with skipped heading levels get summarized with structural confusion; pages with unlabeled buttons get cited less often.

axe-core is the canonical engine for automated a11y validation (Deque Systems, open-source, ~50 WCAG 2.0/2.1/2.2 rules). Lighthouse bundles axe-core in its accessibility category. PageSpeed Insights returns the same audits via API. This check makes a single PSI call and surfaces each failing a11y rule as a finding.

## What this check does

1. **15.score** — overall accessibility category score (0..1). PASS ≥0.95, WARN ≥0.80, FAIL <0.80.
2. **15.failures** — per-audit cause list. For each Lighthouse a11y audit with `score < 1` and `details.items` non-empty:
   - audit ID (e.g., `color-contrast`, `image-alt`, `link-name`, `heading-order`)
   - title + description (Lighthouse-provided)
   - weight (Lighthouse's per-audit contribution to category score; 7-10 = highest impact)
   - failing node count
   Sorted by weight × node-count descending; top 15 shown in the markdown report; full list in the JSON output.

## Failure modes covered

The check exposes Lighthouse's full a11y audit set, including (illustrative, not exhaustive):

- **Content/text:** `image-alt`, `input-image-alt`, `object-alt`, `area-alt`, `button-name`, `link-name`, `frame-title`, `video-caption`
- **Color/contrast:** `color-contrast`
- **Structure:** `heading-order`, `landmark-one-main`, `html-has-lang`, `html-lang-valid`, `valid-lang`, `meta-viewport`, `meta-refresh`
- **ARIA:** `aria-allowed-attr`, `aria-required-attr`, `aria-valid-attr`, `aria-valid-attr-value`, `aria-hidden-body`, `aria-roles`, `aria-required-children`, `aria-required-parent`, `aria-input-field-name`, `aria-toggle-field-name`, `aria-command-name`, `aria-progressbar-name`, `aria-tooltip-name`, `aria-treeitem-name`, `aria-meter-name`, `aria-dialog-name`, `aria-text`
- **Keyboard/focus:** `tabindex`, `scrollable-region-focusable`, `focus-traps`
- **Forms:** `label`, `select-name`, `input-button-name`
- **Lists/tables:** `list`, `listitem`, `definition-list`, `dlitem`, `td-headers-attr`, `th-has-data-cells`, `table-fake-caption`, `scope-attr-valid`
- **Misc:** `bypass`, `document-title`, `accesskeys`, `duplicate-id-active`, `duplicate-id-aria`

## Config

- Reuses `live_probe_origin` (post-launch) or `canonical_origin` (pre-launch) from `.launch-readiness.yml`
- Requires `PAGESPEED_API_KEY` env var OR `pagespeed_secret_path` config field
- Mobile strategy is canonical (a11y rules are device-agnostic; mobile is the citation-class target)

## Fix safety

All findings are `manual` — accessibility fixes require source-code changes (semantic HTML, ARIA attribution, lang declarations, focus traps). No auto-fix is shipped because a11y improvements are case-by-case structural edits.

## Reference

- Lighthouse accessibility audit guide: https://web.dev/lighthouse-accessibility/
- axe-core rule descriptions: https://dequeuniversity.com/rules/axe/
- WCAG 2.1 quick reference: https://www.w3.org/WAI/WCAG21/quickref/
- Per-audit fix examples: https://web.dev/learn/accessibility/

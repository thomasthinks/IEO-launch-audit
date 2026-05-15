# Check 06 — IndexNow setup

## Why this matters

IndexNow is a search-engine protocol for instant URL submission. Adopted
by Bing, Yandex, Naver, Seznam — covers ~all human-search-engine reach
outside Google (which doesn't consume IndexNow). For an editorial site
publishing weekly, IndexNow is the fastest path from `git push` to
Bing/Yandex indexing.

The setup is two steps: (1) place a key file at `/<key>.txt` at the site
root, (2) POST each new/updated URL to `api.indexnow.org` on publish.

**Cited sources:** [IndexNow protocol spec](https://www.indexnow.org/);
"IndexNow vs Sitemap 2026" — Whitebunnie; Bing Webmaster IndexNow
documentation.

## What's checked

### 6.1 — Key file presence

| Assertion | Pass | Fail |
|---|---|---|
| `<key>.txt` file exists at site root | yes | no |
| File contents exactly equal the key | yes | mismatch |
| Key is referenced consistently in publish hooks | yes | no |

### 6.2 — Publish-hook integration

| Assertion | Pass | Warn |
|---|---|---|
| Build / publish pipeline POSTs new URLs to api.indexnow.org | yes | no |
| Pings are batched (max 10,000 URLs per request) | yes | one-by-one |
| Failure handling: retries with exponential backoff | yes | no |

The keyfile alone is NOT enough: search engines only learn about a new
URL when a publish-time POST fires. The check looks for the substring
`api.indexnow.org` or `indexnow.org/indexnow` anywhere under `scripts/`,
in the runbooks under `docs/runbooks/`, or in `Makefile` /
`.github/workflows/` -- a callable script + a runbook step that
references it is the canonical pattern.

## How to fix

### Fix 6.1 — Generate key + emit file

```bash
# Generate a UUID-style key
KEY=$(uuidgen | tr 'A-Z' 'a-z' | tr -d '-')
echo $KEY > dist/public/$KEY.txt
echo "IndexNow key: $KEY"
```

Store the key in `.env` or a config file referenced by the publish hook.
The file at `/<key>.txt` must be served as plain text with HTTP 200.

**Auto-fix safety: safe** (generates key + emits file; idempotent if key
already exists).

### Fix 6.2 — Add publish hook

Two-part fix: (a) ship a callable script that POSTs to IndexNow, (b)
reference it from the publish runbook so it actually fires on every
new-URL deploy.

**(a) Callable script** -- stdlib-only Python is enough; no `requests`
dependency needed. Convention: `scripts/publish_to_indexnow.py`. Read
host + key from `.launch-readiness.yml` (canonical_origin) and the
keyfile in the public root; allow `--host` / `--key` / `--urls` /
`--slugs` / `--dry-run` overrides.

```python
import json, urllib.request
payload = {
    "host": "example.com",
    "key": "<key>",
    "keyLocation": "https://example.com/<key>.txt",
    "urlList": ["https://example.com/writing/slug-1/"],
}
req = urllib.request.Request(
    "https://api.indexnow.org/indexnow",
    data=json.dumps(payload).encode("utf-8"),
    method="POST",
    headers={"Content-Type": "application/json; charset=utf-8"},
)
with urllib.request.urlopen(req, timeout=10) as resp:
    print(resp.status)  # 200 or 202 on success
```

**(b) Runbook reference** -- add a step to `docs/runbooks/live-publish.md`
(or equivalent) that invokes the script post-deploy, after the URL is
verified reachable. IndexNow rejects URLs that don't return 200 on
fetch, so this step must come after deploy + apex-verify.

**Auto-fix safety: manual** (touches the publish pipeline).

## Failure ratings

- **FAIL:** key file missing.
- **WARN:** publish-hook not wired.
- **PASS:** key file present + hook wired.

## Cited research

- [IndexNow protocol spec](https://www.indexnow.org/)
- [IndexNow guide 2026](https://www.trysight.ai/blog/indexnow-implementation-for-faster-indexing)
- [IndexNow vs Sitemap 2026](https://whitebunnie.com/blog/indexnow-vs-sitemap-which-one-should-you-use-in-2026/)

## Implementation notes

`scripts/check-indexnow.py`:
1. Looks for any `<32-char-hex>.txt` file in `dist/public/` (or other
   common public roots: `public/`, `out/`, `_site/`, `build/`, `static/`)
2. Verifies its contents match its filename
3. Scans the consumer repo for the substring `api.indexnow.org` (or
   `indexnow.org/indexnow`) under `scripts/`, `docs/runbooks/`,
   `Makefile`, `.github/workflows/`. A match in any of those locations
   satisfies 6.2 -- the convention is a callable script (any filename)
   plus a runbook step that references it.
4. Reports gaps + fix snippets.

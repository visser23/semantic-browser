# Semantic Browser Runtime

Make browser automation feel less like parsing soup and more like a text adventure.

This project turns a live Chromium page into a compact control panel for an LLM:

- **where am I?** (`location`)
- **what can I see?** (`what_you_see`)
- **what can I do?** (`available_actions`)
- **what is in the way?** (`blockers`)

Then the model replies with one action ID and keeps moving.

In plain English: this is not "yet another browser". It is the semantic layer that lets an LLM behave more like a focused human operator, and less like a confused DOM archaeologist.

## Why this is actually great

Most browser loops waste tokens on page noise. Semantic Browser is designed to stop that.

- **Auto routing**: ARIA-quality-aware mode selection (`observe(mode="auto")`)
- **Top-first extraction**: starts at the part humans read first
- **Planner payload**: tiny, capped control-panel view for LLM turns
- **Stable actions**: deterministic IDs instead of fragile selectors
- **Escalation path**: go from compact to full only when needed

If your bot has ever clicked the wrong thing because a cookie banner sneezed, this is for you.

---

## Comparative results (10 major sites, 20 action tasks, median)

Benchmark files:
- `docs/benchmarks/2026-03-11-actionset-compare.md`
- `docs/benchmarks/2026-03-11-actionset-compare.json`

Tested sites: Amazon, YouTube, Reddit, LinkedIn, Instagram, X, Google Maps, Notion, Wikipedia, BBC.

| Method | Success rate | Stuck rate | Median speed (ms) | Median token-in | Median token-out |
|---|---:|---:|---:|---:|---:|
| Standard browser use | 0.75 | 0.25 | 2491.1 | 268.0 | 13.0 |
| OpenClaw browser | 0.65 | 0.35 | 2557.9 | 2644.0 | 13.0 |
| **Semantic Browser (auto + planner)** | 0.50 | 0.50 | 3633.2 | 920.0 | 13.0 |

### What this means (honest version)

- This run is now **action-set based**, so it captures getting stuck, not just pretty snapshots.
- **OpenClaw and standard** currently win on speed/success in this specific harness.
- **Semantic Browser** still needs improvement on action matching/execution reliability.
- Token-in remains controlled and predictable with the planner payload, but reliability is the next hill to climb.

In other words: the architecture is right, but we need to finish the job on execution quality before claiming victory laps.

---

## What This Is (Simple Version)

You open a real webpage.

Instead of dumping giant blobs into the model, you run a clean loop:

1. "What can I see?"
2. "What can I do?"
3. "Do this action."
4. "What changed?"

Rinse and repeat.

---

## Install

### 1) Core package (attach mode support)

```bash
pip install semantic-browser
```

### 2) Managed browser mode (recommended for first use)

```bash
pip install "semantic-browser[managed]"
```

### 3) Local service mode

```bash
pip install "semantic-browser[server]"
```

### 4) Everything (dev + tests + server + managed)

```bash
pip install "semantic-browser[full]"
```

---

## Dependencies (Clear and Explicit)

- Python: `>=3.11`
- Browser engine (v1): Chromium/Chrome only
- Automation library: Playwright async API
- Core deps:
  - `pydantic`
  - `click`
  - `PyYAML`
- Optional deps:
  - `playwright` for managed mode
  - `fastapi`, `uvicorn` for service mode

Install Chromium for managed mode:

```bash
semantic-browser install-browser
```

Check your environment:

```bash
semantic-browser doctor
```

---

## Fastest First Run (Copy/Paste)

```bash
pip install "semantic-browser[managed]"
semantic-browser install-browser
semantic-browser portal --url https://example.com --headless
```

In portal mode, try:

- `observe summary`
- `actions`
- `act <action_id>`
- `back`
- `forward`
- `reload`
- `trace my-trace.json`
- `quit`

---

## Python Library Usage

```python
import asyncio
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest

async def demo():
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime

    await runtime.navigate("https://example.com")
    obs = await runtime.observe(mode="summary")
    print("actions:", len(obs.available_actions))

    first_open = next((a for a in obs.available_actions if a.op == "open"), None)
    if first_open:
        step = await runtime.act(ActionRequest(action_id=first_open.id))
        print("step:", step.status, step.observation.page.url)

    await runtime.export_trace("trace.json")
    await session.close()

asyncio.run(demo())
```

### CDP attach tips (important)

When attaching to an already-running Chrome, use the **browser-level** websocket:

- ✅ `ws://.../devtools/browser/<id>`
- ❌ `ws://.../devtools/page/<id>`

If you pass a page websocket, runtime now raises a clear `AttachmentError`
explaining that a browser websocket is required.

You can also hint which tab to bind:

```python
runtime = await SemanticBrowserRuntime.from_cdp_endpoint(
    endpoint,
    target_url_contains="x.com",
    prefer_non_blank=True,
)
```

If you do not provide a hint, the runtime now prefers non-blank pages over
`about:blank`.

If you use `page_index`, it must be zero-based and valid for the target context.
Invalid indices now raise `AttachmentError` instead of silently falling back.

Observation recovery: summary observations now auto-retry up to 2 extra times
when extraction returns a transient "No visible nodes" state:
- retry 1: short backoff
- retry 2: page reload + settle backoff

This reduces flaky low-confidence results on dynamic SPAs (for example Teams).

Top-first token behaviour (summary mode):
- `observe(mode="summary")` now focuses on a top-of-page slice (viewport + buffer)
- `observe(mode="full")` returns broader full-page context
- summary key points include a `top-scope summary: X/Y interactables included` hint

Auto routing mode:
- `observe(mode="auto")` computes a lightweight ARIA quality score and chooses route automatically:
  - good ARIA => compact top-scope route (`aria_compact`)
  - weak/noisy ARIA => broader route (`semantic_full`)
- route and quality are exposed in `observation.metrics` and summary key points.

Planner control-panel view (BBC Micro loop style):
- each observation now includes `observation.planner`:
  - `location`: concise room/location line
  - `what_you_see`: short capped bullet list
  - `available_actions`: capped action list (`id`, `label`, `op`)
  - `blockers`: active blocker hints
- use this as the LLM-facing payload for low token-in turns; keep full observation internal for diagnostics/recovery.

This keeps default observations leaner while allowing deterministic escalation to full context.

---

## CLI Commands

```bash
semantic-browser version
semantic-browser doctor
semantic-browser install-browser

semantic-browser portal --url https://example.com
semantic-browser serve --host 127.0.0.1 --port 8765
semantic-browser eval-corpus --config corpus/sites.yaml --out corpus-report.json

semantic-browser launch --headless
semantic-browser observe --session <id> --mode summary
semantic-browser navigate --session <id> --url https://example.com
semantic-browser act --session <id> --action <action_id>
semantic-browser inspect --session <id> --target <target_id>
semantic-browser back --session <id>
semantic-browser forward --session <id>
semantic-browser reload --session <id>
semantic-browser wait --session <id> --ms 500
semantic-browser export-trace --session <id> --out trace.json
```

---

## Docs

- `docs/vision.md` - product intent and non-negotiables
- `docs/requirements.md` - behavior requirements and KPIs
- `docs/technical_spec.md` - architecture and design
- `docs/project_plan.md` - implementation checklist and status
- `docs/system_arch.md` - architecture diagrams
- `docs/getting_started.md` - copy/paste onboarding guide
- `docs/dependencies.md` - explicit dependency matrix

If you just cloned the repo, start with `docs/project_plan.md`.

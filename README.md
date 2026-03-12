# Semantic Browser
<p align="left">
  <img src="<img src="https://github.com/user-attachments/assets/dac79ee0-6ebb-48b3-a27d-2e339ea16961" alt="Semantic Browser mascot" width="240" align="right" />
</p>
Make browser automation feel less like parsing soup and more like an old BBC Micro text adventure.

Turn a live Chromium page into a compact semantic “room” an LLM can reason about.
<img width="800" height="800" alt="Gemini_Generated_Image_n0t5nrn0t5nrn0t5" src="https://github.com/user-attachments/assets/dac79ee0-6ebb-48b3-a27d-2e339ea16961" />

- Live page → structured room state
- DOM distilled into meaningful objects, not soup
- Built for agentic browser automation
- Token-efficient, deterministic, inspectable

```
@ BBC News (bbc.co.uk)
> Home page. Main content: "Top stories". Navigation: News, Sport, Weather.
1 open "News" [a10]
2 open "Sport" [a11]
3 fill Search BBC [a17] *value
+ 28 more [more]
```

The model replies with one action ID (`a10`) and we go again.

No giant JSON blobs. No DOM dumps. No pretending every page is stable.  
Just: what you see, what you can do, what changed.

## Why this is different (and why it now works)

Other browser tools give the LLM the same data in a different wrapper. We give it a fundamentally different view.

- **Plain-text room descriptions** - prose, not JSON.
- **Curated actions first** - top 15 useful actions, then `more` if needed.
- **Progressive disclosure** - `more` gives full action list without flooding every step.
- **Tiny action replies** - `a10`, `nav "https://..."`, `back`, `done`.
- **Narrative history** - readable previous steps, not noisy machine dump.
- **Guardrails for reality** - anti-repeat fallback, nav hardening, transient extract retry.
- **Honest failure mode** - if a site throws anti-bot gates, we say so and show evidence.

#### Cross-method comparator (shared 25-task pack)

| Method | Success rate | Failures | Median speed (ms) | Planner input median (billable) | Planner output median (billable) | Payload token-est median (estimated) | Total effective context median (estimated) | Median browser/runtime calls | Indicative planner cost/request (USD) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Standard browser tooling | 24% (6/25) | 19 | 11,819.8 | 10,118 | 74 | 6,918 | 17,224 | 6.0 | 0.041005 |
| OpenClaw browser tooling | 72% (18/25) | 7 | 10,514.2 | 6,833 | 66 | 5,219 | 12,078 | 6.0 | 0.022053 |
| Semantic Browser | 100% (25/25) | 0 | 9,353.3 | 540 | 14 | 310 | 879 | 5.0 | 0.004036 |


This is a dramatic jump.

The last anti-bot loop in this pack now has a robust recovery path:
- capture challenge evidence (screenshot),
- try direct same-origin query route,
- then use a public read-only fallback endpoint when the primary UI is hard-blocked.

25 tasks across: navigation, search, multi-step, content, interaction, resilience, speed.

If challenge/captcha is detected, harness captures a screenshot and includes it in the LLM call.

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

# Semantic Browser Runtime

Turn a real browser page into a clean, LLM-friendly action surface.

If you are tired of giving your model raw DOM noise and brittle selectors, this
project gives you:

- structured observations (`summary`, `full`, `delta`, `debug`)
- stable action IDs
- executable actions (`act`)
- blocker and confidence signals
- optional local service + CLI

In plain English: this is a semantic control layer on top of Chromium, not a
new browser.

---

## What This Is (Simple Version)

You open a real webpage.

Instead of handing your LLM giant HTML blobs, you ask this runtime:

1. "What can I see?"
2. "What can I do?"
3. "Do this action."
4. "What changed?"

That is the whole idea.

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

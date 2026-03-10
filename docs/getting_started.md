# Getting Started (Zero Guesswork)

This guide is for people pulling down the repo for the first time.

If you want the shortest path to success, follow this file exactly.

---

## 1) What You Need

- Python 3.11+
- `pip`
- Internet access (for live website interaction)

Optional (only if using managed mode):

- Playwright Chromium browser bundle (installed via command below)

---

## 2) Install

From repo root:

```bash
pip install -e ".[full]"
```

Install browser runtime:

```bash
semantic-browser install-browser
```

Validate environment:

```bash
semantic-browser doctor
```

---

## 3) First E2E Run (Interactive)

Start porthole mode:

```bash
semantic-browser portal --url https://example.com --headless
```

Then run these commands inside the prompt:

```text
observe summary
actions
act <an-open-action-id>
observe delta
back
forward
reload
trace first-trace.json
quit
```

What success looks like:

- `observe summary` returns structured JSON with actions/regions/forms
- `act ...` returns a `StepResult` with `status`
- `observe delta` is smaller than full output
- `trace ...` writes a trace file

---

## 4) First E2E Run (Python Script)

```python
import asyncio
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest

async def run():
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime

    await runtime.navigate("https://example.com")
    obs = await runtime.observe("summary")
    print("action_count:", len(obs.available_actions))

    open_action = next((a for a in obs.available_actions if a.op == "open"), None)
    if open_action:
        result = await runtime.act(ActionRequest(action_id=open_action.id))
        print("step_status:", result.status)
        print("new_url:", result.observation.page.url)

    trace_path = await runtime.export_trace("quickstart-trace.json")
    print("trace:", trace_path)
    await session.close()

asyncio.run(run())
```

---

## 5) Local Service Mode (For Tool-Calling Agents)

Start service:

```bash
semantic-browser serve --host 127.0.0.1 --port 8765
```

Example requests:

```bash
curl -X POST http://127.0.0.1:8765/sessions/launch \
  -H "Content-Type: application/json" \
  -d '{"headful": false}'

curl -X POST http://127.0.0.1:8765/sessions/<session_id>/navigate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

curl -X POST http://127.0.0.1:8765/sessions/<session_id>/observe \
  -H "Content-Type: application/json" \
  -d '{"mode": "summary"}'
```

---

## 6) Troubleshooting

- `Playwright not installed`:
  - install with `pip install "semantic-browser[managed]"`
- Browser launch fails:
  - run `semantic-browser install-browser`
- Empty/low-confidence observations:
  - page may be highly dynamic or low semantic quality
  - use `observe debug` and inspect blockers/warnings

---

## 7) Quick Reality Check

Run tests:

```bash
python3 -m pytest -q
```

Run corpus benchmark:

```bash
semantic-browser eval-corpus --config corpus/sites.yaml --headless --out corpus-report.json
```

If both pass, your local setup is healthy.

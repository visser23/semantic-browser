# Getting Started

From zero to a working browser automation agent in under 10 minutes.

## Prerequisites

- Python 3.11 or later
- pip
- Internet access (for live-site runs)

## Install

```bash
pip install "semantic-browser[managed]"
semantic-browser install-browser
semantic-browser doctor
```

`managed` installs Playwright for browser control. `install-browser` downloads a Chromium binary. `doctor` verifies everything is working.

For service mode (HTTP API):

```bash
pip install "semantic-browser[server]"
```

For everything (dev, tests, linting):

```bash
pip install "semantic-browser[full]"
```

## Verify Installation

```bash
semantic-browser version
# semantic-browser 1.3.2

semantic-browser doctor
# ✓ Python 3.11+
# ✓ Playwright installed
# ✓ Browser binary found
```

## First Run: Interactive Portal

The portal is a REPL that lets you explore any website through Semantic Browser's eyes.

```bash
semantic-browser portal --url https://news.ycombinator.com --headless
```

Inside the portal:

```text
> observe summary
@ Hacker News (news.ycombinator.com)
> Hacker News. Main content: "Show HN: ...". Navigation: new, past, comments, ask.
1 open "Show HN: ..." [act-8f2a2d1c-0]
2 open "Some Article Title" [act-c3e119fa-0]
3 open "new" [act-0b9411de-0]
+ 28 more [more]

> act act-8f2a2d1c-0
Status: success

> observe delta
@ Article Page (example.com)
> Article page. Main content: "Show HN: ..."
...

> back
> quit
```

Portal commands:

| Command | Description |
|---------|-------------|
| `observe summary` | Compact observation of top-scope elements |
| `observe full` | Full observation of all elements |
| `observe delta` | Show what changed since last observation |
| `actions` | List available actions |
| `act <action_id>` | Execute an action |
| `act <action_id> <value>` | Execute an action with a value (for fill/select) |
| `inspect <target_id>` | Get details about a specific element |
| `back` / `forward` / `reload` | Browser navigation |
| `navigate <url>` | Go to a URL |
| `trace run-trace.json` | Export session trace |
| `quit` | Exit the portal |

## First Run: Python API

```python
import asyncio
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest


async def main() -> None:
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime

    await runtime.navigate("https://example.com")
    obs = await runtime.observe(mode="summary")

    # Print the room text (what an LLM planner would see)
    print(obs.planner.room_text)

    # Find and click the first link
    first_link = next((a for a in obs.available_actions if a.op == "open"), None)
    if first_link:
        result = await runtime.act(ActionRequest(action_id=first_link.id))
        print(f"Status: {result.status}")
        print(f"Now at: {result.observation.page.url}")

    await session.close()


asyncio.run(main())
```

## First Run: CLI Commands

For scripted or shell-based workflows:

```bash
# Launch a headless session
semantic-browser launch --headless
# Output: Session <session-id>

# Navigate
semantic-browser navigate --session <session-id> --url https://example.com

# Observe
semantic-browser observe --session <session-id> --mode summary

# Act on an action
semantic-browser act --session <session-id> --action act-XXXX-0

# Close
# Session closes when the CLI exits
```

## First Run: HTTP Service

For language-agnostic integration (TypeScript, Go, Rust, etc.):

```bash
# Terminal 1: start the service
semantic-browser serve --host 127.0.0.1 --port 8765 --api-token dev-token
```

```bash
# Terminal 2: interact via curl
# Health check (no token required)
curl -s http://127.0.0.1:8765/health | jq .

# Launch a session
curl -s -X POST http://127.0.0.1:8765/sessions/launch \
  -H "Content-Type: application/json" \
  -H "X-API-Token: dev-token" \
  -d '{"headful": false}'

# Observe (replace <session_id>)
curl -s -X POST http://127.0.0.1:8765/sessions/<session_id>/observe \
  -H "Content-Type: application/json" \
  -H "X-API-Token: dev-token" \
  -d '{"mode": "summary"}'
```

## Understanding the Output

Every observation produces a `PlannerView` with a `room_text` field. This is the core interface — a compact, plain-text description of the page designed for LLM consumption:

```
@ BBC News (bbc.co.uk)
> Home page. Main content: "Top stories". Navigation: News, Sport, Weather.
! Cookie consent banner detected -> dismiss [act-a1b2c3d4-0]
1 open "News" [act-8f2a2d1c-0]
2 open "Sport" [act-c3e119fa-0]
3 fill Search BBC [act-0b9411de-0] *value
+ 28 more [more]
```

| Symbol | Meaning |
|--------|---------|
| `@` | Current location (page title + domain) |
| `>` | What you see (prose description) |
| `!` | Blocker requiring attention (with dismiss hint) |
| `N` | Numbered action: `index op "label" [action_id]` |
| `*value` | This action needs a text value |
| `+` | More actions available (use `more` to expand) |

The planner picks one action ID. The runtime executes it. That's the full loop.

## What to Read Next

| Topic | Document |
|-------|----------|
| How to wire this into an LLM agent | [Planner Contract](planner_contract.md) |
| OpenAI, Anthropic, and local loop examples | [Integration Examples](integration_examples.md) |
| Full API reference (every class and method) | [API Reference](api_reference.md) |
| Choosing the right browser/profile mode | [Runtime Modes](runtime_modes.md) |
| Using real logged-in browser profiles | [Real Profiles](real_profiles.md) |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: playwright` | `pip install "semantic-browser[managed]"` |
| Browser fails to launch | `semantic-browser install-browser` |
| Empty or broken observations | Try `observe full` or `observe debug`; check `doctor` output |
| Weak observations on dynamic SPAs | Retry observation — the runtime retries up to 3 times automatically |
| Profile lock warning | Close other Chrome instances using the same profile directory |
| Site redirects to stripped page | Use `headful=True` — site is likely detecting headless Chrome |
| Actions returning `stale` | Re-observe — the page changed since the last observation |
| Anti-bot / CAPTCHA detected | Check `obs.blockers`; may need manual intervention or alternative route |
| Migrating from v1.0 | Replace `user_data_dir` with `profile_dir` or `storage_state_path` (see [Runtime Modes](runtime_modes.md)) |

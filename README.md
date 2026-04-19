# Semantic Browser

<p align="left">
  <img src="https://github.com/user-attachments/assets/dac79ee0-6ebb-48b3-a27d-2e339ea16961" alt="Semantic Browser mascot" width="240" align="right" />
</p>

**Version 1.3.2 (Beta)** · [PyPI](https://pypi.org/project/semantic-browser/) · [Changelog](CHANGELOG.md) · [License: MIT](LICENSE)

Semantic Browser turns live Chromium pages into compact semantic "rooms" for LLM planners. The planner sees a text-adventure description of the page, picks one action ID, and the runtime executes it deterministically.

```
@ BBC News (bbc.co.uk)
> Home page. Main content: "Top stories". Navigation: News, Sport, Weather.
! Cookie consent banner detected -> dismiss [act-a1b2c3d4-0]
1 open "News" [act-8f2a2d1c-0]
2 open "Sport" [act-c3e119fa-0]
3 fill Search BBC [act-0b9411de-0] *value
+ 28 more [more]
```

Less confusion, less hallucination, dramatically less cost.

## Why Semantic Browser

- **Plain-text room descriptions** — prose, not JSON soup.
- **Curated action surface** — top 25 actions, with `more` for progressive disclosure.
- **Deterministic execution** — `observe → act → observe delta`, every time.
- **Built-in blockers** — cookie banners, modals, and anti-bot gates are detected and signaled.
- **Token-efficient** — median planner input of ~540 tokens vs ~10,000 for standard tooling.
- **Three interfaces** — Python API, CLI, and HTTP service.

## Install

```bash
pip install "semantic-browser[managed]"
semantic-browser install-browser
```

For service mode: `pip install "semantic-browser[server]"`

## Quickstart

### Interactive portal

```bash
semantic-browser portal --url https://example.com --headless
```

### Python

```python
import asyncio
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest

async def main() -> None:
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime

    await runtime.navigate("https://example.com")
    obs = await runtime.observe(mode="summary")
    print(obs.planner.room_text)

    first_link = next((a for a in obs.available_actions if a.op == "open"), None)
    if first_link:
        result = await runtime.act(ActionRequest(action_id=first_link.id))
        print(result.status, result.observation.page.url)

    await session.close()

asyncio.run(main())
```

### LLM Agent Loop (Minimal)

```python
async def agent_loop(url: str, task: str) -> None:
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime
    await runtime.navigate(url)
    obs = await runtime.observe(mode="summary")

    for step in range(25):
        action_id = call_your_llm(obs.planner.room_text, task)  # returns one action ID
        if action_id == "done":
            break
        result = await runtime.act(ActionRequest(action_id=action_id))
        obs = result.observation

    await session.close()
```

Full worked examples for OpenAI, Anthropic, and more: **[Integration Examples](docs/integration_examples.md)**

## Documentation

| Document | What it covers |
|----------|---------------|
| **[Getting Started](docs/getting_started.md)** | Install, first run, interactive portal, Python/CLI/service quickstarts |
| **[Planner Contract](docs/planner_contract.md)** | The exact interface between Semantic Browser and an LLM planner — what the planner receives, what it should reply, how to handle blockers, failures, and stopping |
| **[Integration Examples](docs/integration_examples.md)** | End-to-end examples: OpenAI chat, OpenAI function-calling, Anthropic tool use, HTTP service, CDP attach, error handling patterns |
| **[API Reference](docs/api_reference.md)** | Every public class, method, model, and field — `ManagedSession`, `SemanticBrowserRuntime`, `Observation`, `StepResult`, `ActionDescriptor`, configuration, errors |
| **[Runtime Modes](docs/runtime_modes.md)** | Decision table for ephemeral/persistent/clone/attach/service modes, headful vs headless, ownership semantics |
| **[Real Profiles](docs/real_profiles.md)** | Using real Chromium profiles for login persistence, SSO, clone mode, safety guarantees, common pitfalls |
| **[Benchmark Protocol](docs/benchmark_protocol.md)** | How benchmark numbers are produced and validated |
| **[Versioning](docs/versioning.md)** | Version numbering scheme |
| **[Publishing](docs/publishing.md)** | PyPI publish checklist |
| **[Changelog](CHANGELOG.md)** | Full release history |

## How It Works

```
Live page → extract semantic tree → group into regions → curate actions → render room text
                                                                              ↓
                                                              LLM planner picks action ID
                                                                              ↓
                                                              runtime resolves & executes
                                                                              ↓
                                                              observe delta → repeat
```

1. **Observe** — the runtime extracts the page's semantic structure, groups it into regions, curates the top actions, and renders a text-adventure "room".
2. **Plan** — the LLM planner reads the room text and replies with one action ID.
3. **Act** — the runtime resolves the action to a DOM element, executes it, waits for the page to settle, and produces a delta observation.
4. **Repeat** — the planner sees the delta and picks the next action.

## Benchmarks

Cross-method comparison on a shared 25-task pack:

| Method | Success | Median planner input (tokens) | Median planner output (tokens) | Indicative cost/request (USD) |
|--------|---------|---:|---:|---:|
| Standard browser tooling | 24% (6/25) | 10,118 | 74 | $0.041 |
| OpenClaw browser tooling | 72% (18/25) | 6,833 | 66 | $0.022 |
| **Semantic Browser** | **100% (25/25)** | **540** | **14** | **$0.004** |

At 5 tasks/day over a year: ~$75/year standard vs ~$7/year Semantic Browser.

These are reference harness results, not universal guarantees. Protocol: [`docs/benchmark_protocol.md`](docs/benchmark_protocol.md). Manifest: [`benchmarks/manifest.json`](benchmarks/manifest.json).

## CLI Reference

```bash
semantic-browser version                # Show version
semantic-browser doctor                 # Verify installation
semantic-browser install-browser        # Download Chromium
semantic-browser launch --headless      # Start a session
semantic-browser attach --cdp <ws-url>  # Attach to running Chrome
semantic-browser portal --url <url>     # Interactive exploration REPL
semantic-browser observe --session <id> --mode summary
semantic-browser act --session <id> --action <action_id>
semantic-browser inspect --session <id> --target <target_id>
semantic-browser navigate --session <id> --url <url>
semantic-browser back --session <id>
semantic-browser forward --session <id>
semantic-browser reload --session <id>
semantic-browser diagnostics --session <id>
semantic-browser export-trace --session <id> --out trace.json
semantic-browser serve --host 127.0.0.1 --port 8765 --api-token <token>
```

## What's New in v1.3.2

- **Added `GET /health` endpoint** — unauthenticated liveness probe for orchestrators and watchdogs.
- **Health payload includes release + runtime signal** — returns `{status, version, active_sessions}`.
- **Service internals hardened** — endpoint now uses public registry API instead of private field access.
- **Service docs corrected** — diagnostics endpoint method fixed to `GET` in HTTP reference.

Full details: [CHANGELOG.md](CHANGELOG.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and PR expectations.

## License

MIT — see [LICENSE](LICENSE).

# Integration Examples

End-to-end examples for wiring Semantic Browser into real LLM agent loops.

## Local Python Loop (Minimal)

The simplest integration: a synchronous loop that feeds room text to any LLM and executes the response.

```python
import asyncio
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest


def call_planner(room_text: str, task: str) -> str:
    """Replace this with your LLM call. Must return one action ID or 'done'."""
    raise NotImplementedError("Wire your LLM here")


async def run_task(url: str, task: str, max_steps: int = 25) -> None:
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime

    await runtime.navigate(url)
    obs = await runtime.observe(mode="summary")

    for step in range(max_steps):
        room_text = obs.planner.room_text
        print(f"\n--- Step {step + 1} ---")
        print(room_text)

        reply = call_planner(room_text, task)
        print(f"Planner: {reply}")

        if reply.strip().lower() == "done":
            print("Task complete.")
            break

        if reply.strip().lower() == "back":
            result = await runtime.back()
        elif reply.strip().lower().startswith("nav "):
            result = await runtime.navigate(reply.strip()[4:])
        elif "|" in reply:
            action_id, value = reply.split("|", 1)
            result = await runtime.act(
                ActionRequest(action_id=action_id.strip(), value=value.strip())
            )
        else:
            result = await runtime.act(ActionRequest(action_id=reply.strip()))

        print(f"Status: {result.status}")
        if result.status == "stale":
            obs = await runtime.observe(mode="summary")
            continue

        obs = result.observation

    await session.close()


asyncio.run(run_task("https://example.com", "Find the 'More information' link and click it"))
```

## OpenAI (Chat Completions)

Using OpenAI's chat API to drive the planner.

```python
import asyncio
from openai import OpenAI
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest

SYSTEM_PROMPT = """You are a browser automation agent. You receive a text description
of the current web page and must reply with exactly ONE action to take.

Rules:
- Reply with a single action ID from the available actions list, nothing else.
- If an action requires a value (marked *value), reply: action_id|value
- If your target is not in the curated list, reply: more
- If the task is complete, reply: done
- If stuck, reply: back
- Always dismiss blockers (cookie banners, modals) before other actions.
- Never output HTML, CSS selectors, or JavaScript."""

client = OpenAI()


def call_planner(room_text: str, task: str, history: list[dict]) -> str:
    history.append({"role": "user", "content": f"Current page:\n{room_text}"})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\nYour goal: {task}"},
            *history,
        ],
        max_tokens=50,
        temperature=0,
    )
    reply = response.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply})
    return reply


async def run_task(url: str, task: str, max_steps: int = 25) -> None:
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime
    history: list[dict] = []

    await runtime.navigate(url)
    obs = await runtime.observe(mode="summary")

    for step in range(max_steps):
        reply = call_planner(obs.planner.room_text, task, history)
        print(f"[Step {step + 1}] {reply}")

        if reply.lower() == "done":
            break

        if reply.lower() == "back":
            result = await runtime.back()
        elif reply.lower().startswith("nav "):
            result = await runtime.navigate(reply[4:])
        elif "|" in reply:
            aid, val = reply.split("|", 1)
            result = await runtime.act(ActionRequest(action_id=aid.strip(), value=val.strip()))
        else:
            result = await runtime.act(ActionRequest(action_id=reply))

        if result.status == "stale":
            obs = await runtime.observe(mode="summary")
        else:
            obs = result.observation

    await session.close()


asyncio.run(run_task("https://news.ycombinator.com", "Find and open the top story"))
```

## OpenAI (Function Calling / Tools)

Using OpenAI's tool-use API for structured action selection.

```python
import asyncio
import json
from openai import OpenAI
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest

client = OpenAI()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "browser_act",
            "description": "Execute a browser action by its ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_id": {
                        "type": "string",
                        "description": "The action ID from the current observation",
                    },
                    "value": {
                        "type": "string",
                        "description": "Value for fill/select actions (only when action has *value marker)",
                    },
                },
                "required": ["action_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate to a specific URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to navigate to"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_back",
            "description": "Go back in browser history",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_done",
            "description": "Signal that the task is complete",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Brief summary of what was accomplished"},
                },
                "required": ["summary"],
            },
        },
    },
]


async def run_task(url: str, task: str, max_steps: int = 25) -> None:
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime
    messages = [
        {
            "role": "system",
            "content": (
                "You are a browser automation agent. You receive a text description "
                "of a web page and use tools to interact with it. Always dismiss "
                "blockers first. Use 'more' as action_id if your target isn't listed."
            ),
        },
        {"role": "user", "content": f"Task: {task}"},
    ]

    await runtime.navigate(url)
    obs = await runtime.observe(mode="summary")
    messages.append({"role": "user", "content": f"Current page:\n{obs.planner.room_text}"})

    for step in range(max_steps):
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="required",
            temperature=0,
        )
        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            break

        call = msg.tool_calls[0]
        args = json.loads(call.function.arguments)
        fn = call.function.name
        print(f"[Step {step + 1}] {fn}({args})")

        if fn == "task_done":
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": "Task marked complete.",
            })
            break

        if fn == "browser_back":
            result = await runtime.back()
        elif fn == "browser_navigate":
            result = await runtime.navigate(args["url"])
        else:
            req = ActionRequest(action_id=args["action_id"], value=args.get("value"))
            result = await runtime.act(req)

        if result.status == "stale":
            obs = await runtime.observe(mode="summary")
        else:
            obs = result.observation

        tool_result = f"Status: {result.status}\nPage:\n{obs.planner.room_text}"
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": tool_result,
        })

    await session.close()


asyncio.run(run_task("https://news.ycombinator.com", "Find and open the top story"))
```

## Anthropic (Tool Use)

Using Anthropic's tool-use API with Claude.

```python
import asyncio
import json
import anthropic
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest

client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "browser_act",
        "description": "Execute a browser action by its ID from the current observation",
        "input_schema": {
            "type": "object",
            "properties": {
                "action_id": {
                    "type": "string",
                    "description": "The action ID from the room text",
                },
                "value": {
                    "type": "string",
                    "description": "Value for fill/select actions (only when *value marker present)",
                },
            },
            "required": ["action_id"],
        },
    },
    {
        "name": "browser_navigate",
        "description": "Navigate to a specific URL",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to navigate to"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_back",
        "description": "Go back in browser history",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "task_done",
        "description": "Signal that the task is complete",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What was accomplished"},
            },
            "required": ["summary"],
        },
    },
]

SYSTEM = """You are a browser automation agent. You receive a text description of a web page
and use tools to interact with it. Always dismiss blockers (cookie banners, modals) before
other actions. Use 'more' as action_id if your target isn't in the curated list."""


async def run_task(url: str, task: str, max_steps: int = 25) -> None:
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime

    await runtime.navigate(url)
    obs = await runtime.observe(mode="summary")

    messages = [
        {"role": "user", "content": f"Task: {task}\n\nCurrent page:\n{obs.planner.room_text}"},
    ]

    for step in range(max_steps):
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            break

        tool_block = next((b for b in response.content if b.type == "tool_use"), None)
        if not tool_block:
            break

        args = tool_block.input
        fn = tool_block.name
        print(f"[Step {step + 1}] {fn}({args})")

        messages.append({"role": "assistant", "content": response.content})

        if fn == "task_done":
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_block.id, "content": "Done."}],
            })
            break

        if fn == "browser_back":
            result = await runtime.back()
        elif fn == "browser_navigate":
            result = await runtime.navigate(args["url"])
        else:
            req = ActionRequest(action_id=args["action_id"], value=args.get("value"))
            result = await runtime.act(req)

        if result.status == "stale":
            obs = await runtime.observe(mode="summary")
        else:
            obs = result.observation

        tool_result = f"Status: {result.status}\nPage:\n{obs.planner.room_text}"
        messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_block.id, "content": tool_result}],
        })

    await session.close()


asyncio.run(run_task("https://news.ycombinator.com", "Find and open the top story"))
```

## HTTP Service Mode

For language-agnostic integration. Start the service, then call it from any HTTP client.

### Start the service

```bash
semantic-browser serve --host 127.0.0.1 --port 8765 --api-token dev-token
```

### Session lifecycle (curl)

```bash
# 1. Launch a browser session
SESSION=$(curl -s -X POST http://127.0.0.1:8765/sessions/launch \
  -H "Content-Type: application/json" \
  -H "X-API-Token: dev-token" \
  -d '{"headful": false, "profile_mode": "ephemeral"}' | jq -r '.session_id')

echo "Session: $SESSION"

# 2. Navigate
curl -s -X POST "http://127.0.0.1:8765/sessions/$SESSION/navigate" \
  -H "Content-Type: application/json" \
  -H "X-API-Token: dev-token" \
  -d '{"url": "https://example.com"}'

# 3. Observe
curl -s -X POST "http://127.0.0.1:8765/sessions/$SESSION/observe" \
  -H "Content-Type: application/json" \
  -H "X-API-Token: dev-token" \
  -d '{"mode": "summary"}' | jq '.planner.room_text'

# 4. Act
curl -s -X POST "http://127.0.0.1:8765/sessions/$SESSION/act" \
  -H "Content-Type: application/json" \
  -H "X-API-Token: dev-token" \
  -d '{"action": {"action_id": "act-XXXX-0"}}'

# 5. Close
curl -s -X POST "http://127.0.0.1:8765/sessions/$SESSION/close" \
  -H "X-API-Token: dev-token"
```

### Service endpoints reference

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/health` | — | `{status, version, active_sessions}` |
| POST | `/sessions/launch` | `LaunchRequest` | `{session_id}` |
| POST | `/sessions/attach` | `AttachRequest` | `{session_id}` |
| POST | `/sessions/{id}/close` | — | `{ok}` |
| POST | `/sessions/{id}/observe` | `ObserveRequest` | `Observation` |
| POST | `/sessions/{id}/inspect` | `InspectRequest` | inspect detail |
| POST | `/sessions/{id}/navigate` | `NavigateRequest` | `StepResult` |
| POST | `/sessions/{id}/act` | `ActRequest` | `StepResult` |
| POST | `/sessions/{id}/back` | — | `StepResult` |
| POST | `/sessions/{id}/forward` | — | `StepResult` |
| POST | `/sessions/{id}/reload` | — | `StepResult` |
| GET | `/sessions/{id}/diagnostics` | — | `DiagnosticsReport` |
| POST | `/sessions/{id}/export-trace` | `ExportTraceRequest` | `{path}` |

All endpoints accept an `X-API-Token` header when `SEMANTIC_BROWSER_API_TOKEN` is set.

## CDP Attach (Existing Browser)

Connect to an already-running Chrome instance via Chrome DevTools Protocol.

```python
import asyncio
from semantic_browser.runtime import SemanticBrowserRuntime
from semantic_browser.models import ActionRequest

async def attach_and_observe() -> None:
    # Start Chrome with: chrome --remote-debugging-port=9222
    runtime = await SemanticBrowserRuntime.from_cdp_endpoint(
        "ws://127.0.0.1:9222/devtools/browser/XXXXX",
        target_url_contains="example.com",  # optional: pick a specific tab
    )

    obs = await runtime.observe(mode="summary")
    print(obs.planner.room_text)

    await runtime.close()

asyncio.run(attach_and_observe())
```

CLI equivalent:

```bash
semantic-browser attach --cdp ws://127.0.0.1:9222/devtools/browser/XXXXX
semantic-browser observe --session <session_id> --mode summary
```

## Error Handling Pattern

Robust agent loops should handle failures gracefully:

```python
async def robust_act(runtime, action_id: str, value: str | None = None) -> StepResult:
    result = await runtime.act(ActionRequest(action_id=action_id, value=value))

    if result.status == "success":
        return result

    if result.status == "stale":
        obs = await runtime.observe(mode="summary")
        new_action = next(
            (a for a in obs.available_actions if a.label == result.request.action_id),
            None,
        )
        if new_action:
            return await runtime.act(ActionRequest(action_id=new_action.id, value=value))

    if result.status == "blocked":
        obs = result.observation
        for blocker in obs.blockers:
            if blocker.related_action_ids:
                await runtime.act(ActionRequest(action_id=blocker.related_action_ids[0]))
        return await runtime.act(ActionRequest(action_id=action_id, value=value))

    return result
```

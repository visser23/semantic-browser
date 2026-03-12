#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import math
import os
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import task_harness as harness
from task_harness import HARNESS_TASKS as CANONICAL_HARNESS_TASKS

from semantic_browser.runtime import SemanticBrowserRuntime

# Sonnet 4.6 pricing constants (USD per 1M tokens)
SONNET46_INPUT_USD_PER_1M = 3.00
SONNET46_OUTPUT_USD_PER_1M = 15.00


@dataclass
class Task:
    name: str
    site: str
    url: str
    request: str
    checks: list[str]
    title_checks: list[str]
    max_steps: int = 7


@dataclass
class Usage:
    tok_in: int
    tok_out: int
    tool_calls: int = 0


PAYLOAD_CHARS_PER_TOKEN_EST = 4.0


TASKS: list[Task] = [
    Task(
        name=t.name,
        site=t.category,
        url=t.url,
        request=t.goal,
        checks=list(t.success_checks),
        title_checks=list(t.success_title_checks),
        max_steps=t.max_steps,
    )
    for t in CANONICAL_HARNESS_TASKS
]


def selected_tasks() -> list[Task]:
    name_filter = os.getenv("BENCHMARK_TASK_NAME", "").strip().lower()
    max_tasks_raw = os.getenv("BENCHMARK_MAX_TASKS", "").strip()
    out = TASKS
    if name_filter:
        out = [t for t in out if t.name.lower() == name_filter]
        if not out:
            available = ", ".join(t.name for t in TASKS)
            raise RuntimeError(f"BENCHMARK_TASK_NAME={name_filter!r} not found. Available: {available}")
    if max_tasks_raw:
        max_tasks = max(1, int(max_tasks_raw))
        out = out[:max_tasks]
    return out


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _fetch_cdp_ws(version_url: str) -> str | None:
    try:
        with urllib.request.urlopen(version_url, timeout=5) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        value = str(raw.get("webSocketDebuggerUrl", "")).strip()
        return value or None
    except Exception:
        return None


def _resolve_cdp_ws() -> str:
    env_ws = os.getenv("CDP_WS", "").strip()
    if env_ws:
        return env_ws

    # Prefer direct Chrome remote-debug endpoint when available.
    ws = _fetch_cdp_ws("http://127.0.0.1:9222/json/version")
    if ws:
        return ws

    # OpenClaw is required for standard/openclaw methods; start if available.
    subprocess.run("openclaw browser start --browser-profile mia --json >/dev/null", shell=True, check=False)

    ws = _fetch_cdp_ws("http://127.0.0.1:18800/json/version")
    if ws:
        return ws

    ws = _fetch_cdp_ws("http://127.0.0.1:9222/json/version")
    if ws:
        return ws

    raise RuntimeError(
        "Cannot determine CDP websocket. Set CDP_WS explicitly or run OpenClaw/Chrome with remote debugging."
    )


def _iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from _iter_dicts(v)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


def _extract_tool_calls(payload: dict[str, Any]) -> int:
    count = 0
    for node in _iter_dicts(payload):
        node_type = str(node.get("type", "")).lower()
        if node_type in {"tool_call", "function_call", "tool_use", "web_search_call", "file_search_call", "computer_call"}:
            count += 1
        if isinstance(node.get("tool_calls"), list):
            count += len([x for x in node["tool_calls"] if isinstance(x, dict)])
        if isinstance(node.get("function_call"), dict):
            count += 1
        if isinstance(node.get("tool_call"), dict):
            count += 1
    return count


def _extract_usage(payload: dict[str, Any]) -> Usage:
    usage = payload.get("usage") or {}
    tok_in = usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("total_input_tokens") or 0
    tok_out = usage.get("completion_tokens") or usage.get("output_tokens") or usage.get("total_output_tokens") or 0
    if not tok_in:
        tok_in = usage.get("total_tokens", 0)
    return Usage(tok_in=int(tok_in or 0), tok_out=int(tok_out or 0), tool_calls=_extract_tool_calls(payload))




def _estimate_payload_bytes_and_tokens(payload: Any) -> tuple[int, int]:
    """Estimate browser/runtime payload size and token-equivalent load.

    Estimated token-equivalent uses character-count / 4 and is not billable.
    """
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload_bytes = len(text.encode("utf-8"))
    payload_tokens_est = int(math.ceil(len(text) / PAYLOAD_CHARS_PER_TOKEN_EST)) if text else 0
    return payload_bytes, payload_tokens_est


def _planner_billable_cost_usd(tok_in: int, tok_out: int) -> float:
    return round((tok_in * SONNET46_INPUT_USD_PER_1M + tok_out * SONNET46_OUTPUT_USD_PER_1M) / 1_000_000, 6)

def _planner_payload(request_text: str, page_view: dict[str, Any], history: list[str]) -> dict[str, Any]:
    schema_prompt = {
        "action": "click|type|press|done",
        "target": "candidate label snippet to match",
        "text": "text to type when action=type, otherwise empty",
        "reason": "short reason",
    }
    return {
        "task_request": request_text,
        "history": history[-8:],
        "page": page_view,
        "output_schema_example": schema_prompt,
    }


def _planner_via_openrouter(payload: dict[str, Any]) -> tuple[dict[str, Any], Usage]:
    model = os.getenv("BENCHMARK_MODEL", "google/gemma-3-27b-it:free")
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a browser task planner. Return compact JSON only with keys: "
                    "action,target,text,reason. Use only listed candidates. "
                    "Prefer click actions. Use done only when goal appears complete."
                ),
            },
            {"role": "user", "content": json.dumps(payload)},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 140,
        "temperature": 0,
    }

    api_key = _require_env("OPENROUTER_API_KEY")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Planner API HTTP {e.code}: {detail[:400]}") from e

    usage = _extract_usage(raw)
    content = ""
    choices = raw.get("choices") or []
    if choices:
        content = str((choices[0].get("message") or {}).get("content", "")).strip()
    parsed = {"action": "done", "target": "", "text": "", "reason": "no-content"}
    if content:
        try:
            maybe = json.loads(content)
            if isinstance(maybe, dict):
                parsed.update(maybe)
        except Exception:
            pass
    return parsed, usage


def _responses_output_text(raw: dict[str, Any]) -> str:
    direct = raw.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks: list[str] = []
    for item in raw.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "output_text":
                text = str(part.get("text") or "").strip()
                if text:
                    chunks.append(text)
    return "\n".join(chunks).strip()


def _planner_via_openai(payload: dict[str, Any]) -> tuple[dict[str, Any], Usage]:
    model = os.getenv("BENCHMARK_MODEL", "gpt-5.3-codex")
    body = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a browser task planner. Return compact JSON only with keys: "
                    "action,target,text,reason. Use only listed candidates. "
                    "Prefer click actions. Use done only when goal appears complete."
                ),
            },
            {"role": "user", "content": json.dumps(payload)},
        ],
        "max_output_tokens": 140,
        "temperature": 0,
    }
    api_key = _require_env("OPENAI_API_KEY")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI planner API HTTP {e.code}: {detail[:400]}") from e

    usage = _extract_usage(raw)
    content = _responses_output_text(raw)
    parsed = {"action": "done", "target": "", "text": "", "reason": "no-content"}
    if content:
        try:
            maybe = json.loads(content)
            if isinstance(maybe, dict):
                parsed.update(maybe)
        except Exception:
            pass
    return parsed, usage


def _planner_via_codex(payload: dict[str, Any]) -> tuple[dict[str, Any], Usage]:
    model = os.getenv("BENCHMARK_MODEL", "gpt-5.3-codex")
    prompt = (
        "You are a browser task planner. Return JSON only with keys action,target,text,reason. "
        "Use only listed candidates. Prefer click actions. Use done only when goal appears complete.\n\n"
        + json.dumps(payload)
    )
    cmd = ["codex", "exec", "--json", "--model", model, "-"]
    proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "codex planner failed")[:600]
        raise RuntimeError(f"Codex planner failed (exit {proc.returncode}): {msg}")

    parsed = {"action": "done", "target": "", "text": "", "reason": "no-content"}
    usage = Usage(tok_in=0, tok_out=0)
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except Exception:
            continue
        et = evt.get("type")
        if et == "item.completed":
            item = evt.get("item") or {}
            text = str(item.get("text") or "").strip()
            if text:
                try:
                    maybe = json.loads(text)
                    if isinstance(maybe, dict):
                        parsed.update(maybe)
                except Exception:
                    pass
        elif et == "turn.completed":
            u = evt.get("usage") or {}
            usage = Usage(tok_in=int(u.get("input_tokens") or 0), tok_out=int(u.get("output_tokens") or 0))
    return parsed, usage


def planner_next_action_from_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], Usage]:
    api = os.getenv("BENCHMARK_API", "codex").strip().lower()

    if api == "codex":
        parsed, usage = _planner_via_codex(payload)
    elif api == "openrouter":
        parsed, usage = _planner_via_openrouter(payload)
    elif api == "openai":
        parsed, usage = _planner_via_openai(payload)
    else:
        raise RuntimeError(f"Unsupported BENCHMARK_API={api!r}. Expected 'codex', 'openai' or 'openrouter'.")

    parsed["action"] = str(parsed.get("action", "done")).strip().lower()
    parsed["target"] = str(parsed.get("target", "")).strip()
    parsed["text"] = str(parsed.get("text", "")).strip()
    parsed["reason"] = str(parsed.get("reason", "")).strip()
    return parsed, usage


def planner_next_action(request_text: str, page_view: dict[str, Any], history: list[str]) -> tuple[dict[str, Any], Usage]:
    payload = _planner_payload(request_text, page_view, history)
    return planner_next_action_from_payload(payload)


def shq(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def sh(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True, text=True)


def run_json(cmd: str, stats: dict[str, int] | None = None) -> dict[str, Any]:
    if stats is not None:
        stats["browser_tool_calls"] = stats.get("browser_tool_calls", 0) + 1
    return json.loads(sh(cmd))


def open_tab(url: str, stats: dict[str, int] | None = None) -> str:
    opened = run_json(f"openclaw browser open --browser-profile mia --json {url}", stats)
    return str(opened["targetId"])


def _is_complete(url: str, title: str, text: str, checks: list[str], title_checks: list[str]) -> bool:
    hay = f"{url}\n{title}\n{text}".lower()
    if checks and any(c.lower() in hay for c in checks):
        return True
    t = title.lower()
    return bool(title_checks and any(c.lower() in t for c in title_checks))


def _match_index(candidates: list[dict[str, Any]], target: str) -> int | None:
    t = target.lower().strip()
    if not t:
        return None
    best_i = None
    best_score = 0
    for i, c in enumerate(candidates):
        label = str(c.get("label", "")).lower()
        if not label:
            continue
        score = 0
        if label == t:
            score = 100
        elif t in label:
            score = 50
        else:
            tokens = [x for x in t.split() if x]
            overlap = sum(1 for tok in tokens if tok in label)
            score = overlap * 10
        if score > best_score:
            best_score = score
            best_i = i
    return best_i if best_score > 0 else None


def _standard_observe(tid: str, stats: dict[str, int] | None = None) -> dict[str, Any]:
    fn = """() => {
      const nodes = Array.from(document.querySelectorAll('a,button,input,[role=button],[role=link],[role=menuitem],textarea,select')).slice(0, 250);
      const candidates = [];
      for (let i = 0; i < nodes.length; i++) {
        const el = nodes[i];
        const raw = (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim();
        if (!raw) continue;
        candidates.push({
          idx: i,
          label: raw.substring(0, 100),
          tag: (el.tagName || '').toLowerCase(),
          type: (el.getAttribute('type') || '').toLowerCase(),
          href: (el.getAttribute('href') || '').substring(0, 120),
          role: (el.getAttribute('role') || '').toLowerCase()
        });
      }
      return {
        url: location.href,
        title: document.title,
        text: ((document.body && document.body.innerText) || '').substring(0, 5000),
        candidates: candidates.slice(0, 80)
      };
    }"""
    payload = run_json(f"openclaw browser evaluate --browser-profile mia --target-id {tid} --fn {shq(fn)} --json", stats)
    return payload.get("result", {})


def _standard_exec(tid: str, action: dict[str, Any], candidates: list[dict[str, Any]], stats: dict[str, int] | None = None) -> tuple[bool, str]:
    idx = _match_index(candidates, action.get("target", ""))
    op = action.get("action", "")
    if op == "done":
        return True, "planner_done"
    if idx is None:
        return False, "target_not_found"

    if op == "click":
        js = (
            "() => {"
            f" const i = {idx};"
            " const nodes = Array.from(document.querySelectorAll('a,button,input,[role=button],[role=link],[role=menuitem],textarea,select')).slice(0, 250);"
            " const el = nodes[i]; if (!el) return false;"
            " try { el.click(); return true; } catch (e) { return false; }"
            "}"
        )
        res = run_json(f"openclaw browser evaluate --browser-profile mia --target-id {tid} --fn {shq(js)} --json", stats)
        return bool(res.get("result", False)), "click"

    if op == "type":
        txt = json.dumps(action.get("text", ""))
        js = (
            "() => {"
            f" const i = {idx};"
            f" const txt = {txt};"
            " const nodes = Array.from(document.querySelectorAll('a,button,input,[role=button],[role=link],[role=menuitem],textarea,select')).slice(0, 250);"
            " const el = nodes[i]; if (!el) return false;"
            " try {"
            "   el.focus();"
            "   el.value = txt;"
            "   el.dispatchEvent(new Event('input', { bubbles: true }));"
            "   el.dispatchEvent(new Event('change', { bubbles: true }));"
            "   return true;"
            " } catch (e) { return false; }"
            "}"
        )
        res = run_json(f"openclaw browser evaluate --browser-profile mia --target-id {tid} --fn {shq(js)} --json", stats)
        return bool(res.get("result", False)), "type"

    if op == "press":
        key = action.get("text", "Enter") or "Enter"
        _ = run_json(f"openclaw browser press --browser-profile mia --target-id {tid} '{key}' --json", stats)
        return True, f"press:{key}"

    return False, f"unsupported_op:{op}"


def standard_method(task: Task) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    t0 = time.perf_counter()
    tok_in = tok_out = planner_tool_calls = 0
    browser_payload_bytes = browser_payload_tokens_est = 0
    stats: dict[str, int] = {"browser_tool_calls": 0}
    history: list[str] = []
    journal: list[dict[str, Any]] = []
    tid = open_tab(task.url, stats)
    try:
        ok = False
        for step in range(1, task.max_steps + 1):
            obs = _standard_observe(tid, stats)
            done = _is_complete(obs.get("url", ""), obs.get("title", ""), obs.get("text", ""), task.checks, task.title_checks)
            if done:
                ok = True
                journal.append({"ts": _now_iso(), "step": step, "phase": "check", "done": True, "url": obs.get("url", "")})
                break
            planner_payload = _planner_payload(task.request, obs, history)
            payload_bytes, payload_tokens_est = _estimate_payload_bytes_and_tokens(planner_payload)
            browser_payload_bytes += payload_bytes
            browser_payload_tokens_est += payload_tokens_est
            plan, usage = planner_next_action_from_payload(planner_payload)
            tok_in += usage.tok_in
            tok_out += usage.tok_out
            planner_tool_calls += usage.tool_calls
            history.append(f"plan={plan}")
            acted, detail = _standard_exec(tid, plan, obs.get("candidates", []), stats)
            history.append(f"acted={acted}")
            journal.append(
                {
                    "ts": _now_iso(),
                    "step": step,
                    "phase": "plan_act",
                    "url": obs.get("url", ""),
                    "title": obs.get("title", ""),
                    "candidate_count": len(obs.get("candidates", [])),
                    "plan": plan,
                    "acted": acted,
                    "act_detail": detail,
                    "usage": {
                        "planner_input_tokens_billable": usage.tok_in,
                        "planner_output_tokens_billable": usage.tok_out,
                        "browser_payload_bytes": payload_bytes,
                        "browser_payload_tokens_estimated": payload_tokens_est,
                    },
                }
            )
            if plan.get("action") == "done":
                break
            time.sleep(0.8)
        ms = (time.perf_counter() - t0) * 1000
        browser_tool_calls = stats.get("browser_tool_calls", 0)
        return {
            "ok": ok,
            "stuck": not ok,
            "speed_ms": round(ms, 1),
            "tok_in": tok_in,
            "tok_out": tok_out,
            "planner_tool_calls": planner_tool_calls,
            "browser_tool_calls": browser_tool_calls,
            "tool_calls_total": planner_tool_calls + browser_tool_calls,
            "planner_input_tokens_billable": tok_in,
            "planner_output_tokens_billable": tok_out,
            "browser_payload_bytes": browser_payload_bytes,
            "browser_payload_tokens_estimated": browser_payload_tokens_est,
            "total_effective_context_load_tokens_estimated": tok_in + browser_payload_tokens_est,
            "indicative_planner_cost_usd": _planner_billable_cost_usd(tok_in, tok_out),
        }, journal
    finally:
        try:
            run_json(f"openclaw browser close --browser-profile mia {tid} --json", stats)
        except Exception:
            pass


def _openclaw_observe(tid: str, stats: dict[str, int] | None = None) -> dict[str, Any]:
    snap = run_json(f"openclaw browser snapshot --browser-profile mia --target-id {tid} --json", stats)
    refs = snap.get("refs", {})
    candidates = []
    for ref, meta in refs.items():
        candidates.append({"ref": ref, "label": str(meta.get("name", "")), "role": str(meta.get("role", ""))})
    return {
        "url": snap.get("url", ""),
        "title": snap.get("title", ""),
        "text": str(snap.get("snapshot", ""))[:5000],
        "candidates": candidates[:100],
    }


def _openclaw_exec(tid: str, action: dict[str, Any], candidates: list[dict[str, Any]], stats: dict[str, int] | None = None) -> tuple[bool, str]:
    op = action.get("action", "")
    if op == "done":
        return True, "planner_done"

    idx = _match_index(candidates, action.get("target", ""))
    if idx is None:
        return False, "target_not_found"
    chosen = candidates[idx]
    ref = chosen.get("ref")
    if not ref:
        return False, "missing_ref"

    if op == "click":
        _ = run_json(f"openclaw browser click --browser-profile mia --target-id {tid} {ref} --json", stats)
        return True, f"click:{ref}"
    if op == "type":
        text = action.get("text", "")
        _ = run_json(f"openclaw browser type --browser-profile mia --target-id {tid} {ref} {json.dumps(text)} --json", stats)
        return True, f"type:{ref}"
    if op == "press":
        key = action.get("text", "Enter") or "Enter"
        _ = run_json(f"openclaw browser press --browser-profile mia --target-id {tid} '{key}' --json", stats)
        return True, f"press:{key}"
    return False, f"unsupported_op:{op}"


def openclaw_method(task: Task) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    t0 = time.perf_counter()
    tok_in = tok_out = planner_tool_calls = 0
    browser_payload_bytes = browser_payload_tokens_est = 0
    stats: dict[str, int] = {"browser_tool_calls": 0}
    history: list[str] = []
    journal: list[dict[str, Any]] = []
    tid = open_tab(task.url, stats)
    try:
        ok = False
        for step in range(1, task.max_steps + 1):
            obs = _openclaw_observe(tid, stats)
            done = _is_complete(obs.get("url", ""), obs.get("title", ""), obs.get("text", ""), task.checks, task.title_checks)
            if done:
                ok = True
                journal.append({"ts": _now_iso(), "step": step, "phase": "check", "done": True, "url": obs.get("url", "")})
                break
            planner_payload = _planner_payload(task.request, obs, history)
            payload_bytes, payload_tokens_est = _estimate_payload_bytes_and_tokens(planner_payload)
            browser_payload_bytes += payload_bytes
            browser_payload_tokens_est += payload_tokens_est
            plan, usage = planner_next_action_from_payload(planner_payload)
            tok_in += usage.tok_in
            tok_out += usage.tok_out
            planner_tool_calls += usage.tool_calls
            history.append(f"plan={plan}")
            acted, detail = _openclaw_exec(tid, plan, obs.get("candidates", []), stats)
            history.append(f"acted={acted}")
            journal.append(
                {
                    "ts": _now_iso(),
                    "step": step,
                    "phase": "plan_act",
                    "url": obs.get("url", ""),
                    "title": obs.get("title", ""),
                    "candidate_count": len(obs.get("candidates", [])),
                    "plan": plan,
                    "acted": acted,
                    "act_detail": detail,
                    "usage": {
                        "planner_input_tokens_billable": usage.tok_in,
                        "planner_output_tokens_billable": usage.tok_out,
                        "browser_payload_bytes": payload_bytes,
                        "browser_payload_tokens_estimated": payload_tokens_est,
                    },
                }
            )
            if plan.get("action") == "done":
                break
            time.sleep(0.8)
        ms = (time.perf_counter() - t0) * 1000
        browser_tool_calls = stats.get("browser_tool_calls", 0)
        return {
            "ok": ok,
            "stuck": not ok,
            "speed_ms": round(ms, 1),
            "tok_in": tok_in,
            "tok_out": tok_out,
            "planner_tool_calls": planner_tool_calls,
            "browser_tool_calls": browser_tool_calls,
            "tool_calls_total": planner_tool_calls + browser_tool_calls,
            "planner_input_tokens_billable": tok_in,
            "planner_output_tokens_billable": tok_out,
            "browser_payload_bytes": browser_payload_bytes,
            "browser_payload_tokens_estimated": browser_payload_tokens_est,
            "total_effective_context_load_tokens_estimated": tok_in + browser_payload_tokens_est,
            "indicative_planner_cost_usd": _planner_billable_cost_usd(tok_in, tok_out),
        }, journal
    finally:
        try:
            run_json(f"openclaw browser close --browser-profile mia {tid} --json", stats)
        except Exception:
            pass


_SEMANTIC_SYSTEM_PROMPT = (
    "You are navigating a website to complete a task. "
    "You receive a room description showing your location, what you see, and available actions.\n\n"
    "Reply with ONLY ONE of:\n"
    "- An action ID from the list (e.g. a3)\n"
    "- An action ID followed by a quoted value for fill/type actions (e.g. a5 \"search text\")\n"
    "- more (to see all available actions if the one you need is not listed)\n"
    "- done (if the task goal is clearly achieved)\n\n"
    "Nothing else. No explanation. No JSON. Just the action ID."
)


def _semantic_build_prompt(task_request: str, room_text: str, history: list[str]) -> str:
    parts = [f"TASK: {task_request}"]
    if history:
        parts.append("\nHISTORY:\n" + "\n".join(history[-5:]))
    parts.append(f"\n{room_text}")
    return "\n".join(parts)


def _semantic_planner_via_openrouter(prompt: str) -> tuple[str, Usage]:
    model = os.getenv("BENCHMARK_MODEL", "google/gemma-3-27b-it:free")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SEMANTIC_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 60,
        "temperature": 0,
    }
    api_key = _require_env("OPENROUTER_API_KEY")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Planner API HTTP {e.code}: {detail[:400]}") from e
    usage = _extract_usage(raw)
    content = ""
    choices = raw.get("choices") or []
    if choices:
        content = str((choices[0].get("message") or {}).get("content", "")).strip()
    return content, Usage(tok_in=usage.tok_in, tok_out=usage.tok_out)


def _semantic_planner_via_openai(prompt: str) -> tuple[str, Usage]:
    model = os.getenv("BENCHMARK_MODEL", "gpt-5.3-codex")
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": _SEMANTIC_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_output_tokens": 60,
        "temperature": 0,
    }
    api_key = _require_env("OPENAI_API_KEY")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI planner API HTTP {e.code}: {detail[:400]}") from e
    usage = _extract_usage(raw)
    content = _responses_output_text(raw)
    return content, usage


def _semantic_planner_via_codex(prompt: str) -> tuple[str, Usage]:
    model = os.getenv("BENCHMARK_MODEL", "gpt-5.3-codex")
    full_prompt = _SEMANTIC_SYSTEM_PROMPT + "\n\n" + prompt
    cmd = ["codex", "exec", "--json", "--model", model, "-"]
    proc = subprocess.run(cmd, input=full_prompt, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "codex planner failed")[:600]
        raise RuntimeError(f"Codex planner failed (exit {proc.returncode}): {msg}")
    content = ""
    usage = Usage(tok_in=0, tok_out=0)
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except Exception:
            continue
        et = evt.get("type")
        if et == "item.completed":
            item = evt.get("item") or {}
            text = str(item.get("text") or "").strip()
            if text:
                content = text
        elif et == "turn.completed":
            u = evt.get("usage") or {}
            usage = Usage(tok_in=int(u.get("input_tokens") or 0), tok_out=int(u.get("output_tokens") or 0))
    return content, usage


def _semantic_planner_next_from_prompt(prompt: str) -> tuple[str, Usage]:
    api = os.getenv("BENCHMARK_API", "codex").strip().lower()
    if api == "codex":
        return _semantic_planner_via_codex(prompt)
    elif api == "openrouter":
        return _semantic_planner_via_openrouter(prompt)
    elif api == "openai":
        return _semantic_planner_via_openai(prompt)
    raise RuntimeError(f"Unsupported BENCHMARK_API={api!r}")


def _semantic_planner_next(task_request: str, room_text: str, history: list[str]) -> tuple[str, Usage]:
    prompt = _semantic_build_prompt(task_request, room_text, history)
    return _semantic_planner_next_from_prompt(prompt)


def _parse_semantic_response(response: str) -> tuple[str | None, str | None]:
    """Parse planner response into (action_id, optional_value).

    Expected formats: 'a3', 'a5 "text"', 'done', 'more'.
    """
    text = response.strip().strip("`").strip()
    if not text:
        return None, None
    if text.lower() == "done":
        return "done", None

    first_quote = text.find('"')
    if first_quote > 0:
        action_id = text[:first_quote].strip()
        value = text[first_quote:].strip().strip('"')
        return action_id, value

    tokens = text.split()
    return tokens[0], None


async def semantic_method(task: Task, ws: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    bench_journal_dir = Path("docs/benchmarks/journals") / datetime.now().strftime("%Y-%m-%d")
    bench_journal_dir.mkdir(parents=True, exist_ok=True)

    planner_payload_bytes = 0
    planner_payload_tokens_est = 0
    planner_tool_calls = 0

    original_planner_next = harness.planner_next

    def wrapped_planner_next(
        goal: str,
        room_text: str,
        history: list[str],
        *,
        image_path: str | None = None,
        system_prompt: str | None = None,
    ) -> tuple[str, harness.Usage]:
        nonlocal planner_payload_bytes, planner_payload_tokens_est, planner_tool_calls
        prompt = harness._build_prompt(goal, room_text, history)
        payload_bytes, payload_tokens_est = _estimate_payload_bytes_and_tokens(prompt)
        planner_payload_bytes += payload_bytes
        planner_payload_tokens_est += payload_tokens_est
        response, usage = original_planner_next(
            goal,
            room_text,
            history,
            image_path=image_path,
            system_prompt=system_prompt,
        )
        planner_tool_calls += int(getattr(usage, "tool_calls", 0) or 0)
        return response, usage

    harness.planner_next = wrapped_planner_next
    rt = await SemanticBrowserRuntime.from_cdp_endpoint(ws, prefer_non_blank=True)
    try:
        harness_task = harness.HarnessTask(
            name=task.name,
            category=task.site,
            url=task.url,
            goal=task.request,
            success_checks=list(task.checks),
            success_title_checks=list(task.title_checks),
            max_steps=task.max_steps,
            tags=[],
        )
        result, journal = await harness.run_task(harness_task, rt, bench_journal_dir)
    finally:
        harness.planner_next = original_planner_next
        await rt.close()

    plan_steps = [j for j in journal if j.get("phase") == "plan_act"]
    act_calls = 0
    for step in plan_steps:
        detail = str(step.get("act_detail", ""))
        action_id = str(step.get("action_id") or "")
        if action_id and action_id != "done" and detail != "see_more_blocked":
            act_calls += 1
    browser_tool_calls = 1 + len(plan_steps) + act_calls

    tok_in = int(result.get("tok_in", 0) or 0)
    tok_out = int(result.get("tok_out", 0) or 0)
    return {
        "ok": bool(result.get("ok")),
        "stuck": not bool(result.get("ok")),
        "speed_ms": float(result.get("speed_ms", 0) or 0),
        "tok_in": tok_in,
        "tok_out": tok_out,
        "planner_tool_calls": planner_tool_calls,
        "browser_tool_calls": browser_tool_calls,
        "tool_calls_total": planner_tool_calls + browser_tool_calls,
        "planner_input_tokens_billable": tok_in,
        "planner_output_tokens_billable": tok_out,
        "browser_payload_bytes": planner_payload_bytes,
        "browser_payload_tokens_estimated": planner_payload_tokens_est,
        "total_effective_context_load_tokens_estimated": tok_in + planner_payload_tokens_est,
        "indicative_planner_cost_usd": _planner_billable_cost_usd(tok_in, tok_out),
    }, journal


def summarise(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    vals = [float(r.get(key, 0) or 0) for r in rows]
    if not vals:
        return {"median": 0.0, "mean": 0.0, "n": 0}
    return {"median": round(statistics.median(vals), 1), "mean": round(statistics.mean(vals), 1), "n": len(vals)}


def cost_per_request_usd(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    avg_in = statistics.mean(float(r.get("planner_input_tokens_billable", r.get("tok_in", 0)) or 0) for r in rows)
    avg_out = statistics.mean(float(r.get("planner_output_tokens_billable", r.get("tok_out", 0)) or 0) for r in rows)
    return round((avg_in * SONNET46_INPUT_USD_PER_1M + avg_out * SONNET46_OUTPUT_USD_PER_1M) / 1_000_000, 6)


def failure_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if not r.get("ok"))


def success_rate(rows: list[dict[str, Any]]) -> float:
    return round(sum(1 for r in rows if r.get("ok")) / max(len(rows), 1), 2)


def success_only(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("ok")]


def _write_journal(path: Path, task: Task, method: str, result: dict[str, Any], entries: list[dict[str, Any]]) -> None:
    payload = {
        "task": task.name,
        "site": task.site,
        "url": task.url,
        "request": task.request,
        "method": method,
        "result": result,
        "entries": entries,
    }
    path.write_text(json.dumps(payload, indent=2))


async def main() -> None:
    planner_api = os.getenv("BENCHMARK_API", "codex").strip().lower()
    if planner_api == "openrouter":
        _require_env("OPENROUTER_API_KEY")

    ws = _resolve_cdp_ws()

    tasks = selected_tasks()
    per_task: list[dict[str, Any]] = []
    standard_rows: list[dict[str, Any]] = []
    openclaw_rows: list[dict[str, Any]] = []
    semantic_rows: list[dict[str, Any]] = []

    out_dir = Path("docs/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    journal_dir = out_dir / "journals" / stamp
    journal_dir.mkdir(parents=True, exist_ok=True)

    for task in tasks:
        try:
            std, std_j = standard_method(task)
        except Exception as e:
            std, std_j = ({"ok": False, "stuck": True, "speed_ms": 60000.0, "tok_in": 0, "tok_out": 0, "planner_tool_calls": 0, "browser_tool_calls": 0, "tool_calls_total": 0}, [{"error": repr(e)}])

        try:
            oc, oc_j = openclaw_method(task)
        except Exception as e:
            oc, oc_j = ({"ok": False, "stuck": True, "speed_ms": 60000.0, "tok_in": 0, "tok_out": 0, "planner_tool_calls": 0, "browser_tool_calls": 0, "tool_calls_total": 0}, [{"error": repr(e)}])

        try:
            sem, sem_j = await semantic_method(task, ws)
        except Exception as e:
            sem, sem_j = ({"ok": False, "stuck": True, "speed_ms": 60000.0, "tok_in": 0, "tok_out": 0, "planner_tool_calls": 0, "browser_tool_calls": 0, "tool_calls_total": 0}, [{"error": repr(e)}])

        standard_rows.append(std)
        openclaw_rows.append(oc)
        semantic_rows.append(sem)

        std_path = journal_dir / f"standard__{task.name}.json"
        oc_path = journal_dir / f"openclaw__{task.name}.json"
        sem_path = journal_dir / f"semantic__{task.name}.json"
        _write_journal(std_path, task, "standard_browser_tooling", std, std_j)
        _write_journal(oc_path, task, "openclaw_browser_tooling", oc, oc_j)
        _write_journal(sem_path, task, "semantic_browser_runtime", sem, sem_j)

        per_task.append(
            {
                "task": task.name,
                "site": task.site,
                "url": task.url,
                "request": task.request,
                "checks": task.checks,
                "standard": std,
                "openclaw": oc,
                "semantic": sem,
                "journals": {
                    "standard": str(std_path),
                    "openclaw": str(oc_path),
                    "semantic": str(sem_path),
                },
            }
        )

    summary = {
        "pricing": {
            "model_reference": "Anthropic Sonnet 4.6 (estimated)",
            "input_usd_per_1m": SONNET46_INPUT_USD_PER_1M,
            "output_usd_per_1m": SONNET46_OUTPUT_USD_PER_1M,
            "note": "Planner route can be non-Sonnet; cost is normalised using Sonnet 4.6 constants.",
            "payload_token_estimate_method": "Estimated as payload character count / 4; non-billable approximation.",
        },
        "planner_route": {"api": planner_api, "model": os.getenv("BENCHMARK_MODEL", "gpt-5.3-codex" if planner_api == "codex" else "google/gemma-3-27b-it:free")},
        "standard_browser_use": {
            "success_rate": success_rate(standard_rows),
            "failure_count": failure_count(standard_rows),
            "speed_ms": summarise(standard_rows, "speed_ms"),
            "planner_input_tokens_billable": summarise(standard_rows, "planner_input_tokens_billable"),
            "planner_output_tokens_billable": summarise(standard_rows, "planner_output_tokens_billable"),
            "browser_payload_bytes": summarise(standard_rows, "browser_payload_bytes"),
            "browser_payload_tokens_estimated": summarise(standard_rows, "browser_payload_tokens_estimated"),
            "total_effective_context_load_tokens_estimated": summarise(standard_rows, "total_effective_context_load_tokens_estimated"),
            "planner_tool_calls": summarise(standard_rows, "planner_tool_calls"),
            "browser_tool_calls": summarise(standard_rows, "browser_tool_calls"),
            "tool_calls_total": summarise(standard_rows, "tool_calls_total"),
            "tool_calls_total_success_only": summarise(success_only(standard_rows), "tool_calls_total"),
            "indicative_planner_cost_per_request_usd": cost_per_request_usd(standard_rows),
        },
        "openclaw_browser": {
            "success_rate": success_rate(openclaw_rows),
            "failure_count": failure_count(openclaw_rows),
            "speed_ms": summarise(openclaw_rows, "speed_ms"),
            "planner_input_tokens_billable": summarise(openclaw_rows, "planner_input_tokens_billable"),
            "planner_output_tokens_billable": summarise(openclaw_rows, "planner_output_tokens_billable"),
            "browser_payload_bytes": summarise(openclaw_rows, "browser_payload_bytes"),
            "browser_payload_tokens_estimated": summarise(openclaw_rows, "browser_payload_tokens_estimated"),
            "total_effective_context_load_tokens_estimated": summarise(openclaw_rows, "total_effective_context_load_tokens_estimated"),
            "planner_tool_calls": summarise(openclaw_rows, "planner_tool_calls"),
            "browser_tool_calls": summarise(openclaw_rows, "browser_tool_calls"),
            "tool_calls_total": summarise(openclaw_rows, "tool_calls_total"),
            "tool_calls_total_success_only": summarise(success_only(openclaw_rows), "tool_calls_total"),
            "indicative_planner_cost_per_request_usd": cost_per_request_usd(openclaw_rows),
        },
        "semantic_browser": {
            "success_rate": success_rate(semantic_rows),
            "failure_count": failure_count(semantic_rows),
            "speed_ms": summarise(semantic_rows, "speed_ms"),
            "planner_input_tokens_billable": summarise(semantic_rows, "planner_input_tokens_billable"),
            "planner_output_tokens_billable": summarise(semantic_rows, "planner_output_tokens_billable"),
            "browser_payload_bytes": summarise(semantic_rows, "browser_payload_bytes"),
            "browser_payload_tokens_estimated": summarise(semantic_rows, "browser_payload_tokens_estimated"),
            "total_effective_context_load_tokens_estimated": summarise(semantic_rows, "total_effective_context_load_tokens_estimated"),
            "planner_tool_calls": summarise(semantic_rows, "planner_tool_calls"),
            "browser_tool_calls": summarise(semantic_rows, "browser_tool_calls"),
            "tool_calls_total": summarise(semantic_rows, "tool_calls_total"),
            "tool_calls_total_success_only": summarise(success_only(semantic_rows), "tool_calls_total"),
            "indicative_planner_cost_per_request_usd": cost_per_request_usd(semantic_rows),
        },
        "task_count": len(tasks),
        "journal_dir": str(journal_dir),
    }

    out = {"summary": summary, "tasks": per_task}
    json_path = out_dir / "2026-03-11-actionset-compare.json"
    md_path = out_dir / "2026-03-11-actionset-compare.md"
    json_path.write_text(json.dumps(out, indent=2))

    task_count = len(tasks)
    md = [
        f"# End-to-end benchmark ({task_count} AI-driven multi-step public-site tasks)",
        "",
        "Methods compared per task request:",
        "- Standard browser tooling (raw DOM extraction + JS actions)",
        "- OpenClaw browser tooling (snapshot refs + browser actions)",
        "- Semantic Browser (observe/act with semantic action IDs)",
        "",
        f"Each method ran the exact same {task_count} prompts and used the same planner model route.",
        f"Planner route: `{summary['planner_route']['api']}:{summary['planner_route']['model']}`",
        "",
        "Cost model: Sonnet 4.6 estimated pricing constants (input $3.00 / 1M, output $15.00 / 1M).",
        "",
        "Metric basis (apples-to-apples across all three methods):",
        "- `planner input tokens (billable)`: tokens billed as planner input by the LLM provider.",
        "- `planner output tokens (billable)`: tokens billed as planner output by the LLM provider.",
        "- `browser/runtime payload bytes`: UTF-8 byte size of observation payload returned from browser/runtime and sent to planner.",
        "- `browser/runtime payload token-estimate` (estimated): payload character count ÷ 4 (non-billable estimate).",
        "- `total effective context load` (estimated): planner input tokens + payload token-estimate.",
        "- `planner tool calls`: LLM-declared tool/function calls returned by planner API response payloads.",
        "- `browser/runtime calls`: browser operations issued by each method loop (navigate/observe/act/open/close/evaluate/click/type/press).",
        "- `total tool calls`: planner tool calls + browser/runtime calls.",
        "- `indicative planner cost/request`: Sonnet 4.6-normalised cost from planner billable tokens only.",
        "",
        "| Method | Success rate | Failures | Median speed ms | Planner in (billable) | Planner out (billable) | Browser payload bytes | Payload token-est (estimated) | Total effective context load (estimated) | Median planner tool calls | Median browser/runtime calls | Median total tool calls | Median total tool calls (success-only) | Indicative planner cost/request (USD) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for key, label in [
        ("standard_browser_use", "Standard browser tooling"),
        ("openclaw_browser", "OpenClaw browser tooling"),
        ("semantic_browser", "Semantic Browser"),
    ]:
        s = summary[key]
        md.append(
            f"| {label} | {s['success_rate']} | {s['failure_count']} | {s['speed_ms']['median']} | {s['planner_input_tokens_billable']['median']} | {s['planner_output_tokens_billable']['median']} | {s['browser_payload_bytes']['median']} | {s['browser_payload_tokens_estimated']['median']} | {s['total_effective_context_load_tokens_estimated']['median']} | {s['planner_tool_calls']['median']} | {s['browser_tool_calls']['median']} | {s['tool_calls_total']['median']} | {s['tool_calls_total_success_only']['median']} | {s['indicative_planner_cost_per_request_usd']:.6f} |"
        )

    md.extend([
        "",
        "## Per-run journals",
        "",
        f"- JSON journals directory: `{journal_dir}`",
        f"- One journal file is written for every method x task run ({task_count * 3} files total).", 
        "",
        "## Tasks",
        "",
        *[f"- **{t.name}** ({t.site}): {t.request}" for t in tasks],
        "",
        f"Artifacts: `{md_path}` and `{json_path}`",
    ])

    md_path.write_text("\n".join(md))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

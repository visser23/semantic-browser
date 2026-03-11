#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from semantic_browser.models import ActionRequest
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
    max_steps: int = 5


@dataclass
class Usage:
    tok_in: int
    tok_out: int


TASKS: list[Task] = [
    Task(
        name="amazon_deals_electronics",
        site="amazon",
        url="https://www.amazon.co.uk/",
        request="Open Today's Deals, then navigate to Electronics deals.",
        checks=["/gp/goldbox"],
    ),
    Task(
        name="reddit_popular_askreddit",
        site="reddit",
        url="https://www.reddit.com/",
        request="Open the Popular feed, then open r/AskReddit.",
        checks=["/r/askreddit"],
    ),
    Task(
        name="youtube_explore_trending",
        site="youtube",
        url="https://www.youtube.com/",
        request="Open Explore, then open Trending.",
        checks=["/feed/trending"],
    ),
    Task(
        name="bbc_news_technology",
        site="bbc",
        url="https://www.bbc.co.uk/",
        request="Open BBC News, then open the Technology section.",
        checks=["/news/technology"],
    ),
    Task(
        name="wikipedia_english_current_events",
        site="wikipedia",
        url="https://www.wikipedia.org/",
        request="Open English Wikipedia, then open Current events.",
        checks=["Portal:Current_events"],
    ),
]


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _extract_usage(payload: dict[str, Any]) -> Usage:
    usage = payload.get("usage") or {}
    tok_in = usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("total_input_tokens") or 0
    tok_out = usage.get("completion_tokens") or usage.get("output_tokens") or usage.get("total_output_tokens") or 0
    return Usage(tok_in=int(tok_in or 0), tok_out=int(tok_out or 0))


def planner_next_action(request_text: str, page_view: dict[str, Any], history: list[str]) -> tuple[dict[str, Any], Usage]:
    api = os.getenv("BENCHMARK_API", "openrouter").strip().lower()
    model = os.getenv("BENCHMARK_MODEL", "openai/gpt-4.1-mini")

    schema_prompt = {
        "action": "click|type|press|done",
        "target": "candidate label snippet to match",
        "text": "text to type when action=type, otherwise empty",
        "reason": "short reason",
    }

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
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task_request": request_text,
                        "history": history[-8:],
                        "page": page_view,
                        "output_schema_example": schema_prompt,
                    }
                ),
            },
        ],
        "response_format": {"type": "json_object"},
    }

    if api == "openai":
        api_key = _require_env("OPENAI_API_KEY")
        url = "https://api.openai.com/v1/chat/completions"
        body["max_completion_tokens"] = 120
    else:
        api_key = _require_env("OPENROUTER_API_KEY")
        url = "https://openrouter.ai/api/v1/chat/completions"
        body["max_tokens"] = 120
        body["temperature"] = 0

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Planner API HTTP {e.code}: {detail[:400]}") from e

    usage = _extract_usage(payload)
    content = ""
    choices = payload.get("choices") or []
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

    parsed["action"] = str(parsed.get("action", "done")).strip().lower()
    parsed["target"] = str(parsed.get("target", "")).strip()
    parsed["text"] = str(parsed.get("text", "")).strip()
    parsed["reason"] = str(parsed.get("reason", "")).strip()
    return parsed, usage


def shq(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def sh(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True, text=True)


def run_json(cmd: str) -> dict[str, Any]:
    return json.loads(sh(cmd))


def open_tab(url: str) -> str:
    opened = run_json(f"openclaw browser open --browser-profile mia --json {url}")
    return str(opened["targetId"])


def _is_complete(url: str, title: str, text: str, checks: list[str]) -> bool:
    hay = f"{url}\n{title}\n{text}".lower()
    return any(c.lower() in hay for c in checks)


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


def _standard_observe(tid: str) -> dict[str, Any]:
    fn = """() => {
      const nodes = Array.from(document.querySelectorAll('a,button,input,[role=button],[role=link],[role=menuitem],textarea,select')).slice(0, 200);
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
        text: ((document.body && document.body.innerText) || '').substring(0, 4000),
        candidates: candidates.slice(0, 60)
      };
    }"""
    payload = run_json(f"openclaw browser evaluate --browser-profile mia --target-id {tid} --fn {shq(fn)} --json")
    return payload.get("result", {})


def _standard_exec(tid: str, action: dict[str, Any], candidates: list[dict[str, Any]]) -> bool:
    idx = _match_index(candidates, action.get("target", ""))
    op = action.get("action", "")
    if op == "done":
        return True
    if idx is None:
        return False

    if op == "click":
        js = (
            "() => {"
            f" const i = {idx};"
            " const nodes = Array.from(document.querySelectorAll('a,button,input,[role=button],[role=link],[role=menuitem],textarea,select')).slice(0, 200);"
            " const el = nodes[i]; if (!el) return false;"
            " try { el.click(); return true; } catch (e) { return false; }"
            "}"
        )
        res = run_json(f"openclaw browser evaluate --browser-profile mia --target-id {tid} --fn {shq(js)} --json")
        return bool(res.get("result", False))

    if op == "type":
        txt = json.dumps(action.get("text", ""))
        js = (
            "() => {"
            f" const i = {idx};"
            f" const txt = {txt};"
            " const nodes = Array.from(document.querySelectorAll('a,button,input,[role=button],[role=link],[role=menuitem],textarea,select')).slice(0, 200);"
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
        res = run_json(f"openclaw browser evaluate --browser-profile mia --target-id {tid} --fn {shq(js)} --json")
        return bool(res.get("result", False))

    if op == "press":
        key = action.get("text", "Enter") or "Enter"
        _ = run_json(f"openclaw browser press --browser-profile mia --target-id {tid} '{key}' --json")
        return True

    return False


def standard_method(task: Task) -> dict[str, Any]:
    t0 = time.perf_counter()
    tok_in = tok_out = 0
    history: list[str] = []
    tid = open_tab(task.url)
    try:
        ok = False
        for _ in range(task.max_steps):
            obs = _standard_observe(tid)
            if _is_complete(obs.get("url", ""), obs.get("title", ""), obs.get("text", ""), task.checks):
                ok = True
                break
            plan, usage = planner_next_action(task.request, obs, history)
            tok_in += usage.tok_in
            tok_out += usage.tok_out
            history.append(f"plan={plan}")
            acted = _standard_exec(tid, plan, obs.get("candidates", []))
            history.append(f"acted={acted}")
            if plan.get("action") == "done":
                break
            time.sleep(0.6)
        ms = (time.perf_counter() - t0) * 1000
        return {"ok": ok, "stuck": not ok, "speed_ms": round(ms, 1), "tok_in": tok_in, "tok_out": tok_out}
    finally:
        subprocess.run(f"openclaw browser close --browser-profile mia {tid} --json >/dev/null", shell=True, check=False)


def _openclaw_observe(tid: str) -> dict[str, Any]:
    snap = run_json(f"openclaw browser snapshot --browser-profile mia --target-id {tid} --json")
    refs = snap.get("refs", {})
    candidates = []
    for ref, meta in refs.items():
        candidates.append(
            {
                "ref": ref,
                "label": str(meta.get("name", "")),
                "role": str(meta.get("role", "")),
            }
        )
    return {
        "url": snap.get("url", ""),
        "title": snap.get("title", ""),
        "text": str(snap.get("snapshot", ""))[:4000],
        "candidates": candidates[:80],
    }


def _openclaw_exec(tid: str, action: dict[str, Any], candidates: list[dict[str, Any]]) -> bool:
    op = action.get("action", "")
    if op == "done":
        return True

    idx = _match_index(candidates, action.get("target", ""))
    if idx is None:
        return False
    chosen = candidates[idx]
    ref = chosen.get("ref")
    if not ref:
        return False

    if op == "click":
        _ = run_json(f"openclaw browser click --browser-profile mia --target-id {tid} {ref} --json")
        return True
    if op == "type":
        text = action.get("text", "")
        _ = run_json(f"openclaw browser type --browser-profile mia --target-id {tid} {ref} {json.dumps(text)} --json")
        return True
    if op == "press":
        key = action.get("text", "Enter") or "Enter"
        _ = run_json(f"openclaw browser press --browser-profile mia --target-id {tid} '{key}' --json")
        return True
    return False


def openclaw_method(task: Task) -> dict[str, Any]:
    t0 = time.perf_counter()
    tok_in = tok_out = 0
    history: list[str] = []
    tid = open_tab(task.url)
    try:
        ok = False
        for _ in range(task.max_steps):
            obs = _openclaw_observe(tid)
            if _is_complete(obs.get("url", ""), obs.get("title", ""), obs.get("text", ""), task.checks):
                ok = True
                break
            plan, usage = planner_next_action(task.request, obs, history)
            tok_in += usage.tok_in
            tok_out += usage.tok_out
            history.append(f"plan={plan}")
            acted = False
            try:
                acted = _openclaw_exec(tid, plan, obs.get("candidates", []))
            except Exception:
                acted = False
            history.append(f"acted={acted}")
            if plan.get("action") == "done":
                break
            time.sleep(0.6)
        ms = (time.perf_counter() - t0) * 1000
        return {"ok": ok, "stuck": not ok, "speed_ms": round(ms, 1), "tok_in": tok_in, "tok_out": tok_out}
    finally:
        subprocess.run(f"openclaw browser close --browser-profile mia {tid} --json >/dev/null", shell=True, check=False)


def _semantic_obs_to_view(obs: Any) -> dict[str, Any]:
    candidates = []
    for a in obs.available_actions[:120]:
        if not a.enabled:
            continue
        if a.op not in {"open", "click", "type", "fill", "press", "toggle", "select_option"}:
            continue
        candidates.append({"id": a.id, "op": a.op, "label": a.label or ""})
    planner = obs.planner.model_dump() if obs.planner else {}
    return {
        "url": obs.page.url,
        "title": obs.page.title,
        "text": json.dumps(planner)[:4000],
        "candidates": candidates[:80],
    }


def _semantic_pick_action_id(candidates: list[dict[str, Any]], target: str) -> str | None:
    idx = _match_index(candidates, target)
    if idx is None:
        return None
    return str(candidates[idx].get("id") or "") or None


async def semantic_method(task: Task, ws: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    tok_in = tok_out = 0
    history: list[str] = []
    rt = await SemanticBrowserRuntime.from_cdp_endpoint(ws, prefer_non_blank=True)
    try:
        await rt.navigate(task.url)
        ok = False
        for _ in range(task.max_steps):
            obs = await rt.observe("auto")
            view = _semantic_obs_to_view(obs)
            if _is_complete(view.get("url", ""), view.get("title", ""), view.get("text", ""), task.checks):
                ok = True
                break
            plan, usage = planner_next_action(task.request, view, history)
            tok_in += usage.tok_in
            tok_out += usage.tok_out
            history.append(f"plan={plan}")
            if plan.get("action") == "done":
                break
            action_id = _semantic_pick_action_id(view.get("candidates", []), plan.get("target", ""))
            acted = False
            if action_id:
                try:
                    step = await rt.act(ActionRequest(action_id=action_id))
                    acted = step.status == "success"
                except Exception:
                    acted = False
            history.append(f"acted={acted}")
            await asyncio.sleep(0.6)
        ms = (time.perf_counter() - t0) * 1000
        return {"ok": ok, "stuck": not ok, "speed_ms": round(ms, 1), "tok_in": tok_in, "tok_out": tok_out}
    finally:
        await rt.close()


def summarise(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    vals = [float(r.get(key, 0) or 0) for r in rows]
    if not vals:
        return {"median": 0.0, "mean": 0.0, "n": 0}
    return {
        "median": round(statistics.median(vals), 1),
        "mean": round(statistics.mean(vals), 1),
        "n": len(vals),
    }


def cost_per_request_usd(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    avg_in = statistics.mean(float(r.get("tok_in", 0) or 0) for r in rows)
    avg_out = statistics.mean(float(r.get("tok_out", 0) or 0) for r in rows)
    return round((avg_in * SONNET46_INPUT_USD_PER_1M + avg_out * SONNET46_OUTPUT_USD_PER_1M) / 1_000_000, 6)


def failure_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if not r.get("ok"))


def success_rate(rows: list[dict[str, Any]]) -> float:
    return round(sum(1 for r in rows if r.get("ok")) / max(len(rows), 1), 2)


async def main() -> None:
    # Require at least one provider key; planner route must be consistent for all methods.
    api = os.getenv("BENCHMARK_API", "openrouter").strip().lower()
    if api == "openai":
        _require_env("OPENAI_API_KEY")
    else:
        _require_env("OPENROUTER_API_KEY")

    subprocess.run("openclaw browser start --browser-profile mia --json >/dev/null", shell=True, check=False)
    ws = sh("curl -s http://127.0.0.1:18800/json/version | /opt/homebrew/bin/jq -r '.webSocketDebuggerUrl'").strip()

    per_task: list[dict[str, Any]] = []
    standard_rows: list[dict[str, Any]] = []
    openclaw_rows: list[dict[str, Any]] = []
    semantic_rows: list[dict[str, Any]] = []

    for task in TASKS:
        try:
            std = standard_method(task)
        except Exception:
            std = {"ok": False, "stuck": True, "speed_ms": 60000.0, "tok_in": 0, "tok_out": 0}

        try:
            oc = openclaw_method(task)
        except Exception:
            oc = {"ok": False, "stuck": True, "speed_ms": 60000.0, "tok_in": 0, "tok_out": 0}

        try:
            sem = await semantic_method(task, ws)
        except Exception:
            sem = {"ok": False, "stuck": True, "speed_ms": 60000.0, "tok_in": 0, "tok_out": 0}

        standard_rows.append(std)
        openclaw_rows.append(oc)
        semantic_rows.append(sem)
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
            }
        )

    summary = {
        "pricing": {
            "model_reference": "Anthropic Sonnet 4.6 (estimated)",
            "input_usd_per_1m": SONNET46_INPUT_USD_PER_1M,
            "output_usd_per_1m": SONNET46_OUTPUT_USD_PER_1M,
            "note": "Planner route can be non-Sonnet; cost is normalised using Sonnet 4.6 constants.",
        },
        "planner_route": {
            "api": api,
            "model": os.getenv("BENCHMARK_MODEL", "openai/gpt-4.1-mini"),
        },
        "standard_browser_use": {
            "success_rate": success_rate(standard_rows),
            "failure_count": failure_count(standard_rows),
            "speed_ms": summarise(standard_rows, "speed_ms"),
            "tok_in": summarise(standard_rows, "tok_in"),
            "tok_out": summarise(standard_rows, "tok_out"),
            "estimated_cost_per_request_usd": cost_per_request_usd(standard_rows),
        },
        "openclaw_browser": {
            "success_rate": success_rate(openclaw_rows),
            "failure_count": failure_count(openclaw_rows),
            "speed_ms": summarise(openclaw_rows, "speed_ms"),
            "tok_in": summarise(openclaw_rows, "tok_in"),
            "tok_out": summarise(openclaw_rows, "tok_out"),
            "estimated_cost_per_request_usd": cost_per_request_usd(openclaw_rows),
        },
        "semantic_browser": {
            "success_rate": success_rate(semantic_rows),
            "failure_count": failure_count(semantic_rows),
            "speed_ms": summarise(semantic_rows, "speed_ms"),
            "tok_in": summarise(semantic_rows, "tok_in"),
            "tok_out": summarise(semantic_rows, "tok_out"),
            "estimated_cost_per_request_usd": cost_per_request_usd(semantic_rows),
        },
        "task_count": len(TASKS),
    }

    out = {"summary": summary, "tasks": per_task}
    out_dir = Path("docs/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "2026-03-11-actionset-compare.json"
    md_path = out_dir / "2026-03-11-actionset-compare.md"
    json_path.write_text(json.dumps(out, indent=2))

    md = [
        "# End-to-end benchmark (5 complex public-site tasks)",
        "",
        "Methods compared per task request:",
        "- Standard browser tooling (raw DOM extraction + JS actions)",
        "- OpenClaw browser tooling (snapshot refs + browser actions)",
        "- Semantic Browser (observe/act with semantic action IDs)",
        "",
        f"Planner route: `{summary['planner_route']['api']}:{summary['planner_route']['model']}` (same for all methods)",
        "",
        "Cost model: Sonnet 4.6 estimated pricing constants (input $3.00 / 1M, output $15.00 / 1M).",
        "",
        "| Method | Success rate | Failures | Median speed ms | Median tok-in | Median tok-out | Est. cost/request (USD) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for key, label in [
        ("standard_browser_use", "Standard browser tooling"),
        ("openclaw_browser", "OpenClaw browser tooling"),
        ("semantic_browser", "Semantic Browser"),
    ]:
        s = summary[key]
        md.append(
            f"| {label} | {s['success_rate']} | {s['failure_count']} | {s['speed_ms']['median']} | {s['tok_in']['median']} | {s['tok_out']['median']} | {s['estimated_cost_per_request_usd']:.6f} |"
        )

    md.extend(
        [
            "",
            "## Tasks",
            "",
            *[f"- **{t.name}** ({t.site}): {t.request}" for t in TASKS],
            "",
            f"Artifacts: `{md_path}` and `{json_path}`",
        ]
    )

    md_path.write_text("\n".join(md))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

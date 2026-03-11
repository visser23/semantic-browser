#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import statistics
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tiktoken
from semantic_browser.models import ActionRequest
from semantic_browser.runtime import SemanticBrowserRuntime


@dataclass
class Task:
    site: str
    url: str
    keyword: str


SYNONYMS: dict[str, list[str]] = {
    "log in": ["log in", "sign in", "signin"],
    "sign in": ["sign in", "log in", "signin"],
    "search": ["search", "find"],
    "account": ["account", "profile", "your account"],
    "request a demo": ["request a demo", "demo"],
    "post": ["post", "tweet", "create"],
    "english": ["english", "en"],
}


TASKS: list[Task] = [
    Task("amazon", "https://www.amazon.co.uk/", "search"),
    Task("amazon", "https://www.amazon.co.uk/", "account"),
    Task("youtube", "https://www.youtube.com/", "search"),
    Task("youtube", "https://www.youtube.com/", "sign in"),
    Task("reddit", "https://www.reddit.com/", "search"),
    Task("reddit", "https://www.reddit.com/", "log in"),
    Task("linkedin", "https://www.linkedin.com/feed/", "sign in"),
    Task("linkedin", "https://www.linkedin.com/feed/", "join"),
    Task("instagram", "https://www.instagram.com/", "log in"),
    Task("instagram", "https://www.instagram.com/", "sign up"),
    Task("x", "https://x.com/home", "search"),
    Task("x", "https://x.com/home", "post"),
    Task("google_maps", "https://www.google.com/maps", "search"),
    Task("google_maps", "https://www.google.com/maps", "directions"),
    Task("notion", "https://www.notion.so/", "log in"),
    Task("notion", "https://www.notion.so/", "request a demo"),
    Task("wikipedia", "https://www.wikipedia.org/", "search"),
    Task("wikipedia", "https://www.wikipedia.org/", "english"),
    Task("bbc", "https://www.bbc.co.uk/", "news"),
    Task("bbc", "https://www.bbc.co.uk/", "sport"),
]

enc = tiktoken.get_encoding("cl100k_base")


def toks(s: str) -> int:
    return len(enc.encode(s))


def sh(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True, text=True)


def run_json(cmd: str) -> dict[str, Any]:
    return json.loads(sh(cmd))


def open_tab(url: str) -> str:
    opened = run_json(f"openclaw browser open --browser-profile mia --json {url}")
    return str(opened["targetId"])


def standard_method(task: Task) -> dict[str, Any]:
    t0 = time.perf_counter()
    tid = open_tab(task.url)
    try:
        fn_payload = "() => ({ title: document.title, url: location.href, text: (document.body?.innerText || \"\").slice(0, 12000) })"
        payload = run_json(f"openclaw browser evaluate --browser-profile mia --target-id {tid} --fn '{fn_payload}' --json")
        result = payload.get("result", {})
        planner_in = json.dumps({"location": result.get("url", ""), "title": result.get("title", ""), "content": result.get("text", "")})
        action = {"op": "click_text", "keyword": task.keyword}
        kw = json.dumps(task.keyword.lower())
        js = (
            "() => {"
            f" const q = {kw};"
            " const nodes = Array.from(document.querySelectorAll(\"a,button,input,[role=button],[role=link]\"));"
            " for (const el of nodes) {"
            "   const txt = ((el.innerText||el.textContent||el.getAttribute(\"aria-label\")||el.getAttribute(\"placeholder\")||\"\").trim()).toLowerCase();"
            "   if (!txt.includes(q)) continue;"
            "   const r = el.getBoundingClientRect();"
            "   if (r.width <= 0 || r.height <= 0) continue;"
            "   try { el.click(); return true; } catch (e) {}"
            " }"
            " return false;"
            "}"
        )
        exec_res = run_json(f"openclaw browser evaluate --browser-profile mia --target-id {tid} --fn '{js}' --json")
        ok = bool(exec_res.get("result", False))
        ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": ok,
            "stuck": not ok,
            "speed_ms": round(ms, 1),
            "tok_in": toks(planner_in),
            "tok_out": toks(json.dumps(action)),
        }
    finally:
        subprocess.run(f"openclaw browser close --browser-profile mia {tid} --json >/dev/null", shell=True, check=False)


def openclaw_method(task: Task) -> dict[str, Any]:
    t0 = time.perf_counter()
    tid = open_tab(task.url)
    try:
        snap = run_json(f"openclaw browser snapshot --browser-profile mia --target-id {tid} --json")
        refs = snap.get("refs", {})
        planner_in = json.dumps({"url": snap.get("url"), "snapshot": snap.get("snapshot", ""), "refs": refs})
        chosen_ref = None
        q = task.keyword.lower()
        for ref, meta in refs.items():
            name = str(meta.get("name", "")).lower()
            role = str(meta.get("role", "")).lower()
            if q in name and role in {"link", "button", "textbox", "searchbox", "menuitem", "tab"}:
                chosen_ref = ref
                break
        if chosen_ref is None:
            ms = (time.perf_counter() - t0) * 1000
            return {"ok": False, "stuck": True, "speed_ms": round(ms, 1), "tok_in": toks(planner_in), "tok_out": toks(json.dumps({"kind": "click", "ref": ""}))}
        action = {"kind": "click", "ref": chosen_ref}
        ok = True
        try:
            _ = run_json(f"openclaw browser click --browser-profile mia --target-id {tid} {chosen_ref} --json")
        except Exception:
            ok = False
        ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": ok,
            "stuck": not ok,
            "speed_ms": round(ms, 1),
            "tok_in": toks(planner_in),
            "tok_out": toks(json.dumps(action)),
        }
    finally:
        subprocess.run(f"openclaw browser close --browser-profile mia {tid} --json >/dev/null", shell=True, check=False)


def _semantic_choose_action(obs: Any, keyword: str):
    terms = SYNONYMS.get(keyword.lower(), [keyword.lower()])
    for a in obs.available_actions:
        label = (a.label or "").lower()
        if any(t in label for t in terms) and a.op in {"open", "click", "fill", "toggle", "select_option"} and a.enabled:
            return a
    return None


async def semantic_method(task: Task, ws: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    rt = await SemanticBrowserRuntime.from_cdp_endpoint(ws, prefer_non_blank=True)
    try:
        await rt.navigate(task.url)
        obs = await rt.observe("auto")
        planner = obs.planner.model_dump() if obs.planner else {}
        tok_in_total = toks(json.dumps(planner))

        chosen = _semantic_choose_action(obs, task.keyword)
        if chosen is None:
            obs_full = await rt.observe("full")
            planner_full = obs_full.planner.model_dump() if obs_full.planner else {}
            tok_in_total += toks(json.dumps(planner_full))
            chosen = _semantic_choose_action(obs_full, task.keyword)
            obs = obs_full

        if chosen is None:
            ms = (time.perf_counter() - t0) * 1000
            return {"ok": False, "stuck": True, "speed_ms": round(ms, 1), "tok_in": tok_in_total, "tok_out": toks(json.dumps({"action_id": ""})), "route": obs.metrics.extraction_route}

        step = await rt.act(ActionRequest(action_id=chosen.id))
        ok = step.status == "success"
        ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": ok,
            "stuck": not ok,
            "speed_ms": round(ms, 1),
            "tok_in": tok_in_total,
            "tok_out": toks(json.dumps({"action_id": chosen.id})),
            "route": obs.metrics.extraction_route,
        }
    finally:
        await rt.close()


def summarise(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    vals = [float(r[key]) for r in rows]
    return {"median": round(statistics.median(vals), 1), "mean": round(statistics.mean(vals), 1)}


async def main() -> None:
    subprocess.run("openclaw browser start --browser-profile mia --json >/dev/null", shell=True, check=False)
    ws = sh("curl -s http://127.0.0.1:18800/json/version | /opt/homebrew/bin/jq -r '.webSocketDebuggerUrl'").strip()

    per_task: list[dict[str, Any]] = []
    standard_rows, openclaw_rows, semantic_rows = [], [], []

    for task in TASKS:
        try:
            std = standard_method(task)
        except Exception:
            std = {"ok": False, "stuck": True, "speed_ms": 30000.0, "tok_in": 0, "tok_out": 0}
        try:
            oc = openclaw_method(task)
        except Exception:
            oc = {"ok": False, "stuck": True, "speed_ms": 30000.0, "tok_in": 0, "tok_out": 0}
        try:
            sem = await semantic_method(task, ws)
        except Exception:
            sem = {"ok": False, "stuck": True, "speed_ms": 30000.0, "tok_in": 0, "tok_out": 0, "route": "error"}

        standard_rows.append(std)
        openclaw_rows.append(oc)
        semantic_rows.append(sem)
        per_task.append({"site": task.site, "url": task.url, "keyword": task.keyword, "standard": std, "openclaw": oc, "semantic": sem})

    def success_rate(rows: list[dict[str, Any]]) -> float:
        return round(sum(1 for r in rows if r["ok"]) / max(len(rows), 1), 2)

    def stuck_rate(rows: list[dict[str, Any]]) -> float:
        return round(sum(1 for r in rows if r["stuck"]) / max(len(rows), 1), 2)

    summary = {
        "standard_browser_use": {
            "task_success_rate": success_rate(standard_rows),
            "stuck_rate": stuck_rate(standard_rows),
            "speed_ms": summarise(standard_rows, "speed_ms"),
            "tok_in": summarise(standard_rows, "tok_in"),
            "tok_out": summarise(standard_rows, "tok_out"),
        },
        "openclaw_browser": {
            "task_success_rate": success_rate(openclaw_rows),
            "stuck_rate": stuck_rate(openclaw_rows),
            "speed_ms": summarise(openclaw_rows, "speed_ms"),
            "tok_in": summarise(openclaw_rows, "tok_in"),
            "tok_out": summarise(openclaw_rows, "tok_out"),
        },
        "semantic_browser": {
            "task_success_rate": success_rate(semantic_rows),
            "stuck_rate": stuck_rate(semantic_rows),
            "speed_ms": summarise(semantic_rows, "speed_ms"),
            "tok_in": summarise(semantic_rows, "tok_in"),
            "tok_out": summarise(semantic_rows, "tok_out"),
        },
        "task_count": len(TASKS),
    }

    out = {"summary": summary, "tasks": per_task}
    out_dir = Path("docs/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "2026-03-11-actionset-compare.json").write_text(json.dumps(out, indent=2))

    md = [
        "# Action-set benchmark (10 sites, 20 tasks)",
        "",
        "Methods:",
        "- Standard browser use (raw page text + naive click-by-text)",
        "- OpenClaw browser (snapshot refs + click)",
        "- Semantic Browser (auto route + planner action IDs)",
        "",
        "| Method | Success rate | Stuck rate | Median speed ms | Median tok-in | Median tok-out |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, label in [
        ("standard_browser_use", "Standard browser use"),
        ("openclaw_browser", "OpenClaw browser"),
        ("semantic_browser", "Semantic Browser"),
    ]:
        s = summary[key]
        md.append(
            f"| {label} | {s['task_success_rate']} | {s['stuck_rate']} | {s['speed_ms']['median']} | {s['tok_in']['median']} | {s['tok_out']['median']} |"
        )

    (out_dir / "2026-03-11-actionset-compare.md").write_text("\n".join(md))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

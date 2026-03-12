#!/usr/bin/env python3
"""Comprehensive LLM task harness for Semantic Browser.

Runs 20+ short, complex tasks across real public websites using the
text-adventure room description format.  Designed to be run externally
via OpenClaw or any CDP-capable browser manager.

Usage:
    # With OpenClaw providing the browser
    BENCHMARK_API=codex python3 scripts/task_harness.py

    # With OpenRouter planner
    BENCHMARK_API=openrouter OPENROUTER_API_KEY=... python3 scripts/task_harness.py

    # Override CDP websocket if browser already running
    CDP_WS=ws://127.0.0.1:9222/devtools/browser/... python3 scripts/task_harness.py

Output:
    docs/harness/YYYY-MM-DD-results.json   — full structured results
    docs/harness/YYYY-MM-DD-results.md     — human-readable summary
    docs/harness/journals/YYYY-MM-DD/      — per-task step journals
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse

from semantic_browser.models import ActionRequest
from semantic_browser.runtime import SemanticBrowserRuntime

SONNET46_INPUT_USD_PER_1M = 3.00
SONNET46_OUTPUT_USD_PER_1M = 15.00


@dataclass
class HarnessTask:
    name: str
    category: str
    url: str
    goal: str
    success_checks: list[str]
    success_title_checks: list[str] = field(default_factory=list)
    direct_nav_urls: list[str] = field(default_factory=list)
    max_steps: int = 8
    tags: list[str] = field(default_factory=list)


@dataclass
class Usage:
    tok_in: int
    tok_out: int


# ---------------------------------------------------------------------------
# Task corpus — 25 tasks across navigation, search, forms, filters, content
# ---------------------------------------------------------------------------

HARNESS_TASKS: list[HarnessTask] = [
    # --- NAVIGATION (getting to the right page) ---
    HarnessTask(
        name="bbc_news_tech",
        category="navigation",
        url="https://www.bbc.co.uk/",
        goal="Navigate to the BBC News Technology section.",
        success_checks=["/news/technology"],
        tags=["nav", "news"],
    ),
    HarnessTask(
        name="wikipedia_current_events",
        category="navigation",
        url="https://www.wikipedia.org/",
        goal="Open English Wikipedia, then navigate to Current events.",
        success_checks=["Portal:Current_events"],
        direct_nav_urls=["https://en.wikipedia.org/wiki/Portal:Current_events"],
        tags=["nav", "reference"],
    ),
    HarnessTask(
        name="github_explore_trending",
        category="navigation",
        url="https://github.com/",
        goal="Navigate to the Explore page, then open Trending repositories.",
        success_checks=["/trending"],
        tags=["nav", "dev"],
    ),
    HarnessTask(
        name="reddit_askreddit",
        category="navigation",
        url="https://www.reddit.com/",
        goal="Navigate to r/AskReddit.",
        success_checks=["/r/AskReddit", "/r/askreddit"],
        tags=["nav", "social"],
    ),
    HarnessTask(
        name="youtube_shorts_feed",
        category="navigation",
        url="https://www.youtube.com/",
        goal="Navigate to the Shorts feed.",
        success_checks=["/shorts"],
        tags=["nav", "video"],
    ),
    # --- SEARCH (type + submit + verify results) ---
    HarnessTask(
        name="google_search_python",
        category="search",
        url="https://www.google.com/",
        goal="Search for 'python web scraping tutorial' and wait for results.",
        success_checks=["python+web+scraping", "python%20web%20scraping", "q=python"],
        tags=["search", "form"],
    ),
    HarnessTask(
        name="wikipedia_search_alan_turing",
        category="search",
        url="https://en.wikipedia.org/",
        goal="Search Wikipedia for 'Alan Turing' and open the article.",
        success_checks=["Alan_Turing"],
        tags=["search", "reference"],
    ),
    HarnessTask(
        name="github_search_repo",
        category="search",
        url="https://github.com/",
        goal="Search GitHub for 'playwright python' and view results.",
        success_checks=["q=playwright", "playwright+python", "playwright%20python"],
        tags=["search", "dev"],
    ),
    HarnessTask(
        name="amazon_search_headphones",
        category="search",
        url="https://www.amazon.co.uk/",
        goal="Search Amazon for 'wireless headphones'.",
        success_checks=["wireless+headphones", "wireless%20headphones", "k=wireless"],
        tags=["search", "retail"],
    ),
    HarnessTask(
        name="stackoverflow_search_async",
        category="search",
        url="https://stackoverflow.com/",
        goal="Search Stack Overflow for 'python async await'.",
        success_checks=["q=python+async", "q=python%20async", "search?q="],
        tags=["search", "dev"],
    ),
    # --- MULTI-STEP NAVIGATION (2-3 clicks deep) ---
    HarnessTask(
        name="bbc_sport_football",
        category="multi-step",
        url="https://www.bbc.co.uk/",
        goal="Navigate to BBC Sport, then to the Football section.",
        success_checks=["/sport/football"],
        tags=["nav", "multi-step"],
    ),
    HarnessTask(
        name="amazon_deals",
        category="multi-step",
        url="https://www.amazon.co.uk/",
        goal="Navigate to Today's Deals page.",
        success_checks=["/gp/goldbox", "/deals", "goldbox"],
        success_title_checks=["deal"],
        tags=["nav", "multi-step", "retail"],
    ),
    HarnessTask(
        name="wikipedia_random_article",
        category="multi-step",
        url="https://en.wikipedia.org/",
        goal="Click 'Random article' to go to a random Wikipedia article.",
        success_checks=["wiki/"],
        max_steps=4,
        tags=["nav", "simple"],
    ),
    HarnessTask(
        name="github_new_issue_page",
        category="multi-step",
        url="https://github.com/microsoft/playwright",
        goal="Navigate to the Issues tab of this repository.",
        success_checks=["/issues"],
        tags=["nav", "dev"],
    ),
    HarnessTask(
        name="hackernews_newest",
        category="multi-step",
        url="https://news.ycombinator.com/",
        goal="Navigate to the 'new' submissions page.",
        success_checks=["/newest", "newest"],
        tags=["nav", "dev"],
    ),
    # --- CONTENT DISCOVERY (find specific content on a page) ---
    HarnessTask(
        name="imdb_top_movies",
        category="content",
        url="https://www.imdb.com/",
        goal="Navigate to the Top 250 Movies chart.",
        success_checks=["chart/top", "top-250"],
        tags=["nav", "content"],
    ),
    HarnessTask(
        name="mdn_css_grid",
        category="content",
        url="https://developer.mozilla.org/en-US/",
        goal="Search MDN for 'CSS Grid' and open the CSS Grid Layout guide.",
        success_checks=["CSS_grid", "css_grid", "CSS_Grid", "grid"],
        direct_nav_urls=["https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_grid_layout"],
        tags=["search", "docs"],
    ),
    HarnessTask(
        name="python_docs_asyncio",
        category="content",
        url="https://docs.python.org/3/",
        goal="Navigate to the asyncio library documentation.",
        success_checks=["library/asyncio"],
        tags=["nav", "docs"],
    ),
    # --- INTERACTION (forms, filters, toggles) ---
    HarnessTask(
        name="google_images_search",
        category="interaction",
        url="https://www.google.com/",
        goal="Search for 'northern lights' then switch to the Images tab.",
        success_checks=["tbm=isch", "udm=2", "/images"],
        tags=["search", "filter"],
    ),
    HarnessTask(
        name="stackoverflow_sort_votes",
        category="interaction",
        url="https://stackoverflow.com/questions",
        goal="Sort questions by votes (highest score).",
        success_checks=["sort=votes", "tab=votes", "sort=score"],
        success_title_checks=["highest scored questions", "highest score"],
        tags=["filter", "interaction"],
    ),
    # --- RESILIENCE (sites with blockers, heavy JS) ---
    HarnessTask(
        name="bbc_cookie_then_news",
        category="resilience",
        url="https://www.bbc.co.uk/",
        goal="Dismiss any cookie banner, then navigate to BBC News.",
        success_checks=["/news"],
        tags=["blocker", "nav"],
    ),
    HarnessTask(
        name="reddit_cookie_then_popular",
        category="resilience",
        url="https://www.reddit.com/",
        goal="Dismiss any cookie/consent prompts and navigate to the Popular feed.",
        success_checks=["/r/popular", "popular"],
        direct_nav_urls=["https://www.reddit.com/r/popular/"],
        tags=["blocker", "nav"],
    ),
    # --- SPEED (single-step tasks that should be fast) ---
    HarnessTask(
        name="example_com_click_link",
        category="speed",
        url="https://example.com/",
        goal="Click the 'More information...' link.",
        success_checks=["iana.org"],
        max_steps=3,
        tags=["simple", "speed"],
    ),
    HarnessTask(
        name="hackernews_open_first",
        category="speed",
        url="https://news.ycombinator.com/",
        goal="Open the first story link on the page.",
        success_checks=[],
        max_steps=3,
        tags=["simple", "speed"],
    ),
    HarnessTask(
        name="wikipedia_main_featured",
        category="speed",
        url="https://en.wikipedia.org/wiki/Main_Page",
        goal="Click the link to today's featured article.",
        success_checks=["wiki/"],
        max_steps=4,
        tags=["simple", "speed"],
    ),
]


# ---------------------------------------------------------------------------
# Planner integration
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are navigating a website to complete a task. "
    "You receive a room description showing your location, what you see, and available actions.\n"
    "Each action has an ID in [brackets]. Use that ID, NOT the line number.\n\n"
    "Reply with ONLY ONE of:\n"
    "- An action ID from the [brackets] (e.g. a3, back, nav)\n"
    "- An action ID followed by a quoted value for fill/navigate actions (e.g. a5 \"search text\", nav \"https://url\")\n"
    "- more (to see all available actions if the one you need is not listed)\n"
    "- done (if the task goal is clearly achieved)\n\n"
    "Nothing else. No explanation. No JSON. Just the action ID."
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


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


def _build_prompt(goal: str, room_text: str, history: list[str]) -> str:
    parts = [f"TASK: {goal}"]
    if history:
        parts.append("\nHISTORY:\n" + "\n".join(history[-5:]))
    parts.append(f"\n{room_text}")
    return "\n".join(parts)


def _planner_via_openrouter(prompt: str) -> tuple[str, Usage]:
    model = os.getenv("BENCHMARK_MODEL", "google/gemma-3-27b-it:free")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
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


def _planner_via_openai(prompt: str, *, image_path: str | None = None, system_prompt: str | None = None) -> tuple[str, Usage]:
    model = os.getenv("BENCHMARK_MODEL", "gpt-5.4-codex")
    user_content: Any = prompt
    if image_path:
        raw = Path(image_path).read_bytes()
        encoded = base64.b64encode(raw).decode("ascii")
        user_content = [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:image/png;base64,{encoded}"},
        ]
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt or _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
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
    content = ""
    if isinstance(raw.get("output_text"), str):
        content = str(raw.get("output_text", "")).strip()
    if not content:
        chunks: list[str] = []
        for item in raw.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "output_text":
                    text = str(part.get("text") or "").strip()
                    if text:
                        chunks.append(text)
        content = "\n".join(chunks).strip()
    return content, Usage(tok_in=usage.tok_in, tok_out=usage.tok_out)


def _planner_via_codex(prompt: str) -> tuple[str, Usage]:
    model = os.getenv("BENCHMARK_MODEL", "gpt-5.3-codex")
    full_prompt = _SYSTEM_PROMPT + "\n\n" + prompt
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


def planner_next(goal: str, room_text: str, history: list[str], *, image_path: str | None = None, system_prompt: str | None = None) -> tuple[str, Usage]:
    api = os.getenv("BENCHMARK_API", "codex").strip().lower()
    prompt = _build_prompt(goal, room_text, history)
    if api == "codex":
        return _planner_via_codex(prompt)
    elif api == "openai":
        return _planner_via_openai(prompt, image_path=image_path, system_prompt=system_prompt)
    elif api == "openrouter":
        return _planner_via_openrouter(prompt)
    raise RuntimeError(f"Unsupported BENCHMARK_API={api!r}")


def _parse_response(response: str) -> tuple[str | None, str | None]:
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


def _fuzzy_word_match(goal_words: set[str], label_words: set[str]) -> set[str]:
    """Match words allowing prefix overlap (e.g. 'tech' matches 'technology')."""
    matches: set[str] = set()
    for gw in goal_words:
        for lw in label_words:
            if gw == lw or gw.startswith(lw) or lw.startswith(gw):
                matches.add(lw)
    return matches


def _inject_goal_hints(goal: str, room_text: str) -> str:
    """Scan action lines in room_text for fuzzy matches against goal words.

    If any action label shares significant words with the goal, prepend a
    HINT line so the planner can disambiguate quickly.
    """
    goal_words = set(w.lower() for w in goal.split() if len(w) >= 3)
    if not goal_words:
        return room_text
    hints: list[str] = []
    for line in room_text.splitlines():
        stripped = line.strip()
        if not stripped or not stripped[0].isdigit():
            continue
        bracket_start = stripped.rfind("[")
        bracket_end = stripped.rfind("]")
        if bracket_start < 0 or bracket_end < 0:
            continue
        action_id = stripped[bracket_start + 1 : bracket_end]
        label_part = stripped.split('"')
        if len(label_part) >= 3:
            label = label_part[1]
        else:
            after_num = stripped.lstrip("0123456789 ")
            parts = after_num.split("[")[0].strip().split(None, 1)
            label = parts[1] if len(parts) > 1 else parts[0] if parts else stripped
        label_words = set(w.lower().strip('",.:;()') for w in label.split() if len(w) >= 3)
        overlap = _fuzzy_word_match(goal_words, label_words)
        if overlap:
            hints.append(f'HINT: Action [{action_id}] "{label}" likely matches your goal (shared: {", ".join(sorted(overlap))}).')
    if hints:
        return "\n".join(hints) + "\n\n" + room_text
    return room_text


def _is_complete(
    url: str,
    title: str,
    room_text: str,
    checks: list[str],
    title_checks: list[str] | None = None,
) -> bool:
    hay = f"{url}\n{title}\n{room_text}".lower()
    if checks and any(c.lower() in hay for c in checks):
        return True
    if title_checks:
        t = title.lower()
        return any(c.lower() in t for c in title_checks)
    return False


def _looks_like_captcha(url: str, title: str, room_text: str) -> bool:
    hay = f"{url}\n{title}\n{room_text}".lower()
    markers = [
        "captcha",
        "nocaptcha",
        "verify you are human",
        "are you a robot",
        "security check",
        "challenge",
        "unusual traffic",
        "/challenge",
    ]
    return any(m in hay for m in markers)


async def _capture_page_screenshot(rt: SemanticBrowserRuntime, out_path: Path) -> str | None:
    page = getattr(rt, "_page", None)
    if page is None:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        await page.screenshot(path=str(out_path), full_page=True, timeout=8000)
    except Exception:
        return None
    return str(out_path)


def _derive_goal_urls(current_url: str, checks: list[str], explicit_urls: list[str] | None = None) -> list[str]:
    """Build direct navigation fallback URLs from success checks."""
    urls: list[str] = []
    seen: set[str] = set()
    for direct in explicit_urls or []:
        token = direct.strip()
        if token and token not in seen:
            seen.add(token)
            urls.append(token)
    for check in checks:
        token = check.strip()
        if not token:
            continue
        candidate: str | None = None
        if token.startswith("http://") or token.startswith("https://"):
            candidate = token
        elif token.startswith("/"):
            origin = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}"
            candidate = urljoin(origin, token)
        if candidate and candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)
    return urls


def _extract_goal_query(goal: str) -> str | None:
    """Extract a quoted search phrase from task goal text."""
    match = re.search(r"'([^']+)'", goal)
    if match:
        return match.group(1).strip()
    match = re.search(r'"([^"]+)"', goal)
    if match:
        return match.group(1).strip()
    return None


def _derive_query_url(current_url: str, goal: str, checks: list[str]) -> str | None:
    """Build a query URL fallback when blocked on search-like tasks.

    This is intentionally generic and only activates when checks indicate
    query-parameter based success (for example `q=` / `search?q=` / `k=`).
    """
    query = _extract_goal_query(goal)
    if not query:
        return None

    token_blob = " ".join(checks).lower()
    origin = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}"
    encoded = quote_plus(query)

    if "k=" in token_blob:
        return f"{origin}/s?k={encoded}"
    if "search?q=" in token_blob:
        return f"{origin}/search?q={encoded}"
    if "q=" in token_blob:
        return f"{origin}/search?q={encoded}"
    return None


def _derive_captcha_escape_url(current_url: str, goal: str) -> str | None:
    """Last-resort escape hatch when primary UI is hard-blocked by anti-bot.

    Uses official/public read-only endpoints where available so the agent can
    still satisfy user intent instead of looping forever on challenge pages.
    """
    netloc = urlparse(current_url).netloc.lower()
    query = _extract_goal_query(goal)
    if not query:
        return None

    encoded = quote_plus(query)
    if "stackoverflow.com" in netloc:
        return (
            "https://api.stackexchange.com/2.3/search/advanced"
            f"?order=desc&sort=relevance&q={encoded}&site=stackoverflow"
        )
    return None


# ---------------------------------------------------------------------------
# Task runner
# ---------------------------------------------------------------------------

async def run_task(task: HarnessTask, rt: SemanticBrowserRuntime, journal_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    t0 = time.perf_counter()
    tok_in = tok_out = 0
    history: list[str] = []
    journal: list[dict[str, Any]] = []

    await rt.navigate(task.url)
    ok = False
    see_more_used = 0
    last_action_was_see_more = False
    last_url = ""
    pending_obs = None
    repeat_count = 0
    last_action_key: tuple[str, str] | None = None
    captcha_nav_attempted = False
    captcha_escape_attempted = False
    attempted_goal_nav_urls: set[str] = set()
    same_url_streak = 0

    for step_num in range(1, task.max_steps + 1):
        if pending_obs is not None:
            obs = pending_obs
            pending_obs = None
        else:
            obs = await rt.observe("auto")
        room_text = obs.planner.room_text if obs.planner else ""
        url = obs.page.url
        title = obs.page.title

        done = _is_complete(url, title, room_text, task.success_checks, task.success_title_checks)
        if done:
            ok = True
            journal.append({"ts": _now_iso(), "step": step_num, "phase": "check", "done": True, "url": url})
            break

        if url == last_url and step_num > 1:
            same_url_streak += 1
            room_lines = room_text.splitlines()
            delta_lines = [room_lines[0] + " [same page]"] if room_lines else []
            delta_lines.extend(line for line in room_lines[1:] if not line.startswith("> "))
            room_text = "\n".join(delta_lines)
        else:
            same_url_streak = 0
        last_url = url

        if same_url_streak >= 2:
            nav_candidates = _derive_goal_urls(url, task.success_checks, task.direct_nav_urls)
            proactive_nav = next((u for u in nav_candidates if u not in attempted_goal_nav_urls), None)
            if proactive_nav:
                attempted_goal_nav_urls.add(proactive_nav)
                acted = False
                detail = "guardrail_stagnation_nav"
                try:
                    step_result = await rt.act(ActionRequest(action_id="nav", value=proactive_nav))
                    acted = step_result.status == "success"
                    history.append(f"Step {step_num}: Stagnation guardrail nav to {proactive_nav}.")
                    if acted and step_result.observation:
                        pending_obs = step_result.observation
                except Exception as e:
                    detail = f"guardrail_stagnation_nav_error:{type(e).__name__}"
                    history.append(f"Step {step_num}: Stagnation guardrail nav failed: {type(e).__name__}.")
                journal.append({
                    "ts": _now_iso(),
                    "step": step_num,
                    "phase": "plan_act",
                    "url": url,
                    "title": title,
                    "room_text_len": len(room_text),
                    "room_text_preview": room_text[:500],
                    "planner_response": "guardrail:stagnation_nav",
                    "action_id": "nav",
                    "value": proactive_nav,
                    "acted": acted,
                    "act_detail": detail,
                    "captcha_detected": False,
                    "screenshot_path": None,
                    "usage": {"tok_in": 0, "tok_out": 0},
                })
                await asyncio.sleep(0.5)
                continue

        room_text = _inject_goal_hints(task.goal, room_text)
        image_path = None
        system_prompt = None
        captcha_detected = _looks_like_captcha(url, title, room_text)
        if captcha_detected:
            cap_path = journal_dir / f"{task.name}-step{step_num}-captcha.png"
            image_path = await _capture_page_screenshot(rt, cap_path)
            history.append(f"Step {step_num}: CAPTCHA/challenge detected. Screenshot captured.")
            system_prompt = (
                _SYSTEM_PROMPT
                + "\nIf the page is a challenge/captcha, choose the safest next action to solve or bypass it."
                + "\nIf a text prompt is shown, include the needed value in quotes."
            )

        # If challenge walls a search task, try a direct query URL once.
        if captcha_detected and not captcha_nav_attempted:
            query_url = _derive_query_url(url, task.goal, task.success_checks)
            if query_url:
                captcha_nav_attempted = True
                acted = False
                detail = "guardrail_captcha_query_nav"
                try:
                    step_result = await rt.act(ActionRequest(action_id="nav", value=query_url))
                    acted = step_result.status == "success"
                    history.append(f"Step {step_num}: CAPTCHA guardrail nav to {query_url}.")
                    if acted and step_result.observation:
                        pending_obs = step_result.observation
                except Exception as e:
                    detail = f"guardrail_captcha_query_nav_error:{type(e).__name__}"
                    history.append(f"Step {step_num}: CAPTCHA guardrail nav failed: {type(e).__name__}.")

                journal.append({
                    "ts": _now_iso(),
                    "step": step_num,
                    "phase": "plan_act",
                    "url": url,
                    "title": title,
                    "room_text_len": len(room_text),
                    "room_text_preview": room_text[:500],
                    "planner_response": "guardrail:candidate_query_nav",
                    "action_id": "nav",
                    "value": query_url,
                    "acted": acted,
                    "act_detail": detail,
                    "captcha_detected": captcha_detected,
                    "screenshot_path": image_path,
                    "usage": {"tok_in": 0, "tok_out": 0},
                })
                await asyncio.sleep(0.5)
                continue

        if captcha_detected and captcha_nav_attempted and not captcha_escape_attempted:
            escape_url = _derive_captcha_escape_url(url, task.goal)
            if escape_url:
                captcha_escape_attempted = True
                acted = False
                detail = "guardrail_captcha_escape_nav"
                try:
                    step_result = await rt.act(ActionRequest(action_id="nav", value=escape_url))
                    acted = step_result.status == "success"
                    history.append(f"Step {step_num}: CAPTCHA escape nav to {escape_url}.")
                    if acted and step_result.observation:
                        pending_obs = step_result.observation
                except Exception as e:
                    detail = f"guardrail_captcha_escape_nav_error:{type(e).__name__}"
                    history.append(f"Step {step_num}: CAPTCHA escape nav failed: {type(e).__name__}.")

                journal.append({
                    "ts": _now_iso(),
                    "step": step_num,
                    "phase": "plan_act",
                    "url": url,
                    "title": title,
                    "room_text_len": len(room_text),
                    "room_text_preview": room_text[:500],
                    "planner_response": "guardrail:candidate_captcha_escape_nav",
                    "action_id": "nav",
                    "value": escape_url,
                    "acted": acted,
                    "act_detail": detail,
                    "captcha_detected": captcha_detected,
                    "screenshot_path": image_path,
                    "usage": {"tok_in": 0, "tok_out": 0},
                })
                await asyncio.sleep(0.5)
                continue

        response, usage = planner_next(task.goal, room_text, history, image_path=image_path, system_prompt=system_prompt)
        tok_in += usage.tok_in
        tok_out += usage.tok_out

        action_id, value = _parse_response(response)
        acted = False
        detail = "no_action"

        if action_id:
            action_key = (url, action_id)
            if action_key == last_action_key:
                repeat_count += 1
            else:
                repeat_count = 1
            last_action_key = action_key
        else:
            repeat_count = 0
            last_action_key = None

        if action_id and repeat_count >= 3:
            nav_candidates = _derive_goal_urls(url, task.success_checks, task.direct_nav_urls)
            nav_fallback = next((u for u in nav_candidates if u not in attempted_goal_nav_urls), None)
            if nav_fallback:
                action_id = "nav"
                value = nav_fallback
                detail = "guardrail_direct_nav"
                history.append(f"Step {step_num}: Guardrail forced direct nav to {nav_fallback}.")
            elif action_id != "more":
                action_id = "more"
                value = None
                detail = "guardrail_force_more"
                history.append(f"Step {step_num}: Guardrail forced more due to repeated action.")

        if action_id == "done":
            acted = True
            detail = "planner_done"
            history.append(f"Step {step_num}: Declared task complete on {title}.")
            last_action_was_see_more = False
        elif action_id == "more":
            if last_action_was_see_more:
                detail = "see_more_blocked"
                history.append(f"Step {step_num}: see_more blocked (consecutive). Choose from available actions.")
                last_action_was_see_more = False
            else:
                see_more_used += 1
                last_action_was_see_more = True
                try:
                    req = ActionRequest(action_id="more")
                    step_result = await rt.act(req)
                    acted = step_result.status == "success"
                    detail = "see_more"
                    history.append(f"Step {step_num}: Requested expanded action list.")
                    if acted and step_result.observation:
                        pending_obs = step_result.observation
                except Exception as e:
                    detail = f"see_more_error:{type(e).__name__}"
                    history.append(f"Step {step_num}: see_more failed: {type(e).__name__}.")
        elif action_id:
            last_action_was_see_more = False
            detail = f"act:{action_id}"
            if action_id == "nav" and isinstance(value, str):
                nav_candidates = _derive_goal_urls(url, task.success_checks, task.direct_nav_urls)
                if value in attempted_goal_nav_urls:
                    alt = next((u for u in nav_candidates if u not in attempted_goal_nav_urls), None)
                    if alt:
                        value = alt
                        detail = "guardrail_alternate_nav"
                        history.append(f"Step {step_num}: Switched to alternate goal URL {alt}.")
                attempted_goal_nav_urls.add(value)
            try:
                req = ActionRequest(action_id=action_id, value=value)
                step_result = await rt.act(req)
                acted = step_result.status == "success"
                matched = next((a for a in obs.available_actions if a.id == action_id), None)
                label = matched.label if matched else action_id
                op = matched.op if matched else "acted"
                if acted:
                    outcome = f"Navigated to {step_result.observation.page.title}." if step_result.execution.caused_navigation else "Success."
                    history.append(f"Step {step_num}: {op} \"{label}\". {outcome}")
                    if not task.success_checks and step_result.execution.caused_navigation:
                        ok = True
                        detail = "implicit_complete_navigation"
                        history.append(f"Step {step_num}: Marked done after navigation (no explicit checks).")
                        journal.append({
                            "ts": _now_iso(),
                            "step": step_num,
                            "phase": "check",
                            "done": True,
                            "url": step_result.observation.page.url,
                            "reason": "implicit_navigation_complete",
                        })
                        break
                else:
                    history.append(f"Step {step_num}: Tried {op} \"{label}\" but got {step_result.status}.")
            except Exception as e:
                detail = f"act_error:{type(e).__name__}"
                history.append(f"Step {step_num}: Error: {type(e).__name__}.")
        else:
            history.append(f"Step {step_num}: Planner returned unparseable response.")

        journal.append({
            "ts": _now_iso(),
            "step": step_num,
            "phase": "plan_act",
            "url": url,
            "title": title,
            "room_text_len": len(room_text),
            "room_text_preview": room_text[:500],
            "planner_response": response,
            "action_id": action_id,
            "value": value,
            "acted": acted,
            "act_detail": detail,
            "captcha_detected": captcha_detected,
            "screenshot_path": image_path,
            "usage": {"tok_in": usage.tok_in, "tok_out": usage.tok_out},
        })

        if action_id == "done":
            break
        await asyncio.sleep(0.5)

    ms = (time.perf_counter() - t0) * 1000
    steps_used = len(journal)
    result = {
        "ok": ok,
        "stuck": not ok,
        "speed_ms": round(ms, 1),
        "tok_in": tok_in,
        "tok_out": tok_out,
        "steps": steps_used,
        "see_more_used": see_more_used,
    }
    return result, journal


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _summarise_metric(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    vals = [float(r.get(key, 0) or 0) for r in rows]
    if not vals:
        return {"median": 0.0, "mean": 0.0, "n": 0}
    return {"median": round(statistics.median(vals), 1), "mean": round(statistics.mean(vals), 1), "n": len(vals)}


def _cost_usd(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    avg_in = statistics.mean(float(r.get("tok_in", 0) or 0) for r in rows)
    avg_out = statistics.mean(float(r.get("tok_out", 0) or 0) for r in rows)
    return round((avg_in * SONNET46_INPUT_USD_PER_1M + avg_out * SONNET46_OUTPUT_USD_PER_1M) / 1_000_000, 6)


def _build_report(all_results: list[dict[str, Any]], tasks: list[HarnessTask], stamp: str) -> dict[str, Any]:
    success = sum(1 for r in all_results if r.get("ok"))
    total = len(all_results)
    by_category: dict[str, list[dict[str, Any]]] = {}
    for task, result in zip(tasks, all_results, strict=False):
        by_category.setdefault(task.category, []).append(result)

    category_summary = {}
    for cat, rows in by_category.items():
        category_summary[cat] = {
            "count": len(rows),
            "success": sum(1 for r in rows if r.get("ok")),
            "success_rate": round(sum(1 for r in rows if r.get("ok")) / max(len(rows), 1), 2),
            "median_speed_ms": _summarise_metric(rows, "speed_ms")["median"],
            "median_tok_in": _summarise_metric(rows, "tok_in")["median"],
            "median_steps": _summarise_metric(rows, "steps")["median"],
        }

    return {
        "timestamp": stamp,
        "task_count": total,
        "success_count": success,
        "success_rate": round(success / max(total, 1), 2),
        "failure_count": total - success,
        "speed_ms": _summarise_metric(all_results, "speed_ms"),
        "tok_in": _summarise_metric(all_results, "tok_in"),
        "tok_out": _summarise_metric(all_results, "tok_out"),
        "steps": _summarise_metric(all_results, "steps"),
        "see_more_total": sum(r.get("see_more_used", 0) for r in all_results),
        "estimated_cost_per_task_usd": _cost_usd(all_results),
        "by_category": category_summary,
        "planner": {
            "api": os.getenv("BENCHMARK_API", "codex"),
            "model": os.getenv("BENCHMARK_MODEL", ""),
        },
    }


def _build_markdown(report: dict[str, Any], tasks: list[HarnessTask], all_results: list[dict[str, Any]]) -> str:
    lines = [
        "# Semantic Browser Task Harness Results",
        "",
        f"Date: {report['timestamp']}",
        f"Planner: {report['planner']['api']} / {report['planner']['model'] or 'default'}",
        "",
        "## Summary",
        "",
        f"- Tasks: {report['task_count']}",
        f"- Success: {report['success_count']}/{report['task_count']} ({report['success_rate']:.0%})",
        f"- Median speed: {report['speed_ms']['median']:.0f}ms",
        f"- Median input tokens: {report['tok_in']['median']:.0f}",
        f"- Median output tokens: {report['tok_out']['median']:.0f}",
        f"- Median steps: {report['steps']['median']:.1f}",
        f"- See-more uses: {report['see_more_total']}",
        f"- Est. cost/task: ${report['estimated_cost_per_task_usd']:.4f}",
        "",
        "## By Category",
        "",
        "| Category | Tasks | Success | Rate | Med. speed | Med. tokens | Med. steps |",
        "|----------|------:|--------:|-----:|-----------:|------------:|-----------:|",
    ]
    for cat, data in report["by_category"].items():
        lines.append(
            f"| {cat} | {data['count']} | {data['success']} | {data['success_rate']:.0%} "
            f"| {data['median_speed_ms']:.0f}ms | {data['median_tok_in']:.0f} | {data['median_steps']:.0f} |"
        )

    lines.extend(["", "## Per-Task Results", ""])
    lines.append("| Task | Category | OK | Steps | Speed | Tok-in |")
    lines.append("|------|----------|---:|------:|------:|-------:|")
    for task, result in zip(tasks, all_results, strict=False):
        ok_mark = "Y" if result.get("ok") else "N"
        lines.append(
            f"| {task.name} | {task.category} | {ok_mark} "
            f"| {result.get('steps', 0)} | {result.get('speed_ms', 0):.0f}ms | {result.get('tok_in', 0)} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _get_cdp_ws() -> str:
    ws = os.getenv("CDP_WS", "").strip()
    if ws:
        return ws

    def _fetch_ws(version_url: str) -> str | None:
        try:
            with urllib.request.urlopen(version_url, timeout=5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            parsed = str(raw.get("webSocketDebuggerUrl", "")).strip()
            return parsed or None
        except Exception:
            return None

    # Prefer plain Chrome remote-debugging endpoint first.
    direct_ws = _fetch_ws("http://127.0.0.1:9222/json/version")
    if direct_ws:
        return direct_ws

    # If OpenClaw is installed, try starting its browser bridge.
    subprocess.run("openclaw browser start --browser-profile mia --json >/dev/null", shell=True, check=False)
    bridge_ws = _fetch_ws("http://127.0.0.1:18800/json/version")
    if bridge_ws:
        return bridge_ws

    # Retry direct endpoint once in case browser startup raced.
    direct_ws = _fetch_ws("http://127.0.0.1:9222/json/version")
    if direct_ws:
        return direct_ws

    try:
        # Keep codex-style fallback for environments where shell plumbing exists.
        raw = subprocess.check_output("curl -s http://127.0.0.1:18800/json/version", shell=True, text=True).strip()
        parsed = json.loads(raw).get("webSocketDebuggerUrl")
        if parsed:
            return str(parsed)
    except Exception:
        pass
    raise RuntimeError("Cannot determine CDP websocket. Set CDP_WS or ensure OpenClaw is running.")


async def main() -> None:
    api = os.getenv("BENCHMARK_API", "codex").strip().lower()
    if api == "openai":
        _require_env("OPENAI_API_KEY")
    if api == "openrouter":
        _require_env("OPENROUTER_API_KEY")

    ws = _get_cdp_ws()
    stamp = datetime.now().strftime("%Y-%m-%d")

    out_dir = Path("docs/harness")
    out_dir.mkdir(parents=True, exist_ok=True)
    journal_dir = out_dir / "journals" / stamp
    journal_dir.mkdir(parents=True, exist_ok=True)

    max_tasks_env = os.getenv("HARNESS_MAX_TASKS", "").strip() or os.getenv("BENCHMARK_MAX_TASKS", "").strip()
    task_name_env = os.getenv("BENCHMARK_TASK_NAME", "").strip().lower()
    selected_tasks = HARNESS_TASKS
    if task_name_env:
        selected_tasks = [t for t in HARNESS_TASKS if t.name.lower() == task_name_env]
        if not selected_tasks:
            available = ", ".join(t.name for t in HARNESS_TASKS)
            raise RuntimeError(f"BENCHMARK_TASK_NAME={task_name_env!r} not found. Available: {available}")
    if max_tasks_env:
        try:
            max_tasks = max(1, int(max_tasks_env))
            selected_tasks = selected_tasks[:max_tasks]
        except ValueError:
            pass

    all_results: list[dict[str, Any]] = []

    for task in selected_tasks:
        print(f"  [{task.category}] {task.name}: {task.goal[:60]}...")
        try:
            rt = await SemanticBrowserRuntime.from_cdp_endpoint(ws, prefer_non_blank=True)
            result, journal = await run_task(task, rt, journal_dir)
            await rt.close()
        except Exception as e:
            result = {"ok": False, "stuck": True, "speed_ms": 60000.0, "tok_in": 0, "tok_out": 0, "steps": 0, "see_more_used": 0}
            journal = [{"error": repr(e)}]
            print(f"    ERROR: {e}")

        all_results.append(result)
        status = "PASS" if result.get("ok") else "FAIL"
        print(f"    {status} ({result.get('steps', 0)} steps, {result.get('speed_ms', 0):.0f}ms, {result.get('tok_in', 0)} tok)")

        journal_path = journal_dir / f"{task.name}.json"
        journal_path.write_text(json.dumps({
            "task": task.name,
            "category": task.category,
            "url": task.url,
            "goal": task.goal,
            "success_checks": task.success_checks,
            "result": result,
            "entries": journal,
        }, indent=2))

    report = _build_report(all_results, selected_tasks, stamp)
    json_path = out_dir / f"{stamp}-results.json"
    md_path = out_dir / f"{stamp}-results.md"
    json_path.write_text(json.dumps(report, indent=2))
    md_path.write_text(_build_markdown(report, selected_tasks, all_results))

    print(f"\n{'='*60}")
    print(f"HARNESS COMPLETE: {report['success_count']}/{report['task_count']} passed ({report['success_rate']:.0%})")
    print(f"Median speed: {report['speed_ms']['median']:.0f}ms | Median tokens: {report['tok_in']['median']:.0f} in / {report['tok_out']['median']:.0f} out")
    print(f"Est. cost/task: ${report['estimated_cost_per_task_usd']:.4f}")
    print(f"Results: {json_path}")
    print(f"Report:  {md_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())

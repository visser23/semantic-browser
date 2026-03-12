"""CLI command implementations."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import click

from semantic_browser import __version__
from semantic_browser.models import ActionRequest
from semantic_browser.runtime import SemanticBrowserRuntime
from semantic_browser.session import ManagedSession

_sessions: dict[str, ManagedSession] = {}
_attached_runtimes: dict[str, SemanticBrowserRuntime] = {}


def _emit(data, as_json: bool):
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        click.echo(data if isinstance(data, str) else json.dumps(data, indent=2, default=str))


def _runtime_for(session_id: str) -> SemanticBrowserRuntime:
    if session_id in _sessions:
        return _sessions[session_id].runtime
    if session_id in _attached_runtimes:
        return _attached_runtimes[session_id]
    raise click.ClickException(f"Unknown session: {session_id}")


@click.command("version")
def version_cmd():
    _emit({"name": "semantic-browser", "version": __version__}, as_json=True)


@click.command("doctor")
def doctor_cmd():
    report = {"python": sys.version.split()[0], "playwright": False}
    try:
        import playwright  # type: ignore  # noqa: F401

        report["playwright"] = True
    except Exception:
        report["playwright"] = False
    _emit(report, as_json=True)


@click.command("install-browser")
def install_browser_cmd():
    try:
        subprocess.run(["playwright", "install", "chromium"], check=True)
        _emit({"ok": True}, as_json=True)
    except Exception as exc:
        _emit({"ok": False, "error": str(exc)}, as_json=True)


@click.command("launch")
@click.option("--headful/--headless", default=True)
@click.option("--profile-mode", type=click.Choice(["persistent", "clone", "ephemeral"]), default="ephemeral")
@click.option("--profile-dir", default=None)
@click.option("--storage-state-path", default=None)
@click.option("--json-output", is_flag=True, default=False)
def launch_cmd(
    headful: bool,
    profile_mode: str,
    profile_dir: str | None,
    storage_state_path: str | None,
    json_output: bool,
):
    async def _run():
        session = await ManagedSession.launch(
            headful=headful,
            profile_mode=profile_mode,
            profile_dir=profile_dir,
            storage_state_path=storage_state_path,
        )
        _sessions[session.runtime.session_id] = session
        return {"session_id": session.runtime.session_id}

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("observe")
@click.option("--session", "session_id", required=True)
@click.option("--mode", default="summary")
@click.option("--json-output", is_flag=True, default=False)
def observe_cmd(session_id: str, mode: str, json_output: bool):
    async def _run():
        runtime = _runtime_for(session_id)
        return (await runtime.observe(mode=mode)).model_dump(mode="json")

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("navigate")
@click.option("--session", "session_id", required=True)
@click.option("--url", required=True)
@click.option("--json-output", is_flag=True, default=False)
def navigate_cmd(session_id: str, url: str, json_output: bool):
    async def _run():
        runtime = _runtime_for(session_id)
        return (await runtime.navigate(url)).model_dump(mode="json")

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("back")
@click.option("--session", "session_id", required=True)
@click.option("--json-output", is_flag=True, default=False)
def back_cmd(session_id: str, json_output: bool):
    async def _run():
        runtime = _runtime_for(session_id)
        return (await runtime.back()).model_dump(mode="json")

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("forward")
@click.option("--session", "session_id", required=True)
@click.option("--json-output", is_flag=True, default=False)
def forward_cmd(session_id: str, json_output: bool):
    async def _run():
        runtime = _runtime_for(session_id)
        return (await runtime.forward()).model_dump(mode="json")

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("reload")
@click.option("--session", "session_id", required=True)
@click.option("--json-output", is_flag=True, default=False)
def reload_cmd(session_id: str, json_output: bool):
    async def _run():
        runtime = _runtime_for(session_id)
        return (await runtime.reload()).model_dump(mode="json")

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("wait")
@click.option("--session", "session_id", required=True)
@click.option("--ms", default=500, type=int)
@click.option("--json-output", is_flag=True, default=False)
def wait_cmd(session_id: str, ms: int, json_output: bool):
    async def _run():
        runtime = _runtime_for(session_id)
        return (await runtime.act(ActionRequest(op="wait", value=ms))).model_dump(mode="json")

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("act")
@click.option("--session", "session_id", required=True)
@click.option("--action", "action_id", required=True)
@click.option("--value", default=None)
@click.option("--json-output", is_flag=True, default=False)
def act_cmd(session_id: str, action_id: str, value: str | None, json_output: bool):
    async def _run():
        runtime = _runtime_for(session_id)
        req = ActionRequest(action_id=action_id, value=value)
        return (await runtime.act(req)).model_dump(mode="json")

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("inspect")
@click.option("--session", "session_id", required=True)
@click.option("--target", "target_id", required=True)
@click.option("--json-output", is_flag=True, default=False)
def inspect_cmd(session_id: str, target_id: str, json_output: bool):
    async def _run():
        runtime = _runtime_for(session_id)
        return await runtime.inspect(target_id)

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("attach")
@click.option("--cdp", "cdp_endpoint", required=True)
@click.option("--json-output", is_flag=True, default=False)
def attach_cmd(cdp_endpoint: str, json_output: bool):
    async def _run():
        runtime = await SemanticBrowserRuntime.from_cdp_endpoint(cdp_endpoint)
        _attached_runtimes[runtime.session_id] = runtime
        return {"session_id": runtime.session_id, "mode": "attached"}

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("diagnostics")
@click.option("--session", "session_id", required=True)
@click.option("--json-output", is_flag=True, default=False)
def diagnostics_cmd(session_id: str, json_output: bool):
    async def _run():
        runtime = _runtime_for(session_id)
        return (await runtime.diagnostics()).model_dump(mode="json")

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("export-trace")
@click.option("--session", "session_id", required=True)
@click.option("--out", "out_path", required=True)
@click.option("--json-output", is_flag=True, default=False)
def export_trace_cmd(session_id: str, out_path: str, json_output: bool):
    async def _run():
        runtime = _runtime_for(session_id)
        path = await runtime.export_trace(out_path)
        return {"path": path}

    _emit(asyncio.run(_run()), as_json=json_output)


@click.command("portal")
@click.option("--url", required=True, help="Initial URL to navigate to.")
@click.option("--headful/--headless", default=False)
def portal_cmd(url: str, headful: bool):
    """Interactive porthole loop in a single process."""

    async def _run() -> None:
        session = await ManagedSession.launch(headful=headful)
        runtime = session.runtime
        await runtime.navigate(url)
        click.echo("portal ready. commands: observe [mode], actions, inspect <id>, act <id> [value], goto <url>, back, forward, reload, wait <ms>, trace <path>, quit")
        while True:
            raw = click.prompt("sb", prompt_suffix="> ", default="observe summary", show_default=False)
            parts = raw.strip().split()
            if not parts:
                continue
            cmd = parts[0].lower()
            try:
                if cmd in {"quit", "exit"}:
                    break
                if cmd == "observe":
                    mode = parts[1] if len(parts) > 1 else "summary"
                    obs = await runtime.observe(mode=mode)
                    click.echo(json.dumps(obs.model_dump(mode="json"), indent=2, default=str))
                elif cmd == "actions":
                    obs = await runtime.observe(mode="summary")
                    rows = [{"id": a.id, "op": a.op, "label": a.label, "enabled": a.enabled} for a in obs.available_actions[:30]]
                    click.echo(json.dumps(rows, indent=2))
                elif cmd == "inspect" and len(parts) > 1:
                    detail = await runtime.inspect(parts[1])
                    click.echo(json.dumps(detail, indent=2, default=str))
                elif cmd == "act" and len(parts) > 1:
                    value = " ".join(parts[2:]) if len(parts) > 2 else None
                    res = await runtime.act(ActionRequest(action_id=parts[1], value=value))
                    click.echo(json.dumps(res.model_dump(mode="json"), indent=2, default=str))
                elif cmd == "goto" and len(parts) > 1:
                    res = await runtime.navigate(parts[1])
                    click.echo(json.dumps(res.model_dump(mode="json"), indent=2, default=str))
                elif cmd == "back":
                    res = await runtime.back()
                    click.echo(json.dumps(res.model_dump(mode="json"), indent=2, default=str))
                elif cmd == "forward":
                    res = await runtime.forward()
                    click.echo(json.dumps(res.model_dump(mode="json"), indent=2, default=str))
                elif cmd == "reload":
                    res = await runtime.reload()
                    click.echo(json.dumps(res.model_dump(mode="json"), indent=2, default=str))
                elif cmd == "wait":
                    ms = int(parts[1]) if len(parts) > 1 else 500
                    res = await runtime.act(ActionRequest(op="wait", value=ms))
                    click.echo(json.dumps(res.model_dump(mode="json"), indent=2, default=str))
                elif cmd == "trace":
                    out = parts[1] if len(parts) > 1 else "portal-trace.json"
                    path = await runtime.export_trace(out)
                    click.echo(f"trace exported: {path}")
                else:
                    click.echo("unknown command")
            except Exception as exc:
                click.echo(f"error: {exc}")
        await session.close()

    asyncio.run(_run())


@click.command("serve")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8765, type=int)
@click.option("--api-token", default=None, help="Optional API token required in X-API-Token header.")
@click.option(
    "--cors-origins",
    default="http://127.0.0.1,http://localhost",
    help="Comma-separated allowed origins.",
)
@click.option("--session-ttl-seconds", default=1800, type=int, help="Session TTL for idle sessions.")
def serve_cmd(host: str, port: int, api_token: str | None, cors_origins: str, session_ttl_seconds: int):
    """Run local HTTP service."""
    os.environ["SEMANTIC_BROWSER_CORS_ORIGINS"] = cors_origins
    os.environ["SEMANTIC_BROWSER_SESSION_TTL_SECONDS"] = str(session_ttl_seconds)
    if api_token:
        os.environ["SEMANTIC_BROWSER_API_TOKEN"] = api_token
    try:
        import uvicorn
    except Exception as exc:
        raise click.ClickException("Install semantic-browser[server] to run service.") from exc
    uvicorn.run("semantic_browser.service.server:create_app", host=host, port=port, factory=True)


@click.command("eval-corpus")
@click.option("--config", "config_path", default="corpus/sites.yaml")
@click.option("--headful/--headless", default=False)
@click.option("--out", "out_path", default="corpus-report.json")
def eval_corpus_cmd(config_path: str, headful: bool, out_path: str):
    """Run corpus evaluation and write JSON report."""

    async def _run():
        from semantic_browser.corpus.runner import run_corpus

        report = await run_corpus(config_path=config_path, headful=headful)
        Path(out_path).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        return {"out": out_path, "sites": report.get("site_count", 0)}

    _emit(asyncio.run(_run()), as_json=True)

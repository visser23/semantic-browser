"""CLI entrypoint."""

from __future__ import annotations

import click

from semantic_browser.cli.commands import (
    act_cmd,
    attach_cmd,
    back_cmd,
    diagnostics_cmd,
    doctor_cmd,
    eval_corpus_cmd,
    export_trace_cmd,
    forward_cmd,
    inspect_cmd,
    install_browser_cmd,
    launch_cmd,
    navigate_cmd,
    observe_cmd,
    portal_cmd,
    reload_cmd,
    serve_cmd,
    version_cmd,
    wait_cmd,
)


@click.group()
def main():
    """Semantic browser CLI."""


main.add_command(version_cmd)
main.add_command(doctor_cmd)
main.add_command(install_browser_cmd)
main.add_command(launch_cmd)
main.add_command(attach_cmd)
main.add_command(observe_cmd)
main.add_command(navigate_cmd)
main.add_command(back_cmd)
main.add_command(forward_cmd)
main.add_command(reload_cmd)
main.add_command(wait_cmd)
main.add_command(portal_cmd)
main.add_command(act_cmd)
main.add_command(inspect_cmd)
main.add_command(diagnostics_cmd)
main.add_command(export_trace_cmd)
main.add_command(serve_cmd)
main.add_command(eval_corpus_cmd)


if __name__ == "__main__":
    main()

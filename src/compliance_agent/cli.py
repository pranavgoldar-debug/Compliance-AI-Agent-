from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

# Auto-load .env from the current working directory (and parents) if present.
# This is a convenience for local dev; the .env file is git-ignored, so it
# never travels with the code. In production, set env vars via your platform.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from compliance_agent.diff import compute_diff
from compliance_agent.extractor import read_document
from compliance_agent.mock import mock_extract, mock_verify
from compliance_agent.models import ExtractionResult
from compliance_agent.report import render_diff_markdown, render_extraction_markdown


@click.group()
def main() -> None:
    """Compliance AI Agent — extract, verify, diff, and render policy requirements."""


def _run_extraction(
    source: Path,
    *,
    live: bool,
    model: str,
    framework_hint: Optional[str],
    verify: bool,
) -> tuple[ExtractionResult, Optional[object]]:
    source_text = read_document(source)

    if live:
        from compliance_agent.extractor import ComplianceExtractor

        click.echo(f"Extracting requirements from {source} (live, {model})...", err=True)
        extraction = ComplianceExtractor(model=model).extract(source_text, framework_hint=framework_hint)
    else:
        click.echo(f"Extracting requirements from {source} (MOCK — no API call)...", err=True)
        extraction = mock_extract(source_text, framework_hint=framework_hint)

    click.echo(f"  → {len(extraction.requirements)} requirements extracted.", err=True)

    verification = None
    if verify:
        if live:
            from compliance_agent.verifier import ComplianceVerifier

            click.echo("Verifying extraction against source (live)...", err=True)
            verification = ComplianceVerifier(model=model).verify(source_text, extraction)
        else:
            click.echo("Verifying extraction against source (MOCK)...", err=True)
            verification = mock_verify(source_text, extraction)

        counts = {"pass": 0, "warning": 0, "fail": 0}
        for f in verification.findings:
            counts[f.status.value] += 1
        click.echo(
            f"  → pass={counts['pass']}  warning={counts['warning']}  fail={counts['fail']}  "
            f"missed={len(verification.missed_requirements)}",
            err=True,
        )

    return extraction, verification


def _write_or_print(rendered: str, output: Optional[Path]) -> None:
    if output:
        output.write_text(rendered, encoding="utf-8")
        click.echo(f"Wrote results to {output}", err=True)
    else:
        sys.stdout.write(rendered if rendered.endswith("\n") else rendered + "\n")


@main.command()
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--framework", "framework_hint", default=None, help="Optional framework hint.")
@click.option("--output", "-o", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--model", default="claude-opus-4-7", show_default=True, help="Claude model (live only).")
@click.option("--verify", is_flag=True, default=False, help="Run the verifier pass.")
@click.option("--live", is_flag=True, default=False, help="Call Anthropic API; default is mock mode.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown"]),
    default="json",
    show_default=True,
)
def extract(
    source: Path,
    framework_hint: Optional[str],
    output: Optional[Path],
    model: str,
    verify: bool,
    live: bool,
    output_format: str,
) -> None:
    """Extract structured compliance requirements from a policy document."""
    extraction, verification = _run_extraction(
        source, live=live, model=model, framework_hint=framework_hint, verify=verify
    )

    if output_format == "markdown":
        rendered = render_extraction_markdown(extraction, verification)
    else:
        payload: dict = {"extraction": extraction.model_dump(mode="json")}
        if verification is not None:
            payload["verification"] = verification.model_dump(mode="json")
        rendered = json.dumps(payload, indent=2)

    _write_or_print(rendered, output)


@main.command()
@click.argument("old_source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("new_source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--framework", "framework_hint", default=None, help="Optional framework hint.")
@click.option("--output", "-o", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--model", default="claude-opus-4-7", show_default=True, help="Claude model (live only).")
@click.option("--live", is_flag=True, default=False, help="Call Anthropic API; default is mock mode.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown"]),
    default="markdown",
    show_default=True,
)
def diff(
    old_source: Path,
    new_source: Path,
    framework_hint: Optional[str],
    output: Optional[Path],
    model: str,
    live: bool,
    output_format: str,
) -> None:
    """Diff two policy versions — show added, removed, and changed requirements."""
    old_extraction, _ = _run_extraction(
        old_source, live=live, model=model, framework_hint=framework_hint, verify=False
    )
    new_extraction, _ = _run_extraction(
        new_source, live=live, model=model, framework_hint=framework_hint, verify=False
    )

    diff_result = compute_diff(old_extraction, new_extraction)
    click.echo(
        f"  → added={len(diff_result.added)}  removed={len(diff_result.removed)}  "
        f"changed={len(diff_result.changed)}",
        err=True,
    )

    if output_format == "markdown":
        rendered = render_diff_markdown(diff_result)
    else:
        rendered = json.dumps(diff_result.model_dump(mode="json"), indent=2)

    _write_or_print(rendered, output)


@main.command()
@click.argument("input_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--output", "-o", type=click.Path(dir_okay=False, path_type=Path), default=None)
def render(input_json: Path, output: Optional[Path]) -> None:
    """Render an existing extraction JSON (from `extract -o out.json`) as Markdown."""
    payload = json.loads(input_json.read_text(encoding="utf-8"))

    if "extraction" in payload:
        extraction = ExtractionResult.model_validate(payload["extraction"])
        verification = None
        if "verification" in payload:
            from compliance_agent.models import VerificationResult

            verification = VerificationResult.model_validate(payload["verification"])
        rendered = render_extraction_markdown(extraction, verification)
    elif "added" in payload and "removed" in payload and "changed" in payload:
        from compliance_agent.diff import DiffResult

        rendered = render_diff_markdown(DiffResult.model_validate(payload))
    else:
        raise click.ClickException(
            f"Could not detect input shape in {input_json}. Expected an extraction or diff JSON."
        )

    _write_or_print(rendered, output)


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
@click.option("--live", is_flag=True, default=False, help="Use live Claude extraction (requires ANTHROPIC_API_KEY).")
@click.option("--reload", is_flag=True, default=False, help="Auto-reload on code changes (dev).")
@click.option("--no-browser", is_flag=True, default=False, help="Do not auto-open the browser.")
def serve(host: str, port: int, live: bool, reload: bool, no_browser: bool) -> None:
    """Launch the country-picker web UI on http://HOST:PORT."""
    import os
    import socket
    import threading
    import time
    import webbrowser

    import uvicorn

    if live:
        os.environ["COMPLIANCE_AGENT_LIVE"] = "1"
        click.echo("Live mode — requests will call Anthropic API.", err=True)
    else:
        os.environ.pop("COMPLIANCE_AGENT_LIVE", None)
        click.echo("Mock mode — no API key required.", err=True)

    # Pre-flight: detect "port already in use" before uvicorn spews a traceback.
    if not _port_is_free(host, port):
        next_port = _find_free_port(host, port + 1, port + 25)
        click.echo("", err=True)
        click.secho(
            f"Port {port} on {host} is already in use.",
            err=True, fg="red", bold=True,
        )
        click.echo(
            "Another `serve` is likely still running. Free the port or pick a new one:",
            err=True,
        )
        click.echo("", err=True)
        if os.name == "nt":
            click.echo(
                f"  PowerShell — find + kill the listener:\n"
                f"    Get-NetTCPConnection -LocalPort {port} | ForEach-Object {{\n"
                f"      Stop-Process -Id $_.OwningProcess -Force\n"
                f"    }}",
                err=True,
            )
        else:
            click.echo(f"  lsof -ti:{port} | xargs kill -9", err=True)
        if next_port is not None:
            click.echo(
                f"\n  Or run on a different port:  "
                f"python -m compliance_agent.cli serve --port {next_port}",
                err=True,
            )
        raise SystemExit(2)

    # Resolve a browser-friendly host. 0.0.0.0 / :: are server-bind addresses,
    # not browsable — point the browser at localhost in that case.
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{port}"

    if not no_browser:
        def _open_browser() -> None:
            time.sleep(1.2)  # let uvicorn finish binding before we open the tab
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open_browser, daemon=True).start()

    click.echo(f"Serving on {url}", err=True)
    uvicorn.run("compliance_agent.web:app", host=host, port=port, reload=reload)


def _port_is_free(host: str, port: int) -> bool:
    """True if we can bind (host, port). Uses SO_REUSEADDR so we don't race
    with our own check on platforms that hold TIME_WAIT."""
    import socket

    bind_host = host
    if host in {"0.0.0.0", "::"}:
        bind_host = "127.0.0.1"
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # On Windows, SO_REUSEADDR has different semantics — don't set it.
        try:
            sock.bind((bind_host, port))
            return True
        except OSError:
            return False
    finally:
        sock.close()


def _find_free_port(host: str, start: int, end: int):
    for p in range(start, end + 1):
        if _port_is_free(host, p):
            return p
    return None


@main.command()
def seed() -> None:
    """Seed the SQLite database with Aspora entities, rules, and users.

    Idempotent — safe to re-run. Creates compliance.db in the working directory
    if it doesn't exist. Login accounts:
       pranav.goldar@aspora.com         admin123        (admin)
       pranavgoldar@gmail.com           aspora2026      (employee)
       pranavgoldar.iitb@gmail.com      iitb2026        (employee)
       pranavgoldar.moodi@gmail.com     moodi2026       (employee)
    """
    from compliance_agent.db.seed import run_seed

    click.echo("Seeding database…", err=True)
    counts = run_seed()
    click.echo(f"  users:                {counts['users']}", err=True)
    click.echo(f"  entities:             {counts['entities']}", err=True)
    click.echo(f"  rules:                {counts['rules']}", err=True)
    click.echo(f"  obligations created:  {counts['obligations_created']}", err=True)
    click.echo(f"  source URLs filled:   {counts.get('source_urls_backfilled', 0)}", err=True)
    click.echo("Done.", err=True)


@main.command(name="backfill-source-urls")
def backfill_source_urls_cmd() -> None:
    """Populate rule.source_url for every rule the curated URL map covers.

    Idempotent — never overwrites a URL an admin already set in the UI.
    Use this after editing src/compliance_agent/fintech/source_urls.py on
    a workspace that's already seeded.
    """
    from compliance_agent.db.seed import run_source_url_backfill_only

    click.echo("Backfilling rule.source_url from curated map…", err=True)
    touched = run_source_url_backfill_only()
    click.echo(f"  rules updated: {touched}", err=True)
    click.echo("Done.", err=True)


@main.command(name="create-user")
@click.option("--email", required=True)
@click.option("--password", required=True, prompt=True, hide_input=True, confirmation_prompt=False)
@click.option("--full-name", default="")
@click.option("--role", type=click.Choice(["admin", "employee"]), default="employee")
def create_user(email: str, password: str, full_name: str, role: str) -> None:
    """Create a new user account."""
    from compliance_agent.auth.passwords import hash_password
    from compliance_agent.db import Role, User, init_db, session_scope

    init_db()
    with session_scope() as db:
        from sqlalchemy import select

        if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
            raise click.ClickException(f"User {email} already exists.")
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=Role(role),
            )
        )
    click.echo(f"Created user {email} ({role}).", err=True)


if __name__ == "__main__":
    main()

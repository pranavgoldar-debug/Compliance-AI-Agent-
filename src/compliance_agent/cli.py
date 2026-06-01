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
@click.option(
    "--no-assign",
    is_flag=True,
    default=False,
    help=(
        "Don't randomly assign obligations to demo employees. Use this for a "
        "production-like seed where every obligation starts unassigned and "
        "admins explicitly assign work."
    ),
)
def seed(no_assign: bool) -> None:
    """Seed the database with Aspora entities, rules, users, and obligations.

    Idempotent — safe to re-run. Login accounts:
       pranav.goldar@aspora.com         admin123        (admin)
       pranavgoldar@gmail.com           aspora2026      (employee)
       pranavgoldar.iitb@gmail.com      iitb2026        (employee)
       pranavgoldar.moodi@gmail.com     moodi2026       (employee)

    By default obligations are randomly distributed across the employee
    accounts to give the demo some activity. Pass --no-assign to leave
    everything unassigned (closer to what fresh production looks like).
    """
    import os

    from compliance_agent.db.seed import run_seed

    # Disable init_db's auto-seed so the CLI flag actually controls assignment.
    # Without this, the auto-seed inside init_db would run first with defaults
    # (auto_assign=True), and the explicit seed call below would be a no-op
    # because everything's already in the DB.
    os.environ["COMPLIANCE_AUTO_SEED"] = "0"

    click.echo("Seeding database…", err=True)
    counts = run_seed(auto_assign=not no_assign)
    click.echo(f"  users:                {counts['users']}", err=True)
    click.echo(f"  entities:             {counts['entities']}", err=True)
    click.echo(f"  rules:                {counts['rules']}", err=True)
    click.echo(f"  obligations created:  {counts['obligations_created']}", err=True)
    if no_assign:
        click.echo("  (everything unassigned — admins must assign work explicitly)", err=True)
    click.echo("Done.", err=True)


@main.command(name="setup-email")
@click.option(
    "--test-to",
    default=None,
    help="Send a test email to this address after saving. Defaults to your Gmail.",
)
def setup_email(test_to: Optional[str]) -> None:
    """Interactive Gmail setup. Asks for your address + App Password,
    writes them to .env, then sends a test email.

    You'll need a Gmail App Password first:
       1. Turn on 2-Step Verification:  https://myaccount.google.com/security
       2. Generate an App Password:     https://myaccount.google.com/apppasswords
       3. Copy the 16-character code Google shows you.

    Then run this command and paste it in.
    """
    import os

    from compliance_agent.email_service import send_email

    click.echo("")
    click.echo("=" * 60, err=True)
    click.echo("Aspora — Gmail setup", err=True)
    click.echo("=" * 60, err=True)
    click.echo(
        "\nBefore continuing, generate an App Password:\n"
        "  1. https://myaccount.google.com/security  → turn on 2-Step Verification\n"
        "  2. https://myaccount.google.com/apppasswords  → create one for 'Aspora'\n"
        "  3. Copy the 16-character code (spaces OK).\n",
        err=True,
    )

    gmail = click.prompt("Your Gmail address", type=str).strip()
    if not gmail or "@" not in gmail:
        raise click.ClickException("That doesn't look like an email address.")
    app_password = click.prompt(
        "App Password (16 chars, hidden)", hide_input=True
    ).strip().replace(" ", "")
    if len(app_password) < 8:
        raise click.ClickException(
            "App Password looks too short. Generate one at "
            "https://myaccount.google.com/apppasswords and try again."
        )
    display_name = click.prompt(
        "Name shown as sender", default="Aspora Compliance", show_default=True
    ).strip() or "Aspora Compliance"

    # One source of truth for the SMTP settings — drives both the .env file
    # we write and the os.environ patch we apply for the test send below.
    smtp_settings: dict[str, str] = {
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USER": gmail,
        "SMTP_PASSWORD": app_password,
        "SMTP_FROM": f"{display_name} <{gmail}>",
        "SMTP_TLS": "1",
    }

    # Write to .env, preserving any non-SMTP_* keys already there.
    env_path = Path(".env")
    existing: list[str] = []
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("SMTP_") or stripped.startswith("# SMTP"):
                continue
            existing.append(line)
        # Drop trailing blank line so we don't accumulate them.
        while existing and not existing[-1].strip():
            existing.pop()

    block = [
        "",
        "# SMTP — auto-generated by `compliance-agent setup-email`",
        *(f"{k}={v}" for k, v in smtp_settings.items()),
        "",
    ]
    env_path.write_text("\n".join(existing + block), encoding="utf-8")
    click.echo(f"\nSaved Gmail settings to {env_path.resolve()}", err=True)

    # Apply them to this process so the test send works immediately.
    os.environ.update(smtp_settings)

    recipient = test_to or gmail
    click.echo(f"\nSending a test email to {recipient}...", err=True)
    ok = send_email(
        to=recipient,
        subject="[Aspora] Email setup test",
        body_text=(
            "If you can read this, your Gmail is wired up correctly.\n\n"
            "Aspora Compliance OS will now send deadline reminders from\n"
            f"{gmail} when `compliance-agent send-reminders` runs.\n"
        ),
    )

    click.echo("", err=True)
    if ok:
        click.echo("Test email sent. Check your inbox in ~10 seconds.", err=True)
        click.echo("\nYou're done. Now run:", err=True)
        click.echo("  python -m compliance_agent.cli send-reminders --dry-run", err=True)
        click.echo("to see who'd be reminded, then drop the --dry-run to send.\n", err=True)
    else:
        click.echo(
            "Test send failed. Most common cause: you pasted your regular\n"
            "Gmail password instead of an App Password. Re-run setup-email\n"
            "after generating one at https://myaccount.google.com/apppasswords",
            err=True,
        )


@main.command(name="send-reminders")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="List who'd be reminded without sending email / Slack or persisting notifications.",
)
def send_reminders_cmd(dry_run: bool) -> None:
    """Send deadline reminders for obligations whose days-remaining hit
    a reminder offset for their effort band.

    Cadence (≈ frequency):
       monthly   (w1)  →  7 days before               (one ping)
       quarterly (w2)  →  25 and 15 days before       (two pings)
       annual    (w8)  →  45 and 30 days before       (two pings)

    Idempotent — each (assignee, obligation, offset) fires exactly once
    across daily cron runs.
    """
    from compliance_agent.db import init_db
    from compliance_agent.reminders import send_reminders

    init_db()
    results = send_reminders(dry_run=dry_run)
    if not results:
        click.echo("No reminders to send — every assigned obligation is either outside its alert window or already reminded.", err=True)
        return

    prefix = "[DRY-RUN] would send " if dry_run else "Sent "
    for r in results:
        click.echo(
            f"{prefix}reminder to {r.assignee_email}  obligation={r.obligation_id}  "
            f"days_left={r.days_remaining}  offset=T-{r.offset_days}d  "
            f"email={r.email_sent}  slack={r.slack_sent}",
            err=True,
        )
    click.echo(f"{len(results)} reminder(s) processed.", err=True)


@main.command(name="send-digest")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the digest summary without sending email / Slack.",
)
def send_digest_cmd(dry_run: bool) -> None:
    """Send the weekly compliance digest to every active admin (email +
    Slack): overdue items, filings due within 7 days, and anything awaiting
    sign-off. Meant to run on a weekly cron.
    """
    from compliance_agent.db import init_db
    from compliance_agent.digest import send_admin_digest

    init_db()
    res = send_admin_digest(dry_run=dry_run)
    s = res.summary
    click.echo(
        f"Digest: {len(s.overdue)} overdue, {len(s.upcoming)} due within 7d, "
        f"{len(s.pending_review)} awaiting sign-off.",
        err=True,
    )
    if dry_run:
        click.echo("[DRY-RUN] nothing sent.", err=True)
        return
    click.echo(
        f"Sent {res.sent_emails} email(s); slack={'yes' if res.slack_sent else 'no'}.",
        err=True,
    )


@main.command(name="merge-finance-legs")
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="Skip the confirmation prompt.",
)
def merge_finance_legs(yes: bool) -> None:
    """Delete the duplicate finance-leg obligations created by the old
    dept-split approach (PR-B). One filing = one obligation again.

    Idempotent: a no-op if there are no department=finance rows.
    """
    from sqlalchemy import select

    from compliance_agent.db import (
        Department,
        Obligation,
        init_db,
        session_scope,
    )

    init_db()
    with session_scope() as db:
        rows = (
            db.execute(select(Obligation).where(Obligation.department == Department.finance))
            .scalars()
            .all()
        )
        if not rows:
            click.echo("No finance-leg obligations — nothing to merge.", err=True)
            return
        click.echo(
            f"Will delete {len(rows)} finance-leg obligation(s). "
            "Each had a matching compliance-leg row (same rule + entity + due_date) "
            "which stays — that's where filing AND payment now live.",
            err=True,
        )
        if not yes and not click.confirm("Proceed?", default=False):
            click.echo("Aborted.", err=True)
            return
        for ob in rows:
            db.delete(ob)
        click.echo(f"Deleted {len(rows)} finance-leg rows.", err=True)


@main.command(name="prune-entities")
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="Skip the confirmation prompt.",
)
def prune_entities(yes: bool) -> None:
    """Delete entities not present in seed.DEMO_ENTITIES.

    Use this after pulling a seed change that removes entities (e.g. when
    syncing to the Aspora Global Compliance Tracker) — `seed` itself is
    additive only, so it won't remove rows that disappeared from the
    canonical list. This command does.

    Cascades:
      rule_entities, documents, licenses → CASCADE on FK
      obligations → no FK cascade, removed explicitly
    """
    from sqlalchemy import select

    from compliance_agent.db import (
        Entity,
        Obligation,
        init_db,
        session_scope,
    )
    from compliance_agent.db.seed import DEMO_ENTITIES

    init_db()
    keep = {e["name"] for e in DEMO_ENTITIES}
    with session_scope() as db:
        all_entities = db.execute(select(Entity)).scalars().all()
        stale = [e for e in all_entities if e.name not in keep]
        if not stale:
            click.echo("No stale entities — DB already matches DEMO_ENTITIES.", err=True)
            return

        click.echo("Will delete:", err=True)
        for e in stale:
            ob_count = db.execute(
                select(Obligation).where(Obligation.entity_id == e.id)
            ).scalars().all()
            click.echo(
                f"  - {e.name} ({e.jurisdiction_code}) — {len(ob_count)} obligations",
                err=True,
            )

        if not yes and not click.confirm("Proceed?", default=False):
            click.echo("Aborted.", err=True)
            return

        for e in stale:
            # Remove obligations first (no FK cascade on entity_id).
            db.execute(
                Obligation.__table__.delete().where(Obligation.entity_id == e.id)
            )
            db.delete(e)
        click.echo(f"Pruned {len(stale)} entity/entities.", err=True)


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

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

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
def serve(host: str, port: int, live: bool, reload: bool) -> None:
    """Launch the country-picker web UI on http://HOST:PORT."""
    import os
    import uvicorn

    if live:
        os.environ["COMPLIANCE_AGENT_LIVE"] = "1"
        click.echo("Live mode — requests will call Anthropic API.", err=True)
    else:
        os.environ.pop("COMPLIANCE_AGENT_LIVE", None)
        click.echo("Mock mode — no API key required.", err=True)

    click.echo(f"Serving on http://{host}:{port}", err=True)
    uvicorn.run("compliance_agent.web:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

from compliance_agent.extractor import ComplianceExtractor, read_document
from compliance_agent.verifier import ComplianceVerifier


@click.command()
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--framework",
    "framework_hint",
    default=None,
    help="Optional framework hint (e.g. 'SOC 2', 'GDPR', 'HIPAA').",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write JSON to this path instead of stdout.",
)
@click.option(
    "--model",
    default="claude-opus-4-7",
    show_default=True,
    help="Claude model ID.",
)
@click.option(
    "--verify",
    is_flag=True,
    default=False,
    help="Run a second-pass verifier that grades each extracted requirement against the source.",
)
def main(
    source: Path,
    framework_hint: Optional[str],
    output: Optional[Path],
    model: str,
    verify: bool,
) -> None:
    """Extract structured compliance requirements from a policy or regulation document."""
    source_text = read_document(source)

    extractor = ComplianceExtractor(model=model)
    click.echo(f"Extracting requirements from {source}...", err=True)
    extraction = extractor.extract(source_text, framework_hint=framework_hint)
    click.echo(f"  → {len(extraction.requirements)} requirements extracted.", err=True)

    payload: dict = {"extraction": extraction.model_dump(mode="json")}

    if verify:
        click.echo("Verifying extraction against source...", err=True)
        verifier = ComplianceVerifier(model=model)
        verification = verifier.verify(source_text, extraction)
        counts = {"pass": 0, "warning": 0, "fail": 0}
        for f in verification.findings:
            counts[f.status.value] += 1
        click.echo(
            f"  → pass={counts['pass']}  warning={counts['warning']}  fail={counts['fail']}  "
            f"missed={len(verification.missed_requirements)}",
            err=True,
        )
        payload["verification"] = verification.model_dump(mode="json")

    rendered = json.dumps(payload, indent=2)
    if output:
        output.write_text(rendered, encoding="utf-8")
        click.echo(f"Wrote results to {output}", err=True)
    else:
        sys.stdout.write(rendered + "\n")


if __name__ == "__main__":
    main()
